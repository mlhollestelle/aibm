"""Download municipality boundaries from PDOK WFS.

Fetches polygons for the configured municipalities and saves them
as GeoJSON.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# isort: split

import geopandas as gpd
import requests
from _config import load_config


def _build_xml_filter(codes: list[str]) -> str:
    """Build an OGC XML filter that matches any of the given statcodes."""
    equals = "".join(
        "<PropertyIsEqualTo>"
        "<PropertyName>statcode</PropertyName>"
        f"<Literal>{code}</Literal>"
        "</PropertyIsEqualTo>"
        for code in codes
    )
    return f'<Filter xmlns="http://www.opengis.net/ogc"><Or>{equals}</Or></Filter>'


def download_boundaries(output: Path, cfg: dict) -> Path:
    """Download and filter municipality boundaries."""
    b = cfg["boundaries"]
    codes: list[str] = b["municipality_codes"]

    resp = requests.get(
        b["wfs_url"],
        params={
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": b["wfs_layer"],
            "outputFormat": "json",
            "srsName": "EPSG:28992",
            "Filter": _build_xml_filter(codes),
        },
        timeout=60,
    )
    resp.raise_for_status()

    gdf = gpd.GeoDataFrame.from_features(resp.json()["features"], crs="EPSG:28992")

    if len(gdf) != len(codes):
        found = gdf["statcode"].tolist()
        raise ValueError(f"Expected {codes}, got {found}")

    output.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(output, driver="GeoJSON")
    print(f"Saved {len(gdf)} municipalities to {output}")
    return output


if __name__ == "__main__":
    cfg = load_config()
    name = cfg["study_area"]["name"]
    download_boundaries(Path(f"data/raw/{name}_gemeenten.geojson"), cfg)
