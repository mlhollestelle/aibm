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
OUTPUT = Path("data/processed/walcheren_pois.parquet")

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
) -> Path:
    """Download POIs for every activity type and save as Parquet.

    Parameters
    ----------
    boundaries_path:
        GeoJSON with Walcheren municipality polygons (EPSG:28992).
    output_path:
        Destination GeoParquet file.

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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(output_path)
    print(f"Saved to {output_path}")
    return output_path


if __name__ == "__main__":
    fetch_pois()
