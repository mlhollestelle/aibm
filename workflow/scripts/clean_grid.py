"""Clean CBS grid data for population synthesis.

Handles CBS anonymisation codes, remaps age groups to ZoneSpec
brackets, derives household size distributions, and adds a
``buurt_name`` column from the CBS PDOK WFS.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# isort: split

import geopandas as gpd
import pandas as pd
import requests
from _config import load_config

INPUT = Path("data/processed/walcheren_grid_raw.parquet")
OUTPUT = Path("data/processed/walcheren_grid_clean.parquet")


def _fetch_buurten(
    wfs_url: str,
    bbox: tuple[int, int, int, int],
) -> gpd.GeoDataFrame:
    """Fetch buurt boundaries from the CBS PDOK WFS for the study area."""
    minx, miny, maxx, maxy = bbox
    resp = requests.get(
        wfs_url,
        params={
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": "gebiedsindelingen:buurt_gegeneraliseerd",
            "outputFormat": "json",
            "srsName": "EPSG:28992",
            "bbox": (f"{minx},{miny},{maxx},{maxy},urn:ogc:def:crs:EPSG::28992"),
        },
        timeout=60,
    )
    resp.raise_for_status()
    return gpd.GeoDataFrame.from_features(resp.json()["features"], crs="EPSG:28992")


def _add_buurt_names(
    gdf: gpd.GeoDataFrame,
    buurten: gpd.GeoDataFrame,
    name_col: str = "statnaam",
) -> gpd.GeoDataFrame:
    """Add ``buurt_name`` column via centroid spatial join with buurt polygons.

    Each grid cell centroid is matched to the buurt polygon it falls
    within.  Cells with no match keep their ``zone_id`` as a fallback.
    """
    centroids = gpd.GeoDataFrame(
        {"zone_id": gdf["zone_id"]},
        geometry=gdf.geometry.centroid,
        crs=gdf.crs,
    )
    joined = gpd.sjoin(
        centroids,
        buurten[[name_col, "geometry"]],
        how="left",
        predicate="within",
    )
    # Guard against duplicates if a centroid touches two polygons
    joined = joined[~joined.index.duplicated(keep="first")]
    gdf = gdf.copy()
    gdf["buurt_name"] = joined[name_col].fillna(gdf["zone_id"]).values
    return gdf


def clean_grid(
    input_path: Path = INPUT,
    output_path: Path = OUTPUT,
    wfs_url: str | None = None,
    bbox: tuple[int, int, int, int] | None = None,
) -> Path:
    """Clean raw grid and prepare columns for ZoneSpec."""
    gdf = gpd.read_parquet(input_path)
    geometry = gdf.geometry  # save before drop
    df = pd.DataFrame(gdf.drop(columns="geometry"))

    # --- Handle CBS anonymisation codes ---
    # -99997 means "value suppressed, 0-4 range" -> use 2
    # -99995 means "not applicable" -> NaN
    numeric_cols = df.select_dtypes(include="number").columns
    df[numeric_cols] = df[numeric_cols].replace(-99997, 2)
    df[numeric_cols] = df[numeric_cols].replace(-99995, pd.NA)

    # --- Remap CBS age groups to ZoneSpec brackets ---
    # CBS: 0-14, 15-24, 25-44, 45-64, 65+
    # ZoneSpec: 0-17, 18-64, 65+
    pop_0_15 = df["aantal_inwoners_0_tot_15_jaar"]
    pop_15_25 = df["aantal_inwoners_15_tot_25_jaar"]
    pop_25_45 = df["aantal_inwoners_25_tot_45_jaar"]
    pop_45_65 = df["aantal_inwoners_45_tot_65_jaar"]
    pop_65_plus = df["aantal_inwoners_65_jaar_en_ouder"]

    # Approximate split: 2/10 of the 15-24 bracket is 15-17
    raw_0_17 = pop_0_15 + (2 / 10) * pop_15_25
    raw_18_64 = (8 / 10) * pop_15_25 + pop_25_45 + pop_45_65
    raw_65_plus = pop_65_plus

    age_total = raw_0_17 + raw_18_64 + raw_65_plus
    # Avoid division by zero for empty cells
    age_total = age_total.replace(0, pd.NA)

    # --- Household size distribution ---
    hh_1 = df["aantal_eenpersoonshuishoudens"]
    hh_2 = df["aantal_meerpersoonshuishoudens_zonder_kind"]
    hh_3 = df["aantal_eenouderhuishoudens"]
    hh_4 = df["aantal_tweeouderhuishoudens"]

    hh_total = hh_1 + hh_2 + hh_3 + hh_4
    hh_total = hh_total.replace(0, pd.NA)

    # Build new columns as a single DataFrame to avoid
    # fragmentation warnings from repeated insert
    new_cols = pd.DataFrame(
        {
            "zone_id": df["crs28992res100m"],
            "n_households": df["aantal_part_huishoudens"],
            "p_0_17": raw_0_17 / age_total,
            "p_18_64": raw_18_64 / age_total,
            "p_65_plus": raw_65_plus / age_total,
            "hh_size_1": hh_1 / hh_total,
            "hh_size_2": hh_2 / hh_total,
            "hh_size_3": hh_3 / hh_total,
            "hh_size_4": hh_4 / hh_total,
        },
        index=df.index,
    )
    df = new_cols

    # Drop rows with no households or missing data
    df = df.dropna()
    df["n_households"] = df["n_households"].astype(int)
    df = df[df["n_households"] > 0]

    print(f"Cleaned data: {len(df)} zones")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = gpd.GeoDataFrame(df, geometry=geometry.loc[df.index], crs=gdf.crs)

    # Add buurt name per grid cell via spatial join with CBS WFS
    if wfs_url and bbox:
        try:
            buurten = _fetch_buurten(wfs_url, bbox)
            result = _add_buurt_names(result, buurten)
            n_named = (result["buurt_name"] != result["zone_id"]).sum()
            print(f"Added buurt names: {n_named} zones matched")
        except Exception as exc:
            print(f"Warning: buurt fetch failed ({exc}), using zone IDs")
            result["buurt_name"] = result["zone_id"]
    else:
        result["buurt_name"] = result["zone_id"]

    result.to_parquet(output_path, index=False)
    print(f"Saved to {output_path}")

    gpkg_path = output_path.with_suffix(".gpkg")
    result.to_file(gpkg_path, driver="GPKG")
    print(f"Saved to {gpkg_path}")

    return output_path


if __name__ == "__main__":
    cfg = load_config()
    clean_grid(
        wfs_url=cfg["boundaries"]["wfs_url"],
        bbox=tuple(int(v) for v in cfg["grid"]["bbox"]),  # type: ignore[arg-type]
    )
