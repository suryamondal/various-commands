# Ant Esports AE900X (Wi-Fi 6 + Bluetooth) on Linux

The Ant Esports AE900X is a USB Wi-Fi 6 / Bluetooth combo adapter built on the
**AICSemi AIC8800D80** chip. Linux has no driver for it: the chip is not in the
mainline kernel, and Ubuntu has no package for it (`apt-cache search aic8800`
finds nothing). Plugged in as-is, it does not even look like a network card:

```
$ lsusb
Bus 001 Device 004: ID 1111:1111 Pandora International Ltd. 88M80
```

That `1111:1111` device is a tiny virtual CD (`/media/$USER/WIFI driver`)
holding only a Windows installer, `Wifi6_install_bt.exe`. The adapter stays in
that mode until the host sends it a vendor-specific command, and `eject` alone
is not enough.

These scripts build the community driver
[shenmintao/aic8800d80](https://github.com/shenmintao/aic8800d80) (pinned to
commit `9594c5c`) into a self-contained prefix, and copy only what the system
needs into `/`. With it installed, the adapter goes through three USB IDs on
every plug-in or boot, in about two seconds:

| USB ID | What it is | What moves it on |
| --- | --- | --- |
| `1111:1111` | virtual driver CD | udev rule runs `usb_modeswitch` (sends SCSI `F3`, then `F2`) |
| `a69c:8d80` | bootloader, no firmware yet | `aic_load_fw` uploads firmware from `/lib/firmware/aic8800D80` |
| `a69c:8d81` | running adapter | `aic8800_fdrv` → Wi-Fi, stock `btusb` → Bluetooth |

Tested on Ubuntu 24.04, kernel `6.8.0-139-generic`, Secure Boot disabled.

## Files

| File | Runs as | Does |
| --- | --- | --- |
| `build.sh` | user | fetches the pinned source, builds the modules, stages everything under `install/root` |
| `deploy.sh` | root | copies the staged files into `/`, runs `depmod`, reloads udev rules |
| `undeploy.sh` | root | removes exactly the files listed in `install/MANIFEST` |

`build.sh` also copies all three scripts into the prefix, so later rebuilds need
only the prefix and not this repository.

## Layout

Everything lives under one prefix, by default `~/products/aic8800d80/v1.0.0`:

```
~/products/aic8800d80/v1.0.0/
├── build.sh              # rebuild for the running kernel
├── source/               # upstream git checkout, never modified
├── build/                # compiled here; build.log has the compiler output
└── install/
    ├── deploy.sh
    ├── undeploy.sh
    ├── MANIFEST          # every file deploy.sh puts on the system
    └── root/             # those files, at their system paths
        ├── etc/udev/rules.d/90-aic8800.rules
        ├── etc/usb_modeswitch.d/1111:1111
        ├── lib/firmware/aic8800*/
        └── lib/modules/<kernel>/updates/aic8800/{aic8800_fdrv,aic_load_fw,aic_zlp_quirk}.ko
```

`deploy.sh` **copies** rather than symlinks. The prefix may sit on a disk that
mounts late in boot (here `~/products` is on a secondary NVMe), and the modules
and firmware must already be readable when udev first sees the adapter.

## Installation

### 1. Prerequisites

```sh
sudo apt install linux-headers-$(uname -r) build-essential usb-modeswitch eject git
mokutil --sb-state        # should print "SecureBoot disabled"
```

The modules are unsigned. With Secure Boot enabled the kernel refuses to load
them; either disable it in the BIOS or sign the modules yourself.

### 2. Build (no sudo)

```sh
./build.sh                                # prefix: ~/products/aic8800d80/v1.0.0
./build.sh /some/other/prefix             # or anywhere else
```

It ends with:

```
Built 9594c5c for 6.8.0-139-generic in /home/surya/products/aic8800d80/v1.0.0
Next: sudo /home/surya/products/aic8800d80/v1.0.0/install/deploy.sh
```

If the build fails, the last 20 lines of `build/build.log` are printed.

### 3. Deploy (sudo)

```sh
sudo ~/products/aic8800d80/v1.0.0/install/deploy.sh
```

This also deletes any `/lib/firmware/aic8800*` directory that is not part of
this build: upstream warns that firmware of the wrong version can freeze the
system.

### 4. Re-plug the adapter

Unplug it completely and plug it back in (or reboot).

## Verification

```sh
lsusb | grep -i aic
# Bus 001 Device 007: ID a69c:8d81 AICSemi AIC 8800D80

nmcli dev status
# wlx688fc93c3faa          wifi      disconnected  --
# p2p-dev-wlx688fc93c3faa  wifi-p2p  disconnected  --

bluetoothctl list
# Controller 68:8F:C9:3C:3F:AB <hostname> [default]

sudo dmesg | grep -E 'chip_id|fw download'
# chip_id=7, chip_mcu_id = 0
# fw download complete
```

**Check `chip_mcu_id`.** `0` means this build (upstream `main`) is the right
one. If it says `1`, see [Troubleshooting](#troubleshooting).

The kernel also logs `loading out-of-tree module taints kernel` and
`module verification failed`. Both are expected for any unsigned third-party
module.

## Connecting to Wi-Fi

```sh
nmcli dev wifi list ifname wlx688fc93c3faa
nmcli --ask dev wifi connect "<SSID>" ifname wlx688fc93c3faa
```

`--ask` prompts for the password, so it stays out of your shell history.
NetworkManager saves the connection with autoconnect on, so it comes back
after a reboot. The interface name comes from the adapter's MAC address, so
yours will differ.

If Ethernet is also connected, NetworkManager keeps using it for the default
route. Wi-Fi only takes over when Ethernet is unplugged, unless you change the
route metrics.

## Bluetooth

No extra step is needed. After firmware upload, the kernel's own `btusb`
driver takes the Bluetooth interface and it appears as `hci0`:

```sh
bluetoothctl show | grep Powered
bluetoothctl --timeout 8 scan on
```

`aic_zlp_quirk.ko` is built and deployed too, but it only attaches to the
`368b:8d81` variant, so it stays unloaded on this adapter. That is expected.

## Regulatory domain (optional)

The driver starts in the world domain (`country 00`), which restricts some
channels. To set India, for example:

```sh
sudo iw reg set IN                                                       # this boot only
echo 'options cfg80211 ieee80211_regdom=IN' | sudo tee /etc/modprobe.d/cfg80211-regdom.conf  # permanent
```

## Persistence and kernel updates

Everything the boot needs is in `/etc` and `/lib` on the root filesystem, so
the adapter works after a reboot without re-plugging:

- udev replays "add" events for devices already present at boot, which runs
  the mode switch;
- `depmod` has registered the modules for `a69c:8d80` and `a69c:8d81`, so they
  load on their own;
- NetworkManager reconnects to saved networks.

The build is **not** DKMS, though. The modules exist only for the kernel they
were built against. After a kernel update, Wi-Fi and Bluetooth disappear until
you rebuild:

```sh
sudo apt install linux-headers-$(uname -r)     # usually already pulled in
~/products/aic8800d80/v1.0.0/build.sh
sudo ~/products/aic8800d80/v1.0.0/install/deploy.sh
```

`build.sh` wipes `install/root` before staging, so only the current kernel's
modules are kept there. Old kernels keep their already-deployed copy under
`/lib/modules/<old>/updates/aic8800` until that kernel is removed.

## Uninstall

```sh
sudo ~/products/aic8800d80/v1.0.0/install/undeploy.sh
rm -rf ~/products/aic8800d80/v1.0.0
```

`undeploy.sh` unloads the modules and deletes only what `MANIFEST` lists. The
`usb-modeswitch` and header packages stay installed. `build.sh` never
installs anything system-wide, so it has nothing to undo.

## Troubleshooting

**Still `1111:1111` after re-plugging.** Check that
`/etc/udev/rules.d/90-aic8800.rules` and `/etc/usb_modeswitch.d/1111:1111`
exist, then try the switch by hand:

```sh
sudo usb_modeswitch -v 1111 -p 1111 \
  -M "555342438765432100000000000010fd0000000000000000000000000000f3" \
  -2 "555342438765432100000000000010fd0000000000000000000000000000f2"
```

**`chip_mcu_id = 1`, or firmware upload times out at `0x170400`.** That is an
older hardware revision, which needs upstream's `legacy-mcu1` branch. Build
from its head commit:

```sh
AIC_COMMIT=$(git ls-remote https://github.com/shenmintao/aic8800d80.git refs/heads/legacy-mcu1 | cut -f1) ./build.sh
sudo ~/products/aic8800d80/v1.0.0/install/deploy.sh
```

Then reboot rather than re-plug, so the old firmware is not still loaded.

**Stuck at `a69c:8d80`.** The firmware did not start. Look at
`sudo dmesg | grep -iE 'aic|fw'` and see upstream
[issue #79](https://github.com/shenmintao/aic8800d80/issues/79).

**`Kernel headers missing`.** Install `linux-headers-$(uname -r)`. If the
package does not exist, the running kernel is older than the archive; reboot
into the newest installed kernel.

## Why not upstream's `install.sh`?

Upstream's `sudo ./install.sh` installs the same files, but through DKMS, with
its own copy of the source under `/usr/src` and its build tree under
`/var/lib/dkms`. These scripts keep source, build and staged output together in
one prefix, run the compiler as a normal user, and limit root to copying a
known file list, which `undeploy.sh` can remove exactly. The trade-off is the
manual rebuild after kernel updates.
