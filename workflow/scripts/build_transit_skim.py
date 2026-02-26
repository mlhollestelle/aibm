"""Build a zone-level transit travel-time skim matrix.

Combines walk access to the nearest stop, a configurable average wait time,
shortest stop-to-stop path travel time, and walk egress from the destination
stop to produce zone-to-zone transit travel times.

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
import pandas as pd
import tables
from _config import load_config

_ZONE_RE = re.compile(r"E(\d+)N(\d+)")


def _zone_centroid_wgs84(zone_id: str) -> tuple[float, float]:
    """Convert E{X}N{Y} zone id to approximate WGS84 lat/lon.

    Uses a linear approximation centred on the Zeeland/Walcheren area.
    Accurate to ~100 m within the study area, which is sufficient for
    snapping zones to stops.
    """
    m = _ZONE_RE.match(zone_id)
    if m is None:
        raise ValueError(f"Cannot parse zone_id: {zone_id}")
    e = int(m.group(1)) * 100 + 50
    n = int(m.group(2)) * 100 + 50
    lat = 51.5 + (n - 392000) / 111320
    lon = 3.7 + (e - 21000) / (111320 * math.cos(math.radians(51.5)))
    return lat, lon


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS84 points."""
    r = 6_371_000.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return r * 2 * math.asin(math.sqrt(a))


def _snap_zones_to_stops(
    zone_ids: list[str],
    stops: dict[str, tuple[float, float]],
    max_walk_m: float,
) -> dict[str, str | None]:
    """Return {zone_id: nearest_stop_node_id or None}.

    Only snaps to stops within *max_walk_m* metres.  ``stops`` maps node
    id strings (as in the GraphML) to (lat, lon) tuples.
    """
    zone_to_stop: dict[str, str | None] = {}
    stop_items = list(stops.items())

    for zid in zone_ids:
        zlat, zlon = _zone_centroid_wgs84(zid)
        best_id: str | None = None
        best_dist = float("inf")
        for stop_id, (slat, slon) in stop_items:
            dist = _haversine_m(zlat, zlon, slat, slon)
            if dist < best_dist:
                best_dist = dist
                best_id = stop_id
        zone_to_stop[zid] = best_id if best_dist <= max_walk_m else None

    return zone_to_stop


def _walk_time_min(
    zone_id: str,
    stop_id: str,
    stops: dict[str, tuple[float, float]],
    walk_speed_kmh: float,
) -> float:
    """Walk time in minutes from zone centroid to stop."""
    zlat, zlon = _zone_centroid_wgs84(zone_id)
    slat, slon = stops[stop_id]
    dist_m = _haversine_m(zlat, zlon, slat, slon)
    return (dist_m / 1000.0 / walk_speed_kmh) * 60.0


def build_transit_skim(cfg: dict) -> Path:
    """Compute zone-level transit skim and write OMX file."""
    name = cfg["study_area"]["name"]
    transit_cfg = cfg.get("transit", {})
    walk_speed = float(transit_cfg.get("walk_speed_kmh", 5.0))
    max_walk_m = float(transit_cfg.get("max_walk_to_stop_m", 800))
    avg_wait_min = float(transit_cfg.get("avg_wait_min", 10.0))
    unreachable = float(cfg["network"]["unreachable"])

    stop_graph_path = Path(f"data/processed/{name}_transit_stops.graphml")
    graph: nx.DiGraph = nx.read_graphml(str(stop_graph_path))

    stops: dict[str, tuple[float, float]] = {}
    for nid, data in graph.nodes(data=True):
        lat = float(data.get("lat", data.get("y", 0)))
        lon = float(data.get("lon", data.get("x", 0)))
        stops[str(nid)] = (lat, lon)

    grid = pd.read_parquet(f"data/processed/{name}_grid_clean.parquet")
    zone_ids: list[str] = sorted(grid["zone_id"].tolist())
    n_zones = len(zone_ids)
    print(f"Loaded {n_zones} zones, {len(stops)} transit stops")

    if not stops:
        print("Warning: no transit stops — writing all-unreachable skim")
        matrix = np.full((n_zones, n_zones), unreachable, dtype=np.float64)
        np.fill_diagonal(matrix, 0.0)
        output = Path(f"data/processed/{name}_skim_transit.omx")
        output.parent.mkdir(parents=True, exist_ok=True)
        _write_omx(output, matrix, zone_ids)
        return output

    zone_to_stop = _snap_zones_to_stops(zone_ids, stops, max_walk_m)
    n_snapped = sum(1 for v in zone_to_stop.values() if v is not None)
    print(f"Snapped {n_snapped}/{n_zones} zones to transit stops")

    matrix = np.full((n_zones, n_zones), unreachable, dtype=np.float64)
    np.fill_diagonal(matrix, 0.0)

    # Pre-compute all-pairs shortest paths through the stop graph.
    lengths: dict[str, dict[str, float]] = {}
    for source in stops:
        lengths[source] = nx.single_source_dijkstra_path_length(
            graph, source, weight="travel_time_min"
        )

    zone_index = {zid: i for i, zid in enumerate(zone_ids)}

    for oi, o_zone in enumerate(zone_ids):
        o_stop = zone_to_stop.get(o_zone)
        if o_stop is None:
            continue
        walk_o = _walk_time_min(o_zone, o_stop, stops, walk_speed)

        for d_zone in zone_ids:
            di = zone_index[d_zone]
            if oi == di:
                continue
            d_stop = zone_to_stop.get(d_zone)
            if d_stop is None:
                continue
            if d_stop not in lengths.get(o_stop, {}):
                continue
            stop_tt = lengths[o_stop][d_stop]
            walk_d = _walk_time_min(d_zone, d_stop, stops, walk_speed)
            matrix[oi, di] = walk_o + avg_wait_min + stop_tt + walk_d

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
