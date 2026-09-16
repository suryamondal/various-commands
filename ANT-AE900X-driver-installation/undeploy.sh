#!/bin/bash
# Remove everything deploy.sh put on the system.
# Usage: sudo ./undeploy.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KVER="$(ls "$HERE/root/lib/modules")"

[ "$EUID" -eq 0 ] || { echo "Run as root: sudo $0"; exit 1; }

modprobe -r aic8800_fdrv aic_load_fw aic_zlp_quirk 2>/dev/null || true
while read -r f; do rm -f "$f"; done < "$HERE/MANIFEST"
rmdir /lib/modules/"$KVER"/updates/aic8800 /lib/firmware/aic8800*/ 2>/dev/null || true

depmod -a "$KVER"
udevadm control --reload-rules
echo "Removed."
