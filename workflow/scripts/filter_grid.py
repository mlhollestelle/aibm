"""Filter CBS 100m grid to Walcheren using spatial join.

Loads the GeoPackage from the CBS zip, filters by bounding box,
then spatial-joins with municipality boundaries to keep only
Walcheren grid cells.
"""

from pathlib import Path

import geopandas as gpd

CBS_ZIP = Path("data/raw/2025-cbs_vk100_2024_v1.zip")
BOUNDARIES = Path("data/raw/walcheren_gemeenten.geojson")
OUTPUT = Path("data/processed/walcheren_grid_raw.parquet")

# Approximate Walcheren bounding box (EPSG:28992)
BBOX = (15_000, 385_000, 40_000, 405_000)


def filter_grid(
    cbs_zip: Path = CBS_ZIP,
    boundaries: Path = BOUNDARIES,
    output: Path = OUTPUT,
) -> Path:
    """Load CBS grid, spatial-filter to Walcheren."""
    gpkg_path = f"/vsizip/{cbs_zip}/cbs_vk100_2024_v1.gpkg"
    grid = gpd.read_file(
        gpkg_path,
        layer="cbs_vk100_2024",
        bbox=BBOX,
        engine="pyogrio",
    )
    print(f"Loaded {len(grid)} cells within bounding box")

    gemeenten = gpd.read_file(boundaries)

    # Spatial join: keep cells whose centroid falls within
    # a municipality polygon
    grid = grid.copy()
    grid["centroid"] = grid.geometry.centroid
    grid = grid.set_geometry("centroid")

    joined = gpd.sjoin(
        grid,
        gemeenten[["statcode", "geometry"]],
        how="inner",
        predicate="within",
    )

    # Restore original geometry and drop helper columns
    joined = joined.set_geometry(grid.loc[joined.index, "geometry"])
    joined = joined.drop(columns=["centroid", "index_right"])

    print(f"Kept {len(joined)} cells within Walcheren")

    output.parent.mkdir(parents=True, exist_ok=True)
    joined.to_parquet(output)
    print(f"Saved to {output}")
    return output


if __name__ == "__main__":
    filter_grid()
