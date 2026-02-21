"""Export cleaned CBS 100m grid to GeoParquet.

Reconstructs 100 m square cell geometries from zone_id strings
and exports the cleaned grid as a GeoParquet file suitable for
visualisation and validation.

Usage:
    uv run python workflow/scripts/export_grid.py
"""

import re
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

INPUT = Path("data/processed/walcheren_grid_clean.parquet")
OUTPUT = Path("data/processed/walcheren_grid.geoparquet")

_ZONE_RE = re.compile(r"E(\d+)N(\d+)")


def zone_id_to_polygon(zone_id: str) -> box:
    """Build a 100 m square polygon from a CBS zone_id.

    Zone IDs follow the format ``E{X}N{Y}`` where *X* and *Y* are
    the easting and northing of the cell's lower-left corner in
    EPSG:28992, expressed in units of 100 m (hectometres).

    Returns a :class:`shapely.geometry.box` in EPSG:28992.

    Raises ``ValueError`` if *zone_id* does not match the expected
    format.
    """
    m = _ZONE_RE.match(zone_id)
    if m is None:
        raise ValueError(f"Cannot parse zone_id: {zone_id!r}")
    x0 = int(m.group(1)) * 100
    y0 = int(m.group(2)) * 100
    return box(x0, y0, x0 + 100, y0 + 100)


def export_grid(
    input_path: Path = INPUT,
    output_path: Path = OUTPUT,
) -> Path:
    """Read the cleaned grid and export it as GeoParquet.

    Geometries are reconstructed from the ``zone_id`` column and
    the resulting GeoDataFrame is stored in EPSG:28992 (RD New).
    """
    df = pd.read_parquet(input_path)

    geometries = df["zone_id"].map(zone_id_to_polygon)
    gdf = gpd.GeoDataFrame(df, geometry=geometries, crs="EPSG:28992")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(output_path)

    print(f"Saved {len(gdf)} grid cells to {output_path}")
    return output_path


if __name__ == "__main__":
    export_grid()
