"""POI — a Point of Interest that can serve as a destination."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class POI:
    """A Point of Interest from OpenStreetMap.

    POIs are specific locations (shops, schools, restaurants …) that
    agents can choose as destinations for their activities.

    Attributes:
        id: Unique identifier (typically the OSM id as a string).
        name: Human-readable name (e.g. ``"Albert Heijn"``).
        x: Projected x-coordinate (e.g. RD New / EPSG:28992).
        y: Projected y-coordinate.
        activity_type: The activity type this POI serves, matching
            one of :data:`aibm.activity.VALID_OUT_OF_HOME_TYPES`
            (e.g. ``"shopping"``, ``"leisure"``).
        zone_id: Grid zone id the POI falls in (set by
            ``fetch_pois.py``).  ``None`` when not available.
    """

    id: str
    name: str
    x: float
    y: float
    activity_type: str
    zone_id: str | None = None


def load_pois(path: str | Path) -> list[POI]:
    """Read POIs from a GeoParquet file.

    The file must contain columns ``osmid``, ``name``,
    ``activity_type``, and a point ``geometry`` column.

    Args:
        path: Path to the GeoParquet file produced by
            ``workflow/scripts/fetch_pois.py``.

    Returns:
        A list of :class:`POI` objects.

    Raises:
        FileNotFoundError: If *path* does not exist.
        ValueError: If required columns are missing.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"POI file not found: {path}")

    import geopandas as gpd  # type: ignore[import-untyped]

    gdf = gpd.read_parquet(path)

    required = {"osmid", "name", "activity_type", "geometry"}
    missing = required - set(gdf.columns)
    if missing:
        raise ValueError(f"Missing columns in POI file: {sorted(missing)}")

    has_zone_id = "zone_id" in gdf.columns

    def _is_na(val: object) -> bool:
        """Check for NaN/None without importing pandas at top level."""
        return val is None or (isinstance(val, float) and val != val)

    pois: list[POI] = []
    for _, row in gdf.iterrows():
        zid: str | None = None
        if has_zone_id and not _is_na(row["zone_id"]):
            zid = str(row["zone_id"])
        name = row["name"]
        pois.append(
            POI(
                id=str(row["osmid"]),
                name="" if _is_na(name) else str(name),
                x=float(row.geometry.x),
                y=float(row.geometry.y),
                activity_type=str(row["activity_type"]),
                zone_id=zid,
            )
        )
    return pois


def filter_pois(
    pois: list[POI],
    activity_type: str,
) -> list[POI]:
    """Return only POIs that match a given activity type.

    Args:
        pois: The full list of POIs.
        activity_type: Activity type to keep
            (e.g. ``"shopping"``).

    Returns:
        Filtered list of POIs.
    """
    return [p for p in pois if p.activity_type == activity_type]
