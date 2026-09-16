#!/bin/bash
# Fetch, build and stage the AIC8800D80 driver for the running kernel.
# Runs as a normal user; the system-wide step is `sudo <prefix>/install/deploy.sh`.
# Re-run after every kernel update.
#
# Usage: ./build.sh [PREFIX]        (default: ~/products/aic8800d80/v1.0.0)
#   AIC_COMMIT=<sha> ./build.sh     build a different upstream commit
set -euo pipefail

REPO="https://github.com/shenmintao/aic8800d80.git"
COMMIT="${AIC_COMMIT:-9594c5c99a337394e95869cd7099bf0e169d1a65}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
P="$(realpath -m "${1:-$HOME/products/aic8800d80/v1.0.0}")"
KVER="$(uname -r)"
ROOT="$P/install/root"

[ -d "/lib/modules/$KVER/build" ] || { echo "Kernel headers missing: sudo apt install linux-headers-$KVER dkms"; exit 1; }

# Source: shallow fetch of exactly the pinned commit
if [ ! -d "$P/source/.git" ]; then
    mkdir -p "$P/source"
    git -C "$P/source" init -q
    git -C "$P/source" remote add origin "$REPO"
fi
git -C "$P/source" fetch -q --depth 1 origin "$COMMIT"
git -C "$P/source" checkout -q --detach FETCH_HEAD

# Build out of the source tree so source/ stays pristine
rm -rf "$P/build"
mkdir -p "$P/build"
cp -a "$P/source/drivers/aic8800/." "$P/build/"
make -C "$P/build" -j"$(nproc)" KVER="$KVER" > "$P/build/build.log" 2>&1 || { tail -20 "$P/build/build.log"; exit 1; }

# Stage the files deploy.sh copies into /, laid out as on the real system
rm -rf "$ROOT"
mkdir -p "$ROOT/lib/modules/$KVER/updates/aic8800" "$ROOT/lib/firmware" "$ROOT/etc/udev/rules.d" "$ROOT/etc/usb_modeswitch.d"
install -m 644 "$P"/build/{aic8800_fdrv/aic8800_fdrv,aic_load_fw/aic_load_fw,aic_zlp_quirk/aic_zlp_quirk}.ko "$ROOT/lib/modules/$KVER/updates/aic8800/"
cp -r "$P"/source/fw/aic8800* "$ROOT/lib/firmware/"
install -m 644 "$P/source/aic.rules" "$ROOT/etc/udev/rules.d/90-aic8800.rules"
install -m 644 "$P/source/usb_modeswitch/1111_1111" "$ROOT/etc/usb_modeswitch.d/1111:1111"
(cd "$ROOT" && find . -type f | sed 's|^\./|/|' | sort) > "$P/install/MANIFEST"

# Keep the scripts next to what they manage, so a rebuild needs only the prefix
if [ "$HERE" != "$P" ]; then
    install -m 755 "$HERE/build.sh" "$P/build.sh"
    install -m 755 "$HERE/deploy.sh" "$HERE/undeploy.sh" "$P/install/"
fi

echo "Built $(git -C "$P/source" rev-parse --short HEAD) for $KVER in $P"
echo "Next: sudo $P/install/deploy.sh"
