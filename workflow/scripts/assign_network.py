"""All-or-nothing network assignment for simulated trips.

Finds the shortest-path route for each trip and counts how many
trips use each network edge.

Usage:
    uv run python workflow/scripts/assign_network.py
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# isort: split

import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from _config import load_config

_ZONE_RE = re.compile(r"E(\d+)N(\d+)")
_SPEED_RE = re.compile(r"(\d+)")


def _parse_maxspeed(value: str | list[str]) -> float | None:
    """Extract a numeric km/h value from an OSM maxspeed tag."""
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


def _add_travel_time_car(
    graph: nx.MultiDiGraph,
    highway_speeds: dict[str, float],
    default_speed: float,
) -> None:
    """Add ``travel_time_min`` edge attribute for car mode."""
    for _, _, data in graph.edges(data=True):
        length_km = data["length"] / 1000.0
        speed: float | None = None
        maxspeed = data.get("maxspeed")
        if maxspeed is not None:
            speed = _parse_maxspeed(maxspeed)
        if speed is None:
            hw_type = _get_highway_type(data.get("highway", ""))
            speed = highway_speeds.get(hw_type, default_speed)
        data["travel_time_min"] = (length_km / speed) * 60.0


def _add_travel_time_bike(
    graph: nx.MultiDiGraph,
    bike_speed: float,
) -> None:
    """Add ``travel_time_min`` edge attribute for bike mode."""
    for _, _, data in graph.edges(data=True):
        length_km = data["length"] / 1000.0
        data["travel_time_min"] = (length_km / bike_speed) * 60.0


def _centroids_from_zone_ids(
    zone_ids: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Derive centroid coordinates (EPSG:28992) from zone_id strings."""
    eastings = np.empty(len(zone_ids))
    northings = np.empty(len(zone_ids))
    for i, zid in enumerate(zone_ids):
        m = _ZONE_RE.match(zid)
        if m is None:
            raise ValueError(f"Cannot parse zone_id: {zid}")
        eastings[i] = int(m.group(1)) * 100 + 50
        northings[i] = int(m.group(2)) * 100 + 50
    return eastings, northings


def _is_zone_id(loc: str) -> bool:
    """Return True if *loc* matches the E{X}N{Y} zone id pattern."""
    return _ZONE_RE.match(loc) is not None


def assign_network(cfg: dict) -> Path:
    """Run assignment and write flow parquet."""
    name = cfg["study_area"]["name"]
    net_cfg = cfg["network"]
    highway_speeds = {k: float(v) for k, v in net_cfg["highway_speeds"].items()}
    default_car_speed = float(net_cfg["default_car_speed_kmh"])
    bike_speed = float(net_cfg["bike_speed_kmh"])

    trips = pd.read_parquet(f"data/processed/{name}_trips.parquet")

    mode_graphs: dict[str, nx.MultiDiGraph] = {}
    for mode in ("car", "bike"):
        gpath = Path(f"data/processed/{name}_network_{mode}.graphml")
        g = ox.load_graphml(gpath)
        if mode == "car":
            _add_travel_time_car(g, highway_speeds, default_car_speed)
        else:
            _add_travel_time_bike(g, bike_speed)
        mode_graphs[mode] = ox.project_graph(g, to_crs="EPSG:28992")

    # flow[(mode, u, v)] -> count
    flow: dict[tuple[str, int, int], int] = defaultdict(int)

    for mode, graph in mode_graphs.items():
        mode_trips = trips[trips["mode"] == mode]
        if mode_trips.empty:
            continue

        # Collect unique zone ids that appear as origin or destination.
        all_locs = set(mode_trips["origin"].tolist()) | set(
            mode_trips["destination"].tolist()
        )
        zone_locs = [loc for loc in all_locs if _is_zone_id(loc)]
        if not zone_locs:
            continue

        eastings, northings = _centroids_from_zone_ids(zone_locs)
        nearest = ox.nearest_nodes(graph, eastings, northings)
        zone_to_node: dict[str, int] = dict(zip(zone_locs, nearest))

        for _, row in mode_trips.iterrows():
            origin = str(row["origin"])
            dest = str(row["destination"])
            if origin not in zone_to_node or dest not in zone_to_node:
                continue
            o_node = zone_to_node[origin]
            d_node = zone_to_node[dest]
            if o_node == d_node:
                continue
            try:
                path = nx.shortest_path(graph, o_node, d_node, weight="travel_time_min")
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue

            for u, v in zip(path[:-1], path[1:]):
                flow[(mode, u, v)] += 1

    rows = [
        {"mode": mode, "u": u, "v": v, "flow": count}
        for (mode, u, v), count in flow.items()
        if count > 0
    ]
    result = pd.DataFrame(rows)

    output = Path(f"data/processed/{name}_assigned_trips.parquet")
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(output, index=False)

    print(f"Wrote {len(result)} loaded edges to {output}")
    return output


if __name__ == "__main__":
    assign_network(load_config())
