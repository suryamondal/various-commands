#!/bin/bash
# Copy the staged AIC8800D80 driver files (install/root) into the system.
# Real copies, not symlinks: ~/products lives on a drive mounted late in boot.
# Usage: sudo ./deploy.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KVER="$(ls "$HERE/root/lib/modules")"

[ "$EUID" -eq 0 ] || { echo "Run as root: sudo $0"; exit 1; }
[ "$(uname -r)" = "$KVER" ] || echo "WARNING: modules built for $KVER, running $(uname -r). Run ../build.sh first."

# Old AIC firmware of a different version can hang the system (upstream README).
for d in /lib/firmware/aic8800*; do
    [ -d "$d" ] && [ ! -e "$HERE/root$d" ] && { echo "Removing stale $d"; rm -rf "$d"; }
done

while read -r f; do
    install -D -m 644 "$HERE/root$f" "$f"
done < "$HERE/MANIFEST"

depmod -a "$KVER"
udevadm control --reload-rules
echo "Deployed. Unplug and re-plug the adapter, then check: lsusb; ip -br link"
