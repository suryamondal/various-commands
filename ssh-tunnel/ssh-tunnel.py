#!/usr/bin/env python3
"""Bring up, inspect and tear down persistent multiplexed SSH masters.

Auth is interactive by design.  These hosts sit behind passphrased keys and
Google Authenticator TOTP, and none of that is bypassed or cached here: ``up``
runs the real ``ssh`` client with this process's terminal attached, so every
prompt reaches you, and ``ssh -f`` backgrounds the master only *after*
authentication has succeeded.

For the same reason there is deliberately no systemd unit and no auto-redial.
An unattended supervisor would re-dial into a TOTP prompt with no terminal,
fail, and loop - burning auth attempts for nothing.  Re-dialing is a manual
act; ``status`` is how you find out that you need to.

    python3 ssh-tunnel.py status
    python3 ssh-tunnel.py up [HOST ...|all]
    python3 ssh-tunnel.py down [HOST ...|all]
    python3 ssh-tunnel.py restart [HOST ...|all]
    python3 ssh-tunnel.py list

The managed hosts are read from the plain-text ``tunnel-hosts`` file next to
this script - one alias per line. Naming a HOST on the command line overrides
that list for a single run.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Aliases match each machine's real hostname, so ~/.ssh/config can derive the
# LAN name as <alias>.local from a single generic rule.
HOSTS_FILE = Path(__file__).resolve().parent / "tunnel-hosts"

# Column width for the host name in printed output; set from the real names by
# set_host_width() once they are known, since the aliases are long.
HOST_W = 24

_PID_RE = re.compile(r"pid=(\d+)")

# ssh -G is not free: for probed hosts it runs the `Match exec` reachability
# test, so resolving a host costs up to the probe timeout.  Cache per run.
_config_cache: dict[str, dict[str, str]] = {}


def load_hosts() -> list[str]:
    """Managed aliases from HOSTS_FILE: one per line, # starts a comment."""
    try:
        text = HOSTS_FILE.read_text()
    except OSError as exc:
        sys.exit(f"ssh-tunnel: cannot read {HOSTS_FILE}: {exc}")

    hosts = []
    for line in text.splitlines():
        name = line.split("#", 1)[0].strip()
        if name:
            hosts.append(name)
    if not hosts:
        sys.exit(f"ssh-tunnel: no hosts listed in {HOSTS_FILE}")
    return hosts


def set_host_width(names: list[str]) -> None:
    """Size the host column to the longest name actually being printed."""
    global HOST_W
    HOST_W = max(len(n) for n in [*names, "HOST"]) + 2


def ssh_config(host: str) -> dict[str, str]:
    """Effective ssh options for *host*, as ssh itself resolves them."""
    if host not in _config_cache:
        proc = subprocess.run(
            ["ssh", "-G", host], capture_output=True, text=True, check=False
        )
        opts: dict[str, str] = {}
        for line in proc.stdout.splitlines():
            key, _, value = line.partition(" ")
            opts.setdefault(key, value)
        _config_cache[host] = opts
    return _config_cache[host]


def address(host: str) -> str:
    return ssh_config(host).get("hostname", "?")


def control_path(host: str) -> Path | None:
    path = ssh_config(host).get("controlpath", "")
    return Path(path) if path and path != "none" else None


def check(host: str) -> tuple[bool, str | None]:
    """Return (alive, pid).

    ``ssh -O check`` is the only trustworthy liveness test - a socket file can
    outlive the master behind it, and connecting to such a socket hangs.
    """
    proc = subprocess.run(
        ["ssh", "-O", "check", host], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        return False, None
    match = _PID_RE.search(proc.stderr + proc.stdout)
    return True, match.group(1) if match else None


def reap_stale(host: str) -> bool:
    """Delete a socket with no live master behind it.

    Left in place it makes the next dial try to reuse a dead master.
    """
    path = control_path(host)
    if path is None or not path.is_socket():
        return False
    try:
        path.unlink()
    except OSError:
        return False
    return True


# up_one outcomes.  ADOPTED is tracked separately from DIALED because a master
# this script did not dial carries whatever ControlPersist the config gave it,
# and may not survive the run.
DIALED, ADOPTED, FAILED = "dialed", "adopted", "failed"


def up_one(host: str) -> str:
    alive, pid = check(host)
    if alive:
        print(f"  {host:<{HOST_W}} already up (pid {pid or '?'})")
        return ADOPTED
    if reap_stale(host):
        print(f"  {host:<{HOST_W}} cleared stale socket")

    print(f"\n  >>> {host}  ->  {address(host)}")
    print("      passphrase / TOTP prompts appear below")
    # No capture_output: stdin/stdout/stderr are inherited so the prompts land
    # on the user's terminal.  -M master, -N no remote command, -f background
    # after authentication.
    #
    # ControlPersist=no is an override, not a default: with -N there is never a
    # client session, so a master inheriting `ControlPersist 30s` from
    # ~/.ssh/config can exit ~30s after being dialed.  `no` keeps it alive
    # until something explicitly closes it.
    proc = subprocess.run(
        ["ssh", "-MNf", "-o", "ControlPersist=no", host], check=False
    )
    if proc.returncode != 0:
        print(f"      FAILED to dial {host} (ssh exit {proc.returncode})", file=sys.stderr)
        return FAILED

    alive, pid = check(host)
    if not alive:
        print(f"      dialed but no master appeared - check {host} manually", file=sys.stderr)
        return FAILED
    print(f"      up (pid {pid or '?'})")
    return DIALED


def down_one(host: str) -> bool:
    alive, _ = check(host)
    if not alive:
        suffix = " (cleared stale socket)" if reap_stale(host) else ""
        print(f"  {host:<{HOST_W}} not running{suffix}")
        return True
    # This also terminates any session still multiplexed over the master.
    proc = subprocess.run(
        ["ssh", "-O", "exit", host], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        print(f"  {host:<{HOST_W}} failed to close: {proc.stderr.strip()}", file=sys.stderr)
        return False
    print(f"  {host:<{HOST_W}} closed")
    return True


def state_of(host: str) -> tuple[bool, str]:
    alive, pid = check(host)
    if alive:
        return True, f"up (pid {pid or '?'})"
    path = control_path(host)
    if path is not None and path.is_socket():
        return False, "down (stale socket)"
    return False, "down"


def cmd_status(hosts: list[str]) -> int:
    # Resolve everything first: MagicDNS names are long enough to overflow a
    # fixed column, so size it from the addresses actually being printed.
    rows = [(host, address(host), state_of(host)) for host in hosts]
    addr_w = max([len(addr) for _, addr, _ in rows] + [len("ADDRESS")]) + 2

    print(f"  {'HOST':<{HOST_W}} {'ADDRESS':<{addr_w}} STATE")
    all_up = True
    for host, addr, (alive, state) in rows:
        all_up &= alive
        print(f"  {host:<{HOST_W}} {addr:<{addr_w}} {state}")
    if not all_up:
        print("\n  re-dial with: python3 ssh-tunnel.py up [HOST]   (needs a terminal)")
    return 0 if all_up else 1


def require_tty(command: str) -> None:
    if not sys.stdin.isatty():
        sys.exit(
            f"ssh-tunnel: '{command}' needs a terminal for passphrase/TOTP prompts"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ssh-tunnel.py",
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Auth is interactive: 'up' and 'restart' must be run from a terminal.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="status",
        choices=["up", "down", "restart", "status", "list"],
    )
    parser.add_argument(
        "hosts",
        nargs="*",
        metavar="HOST",
        help="hosts to act on; omit or use 'all' for every managed host",
    )
    args = parser.parse_args(argv)

    managed = load_hosts()
    targets = managed if not args.hosts or args.hosts[0] == "all" else args.hosts
    set_host_width(targets)

    if args.command == "list":
        print("\n".join(managed))
        return 0

    if args.command == "status":
        return cmd_status(targets)

    if args.command == "down":
        return 0 if all(down_one(h) for h in targets) else 1

    if args.command == "restart":
        require_tty(args.command)
        for host in targets:
            down_one(host)
        # fall through to the dial loop below

    if args.command == "up":
        require_tty(args.command)

    # Hosts are dialed one at a time and never in parallel, so that TOTP and
    # passphrase prompts cannot interleave.
    ok = True
    adopted = []
    for host in targets:
        outcome = up_one(host)
        if outcome == ADOPTED:
            adopted.append(host)
        elif outcome == FAILED:
            ok = False

    print()
    final = cmd_status(targets)

    # A master this script did not dial inherits `ControlPersist 30s` from
    # ~/.ssh/config, so it can expire while you are still answering prompts for
    # later hosts.  Explain that rather than letting the summary silently
    # contradict the "already up" line printed earlier in the same run.
    vanished = [h for h in adopted if not check(h)[0]]
    for host in vanished:
        print(
            f"\n  note: {host} was up when this run started but has since expired.\n"
            "        Masters dialed outside this script inherit ControlPersist 30s\n"
            "        from ~/.ssh/config and die once idle. Re-dial it with 'up' to\n"
            "        get one that persists."
        )

    return 0 if ok and final == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
