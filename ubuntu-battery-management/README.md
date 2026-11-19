# Ubuntu battery management and lock screen

Charge limits, low-battery warnings, hibernate at critical battery, and a
screen lock that survives every kind of sleep.

> Deployed on a Dell Latitude 3450, Ubuntu 26.04 (kernel 7.0, systemd 259,
> UPower 1.91, TLP 1.8, MATE desktop) on 2026-11-19. The Dell-specific parts
> are marked; the rest applies to any Ubuntu laptop.

| File | Goes to | Purpose |
|---|---|---|
| `01-battery.conf` | `/etc/tlp.d/` | Charge start/stop thresholds |
| `90-battery-levels.conf` | `/etc/UPower/UPower.conf.d/` | Low/critical warnings and the critical action |
| `lock-before-sleep.service` | `/etc/systemd/system/` | Lock all sessions before any suspend/hibernate |
| `battery-check.sh` | run from here | Shows whether all of the above is live |
| `discharge-report.sh` | run from here | Analyses the last on-battery run from UPower's history |

Install everything:
```BASH
sudo cp 01-battery.conf /etc/tlp.d/
sudo cp 90-battery-levels.conf /etc/UPower/UPower.conf.d/
sudo cp lock-before-sleep.service /etc/systemd/system/
sudo tlp setcharge
sudo systemctl restart upower
sudo systemctl daemon-reload
sudo systemctl enable lock-before-sleep.service
./battery-check.sh
```


## 1. Charge limits (upper and lower)

Check that the kernel exposes thresholds:
```BASH
cat /sys/class/power_supply/BAT0/charge_control_{start,end}_threshold
```

Set them persistently with TLP in `/etc/tlp.d/01-battery.conf`:
```BASH
START_CHARGE_THRESH_BAT0=75   # charging starts below this
STOP_CHARGE_THRESH_BAT0=80    # charging stops here
```

Then **apply** - editing the file alone does nothing until the next boot.
TLP's automatic runs on plug/unplug do not re-apply thresholds:
```BASH
sudo tlp setcharge
sudo tlp fullcharge     # one-off charge to 100 %, limits return on next boot / setcharge
```

Quick, non-persistent test without TLP:
```BASH
echo 80 | sudo tee /sys/class/power_supply/BAT0/charge_control_end_threshold
echo 75 | sudo tee /sys/class/power_supply/BAT0/charge_control_start_threshold
```

### Dell pitfalls

* **The firmware ignores the thresholds unless the charge mode is `Custom`.**
  In `Adaptive` (the default) the battery charged to 97 % with the stop
  threshold at 90. Check and fix:
  ```BASH
  cat /sys/class/power_supply/BAT0/charge_types     # want: ... [Custom]
  echo Custom | sudo tee /sys/class/power_supply/BAT0/charge_types
  ```
  `tlp setcharge` switched it to Custom by itself here.
* The stop threshold must be at least start + 5.
* The same setting exists in the BIOS (F2 -> Power -> Battery Charge
  Configuration -> Custom); whatever is written last wins.
* `Not charging` at a level above the stop threshold, on AC, is the
  correct behaviour.


## 2. Low-battery warnings and critical action (UPower)

UPower has three levels:

| Setting | Here | Effect |
|---|---|---|
| `PercentageLow` | 15 % | "Battery low" notification |
| `PercentageCritical` | 10 % | "Battery critical" notification |
| `PercentageAction` | 5 % | Runs `CriticalPowerAction` |

`CriticalPowerAction` is one of `PowerOff`, `Hibernate`, `HybridSleep`
(the Ubuntu default) or `Suspend` (needs `AllowRiskyCriticalPowerAction=true`).

Put overrides in a drop-in (`/etc/UPower/UPower.conf.d/90-battery-levels.conf`)
instead of editing `UPower.conf`, then:
```BASH
sudo systemctl restart upower
busctl call org.freedesktop.UPower /org/freedesktop/UPower org.freedesktop.UPower GetCriticalAction
```

**UPower reads its config only at start.** An edit after the last restart is
silently ignored - `battery-check.sh` warns about this.

### Why not the default `HybridSleep`

What happened on the first test at 2 %: UPower started hybrid sleep, which
wrote a hibernate image and suspended to RAM. The laptop woke a few seconds
later; waking from the RAM half discards the image. It was then suspended
again (lid closed), the battery died in suspend, and the session was lost.
Use `Hibernate` (once section 3 is tested) or `PowerOff`.


## 3. Hibernate at critical battery

Requirements:

* swap at least the size of RAM (here 9.5 GB swap, 7.4 GB RAM);
* Secure Boot off, or kernel lockdown `[none]`
  (`cat /sys/kernel/security/lockdown`), since lockdown blocks hibernation;
* a resume device known to the kernel.

Check the resume device:
```BASH
cat /sys/power/resume          # e.g. 259:3 = the swap partition; 0:0 = none
lsinitramfs /boot/initrd.img-$(uname -r) | grep resume
```
On Ubuntu, `initramfs-tools` detects the swap partition by itself when the
initrd is built (`conf/conf.d/zz-resume-auto`), so **no `resume=` on the
kernel command line and no `/etc/initramfs-tools/conf.d/resume` were
needed**. Add them only if `/sys/power/resume` shows `0:0`:
```BASH
UUID=$(blkid -s UUID -o value /dev/<swap-partition>)
echo "RESUME=UUID=$UUID" | sudo tee /etc/initramfs-tools/conf.d/resume
# and append resume=UUID=$UUID to GRUB_CMDLINE_LINUX_DEFAULT in /etc/default/grub
sudo update-initramfs -u -k all && sudo update-grub
```

### `CanHibernate` says `no` - that is fine

```BASH
busctl call org.freedesktop.login1 /org/freedesktop/login1 org.freedesktop.login1.Manager CanHibernate
```
returns `no` because Ubuntu's polkit rule
(`/usr/share/polkit-1/rules.d/com.ubuntu.desktop.rules`) forbids hibernate for
normal users - which is also why it is missing from the shutdown menu. Root is
not affected, and UPower runs as root, so the critical action still works.

### Test it before relying on it

```BASH
sudo systemctl hibernate
```
The machine must power off completely and, after pressing the power button,
come back with open windows intact. In the journal the resumed kernel shows
`PM: hibernation: hibernation entry` followed by
`ACPI: PM: Waking up from system sleep state S4`, with a gap of the time it was
off. The "Image saving" lines are missing on a real resume - they were written
after the snapshot and are not in the restored log.


## 4. Lock the screen before every sleep

MATE's `org.mate.power-manager lock-hibernate` / `lock-suspend` only apply when
mate-power-manager starts the sleep. Hibernate started by UPower (critical
battery) or by `systemctl` bypasses it, and the session **resumed unlocked**.

`lock-before-sleep.service` fixes this for every trigger. It runs
`loginctl lock-sessions` ordered `Before=sleep.target`, so before
`systemd-sleep` freezes `user.slice`; the screen locker (mate-screensaver here,
any logind-aware locker works) is still running and locks, and the 1 s pause
lets it blank the screen before the image is taken.
```BASH
sudo cp lock-before-sleep.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable lock-before-sleep.service
```
Verify after a hibernate:
```BASH
journalctl -b | grep -E 'lock-before-sleep|sleep operation'      # lock runs first
journalctl -b | grep 'mate-screensaver'                          # unlock prompt after resume
```
Note: `ps -eo comm` cuts names at 15 characters, so the locker shows up as
`mate-screensave` - grep for that, not `mate-screensaver`.


## 5. Capacity test - how far to trust the % reading

1. Raise the limits (e.g. 90/95), `sudo tlp setcharge`, charge to the stop level.
2. Set `PercentageAction` low (2 %) and restart upower.
3. Unplug and use the laptop normally until the critical action fires.
4. Run `./discharge-report.sh`.

It reads UPower's history in `/var/lib/upower/` and prints:

* every percentage step - anything other than `-1` is marked `JUMP`
  (a gauge that falls from, say, 9 % straight to 2 % cannot be trusted at
  the bottom);
* runtime and energy actually drawn (power integrated over time) against what
  the gauge claims; a difference of a few percent means the gauge is calibrated;
* start and end voltage.

Result here: 96 % -> 2 % in 3 h 40 min at 7.9 W average, 29.1 Wh drawn vs
29.6 Wh claimed (-1.9 %), every step exactly -1 %, voltage falling smoothly
to 10.70 V (3.57 V/cell, so the gauge keeps a reserve below 0 %). Battery
health 75 % of design at 82 cycles. Expected runtime is roughly
`full Wh / average W` - 4 h at 8 W, about 7-8 h at 4 W.

Afterwards restore the everyday limits and action level.
