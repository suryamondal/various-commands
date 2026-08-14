# SSH tunnels (ControlMaster) with LAN/Tailscale failover

One persistent multiplexed SSH master per host, so later connections (`ssh`,
`scp`, `rsync`, `git`, VS Code Remote) reuse it instead of re-authenticating.
Each host is reached by its mDNS name on its LAN and by its Tailscale MagicDNS
name otherwise — same alias either way, and no addresses to maintain.

Placeholders below: `<hostname-N>` is a machine's real hostname, `<user>` its
login, `<key>` its private key, `<tailnet>` the MagicDNS suffix from
`tailscale status --json | grep MagicDNSSuffix`.

## `~/.ssh/config` structure

Name each alias after the machine's real hostname. Then the LAN name is always
`%h.local`, one `Match` rule covers every probed host, and nothing has to be
edited twice. The `Match` block must come first: ssh keeps the first value it
obtains for each keyword, so a successful probe wins and a failed one falls
through to the `Host` block below.

```SSHCONFIG
# Probed hosts: LAN when reachable, Tailscale otherwise.
#   timeout 1  - nc -w bounds the connect, not the name lookup (~5s on avahi)
#   >/dev/null - else nc prints "succeeded!" on every ssh invocation
#   port 22, not name resolution - avahi serves cached names for dead hosts
#   keep the host list - a bare "Match exec" would probe github.com too
Match host <hostname-1>,<hostname-2> exec "timeout 1 nc -z -w1 %h.local 22 >/dev/null 2>&1"
     HostName %h.local

Host <hostname-1>
     HostName %h.<tailnet>            # MagicDNS fallback when the probe fails
     User <user>
     IdentityFile ~/.ssh/<key>
     HostKeyAlias <hostname-1>        # HostName floats; pin one known_hosts id

Host <hostname-2>
     HostName %h.<tailnet>
     User <user>
     IdentityFile ~/.ssh/<key>
     HostKeyAlias <hostname-2>

# LAN-only host: one stable address, so no probe and no HostKeyAlias.
Host <hostname-3>
     HostName %h.local
     User <user>
     IdentityFile ~/.ssh/<key>

# LAN-only host keeping extra short aliases, so HostName is spelled out
# rather than derived from %h.
Host <hostname-4> <short-alias>
     HostName <hostname-4>.local
     User <user>
     IdentityFile ~/.ssh/<key>

# Shared master/keepalive settings.
#   ControlPath on %n (alias), never %h (resolved address) - a floating
#   HostName would otherwise open a second master after a network switch.
Host <hostname-1> <hostname-2> <hostname-3> <hostname-4> <short-alias>
     IdentitiesOnly yes
     ControlMaster auto
     ControlPath ~/.ssh/log/cm-%n
     ControlPersist 30s
     ServerAliveInterval 15
     ServerAliveCountMax 3

# Global defaults LAST - options above any Host block are obtained first and
# would silently override every per-host value.
Host *
     ServerAliveInterval 60
```

Check the result without connecting:

```BASH
ssh -G <hostname-1> | grep -E '^(hostname|controlpath|hostkeyalias) '
```

## Running the script

```BASH
python3 ssh-tunnel.py status              # default; exit 1 if any host is down
python3 ssh-tunnel.py up [HOST ...|all]   # dial; needs a terminal
python3 ssh-tunnel.py down [HOST ...|all]
python3 ssh-tunnel.py restart [HOST ...|all]
python3 ssh-tunnel.py list
```

Managed hosts come from the `tunnel-hosts` file next to the script — one
ssh_config alias per line, `#` starts a comment. Comment a line out to drop a
host; naming a HOST on the command line overrides the file for one run. The
file is gitignored, since it names real machines on private networks.

```
<hostname-1>
<hostname-2>
<hostname-3>
<hostname-4>
```

```
  HOST           ADDRESS                  STATE
  <hostname-1>   <hostname-1>.local       up (pid 672240)
  <hostname-2>   <hostname-2>.<tailnet>   up (pid 672258)
  <hostname-3>   <hostname-3>.local       up (pid 672269)
  <hostname-4>   <hostname-4>.local       down
```

Both columns size themselves to the names being printed, so a MagicDNS name
does not push `STATE` out of alignment.

`up` and `restart` need a terminal: hosts behind passphrased keys and Google
Authenticator TOTP ([`../ssh-with-google-totp/README.md`](../ssh-with-google-totp/README.md))
prompt interactively, nothing is cached or replayed, and hosts are dialed one at
a time so prompts cannot interleave. There is no systemd unit and no auto-redial
— an unattended re-dial would hit a TOTP prompt with no terminal, fail, and loop.
