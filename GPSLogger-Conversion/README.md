# GPS Logger backup to GPX

Converts a [BasicAirData GPS Logger](https://github.com/BasicAirData/GPSLogger)
Android backup into one GPX 1.0 file per track.

The backup `.zip` contains no GPX at all — that is the whole problem it solves.
The tracks live in the app's SQLite database at
`eu.basicairdata.graziano.gpslogger/databases/GPSLogger`, as a `tracks` table of
per-track statistics plus a `locations` table holding every individual fix. These
scripts read that database and write the GPX the app itself would have produced,
which matters when the backup is all you have left and the app is gone, or when
there are more tracks than you care to export by hand.

## Usage

```sh
python3 gpslogger_to_gpx.py "20260818-142639 - BACKUP - GPSLogger Tracklist.zip" -o gpx
```

An already-extracted `GPSLogger` database file works in place of the zip.

| option | effect |
| --- | --- |
| `-o, --out DIR` | output directory (default `gpx`) |
| `--egm-grid PATH` | geoid grid to use; autodetects PROJ's `egm96_15.gtx` |
| `--no-egm` | keep raw ellipsoidal altitudes instead of correcting them |
| `--with-course` | also write `<course>` from the recorded bearing (the app omits it) |
| `--track NAME` | export only this track name or id; repeatable |
| `--overwrite` | rewrite files that already exist |

Needs `numpy`, and a copy of the EGM96 geoid grid (see below). One run over a
290-track, 1.4-million-point backup takes about a minute.

## Altitude, and why the geoid correction is not optional

Android reports altitude as an **ellipsoidal (WGS84) height**, and that is what the
database stores. Sea-level altitude needs the geoid subtracted:

```
orthometric height = ellipsoidal height − EGM96 undulation
```

That undulation is roughly 46 m in Italy and 40 m near Hamburg. Skipping this step
does not introduce a rounding error, it puts every trackpoint tens of metres too
high, and by a different amount in each country the track passes through. The app
does the correction itself when its "EGM96 altitude correction" setting is on, so
raw database altitudes do not match the app's own exports until it is applied.

`egm96.py` reproduces the app's algorithm from its `EGM96.java`: bilinear
interpolation over a 1440 × 721 grid of `int16` centimetre values — the classic
`WW15MGH.DAC`. That file is not redistributed here, so by default the grid is
rebuilt from PROJ's `egm96_15.gtx`, which is already on most Linux systems at
`/usr/share/proj/egm96_15.gtx`. Nothing needs downloading. Pass `--egm-grid` to
point at a real `WW15MGH.DAC`, or at a `.gtx` somewhere else.

## Checking the output against the app

Anything reimplementing a format this closely deserves evidence rather than
assurances. If some tracks were exported by the app before the backup was made,
`validate.py` compares them field by field:

```sh
python3 validate.py reference-gpx-dir converted-gpx-dir
```

Run against 10 app-exported tracks (~20 000 points, from city walks to
intercontinental flights), every one reproduced the app's output: identical
coordinates, timestamps, speeds and satellite counts, and identical elevations on
8 of the 10.

On the two long-haul flights a few points differed by up to **1 cm**. The cause is
worth recording, because it is not a bug to chase: PROJ's `egm96_15.gtx` and the
app's `WW15MGH.DAC` round a handful of grid cells differently by one count. The
differences ramp smoothly from 0 to exactly 0.010 m and stop dead there, which is
the signature of a one-count corner disagreement spread out by the bilinear
interpolation. GPS altitude noise is metres; this is three orders of magnitude
below it. `--tolerance` sets the threshold the check applies.

## Details worth knowing

- **Missing values.** GPS Logger stores `-100000`, not NULL, for a reading it never
  got. Those elements are omitted from the GPX rather than written as a nonsense
  number that downstream tools would happily plot. A satellite count of `0` means
  the same thing and is likewise omitted, matching the app.
- **Activity keywords.** `<keywords>` comes from the track's `type` column. Codes 1
  (walking), 2 (mountaineering), 5 (car), 6 (flying) and the `-100000` fallback
  (`driving_general`) are confirmed against app exports. 0 (steady), 3 (running) and
  4 (cycling) follow the app's constant order but were not exercised by any
  reference file, so treat them as inferred.
- **Header statistics.** The leading comment block is recomputed from the `tracks`
  table. `Direction` matched the app on all 10 reference tracks; `Altitude Gap`
  matched on 8, the other two off by 1–2 m because the app snapshots its start and
  end altitude at a slightly different moment than the first and last trackpoint.
- **Bearing** is recorded in the database but the app never exports it. `--with-course`
  keeps it instead of discarding it.
- **Placemarks** are exported as `<wpt>`.
- Tracks with no recorded locations are skipped — the app keeps an empty row for the
  current track slot.
