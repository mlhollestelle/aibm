"""Filter CBS 100m grid to the study area using spatial join.

Loads the GeoPackage from the CBS zip, filters by bounding box,
then spatial-joins with municipality boundaries to keep only
cells within the study area.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# isort: split

import geopandas as gpd
from _config import load_config


def filter_grid(
    cbs_zip: Path,
    boundaries: Path,
    output: Path,
    cfg: dict,
) -> Path:
    """Load CBS grid, spatial-filter to study area."""
    g = cfg["grid"]
    bbox = tuple(g["bbox"])
    gpkg_file = g["gpkg_file"]
    gpkg_layer = g["gpkg_layer"]

    gpkg_path = f"/vsizip/{cbs_zip}/{gpkg_file}"
    grid = gpd.read_file(
        gpkg_path,
        layer=gpkg_layer,
        bbox=bbox,
        engine="pyogrio",
    )
    print(f"Loaded {len(grid)} cells within bounding box")

    gemeenten = gpd.read_file(boundaries)

    grid = grid.copy()
    grid["centroid"] = grid.geometry.centroid
    grid = grid.set_geometry("centroid")

    joined = gpd.sjoin(
        grid,
        gemeenten[["statcode", "geometry"]],
        how="inner",
        predicate="within",
    )

    joined = joined.set_geometry(grid.loc[joined.index, "geometry"])
    joined = joined.drop(columns=["centroid", "index_right"])

    print(f"Kept {len(joined)} cells within study area")

    output.parent.mkdir(parents=True, exist_ok=True)
    joined.to_parquet(output)
    print(f"Saved to {output}")
    return output


if __name__ == "__main__":
    cfg = load_config()
    name = cfg["study_area"]["name"]
    g = cfg["grid"]
    filter_grid(
        cbs_zip=Path(f"data/raw/{g['raw_zip']}"),
        boundaries=Path(f"data/raw/{name}_gemeenten.geojson"),
        output=Path(f"data/processed/{name}_grid_raw.parquet"),
        cfg=cfg,
    )
