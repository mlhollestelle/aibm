"""Export OSM network nodes and edges to GeoParquet.

Reads a GraphML network produced by download_network.py and
exports its nodes and edges as separate GeoParquet files,
suitable for visualisation and validation.

Usage:
    uv run python workflow/scripts/export_network.py --mode car
    uv run python workflow/scripts/export_network.py --mode bike
"""

import argparse
from pathlib import Path

import geopandas as gpd
import osmnx as ox

NETWORK_TEMPLATE = "data/processed/walcheren_network_{mode}.graphml"
NODES_TEMPLATE = "data/processed/walcheren_network_{mode}_nodes.parquet"
EDGES_TEMPLATE = "data/processed/walcheren_network_{mode}_edges.parquet"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Export OSM network to GeoParquet.",
    )
    parser.add_argument(
        "--mode",
        choices=["car", "bike"],
        required=True,
        help="Transport mode (car or bike).",
    )
    return parser.parse_args()


def coerce_list_columns(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Convert list-valued columns to pipe-joined strings.

    OSMnx may store multi-valued attributes (e.g. a road that
    belongs to two highway categories) as Python lists.  Parquet
    requires a consistent dtype per column, so these values are
    stringified with ``|`` as the separator.
    """
    gdf = gdf.copy()
    for col in gdf.columns:
        if col == "geometry":
            continue
        if gdf[col].apply(lambda x: isinstance(x, list)).any():
            gdf[col] = gdf[col].apply(
                lambda x: "|".join(str(v) for v in x) if isinstance(x, list) else str(x)
            )
    return gdf


def export_network(mode: str) -> tuple[Path, Path]:
    """Export network nodes and edges as GeoParquet.

    Loads the GraphML file for *mode*, extracts nodes and edges
    via :func:`osmnx.graph_to_gdfs`, coerces any list-valued
    columns to strings, resets the index so all identifiers
    become plain columns, and writes two GeoParquet files.

    Returns a ``(nodes_path, edges_path)`` tuple.
    """
    network_path = Path(NETWORK_TEMPLATE.format(mode=mode))
    graph = ox.load_graphml(network_path)

    nodes, edges = ox.graph_to_gdfs(graph)

    # Reset indices so osmid / (u, v, key) become regular columns,
    # which makes the files easier to use in downstream tools.
    nodes = nodes.reset_index()
    edges = edges.reset_index()

    nodes = coerce_list_columns(nodes)
    edges = coerce_list_columns(edges)

    nodes_out = Path(NODES_TEMPLATE.format(mode=mode))
    edges_out = Path(EDGES_TEMPLATE.format(mode=mode))
    nodes_out.parent.mkdir(parents=True, exist_ok=True)

    nodes.to_parquet(nodes_out)
    edges.to_parquet(edges_out)

    nodes.to_file(nodes_out.with_suffix(".gpkg"), driver="GPKG")
    edges.to_file(edges_out.with_suffix(".gpkg"), driver="GPKG")

    print(f"Saved {mode} network: {len(nodes)} nodes to {nodes_out}")
    print(f"Saved {mode} network: {len(edges)} edges to {edges_out}")
    return nodes_out, edges_out


if __name__ == "__main__":
    args = parse_args()
    export_network(args.mode)
