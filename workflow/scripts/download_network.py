"""Download an OSMnx routable network for the study area.

Reads municipality boundaries, merges them into a single polygon,
and downloads the OSM street network clipped to that area.

Usage:
    uv run python workflow/scripts/download_network.py --mode car
    uv run python workflow/scripts/download_network.py --mode bike
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# isort: split

import geopandas as gpd
import osmnx as ox
from _config import load_config

MODE_TO_NETWORK_TYPE = {
    "car": "drive",
    "bike": "bike",
    "walk": "walk",
}


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Download OSM network for study area.",
    )
    parser.add_argument(
        "--mode",
        choices=["car", "bike", "walk"],
        required=True,
        help="Transport mode (car, bike, or walk).",
    )
    return parser.parse_known_args()[0]


def download_network(
    mode: str,
    boundaries: Path,
    output: Path,
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

    output.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(graph, filepath=output)

    n_nodes = graph.number_of_nodes()
    n_edges = graph.number_of_edges()
    print(f"Saved {mode} network ({n_nodes} nodes, {n_edges} edges) to {output}")
    return output


if __name__ == "__main__":
    args = parse_args()
    cfg = load_config()
    name = cfg["study_area"]["name"]
    download_network(
        mode=args.mode,
        boundaries=Path(f"data/raw/{name}_gemeenten.geojson"),
        output=Path(f"data/processed/{name}_network_{args.mode}.graphml"),
    )
