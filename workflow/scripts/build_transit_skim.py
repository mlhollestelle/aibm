"""Build a zone-level transit travel-time skim matrix.

Uses the pedestrian network for walk access and egress to the nearest
transit stop, combined with shortest stop-to-stop transit times.

Total time = walk_to_stop + avg_wait + transit_stop_to_stop + walk_from_stop

Usage:
    uv run python workflow/scripts/build_transit_skim.py
"""

import argparse
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# isort: split

import networkx as nx
import numpy as np
import openmatrix as omx
import osmnx as ox
import pandas as pd
import tables
from _config import load_config
from pyproj import Transformer

_ZONE_RE = re.compile(r"E(\d+)N(\d+)")


def _centroids_from_zone_ids(
    zone_ids: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Derive cell-centre coordinates (EPSG:28992) from CBS zone_id strings."""
    eastings = np.empty(len(zone_ids))
    northings = np.empty(len(zone_ids))
    for i, zid in enumerate(zone_ids):
        m = _ZONE_RE.match(zid)
        if m is None:
            raise ValueError(f"Cannot parse zone_id: {zid}")
        eastings[i] = int(m.group(1)) * 100 + 50
        northings[i] = int(m.group(2)) * 100 + 50
    return eastings, northings


def _add_travel_time_walk(graph: nx.MultiDiGraph, walk_speed: float) -> None:
    """Add ``travel_time_min`` edge attribute based on constant walk speed."""
    for _, _, data in graph.edges(data=True):
        length_km = data["length"] / 1000.0
        data["travel_time_min"] = (length_km / walk_speed) * 60.0


def _snap_stops_to_walk_graph(
    stops: dict[str, tuple[float, float]],
    walk_graph: nx.MultiDiGraph,
    active_stop_ids: set[str],
) -> dict[int, list[str]]:
    """Snap transit stop WGS84 coordinates to walk network nodes.

    Only snaps stops that are active (have at least one edge in the transit
    graph), so that zones are never routed to an isolated stop node.

    Returns a mapping walk_node_id -> list of stop_ids that snap to it.
    """
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:28992", always_xy=True)
    stop_ids = [s for s in stops if s in active_stop_ids]
    if not stop_ids:
        return {}
    stop_lats = np.array([stops[s][0] for s in stop_ids])
    stop_lons = np.array([stops[s][1] for s in stop_ids])
    eastings, northings = transformer.transform(stop_lons, stop_lats)
    walk_nodes = ox.nearest_nodes(walk_graph, eastings, northings)

    walknode_to_stops: dict[int, list[str]] = {}
    for stop_id, wnode in zip(stop_ids, walk_nodes):
        walknode_to_stops.setdefault(int(wnode), []).append(stop_id)
    return walknode_to_stops


def _compute_zone_access(
    unique_zone_nodes: list[int],
    node_to_zones: dict[int, list[int]],
    walk_graph: nx.MultiDiGraph,
    walknode_to_stops: dict[int, list[str]],
    n_zones: int,
) -> list[tuple[str, float] | None]:
    """Return per-zone (nearest_stop_id, walk_time_min) via the walk network.

    Runs Dijkstra from each unique zone walk node and picks the transit
    stop walk-node with the lowest travel time.
    """
    stop_node_set = set(walknode_to_stops.keys())
    zone_access: list[tuple[str, float] | None] = [None] * n_zones

    for count, origin_node in enumerate(unique_zone_nodes, 1):
        if count % 100 == 0 or count == len(unique_zone_nodes):
            print(f"  Dijkstra {count}/{len(unique_zone_nodes)}", flush=True)

        costs = nx.single_source_dijkstra_path_length(
            walk_graph, origin_node, weight="travel_time_min"
        )

        best_stop: str | None = None
        best_tt = math.inf
        for wnode, tt in costs.items():
            if wnode in stop_node_set and tt < best_tt:
                best_tt = tt
                best_stop = walknode_to_stops[wnode][0]

        access = (best_stop, best_tt) if best_stop is not None else None
        for zi in node_to_zones[origin_node]:
            zone_access[zi] = access

    return zone_access


def build_transit_skim(cfg: dict) -> Path:
    """Compute zone-level transit skim using the walk network and write OMX."""
    name = cfg["study_area"]["name"]
    transit_cfg = cfg.get("transit", {})
    walk_speed = float(transit_cfg.get("walk_speed_kmh", 5.0))
    avg_wait_min = float(transit_cfg.get("avg_wait_min", 10.0))
    unreachable = float(cfg["network"]["unreachable"])

    # Load and prepare walk network.
    walk_path = Path(f"data/processed/{name}_network_walk.graphml")
    walk_graph = ox.load_graphml(walk_path)
    _add_travel_time_walk(walk_graph, walk_speed)
    walk_graph = ox.project_graph(walk_graph, to_crs="EPSG:28992")

    # Load zones.
    grid = pd.read_parquet(f"data/processed/{name}_grid_clean.parquet")
    zone_ids: list[str] = sorted(grid["zone_id"].tolist())
    n_zones = len(zone_ids)

    # Load transit stop graph.
    stop_graph_path = Path(f"data/processed/{name}_transit_stops.graphml")
    stop_graph: nx.DiGraph = nx.read_graphml(str(stop_graph_path))

    stops: dict[str, tuple[float, float]] = {}
    for nid, data in stop_graph.nodes(data=True):
        lat = float(data.get("lat", data.get("y", 0)))
        lon = float(data.get("lon", data.get("x", 0)))
        stops[str(nid)] = (lat, lon)

    print(f"Loaded {n_zones} zones, {len(stops)} transit stops")

    if not stops:
        print("Warning: no transit stops — writing all-unreachable skim")
        matrix = np.full((n_zones, n_zones), unreachable, dtype=np.float64)
        np.fill_diagonal(matrix, 0.0)
        output = Path(f"data/processed/{name}_skim_transit.omx")
        output.parent.mkdir(parents=True, exist_ok=True)
        _write_omx(output, matrix, zone_ids)
        return output

    # Snap zone centroids to walk network nodes.
    eastings, northings = _centroids_from_zone_ids(zone_ids)
    zone_walk_nodes = ox.nearest_nodes(walk_graph, eastings, northings)

    node_to_zones: dict[int, list[int]] = {}
    for i, node in enumerate(zone_walk_nodes):
        node_to_zones.setdefault(int(node), []).append(i)

    # Only snap stops that participate in at least one route (have edges).
    active_stop_ids = {str(u) for u, v in stop_graph.edges()} | {
        str(v) for u, v in stop_graph.edges()
    }
    print(f"  {len(active_stop_ids)} active stops (part of a route)")

    # Snap transit stops to walk network nodes.
    walknode_to_stops = _snap_stops_to_walk_graph(stops, walk_graph, active_stop_ids)

    # For each zone, find nearest transit stop via the walk network.
    unique_zone_nodes = list(node_to_zones.keys())
    print(f"Computing walk access for {len(unique_zone_nodes)} unique zone nodes …")
    zone_access = _compute_zone_access(
        unique_zone_nodes, node_to_zones, walk_graph, walknode_to_stops, n_zones
    )

    n_access = sum(1 for a in zone_access if a is not None)
    print(f"  {n_access}/{n_zones} zones can reach a transit stop on foot")

    # Pre-compute all-pairs shortest paths on the stop graph.
    print("Computing stop-to-stop transit times …")
    stop_lengths: dict[str, dict[str, float]] = {}
    for source in stop_graph.nodes():
        stop_lengths[str(source)] = {
            str(k): v
            for k, v in nx.single_source_dijkstra_path_length(
                stop_graph, source, weight="travel_time_min"
            ).items()
        }

    # Assemble zone-to-zone transit matrix.
    matrix = np.full((n_zones, n_zones), unreachable, dtype=np.float64)
    np.fill_diagonal(matrix, 0.0)

    for oi in range(n_zones):
        o_access = zone_access[oi]
        if o_access is None:
            continue
        o_stop, o_walk = o_access
        o_paths = stop_lengths.get(o_stop, {})

        for di in range(n_zones):
            if oi == di:
                continue
            d_access = zone_access[di]
            if d_access is None:
                continue
            d_stop, d_walk = d_access
            tt_transit = o_paths.get(d_stop)
            if tt_transit is None:
                continue
            matrix[oi, di] = o_walk + avg_wait_min + tt_transit + d_walk

    output = Path(f"data/processed/{name}_skim_transit.omx")
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_omx(output, matrix, zone_ids)

    n_unreachable = int(np.sum(matrix == unreachable))
    pct = n_unreachable / (n_zones * n_zones) * 100
    reachable = matrix[matrix < unreachable]
    mean_tt = float(np.mean(reachable)) if reachable.size else float("nan")
    print(f"Wrote {output}  shape={matrix.shape}")
    print(f"  mean travel time: {mean_tt:.1f} min")
    print(f"  unreachable pairs: {n_unreachable} ({pct:.1f}%)")
    return output


def _write_omx(output: Path, matrix: np.ndarray, zone_ids: list[str]) -> None:
    """Write *matrix* and zone lookup to an OMX file at *output*."""
    with omx.open_file(str(output), "w") as f:
        f["travel_time_min"] = matrix
        if "lookup" not in f.root:
            f.create_group(f.root, "lookup")
        max_len = max(len(z) for z in zone_ids)
        atom = tables.StringAtom(itemsize=max_len)
        arr = f.create_array(
            f.root.lookup, "zone_id", atom=atom, shape=(len(zone_ids),)
        )
        arr[:] = np.array(zone_ids, dtype=f"S{max_len}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build transit travel-time skim matrix."
    )
    parser.parse_known_args()
    cfg = load_config()
    build_transit_skim(cfg)
