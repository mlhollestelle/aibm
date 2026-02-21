"""Fetch Points of Interest from OpenStreetMap for Walcheren.

Downloads OSM features that match each out-of-home activity type
and writes a single GeoParquet file with an ``activity_type``
column.

Uses *osmnx* to query the Overpass API.  The Walcheren boundary
polygon (union of Middelburg, Veere, Vlissingen) is read from the
previously downloaded GeoJSON.
"""

from pathlib import Path

import geopandas as gpd
import osmnx
import pandas as pd
from shapely.geometry import Point

# ----- paths --------------------------------------------------------
BOUNDARIES = Path("data/raw/walcheren_gemeenten.geojson")
GRID = Path("data/processed/walcheren_grid_clean.parquet")
OUTPUT = Path("data/processed/walcheren_pois.parquet")
OUTPUT_GPKG = Path("data/processed/walcheren_pois.gpkg")

# ----- OSM tag mapping per activity type ----------------------------
# Keys are the activity types from aibm.activity.VALID_OUT_OF_HOME_TYPES.
# Values are *osmnx* tag dicts: key → True (any value) or list of
# specific values.
ACTIVITY_TAGS: dict[str, dict[str, bool | list[str]]] = {
    "work": {
        "office": True,
        "building": ["office", "commercial", "industrial"],
        "landuse": ["commercial", "industrial"],
    },
    "school": {
        "amenity": [
            "school",
            "university",
            "college",
            "kindergarten",
        ],
    },
    "shopping": {
        "shop": True,
        "amenity": ["marketplace"],
    },
    "leisure": {
        "leisure": True,
        "tourism": True,
        "amenity": [
            "cinema",
            "theatre",
            "library",
            "community_centre",
        ],
        "sport": True,
    },
    "personal_business": {
        "amenity": [
            "bank",
            "post_office",
            "doctors",
            "dentist",
            "pharmacy",
            "hospital",
            "clinic",
            "townhall",
        ],
        "office": ["government"],
    },
    "escort": {
        "amenity": ["childcare", "kindergarten", "school"],
    },
    "eating_out": {
        "amenity": [
            "restaurant",
            "cafe",
            "fast_food",
            "bar",
            "pub",
            "food_court",
        ],
    },
}


def assign_grid_zone(
    pois: gpd.GeoDataFrame,
    grid: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Add a ``zone_id`` column to *pois* from the nearest grid cell.

    Each POI point is matched to the geographically nearest 100 m grid
    cell polygon.  Both GeoDataFrames must be in the same CRS.

    Parameters
    ----------
    pois:
        GeoDataFrame of POI points.
    grid:
        GeoDataFrame of grid cell polygons with a ``zone_id`` column.

    Returns
    -------
    Copy of *pois* with an added ``zone_id`` column.
    """
    # "left" join ensures every POI gets a zone_id, including those
    # slightly outside the study area boundary — they snap to the
    # nearest cell rather than being dropped.
    joined = gpd.sjoin_nearest(
        pois,
        grid[["zone_id", "geometry"]],
        how="left",
    )
    return joined.drop(columns=["index_right"])


def _to_point(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Convert all geometries to their centroid point."""
    gdf = gdf.copy()
    gdf["geometry"] = gdf.geometry.centroid
    # Drop rows whose centroid could not be computed
    gdf = gdf[gdf.geometry.apply(lambda g: isinstance(g, Point))]
    return gdf


def fetch_pois(
    boundaries_path: Path = BOUNDARIES,
    output_path: Path = OUTPUT,
    output_gpkg: Path = OUTPUT_GPKG,
    grid_path: Path = GRID,
) -> Path:
    """Download POIs for every activity type and save as Parquet.

    Parameters
    ----------
    boundaries_path:
        GeoJSON with Walcheren municipality polygons (EPSG:28992).
    output_path:
        Destination GeoParquet file.
    output_gpkg:
        Destination GeoPackage file.
    grid_path:
        GeoParquet with cleaned 100 m grid cells (EPSG:28992).
        Each POI is matched to its nearest grid cell and the
        ``zone_id`` is stored in the output.

    Returns
    -------
    Path to the written file.
    """
    boundaries = gpd.read_file(boundaries_path)
    # osmnx expects WGS 84
    boundary_4326 = boundaries.to_crs(epsg=4326)
    polygon = boundary_4326.union_all()

    frames: list[gpd.GeoDataFrame] = []

    for activity_type, tags in ACTIVITY_TAGS.items():
        print(f"Fetching POIs for '{activity_type}' …")
        try:
            gdf = osmnx.features_from_polygon(polygon, tags=tags)
        except osmnx._errors.InsufficientResponseError:
            print(f"  No features found for '{activity_type}'.")
            continue

        # Keep only useful columns; OSM returns many.
        keep = ["geometry", "name", "osmid"]
        keep = [c for c in keep if c in gdf.columns]
        # osmid lives in the index for osmnx ≥2
        if "osmid" not in gdf.columns:
            gdf = gdf.reset_index()
            keep = [c for c in ["geometry", "name", "osmid"] if c in gdf.columns]

        gdf = gdf[keep].copy()
        gdf["activity_type"] = activity_type

        # Normalise to point geometries and reproject to RD New
        gdf = _to_point(gdf)
        gdf = gdf.to_crs(epsg=28992)

        print(f"  Found {len(gdf)} features.")
        frames.append(gdf)

    if not frames:
        raise RuntimeError("No POIs found for any activity type.")

    result = gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True),
        crs="EPSG:28992",
    )
    print(
        f"\nTotal: {len(result)} POIs across "
        f"{result['activity_type'].nunique()} activity types."
    )

    grid = gpd.read_parquet(grid_path)[["zone_id", "geometry"]]
    result = assign_grid_zone(result, grid)
    print("Assigned each POI to its nearest grid zone_id.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(output_path)
    print(f"Saved to {output_path}")

    output_gpkg.parent.mkdir(parents=True, exist_ok=True)
    result.to_file(output_gpkg, driver="GPKG")
    print(f"Saved to {output_gpkg}")

    return output_path


if __name__ == "__main__":
    fetch_pois()
