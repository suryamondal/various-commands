#!/usr/bin/env python3
"""
Export every track from a BasicAirData GPS Logger backup to a GPX 1.0 file.

The backup zip contains the app's SQLite database under
`eu.basicairdata.graziano.gpslogger/databases/GPSLogger`; this reads its
`tracks`, `locations` and `placemarks` tables and writes one .gpx per track,
matching the layout the app itself produces (see scripts/README.md).

Altitudes are stored by Android as ellipsoidal (WGS84) heights. By default they
are converted to orthometric (sea level) heights with the EGM96 geoid, exactly
as the app does when its "EGM96 altitude correction" setting is on. Pass
--no-egm to keep the raw values.

    ./gpslogger_to_gpx.py backup.zip -o gpx/
"""

import argparse
import math
import os
import sqlite3
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from xml.sax.saxutils import escape, quoteattr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from egm96 import Egm96  # noqa: E402

DB_MEMBER = "eu.basicairdata.graziano.gpslogger/databases/GPSLogger"

# GPS Logger stores "value not available" as this sentinel rather than NULL.
NOT_AVAILABLE = -100000.0

# Track.TRACK_TYPE_* -> the GPX <keywords> activity the app writes.
# Codes 1, 2, 5, 6 and the -100000 fallback are confirmed against app exports;
# 0, 3 and 4 follow the app's constant order and are unverified here.
ACTIVITY = {
    -100000: "driving_general",
    0: "steady",
    1: "walking",
    2: "mountaineering",
    3: "running",
    4: "cycling",
    5: "car",
    6: "flying",
}

COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")

TRACK_COLUMNS = """
    id, name, start_latitude, start_longitude, start_altitude, start_time,
    end_latitude, end_longitude, end_altitude, end_time,
    min_latitude, min_longitude, max_latitude, max_longitude,
    duration, duration_moving, distance, speed_max, speed_average,
    speed_average_moving, number_of_locations, number_of_placemarks,
    type, description, validmap
"""


def available(value):
    """GPS Logger writes -100000 for missing readings; NULL happens too."""
    return value is not None and value > NOT_AVAILABLE + 1


# --------------------------------------------------------------- formatting

def iso_time(millis):
    """Epoch milliseconds -> the UTC timestamp format GPX wants."""
    return datetime.fromtimestamp(millis / 1000.0, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def format_distance(metres):
    if not available(metres):
        return "-"
    if metres < 1000:
        return f"{metres:.0f} m"
    km = metres / 1000.0
    return f"{km:.2f} km" if km < 10 else f"{km:.1f} km"


def format_duration(millis):
    if not available(millis):
        return "-"
    total = int(round(millis / 1000.0))
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def bearing(lat1, lon1, lat2, lon2):
    """Initial great-circle bearing in degrees, 0 = north."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)
    return math.degrees(math.atan2(y, x)) % 360.0


# ------------------------------------------------------------------ writing

def write_header(out, track, geoid, creator, with_course):
    """The comment block, <name>/<time>/<keywords> and <bounds>."""
    activity = ACTIVITY.get(track["type"], "unknown")
    out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    out.write(f"<!-- Created with {creator} -->\n")
    out.write("<!-- Exported from a BasicAirData GPS Logger backup database -->\n")
    out.write(f"<!-- Track {track['id']} = {track['number_of_locations']} TrackPoints"
              f" + {track['number_of_placemarks']} Placemarks -->\n\n")

    out.write("<!-- Track Statistics (based on Total Time | Time in Movement): -->\n")
    out.write(f"<!--  Distance = {format_distance(track['distance'])} -->\n")
    out.write(f"<!--  Duration = {format_duration(track['duration'])}"
              f" | {format_duration(track['duration_moving'])} -->\n")

    start_alt, end_alt = track["start_altitude"], track["end_altitude"]
    if available(start_alt) and available(end_alt):
        if geoid:
            start_alt -= geoid.undulation(track["start_latitude"], track["start_longitude"])
            end_alt -= geoid.undulation(track["end_latitude"], track["end_longitude"])
        out.write(f"<!--  Altitude Gap = {end_alt - start_alt:.0f} m -->\n")

    if available(track["speed_max"]):
        out.write(f"<!--  Max Speed = {track['speed_max'] * 3.6:.0f} km/h -->\n")
    if available(track["speed_average"]) and available(track["speed_average_moving"]):
        out.write(f"<!--  Avg Speed = {track['speed_average'] * 3.6:.1f}"
                  f" | {track['speed_average_moving'] * 3.6:.1f} km/h -->\n")

    if track["validmap"]:
        heading = bearing(track["start_latitude"], track["start_longitude"],
                          track["end_latitude"], track["end_longitude"])
        out.write(f"<!--  Direction = {COMPASS[int(round(heading / 22.5)) % 16]} -->\n")
    out.write(f"<!--  Activity = {activity} -->\n")
    out.write("<!--  Altitudes = %s -->\n" % (
        "Corrected using EGM96 grid (bilinear interpolation)" if geoid
        else "Raw ellipsoidal (WGS84) heights, not geoid corrected"))

    out.write('\n<gpx version="1.0"\n')
    out.write(f"     creator={quoteattr(creator)}\n")
    out.write('     xmlns="http://www.topografix.com/GPX/1/0"\n')
    out.write('     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n')
    out.write('     xsi:schemaLocation="http://www.topografix.com/GPX/1/0'
              ' http://www.topografix.com/GPX/1/0/gpx.xsd">\n')
    out.write(f"<name>GPS Logger {escape(track['name'])}</name>\n")
    if track["description"]:
        out.write(f"<desc>{escape(track['description'])}</desc>\n")
    out.write(f"<time>{iso_time(time.time() * 1000)}</time>\n")
    out.write(f"<keywords>{activity}</keywords>\n")
    if track["validmap"]:
        out.write(f'<bounds minlat="{track["min_latitude"]:.8f}"'
                  f' minlon="{track["min_longitude"]:.8f}"'
                  f' maxlat="{track["max_latitude"]:.8f}"'
                  f' maxlon="{track["max_longitude"]:.8f}" />\n')
    out.write("\n")


def write_point(out, row, tag, geoid, with_course, indent, name=None):
    """One <trkpt> or <wpt>, with the child elements the app emits."""
    parts = [f'{indent}<{tag} lat="{row["latitude"]:.8f}" lon="{row["longitude"]:.8f}">']
    altitude = row["altitude"]
    if available(altitude):
        if geoid:
            altitude -= geoid.undulation(row["latitude"], row["longitude"])
        parts.append(f"<ele>{altitude:.3f}</ele>")
    if available(row["time"]):
        parts.append(f"<time>{iso_time(row['time'])}</time>")
    if with_course and available(row["bearing"]):
        parts.append(f"<course>{row['bearing']:.3f}</course>")
    if available(row["speed"]):
        parts.append(f"<speed>{row['speed']:.3f}</speed>")
    if name:
        parts.append(f"<name>{escape(name)}</name>")
    # A count of 0 means "not reported"; the app leaves <sat> out in that case.
    satellites = row["number_of_satellites_used_in_fix"]
    if available(satellites) and satellites > 0:
        parts.append(f"<sat>{int(satellites)}</sat>")
    parts.append(f"</{tag}>\n")
    out.write("".join(parts))


def write_track(db, track, path, geoid, creator, with_course):
    """Write one track's GPX file. Returns the number of trackpoints written."""
    with open(path, "w", encoding="utf-8") as out:
        write_header(out, track, geoid, creator, with_course)

        placemarks = db.execute(
            "SELECT * FROM placemarks WHERE track_id = ? ORDER BY nr, id",
            (track["id"],))
        for row in placemarks:
            write_point(out, row, "wpt", geoid, with_course, "", name=row["name"])

        out.write("<trk>\n")
        out.write(f" <name>Track {escape(track['name'])}</name>\n")
        out.write(" <trkseg>\n")
        count = 0
        rows = db.execute(
            "SELECT * FROM locations WHERE track_id = ? ORDER BY nr, id",
            (track["id"],))
        for row in rows:
            write_point(out, row, "trkpt", geoid, with_course, "  ")
            count += 1
        out.write(" </trkseg>\n")
        out.write("</trk>\n\n")
        out.write("</gpx>\n")
    return count


# -------------------------------------------------------------------- input

def open_database(source, workdir):
    """Accept either the backup zip or an already-extracted database file."""
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            member = DB_MEMBER
            if member not in archive.namelist():
                matches = [n for n in archive.namelist()
                           if n.endswith("/databases/GPSLogger")]
                if not matches:
                    raise SystemExit(f"{source}: no GPS Logger database inside the zip")
                member = matches[0]
            target = os.path.join(workdir, "GPSLogger.db")
            with archive.open(member) as src, open(target, "wb") as dst:
                while chunk := src.read(1 << 20):
                    dst.write(chunk)
            return target
    return source


def safe_filename(track):
    """Track names are user text; keep them usable as filenames."""
    name = (track["name"] or "").strip() or f"track_{track['id']}"
    cleaned = "".join(c if c.isalnum() or c in "-_. " else "_" for c in name).strip()
    return cleaned or f"track_{track['id']}"


def main():
    parser = argparse.ArgumentParser(
        description="Convert a BasicAirData GPS Logger backup into GPX files.")
    parser.add_argument("source",
                        help="the backup .zip, or an extracted GPSLogger database")
    parser.add_argument("-o", "--out", default="gpx",
                        help="output directory (default: gpx)")
    parser.add_argument("--egm-grid", metavar="PATH",
                        help="egm96_15.gtx or WW15MGH.DAC (default: autodetect PROJ's)")
    parser.add_argument("--no-egm", action="store_true",
                        help="keep raw ellipsoidal altitudes instead of correcting them")
    parser.add_argument("--with-course", action="store_true",
                        help="also emit <course> from the recorded bearing")
    parser.add_argument("--track", action="append", metavar="NAME",
                        help="export only this track name or id (repeatable)")
    parser.add_argument("--overwrite", action="store_true",
                        help="rewrite files that already exist")
    args = parser.parse_args()

    geoid = None
    if not args.no_egm:
        geoid = Egm96.load(args.egm_grid)
        print(f"EGM96 grid: {geoid.source}")

    creator = "gpslogger_to_gpx.py"
    os.makedirs(args.out, exist_ok=True)

    with tempfile.TemporaryDirectory() as workdir:
        db_path = open_database(args.source, workdir)
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row

        tracks = db.execute(f"SELECT {TRACK_COLUMNS} FROM tracks ORDER BY id").fetchall()
        if args.track:
            wanted = set(args.track)
            tracks = [t for t in tracks
                      if t["name"] in wanted or str(t["id"]) in wanted]
            if not tracks:
                raise SystemExit("no track matched --track")

        written = skipped = empty = 0
        total_points = 0
        for track in tracks:
            if not track["number_of_locations"]:
                empty += 1
                continue
            path = os.path.join(args.out, safe_filename(track) + ".gpx")
            if os.path.exists(path) and not args.overwrite:
                skipped += 1
                continue
            count = write_track(db, track, path, geoid, creator, args.with_course)
            total_points += count
            written += 1
            print(f"  {os.path.basename(path):24s} {count:7d} points")

        db.close()

    print(f"\n{written} track(s) written to {args.out}/ "
          f"({total_points} trackpoints)")
    if skipped:
        print(f"{skipped} already existed (use --overwrite to replace)")
    if empty:
        print(f"{empty} track(s) had no recorded locations and were skipped")


if __name__ == "__main__":
    main()
