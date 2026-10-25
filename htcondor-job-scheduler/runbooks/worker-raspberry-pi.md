# Worker: Raspberry Pi (aarch64, no GPU)

**No Pi has joined yet.** Everything about the Pi class here is reasoned from
the Jetson deployment, not observed. Treat the sizing as a starting point and
anything marked UNTESTED as exactly that.

Expected: 4 cores, 4 G RAM, ~36 G on SD, Debian 13.

**Ten machines are being added** as `pi-node-NN`, handed to a colleague to
install. The handover tarball contains this runbook's config as a filled-in
template, the `condor-owner-session` script, and ten tokens. What follows is the
operator's copy: the reasoning, and the decisions already made on their behalf.

## What should carry over unchanged

The Jetson proved the policy needs no porting for aarch64: same owner policy,
same `STARTD_CRON` job, same measured-memory override, jobs as `nobody` at
nice 10. Expect the same here.

## What to check first, in this order

**Condor version.** The Jetson runs Ubuntu 24.04, which ships 23.4.0, matching
the pool. **Debian 13 ships 23.9.6.** That is a different version, and while
HTCondor tolerates some skew, the pool's own rule is that the central manager
should not be older than its workers. Confirm what `apt-cache policy condor`
offers before assuming this class is a drop-in.

**Disk.** ~36 G on an SD card is the tightest in the fleet and the standard
`RESERVED_DISK = 20480` is over half of it. The Jetson needed 4096 for the same
reason; this will need less again. Compute it from actual free space:

```
RESERVED_DISK   ~10% of free, leaving the fractional floors room to work
```

SD cards are also slow. `EXECUTE` on one will make file transfer and job
sandboxes noticeably worse than any other machine in the pool, which is a
throughput consideration rather than a correctness one.

**Memory floors bite differently at 4 G.** `MEM_HARD_FLOOR` is
`max(1024, 10% of total)`, so on a 4 G machine the **absolute** 1024 MB dominates
rather than the fraction. That is deliberate: 10% of 4 G is 410 MB, too little to
avoid thrashing. Expect this machine to decline work sooner than the others.

```
RESERVED_MEMORY = 400        10% of 4 G
```

## Board identity

Publish it, so a job can distinguish this from a Jetson. `Arch` alone cannot:
both are aarch64 and both may run Ubuntu or Debian.

```
HostBoard      = "<from /proc/device-tree/model>"
HostBoardClass = "rpi-<model>"
STARTD_ATTRS   = $(STARTD_ATTRS) HostBoard HostBoardClass
```

`HostBoardClass` names a **board, not a family** - `skull-n100`,
`skull-ryzen7`, `jetson-orin-nano`. So this is `rpi-5` or `rpi-4b`, not `rpi`:
a value that cannot tell a Pi 4 from a Pi 5 has the same defect as calling
every x86 machine `skull-saints`, which is what this convention replaced.

`/proc/device-tree/model` reads `Raspberry Pi ...` here and `NVIDIA Jetson ...`
on the Jetson, which is the authoritative discriminator.

## No GPU

Skip the entire GPU section of the Jetson runbook. Do **not** add `condor` or
`nobody` to `video`/`render`; there is nothing to reach and it grants access for
no reason.

## Targeting it

```
requirements = (Arch == "AARCH64") && (HostBoardClass =?= "rpi-<model>")
```

`Arch` must appear, or `condor_submit` appends `Arch == "X86_64"` and the job
never matches. Same trap as the Jetson.

## Tokens: one identity, ten files

Workers authenticate as the **pool's daemon identity**, not as themselves:

```
condor_token_create -identity condor@<pool>.internal
```

`ALLOW_DAEMON` is `condor@*`, so every worker in the fleet — x86, Jetson, both
Macs — carries this same identity. A per-machine identity would not match and
the machine would never register.

**Issue them as separate files anyway.** Each carries its own `jti`, so one
machine can be revoked without invalidating the rest. Ten identical copies of
one file cannot be. Verify after minting, because "it produced ten files" is
not the same as "it produced ten distinct tokens":

```
python3 -c "import base64,json,sys; t=open(sys.argv[1]).read().strip().split('.'); \
  p=t[1]+'='*(-len(t[1])%4); print(json.loads(base64.urlsafe_b64decode(p)))" <file>
```

Expect one distinct `sub` across all of them and N distinct `jti`.

Workers need **no Unix account** on the entry node. That is a submitter
requirement — the schedd forks a shadow as the submitting user — and does not
apply here.

## Traps this pool has already paid for

All of these were learned on other machines. They apply to a Pi and the first
two apply *especially*, because these are headless.

**`NETWORK_INTERFACE` does not self-correct.** Set once in the config, updated
by nothing. `condor-network-select` derives `PRIVATE_NETWORK_NAME` only. If the
cable moves to another port the pin names a dead interface, `condor_master`
fails at startup and loops under `activating (auto-restart)` — while the machine
stays up, ssh works, and everything looks healthy. It leaves the pool silently
when its ad ages out. Verify with `condor_status -af Name MyAddress` after any
cabling change.

**The boot splash deadlocks package upgrades on a headless machine.**
`plymouth-quit-wait.service` runs `plymouth --wait` with no timeout and never
returns when no monitor is attached. systemd serialises jobs, so any package
whose postinst runs `systemctl restart` queues behind it and `apt` hangs. Clear
it with `plymouth quit` **directly** — a `systemctl` call becomes another queued
job behind the same blockage. Mask the unit to prevent it recurring.

**Verify the cron is publishing, not just that Condor started.** A machine can
appear in `condor_status`, look healthy, and be incapable of running anything
because `HostMemAvailMB` is UNDEFINED and `Memory` is 0. Check both.

**Disable `unattended-upgrades`**, as the rest of the fleet does. It holds the
dpkg lock and breaks deliberate updates; one machine had it running for fifteen
days. The trade-off is explicit: security updates stop installing themselves.

**A hardware watchdog is worth having here.** These are cheap boards on SD
cards. `iTCO_wdt` is Intel-specific and will not exist on a Pi — the Pi has its
own (`bcm2835_wdt`), usually already present as `/dev/watchdog`. Setting
`RuntimeWatchdogSec` makes a hung board reset itself, and a non-zero
`/sys/class/watchdog/watchdog0/bootstatus` afterwards proves it hung rather
than lost power. UNTESTED on this class.

## Open questions this class will answer

- Whether the Debian-shipped Condor version interoperates cleanly with a 23.4.0
  central manager.
- Whether an SD-backed `EXECUTE` makes disk-pressure eviction fire in normal use.
  It is the one policy branch never observed firing, and this is the machine most
  likely to trigger it honestly.
