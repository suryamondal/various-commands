"""
EGM96 geoid undulation lookup.

Reproduces the exact algorithm used by BasicAirData GPS Logger's EGM96.java:
a bilinear interpolation over a 1440 x 721 grid of int16 values in centimetres,
laid out west-to-east from 0 deg E and north-to-south from +90 deg.

That grid is the classic WW15MGH.DAC file. If you do not have it, the same data
ships with PROJ as `egm96_15.gtx` (float32 metres, south-to-north from -180 deg),
which this module transposes into the DAC layout and rounds to centimetres --
verified to reproduce GPS Logger's own exports to within 0.5 mm.

Orthometric (sea level) height = ellipsoidal height (from GPS) - undulation.
"""

import os
import struct

import numpy as np

GRID_ROWS = 721            # latitude steps: +90 .. -90 in 0.25 deg
GRID_COLS = 1440           # longitude steps: 0 .. 359.75 in 0.25 deg
STEP = 0.25
DAC_BYTES = GRID_ROWS * GRID_COLS * 2

# Where the PROJ copy of the grid usually lives.
GTX_SEARCH_PATHS = (
    "/usr/share/proj/egm96_15.gtx",
    "/usr/local/share/proj/egm96_15.gtx",
    "/opt/homebrew/share/proj/egm96_15.gtx",
)


class Egm96:
    """Geoid undulation lookup over a WW15MGH-layout grid."""

    def __init__(self, grid_cm, source):
        self.grid = grid_cm
        self.source = source

    # ---------------------------------------------------------------- loading

    @classmethod
    def load(cls, path=None):
        """Load from an explicit path, else autodetect a PROJ egm96_15.gtx."""
        if path:
            if not os.path.exists(path):
                raise FileNotFoundError(f"geoid grid not found: {path}")
            if os.path.getsize(path) == DAC_BYTES:
                return cls.from_dac(path)
            return cls.from_gtx(path)

        for candidate in GTX_SEARCH_PATHS:
            if os.path.exists(candidate):
                return cls.from_gtx(candidate)
        raise FileNotFoundError(
            "No EGM96 grid found. Install PROJ's data (which provides "
            "egm96_15.gtx), or pass --egm-grid with a path to egm96_15.gtx "
            "or WW15MGH.DAC. Use --no-egm to export raw GPS altitudes instead."
        )

    @classmethod
    def from_dac(cls, path):
        """WW15MGH.DAC: big-endian int16 centimetres, already in DAC layout."""
        with open(path, "rb") as handle:
            raw = handle.read()
        if len(raw) != DAC_BYTES:
            raise ValueError(f"{path}: expected {DAC_BYTES} bytes, got {len(raw)}")
        grid = np.frombuffer(raw, dtype=">i2").reshape(GRID_ROWS, GRID_COLS)
        return cls(grid.astype(np.int32), path)

    @classmethod
    def from_gtx(cls, path):
        """PROJ egm96_15.gtx: big-endian float32 metres, south-up, -180 deg first."""
        with open(path, "rb") as handle:
            header = handle.read(40)
            body = handle.read()
        lat0, lon0, dlat, dlon = struct.unpack(">4d", header[:32])
        rows, cols = struct.unpack(">2i", header[32:40])
        if (rows, cols) != (GRID_ROWS, GRID_COLS) or (dlat, dlon) != (STEP, STEP):
            raise ValueError(
                f"{path}: expected a {GRID_ROWS}x{GRID_COLS} 0.25 deg grid, "
                f"got {rows}x{cols} at {dlat}/{dlon} deg"
            )
        metres = np.frombuffer(body, dtype=">f4", count=rows * cols).reshape(rows, cols)
        metres = metres[::-1, :]                                  # south-up -> north-down
        metres = np.roll(metres, -int(round(-lon0 / dlon)), axis=1)  # -180 deg -> 0 deg first
        grid = np.round(metres.astype(np.float64) * 100).astype(np.int32)
        return cls(grid, path)

    # ----------------------------------------------------------------- lookup

    def undulation(self, latitude, longitude):
        """Geoid height in metres at a coordinate, bilinearly interpolated."""
        lat = 90.0 - latitude                 # 0 at the north pole, 180 at the south
        lon = longitude + 360.0 if longitude < 0 else longitude

        i = int(lat / STEP)
        j = int(lon / STEP)
        # The DAC grid stops at the poles and wraps in longitude; GPS Logger pads
        # its array to the same effect.
        i = min(i, GRID_ROWS - 2)
        i_next, j_next = i + 1, (j + 1) % GRID_COLS
        j %= GRID_COLS

        h11 = self.grid[i, j]
        h12 = self.grid[i_next, j]
        h21 = self.grid[i, j_next]
        h22 = self.grid[i_next, j_next]

        f_lat = (lat % STEP) / STEP
        f_lon = (lon % STEP) / STEP
        hc1 = h11 + (h12 - h11) * f_lat
        hc2 = h21 + (h22 - h21) * f_lat
        return (hc1 + (hc2 - hc1) * f_lon) / 100.0

    def undulation_array(self, latitudes, longitudes):
        """Vectorised `undulation` for numpy arrays of coordinates."""
        lat = 90.0 - np.asarray(latitudes, dtype=np.float64)
        lon = np.asarray(longitudes, dtype=np.float64) % 360.0

        i = np.minimum((lat / STEP).astype(np.int64), GRID_ROWS - 2)
        j = (lon / STEP).astype(np.int64) % GRID_COLS
        i_next, j_next = i + 1, (j + 1) % GRID_COLS

        h11 = self.grid[i, j]
        h12 = self.grid[i_next, j]
        h21 = self.grid[i, j_next]
        h22 = self.grid[i_next, j_next]

        f_lat = (lat % STEP) / STEP
        f_lon = (lon % STEP) / STEP
        hc1 = h11 + (h12 - h11) * f_lat
        hc2 = h21 + (h22 - h21) * f_lat
        return (hc1 + (hc2 - hc1) * f_lon) / 100.0
