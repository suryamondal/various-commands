# Ubuntu battery management and lock screen

Charge limits, low-battery warnings, hibernate at critical battery, and a
screen lock that covers every kind of sleep.

> Deployed on a Dell Latitude 3450, Ubuntu 26.04 (systemd 259, UPower 1.91,
> TLP 1.8, MATE) on 2026-11-19. Dell-specific parts are marked.

| File | Goes to | Purpose |
|---|---|---|
| `01-battery.conf` | `/etc/tlp.d/` | Charge start/stop thresholds |
| `90-battery-levels.conf` | `/etc/UPower/UPower.conf.d/` | Low-battery levels and critical action |
| `lock-before-sleep.service` | `/etc/systemd/system/` | Lock all sessions before any suspend/hibernate |
| `battery-check.sh` | - | Shows whether all of the above is live |
| `discharge-report.sh` | - | Analyses the last on-battery run |

```BASH
sudo cp 01-battery.conf /etc/tlp.d/
sudo cp 90-battery-levels.conf /etc/UPower/UPower.conf.d/
sudo cp lock-before-sleep.service /etc/systemd/system/
sudo tlp setcharge
sudo systemctl restart upower
sudo systemctl daemon-reload && sudo systemctl enable lock-before-sleep.service
./battery-check.sh
```


## 1. Charge limits

Editing `/etc/tlp.d/01-battery.conf` does nothing until the next boot; TLP's
plug/unplug runs do not re-apply thresholds. Apply with:
```BASH
sudo tlp setcharge
sudo tlp fullcharge     # one-off charge to 100 %
```

**Dell:** the firmware ignores the thresholds unless the charge mode is
`Custom`; in the default `Adaptive` it charged to 97 % with the stop at 90.
`tlp setcharge` switched it here; otherwise:
```BASH
cat /sys/class/power_supply/BAT0/charge_types     # want: ... [Custom]
echo Custom | sudo tee /sys/class/power_supply/BAT0/charge_types
```
Stop must be at least start + 5. The BIOS has the same setting (Power ->
Battery Charge Configuration); whichever is written last wins.


## 2. Low-battery levels (UPower)

| Setting | Here | Effect |
|---|---|---|
| `PercentageLow` | 15 % | "Battery low" notification |
| `PercentageCritical` | 10 % | "Battery critical" notification |
| `PercentageAction` | 5 % | Runs `CriticalPowerAction` |

UPower reads its config only at start, so restart it after every edit
(`battery-check.sh` warns if you forgot) and confirm:
```BASH
sudo systemctl restart upower
busctl call org.freedesktop.UPower /org/freedesktop/UPower org.freedesktop.UPower GetCriticalAction
```

Avoid Ubuntu's default `HybridSleep`: at 2 % it wrote an image and suspended,
the laptop woke seconds later (which discards the image), was suspended again
by closing the lid, and the battery died in suspend. Use `Hibernate` once
section 3 is tested, else `PowerOff`.


## 3. Hibernate

Needs swap at least the size of RAM, kernel lockdown `[none]`
(`cat /sys/kernel/security/lockdown`) and a resume device:
```BASH
cat /sys/power/resume          # 259:3 = swap partition; 0:0 = none
```
Ubuntu's initramfs detects the swap partition by itself (`zz-resume-auto`),
so nothing else was needed. Only if it shows `0:0`:
```BASH
UUID=$(blkid -s UUID -o value /dev/<swap-partition>)
echo "RESUME=UUID=$UUID" | sudo tee /etc/initramfs-tools/conf.d/resume
# add resume=UUID=$UUID to GRUB_CMDLINE_LINUX_DEFAULT in /etc/default/grub
sudo update-initramfs -u -k all && sudo update-grub
```

`CanHibernate` on logind returns `no` because Ubuntu's polkit rule
(`com.ubuntu.desktop.rules`) blocks hibernate for users, which also hides it
from the menu. UPower runs as root and is not affected.

Test before relying on it: `sudo systemctl hibernate` must power off fully and
resume with windows intact. The journal then shows `hibernation entry`
followed by `Waking up from system sleep state S4`, without "Image saving"
lines (those are written after the snapshot, so a real resume loses them).


## 4. Lock before sleep

MATE's `lock-hibernate`/`lock-suspend` only apply when mate-power-manager
starts the sleep; hibernate from UPower or `systemctl` resumed **unlocked**.
`lock-before-sleep.service` runs `loginctl lock-sessions` before
`sleep.target`, while the locker is still running, for every trigger.
Verify after a hibernate:
```BASH
journalctl -b | grep -E 'lock-before-sleep|sleep operation'   # lock runs first
journalctl -b | grep mate-screensaver                         # unlock prompt after resume
```


## 5. Capacity test

Raise the limits (e.g. 90/95), set `PercentageAction=2`, charge full, unplug,
use normally until the action fires, then run `./discharge-report.sh`. It
reads `/var/lib/upower/` history and prints every % step (anything but `-1` is
flagged `JUMP`), the runtime, the energy drawn against what the gauge claims,
and the voltage. A difference of a few percent means the gauge is calibrated.

Result here: 96 -> 2 % in 3 h 40 min at 7.9 W, 29.1 Wh drawn vs 29.6 Wh
claimed (-1.9 %), every step -1 %, smooth voltage down to 10.70 V. Health
75 % at 82 cycles. Runtime is roughly `full Wh / average W`: 4 h at 8 W.
Restore the everyday limits and action level afterwards.
