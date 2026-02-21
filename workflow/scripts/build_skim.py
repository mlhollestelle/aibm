"""Build an all-pairs travel-time skim matrix for Walcheren.

Loads a GraphML network and the zone grid, computes shortest-path
travel times from every zone centroid, and writes the result as an
OMX file.

Usage:
    uv run python workflow/scripts/build_skim.py --mode car
    uv run python workflow/scripts/build_skim.py --mode bike
"""

import argparse
import re
from pathlib import Path

import networkx as nx
import numpy as np
import openmatrix as omx
import osmnx as ox
import pandas as pd
import tables

NETWORK_TEMPLATE = "data/processed/walcheren_network_{mode}.graphml"
GRID = Path("data/processed/walcheren_grid_clean.parquet")
OUTPUT_TEMPLATE = "data/processed/walcheren_skim_{mode}.omx"

UNREACHABLE = 999.0

# Default speed limits (km/h) by OSM highway tag for car mode.
HIGHWAY_SPEED_DEFAULTS: dict[str, float] = {
    "motorway": 100,
    "motorway_link": 60,
    "trunk": 80,
    "trunk_link": 50,
    "primary": 80,
    "primary_link": 50,
    "secondary": 70,
    "secondary_link": 50,
    "tertiary": 50,
    "tertiary_link": 30,
    "residential": 30,
    "living_street": 15,
    "unclassified": 50,
    "service": 20,
}
DEFAULT_CAR_SPEED = 30.0  # km/h fallback
BIKE_SPEED = 18.0  # km/h flat terrain

# Pattern to extract a numeric speed from OSM maxspeed tag.
_SPEED_RE = re.compile(r"(\d+)")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Build travel-time skim matrix.",
    )
    parser.add_argument(
        "--mode",
        choices=["car", "bike"],
        required=True,
        help="Transport mode (car or bike).",
    )
    return parser.parse_args()


def _parse_maxspeed(value: str | list[str]) -> float | None:
    """Extract a numeric km/h value from an OSM maxspeed tag.

    Returns None if the value cannot be parsed.
    """
    if isinstance(value, list):
        value = value[0]
    match = _SPEED_RE.search(str(value))
    if match:
        return float(match.group(1))
    return None


def _get_highway_type(value: str | list[str]) -> str:
    """Return a single highway type string."""
    if isinstance(value, list):
        return value[0]
    return value


def _add_travel_time_car(graph: nx.MultiDiGraph) -> None:
    """Add ``travel_time_min`` edge attribute for car mode."""
    for _, _, data in graph.edges(data=True):
        length_km = data["length"] / 1000.0

        speed: float | None = None
        maxspeed = data.get("maxspeed")
        if maxspeed is not None:
            speed = _parse_maxspeed(maxspeed)

        if speed is None:
            highway = data.get("highway", "")
            hw_type = _get_highway_type(highway)
            speed = HIGHWAY_SPEED_DEFAULTS.get(hw_type, DEFAULT_CAR_SPEED)

        data["travel_time_min"] = (length_km / speed) * 60.0


def _add_travel_time_bike(graph: nx.MultiDiGraph) -> None:
    """Add ``travel_time_min`` edge attribute for bike mode."""
    for _, _, data in graph.edges(data=True):
        length_km = data["length"] / 1000.0
        data["travel_time_min"] = (length_km / BIKE_SPEED) * 60.0


def _centroids_from_zone_ids(
    zone_ids: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Derive cell centre coordinates from CBS zone_id strings.

    Zone IDs have the format ``E{XXXX}N{YYYY}`` where the numbers
    are hectometre indices (100 m cells, EPSG:28992).

    Returns (eastings, northings) arrays in EPSG:28992.
    """
    pattern = re.compile(r"E(\d+)N(\d+)")
    eastings = np.empty(len(zone_ids))
    northings = np.empty(len(zone_ids))

    for i, zid in enumerate(zone_ids):
        m = pattern.match(zid)
        if m is None:
            raise ValueError(f"Cannot parse zone_id: {zid}")
        eastings[i] = int(m.group(1)) * 100 + 50
        northings[i] = int(m.group(2)) * 100 + 50

    return eastings, northings


def build_skim(mode: str) -> Path:
    """Compute skim matrix and write OMX file."""
    # Load network and add travel times.
    network_path = Path(NETWORK_TEMPLATE.format(mode=mode))
    graph = ox.load_graphml(network_path)

    if mode == "car":
        _add_travel_time_car(graph)
    else:
        _add_travel_time_bike(graph)

    # Project to EPSG:28992 so nearest_nodes uses a KD-tree (no scikit-learn).
    graph = ox.project_graph(graph, to_crs="EPSG:28992")

    # Load zones, sorted for consistent ordering.
    grid = pd.read_parquet(GRID)
    zone_ids: list[str] = sorted(grid["zone_id"].tolist())
    n_zones = len(zone_ids)
    print(f"Loaded {n_zones} zones")

    # Snap zone centroids to nearest network nodes.
    eastings, northings = _centroids_from_zone_ids(zone_ids)
    nearest_nodes = ox.nearest_nodes(graph, eastings, northings)

    # Build lookup: node -> list of zone indices.
    node_to_zones: dict[int, list[int]] = {}
    for i, node in enumerate(nearest_nodes):
        node_to_zones.setdefault(node, []).append(i)

    unique_nodes = list(node_to_zones.keys())
    print(f"Snapped to {len(unique_nodes)} unique network nodes")

    # Compute shortest paths from each unique origin node.
    matrix = np.full((n_zones, n_zones), UNREACHABLE, dtype=np.float64)

    for count, origin_node in enumerate(unique_nodes, 1):
        if count % 100 == 0 or count == len(unique_nodes):
            print(
                f"  Dijkstra {count}/{len(unique_nodes)}",
                flush=True,
            )

        costs = nx.single_source_dijkstra_path_length(
            graph, origin_node, weight="travel_time_min"
        )

        origin_indices = node_to_zones[origin_node]
        for dest_node, dest_indices in node_to_zones.items():
            if dest_node in costs:
                tt = costs[dest_node]
                for oi in origin_indices:
                    for di in dest_indices:
                        matrix[oi, di] = tt

    # Diagonal = 0 (intra-zone travel time).
    np.fill_diagonal(matrix, 0.0)

    # Write OMX.
    output = Path(OUTPUT_TEMPLATE.format(mode=mode))
    output.parent.mkdir(parents=True, exist_ok=True)

    with omx.open_file(str(output), "w") as f:
        f["travel_time_min"] = matrix
        # create_mapping only supports UInt32; write strings via PyTables.
        if "lookup" not in f.root:
            f.create_group(f.root, "lookup")
        max_len = max(len(z) for z in zone_ids)
        atom = tables.StringAtom(itemsize=max_len)
        arr = f.create_array(
            f.root.lookup, "zone_id", atom=atom, shape=(len(zone_ids),)
        )
        arr[:] = np.array(zone_ids, dtype=f"S{max_len}")

    n_unreachable = int(np.sum(matrix == UNREACHABLE))
    pct = n_unreachable / (n_zones * n_zones) * 100
    mean_tt = np.mean(matrix[matrix < UNREACHABLE])
    print(f"Wrote {output}  shape={matrix.shape}")
    print(f"  mean travel time: {mean_tt:.1f} min")
    print(f"  unreachable pairs: {n_unreachable} ({pct:.1f}%)")
    return output


if __name__ == "__main__":
    args = parse_args()
    build_skim(args.mode)
