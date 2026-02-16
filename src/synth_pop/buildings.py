from __future__ import annotations

import geopandas as gpd
import osmnx as ox
from shapely.geometry import MultiPolygon, Polygon


def fetch_residential_buildings(place: str) -> gpd.GeoDataFrame:
    """Fetch residential building footprints from OpenStreetMap for a place.

    Parameters
    ----------
    place:
        Nominatim query string, e.g. "Veere, Zeeland, Netherlands".

    Returns
    -------
    gpd.GeoDataFrame
        Columns: osmid, geometry (Polygon/MultiPolygon), centroid_x, centroid_y.
        CRS: EPSG:28992 (Dutch RD New).
    """
    tags = {"building": ["residential", "house", "apartments"]}
    gdf = ox.features_from_place(place, tags=tags)

    # Keep only polygon geometries (buildings are areas, not points/lines)
    mask = gdf.geometry.apply(lambda g: isinstance(g, Polygon | MultiPolygon))
    gdf = gdf[mask].copy()

    # Reproject to Dutch RD New (metric coordinates)
    gdf = gdf.to_crs(epsg=28992)

    # Add centroid columns
    centroids = gdf.geometry.centroid
    gdf["centroid_x"] = centroids.x
    gdf["centroid_y"] = centroids.y

    # Make osmid a regular column instead of the index.
    # osmnx 2.x uses a MultiIndex with levels ('element', 'id'); rename 'id' to 'osmid'.
    gdf = gdf.reset_index()
    if "id" in gdf.columns and "osmid" not in gdf.columns:
        gdf = gdf.rename(columns={"id": "osmid"})

    return gdf[["osmid", "geometry", "centroid_x", "centroid_y"]]
