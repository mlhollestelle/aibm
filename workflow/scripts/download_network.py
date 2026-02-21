"""Download an OSMnx routable network for Walcheren.

Reads municipality boundaries, merges them into a single polygon,
and downloads the OSM street network clipped to that area.

Usage:
    uv run python workflow/scripts/download_network.py --mode car
    uv run python workflow/scripts/download_network.py --mode bike
"""

import argparse
from pathlib import Path

import geopandas as gpd
import osmnx as ox

BOUNDARIES = Path("data/raw/walcheren_gemeenten.geojson")
OUTPUT_TEMPLATE = "data/processed/walcheren_network_{mode}.graphml"

MODE_TO_NETWORK_TYPE = {
    "car": "drive",
    "bike": "bike",
}


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Download OSM network for Walcheren.",
    )
    parser.add_argument(
        "--mode",
        choices=["car", "bike"],
        required=True,
        help="Transport mode (car or bike).",
    )
    return parser.parse_args()


def download_network(
    mode: str,
    boundaries: Path = BOUNDARIES,
) -> Path:
    """Download and save a routable network for *mode*."""
    gdf = gpd.read_file(boundaries).to_crs(epsg=4326)
    polygon = gdf.union_all()

    network_type = MODE_TO_NETWORK_TYPE[mode]
    graph = ox.graph_from_polygon(
        polygon,
        network_type=network_type,
        simplify=True,
    )

    output = Path(OUTPUT_TEMPLATE.format(mode=mode))
    output.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(graph, filepath=output)

    n_nodes = graph.number_of_nodes()
    n_edges = graph.number_of_edges()
    print(f"Saved {mode} network ({n_nodes} nodes, {n_edges} edges) to {output}")
    return output


if __name__ == "__main__":
    args = parse_args()
    download_network(args.mode)
