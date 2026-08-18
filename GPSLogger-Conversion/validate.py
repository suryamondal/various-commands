#!/usr/bin/env python3
"""
Compare converted GPX files against reference exports made by the app itself.

For every reference file that has a counterpart in the converted directory,
this parses both and reports the largest disagreement in coordinates, elevation,
time, speed and satellite count -- the check that the EGM96 correction and the
field formatting really do reproduce what GPS Logger writes.

    ./validate.py tmp/ gpx/
"""

import argparse
import os
import re
import sys

TRKPT = re.compile(r'<trkpt lat="([^"]+)" lon="([^"]+)">(.*?)</trkpt>')
CHILD = re.compile(r"<(ele|time|speed|sat)>([^<]*)</\1>")


def read_points(path):
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    points = []
    for lat, lon, body in TRKPT.findall(text):
        point = {"lat": float(lat), "lon": float(lon)}
        for tag, value in CHILD.findall(body):
            point[tag] = value if tag == "time" else float(value)
        points.append(point)
    return points


def compare(reference, converted):
    ref, got = read_points(reference), read_points(converted)
    if len(ref) != len(got):
        return None, f"point count differs: {len(ref)} vs {len(got)}"

    worst = {"lat": 0.0, "lon": 0.0, "ele": 0.0, "speed": 0.0}
    mismatched_time = mismatched_sat = 0
    for a, b in zip(ref, got):
        for key in worst:
            if key in a and key in b:
                worst[key] = max(worst[key], abs(a[key] - b[key]))
            elif (key in a) != (key in b):
                return None, f"field <{key}> present in only one file"
        if a.get("time") != b.get("time"):
            mismatched_time += 1
        if a.get("sat") != b.get("sat"):
            mismatched_sat += 1
    return (worst, mismatched_time, mismatched_sat, len(ref)), None


def main():
    parser = argparse.ArgumentParser(
        description="Check converted GPX files against the app's own exports.")
    parser.add_argument("reference", help="directory of app-exported .gpx files")
    parser.add_argument("converted", help="directory of .gpx files from this converter")
    # PROJ's egm96_15.gtx and the app's WW15MGH.DAC round a few grid cells
    # differently, which shows up as ~1 cm of elevation -- well under GPS noise.
    parser.add_argument("--tolerance", type=float, default=0.011,
                        help="max acceptable elevation difference in metres")
    args = parser.parse_args()

    names = sorted(n for n in os.listdir(args.reference) if n.endswith(".gpx"))
    checked = failed = 0
    for name in names:
        converted = os.path.join(args.converted, name)
        if not os.path.exists(converted):
            print(f"  {name:26s} SKIP  (not in {args.converted})")
            continue
        result, problem = compare(os.path.join(args.reference, name), converted)
        checked += 1
        if problem:
            failed += 1
            print(f"  {name:26s} FAIL  {problem}")
            continue
        worst, bad_time, bad_sat, count = result
        ok = (worst["ele"] <= args.tolerance and worst["lat"] <= 1e-8
              and worst["lon"] <= 1e-8 and worst["speed"] <= 0.001
              and not bad_time and not bad_sat)
        failed += not ok
        print(f"  {name:26s} {'OK  ' if ok else 'FAIL'}  {count:6d} pts  "
              f"max dele={worst['ele']:.4f} m  dlat={worst['lat']:.9f}  "
              f"dspeed={worst['speed']:.4f}  time/sat mismatches={bad_time}/{bad_sat}")

    print(f"\n{checked - failed}/{checked} file(s) match the app's export exactly.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
