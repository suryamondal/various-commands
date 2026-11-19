#!/usr/bin/env bash
# battery-check.sh - show whether the battery setup in this directory is live.
# Read-only; run as a normal user.
set -u

BAT=${1:-BAT0}
B=/sys/class/power_supply/$BAT
[ -d "$B" ] || { echo "no $B"; exit 1; }

rd() { cat "$1" 2>/dev/null || echo "n/a"; }
logind() {
    busctl call org.freedesktop.login1 /org/freedesktop/login1 \
        org.freedesktop.login1.Manager "$1" 2>/dev/null | awk '{print $2}' | tr -d '"'
}

echo "== Battery ($BAT)"
echo "level        : $(rd $B/capacity)%  ($(rd $B/status))"
if [ -r $B/energy_full ]; then
    full=$(rd $B/energy_full); design=$(rd $B/energy_full_design)
else
    full=$(rd $B/charge_full); design=$(rd $B/charge_full_design)
fi
awk -v f="$full" -v d="$design" 'BEGIN{ if (d > 0) printf "health       : %.1f%% of design\n", 100*f/d }'
echo "cycles       : $(rd $B/cycle_count)"

echo "== Charge thresholds"
echo "start / stop : $(rd $B/charge_control_start_threshold) / $(rd $B/charge_control_end_threshold)"
echo "charge mode  : $(rd $B/charge_types)   (Dell: must be [Custom])"
echo "tlp drop-ins : $(grep -hE '^(START|STOP)_CHARGE_THRESH_'"$BAT" /etc/tlp.d/*.conf 2>/dev/null | tr '\n' ' ')"

echo "== UPower low-battery policy"
grep -hE '^(Percentage|CriticalPowerAction|UsePercentage)' /etc/UPower/UPower.conf.d/*.conf 2>/dev/null | sed 's/^/drop-in      : /'
act=$(busctl call org.freedesktop.UPower /org/freedesktop/UPower \
        org.freedesktop.UPower GetCriticalAction 2>/dev/null | awk '{print $2}' | tr -d '"')
echo "live action  : ${act:-n/a}"
started=$(systemctl show upower -p ActiveEnterTimestamp --value)
newest=$(ls -t /etc/UPower/UPower.conf.d/*.conf 2>/dev/null | head -1)
if [ -n "$newest" ] && [ "$(stat -c %Y "$newest")" -gt "$(date -d "$started" +%s)" ]; then
    echo "WARNING      : $newest changed after upower started - run: sudo systemctl restart upower"
fi

echo "== Hibernate"
echo "resume dev   : $(rd /sys/power/resume)   (0:0 = none, resume will not work)"
swapon --show=NAME,SIZE,USED --noheadings | sed 's/^/swap         : /'
free -h | awk '/^Mem:/{print "ram          : " $2}'
echo "CanHibernate : $(logind CanHibernate)   ('no' is Ubuntu's polkit rule for users; root/UPower may still hibernate)"

echo "== Lock before sleep"
echo "service      : $(systemctl is-enabled lock-before-sleep.service 2>/dev/null || echo missing)"
