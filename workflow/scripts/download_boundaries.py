"""Download Walcheren municipality boundaries from PDOK WFS.

Fetches polygons for Middelburg (GM0687), Veere (GM0717), and
Vlissingen (GM0718) and saves them as GeoJSON.
"""

from pathlib import Path

import geopandas as gpd
import requests

WFS_BASE = "https://service.pdok.nl/cbs/gebiedsindelingen/2024/wfs/v1_0"
LAYER = "gebiedsindelingen:gemeente_gegeneraliseerd"
WALCHEREN_CODES = ["GM0687", "GM0717", "GM0718"]

OUTPUT = Path("data/raw/walcheren_gemeenten.geojson")

# OGC XML filter to select the three municipalities
_XML_FILTER = (
    '<Filter xmlns="http://www.opengis.net/ogc"><Or>'
    "<PropertyIsEqualTo>"
    "<PropertyName>statcode</PropertyName>"
    "<Literal>GM0687</Literal>"
    "</PropertyIsEqualTo>"
    "<PropertyIsEqualTo>"
    "<PropertyName>statcode</PropertyName>"
    "<Literal>GM0717</Literal>"
    "</PropertyIsEqualTo>"
    "<PropertyIsEqualTo>"
    "<PropertyName>statcode</PropertyName>"
    "<Literal>GM0718</Literal>"
    "</PropertyIsEqualTo>"
    "</Or></Filter>"
)


def download_boundaries(output: Path = OUTPUT) -> Path:
    """Download and filter municipality boundaries."""
    resp = requests.get(
        WFS_BASE,
        params={
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": LAYER,
            "outputFormat": "json",
            "srsName": "EPSG:28992",
            "Filter": _XML_FILTER,
        },
        timeout=60,
    )
    resp.raise_for_status()

    gdf = gpd.GeoDataFrame.from_features(resp.json()["features"], crs="EPSG:28992")

    if len(gdf) != len(WALCHEREN_CODES):
        found = gdf["statcode"].tolist()
        raise ValueError(f"Expected {WALCHEREN_CODES}, got {found}")

    output.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(output, driver="GeoJSON")
    print(f"Saved {len(gdf)} municipalities to {output}")
    return output


if __name__ == "__main__":
    download_boundaries()
