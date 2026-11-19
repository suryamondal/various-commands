#!/usr/bin/env bash
# discharge-report.sh - analyse the last on-battery run from UPower's history.
#
# Prints every percentage step (to spot jumps such as 9% -> 2%), the runtime,
# the energy actually drawn (power integrated over time) and compares it with
# what the fuel gauge claims, which tells you how far the % reading can be
# trusted.
#
# Usage: discharge-report.sh [history-id]
#   history-id: the part after "history-charge-" in /var/lib/upower, e.g.
#               DELL_02HHX539-42-1939 (default: the laptop battery file that
#               was updated last).
set -eu

D=/var/lib/upower
ID=${1:-$(ls -t $D/history-charge-*.dat | grep -v generic_id | head -1 \
          | sed 's|.*/history-charge-||; s|\.dat$||')}
CHARGE=$D/history-charge-$ID.dat
RATE=$D/history-rate-$ID.dat
VOLT=$D/history-voltage-$ID.dat
[ -r "$CHARGE" ] || { echo "cannot read $CHARGE"; exit 1; }

# Last continuous "discharging" stretch in the charge history.
read -r T0 T1 P0 P1 < <(awk '
    $3 == "discharging" { if (!run) { s = $1; ps = $2 } run = 1; e = $1; pe = $2; next }
    { if (run) { S = s; E = e; PS = ps; PE = pe } run = 0 }
    END { if (run) { S = s; E = e; PS = ps; PE = pe } print S, E, int(PS + 0.5), int(PE + 0.5) }' "$CHARGE")
[ -n "${T1:-}" ] || { echo "no discharge found"; exit 1; }

echo "battery : $ID"
echo "run     : $(date -d @"$T0" '+%F %T') -> $(date -d @"$T1" '+%T')  ($P0% -> $P1%)"
echo

echo "== Percentage steps (anything other than -1 is a jump)"
awk -v a="$T0" -v b="$T1" '$1 >= a && $1 <= b && $3 == "discharging" {
        v = int($2 + 0.5)
        if (n++) printf "%s %3d%%  step %+d  after %4.1f min%s\n",
                        strftime("%H:%M:%S", $1), v, v - pv, ($1 - pt) / 60,
                        (v - pv < -1 ? "   <-- JUMP" : "")
        else     printf "%s %3d%%\n", strftime("%H:%M:%S", $1), v
        pv = v; pt = $1 }' "$CHARGE"
echo

# Full capacity in µWh. Some batteries (e.g. Dell) only expose charge_* in µAh;
# UPower converts those with voltage_min_design, and so do we.
B=/sys/class/power_supply/BAT0
if [ -r $B/energy_full ]; then
    FULL=$(cat $B/energy_full)
elif [ -r $B/charge_full ] && [ -r $B/voltage_min_design ]; then
    FULL=$(awk -v c="$(cat $B/charge_full)" -v v="$(cat $B/voltage_min_design)" 'BEGIN{printf "%.0f", c * v / 1e6}')
else
    FULL=0
fi

echo "== Energy"
awk -v a="$T0" -v b="$T1" -v pct=$(awk -v x="$P0" -v y="$P1" 'BEGIN{print x - y}') \
    -v full="$FULL" '
    $1 >= a && $1 <= b && $3 == "discharging" {
        if (p) { E += r * ($1 - p) / 3600; T += $1 - p }
        p = $1; r = $2 }
    END {
        printf "runtime          : %d h %02d min for %d%% of the battery\n", T / 3600, (T % 3600) / 60, pct
        printf "energy drawn     : %.2f Wh (average %.2f W)\n", E, E / (T / 3600)
        if (full > 0) {
            g = full / 1e6 * pct / 100
            printf "gauge claims     : %.2f Wh (%d%% of %.2f Wh full)\n", g, pct, full / 1e6
            printf "difference       : %+.1f%%  (within a few %% = trust the gauge)\n", 100 * (E - g) / g
            printf "full 100->0 est. : %.1f h at this average draw\n", full / 1e6 / (E / (T / 3600))
        }
    }' "$RATE"

if [ -r "$VOLT" ]; then
    echo
    echo "== Voltage (smooth fall = healthy; a sudden sag = cells giving out)"
    awk -v a="$T0" -v b="$T1" '$1 >= a && $1 <= b && $3 == "discharging" { if (!n++) f = $0; l = $0 }
        END { split(f, x); split(l, y)
              printf "start %.3f V  ->  end %.3f V\n", x[2], y[2] }' "$VOLT"
fi
