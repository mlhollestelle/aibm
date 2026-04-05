"""All-or-nothing network assignment for simulated trips.

Finds the shortest-path route for each trip and stores the
individual route (sequence of network node IDs) per agent trip.

Usage:
    uv run python workflow/scripts/assign_network.py
"""

import re
import sys
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
_POI_RE = re.compile(r"^(\d+)")


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


def _add_travel_time_walk(
    graph: nx.MultiDiGraph,
    walk_speed: float,
) -> None:
    """Add ``travel_time_min`` edge attribute for walk mode."""
    for _, _, data in graph.edges(data=True):
        length_km = data["length"] / 1000.0
        data["travel_time_min"] = (length_km / walk_speed) * 60.0


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


def _parse_osm_node_id(loc: str) -> int | None:
    """Extract numeric OSM node ID from a POI location string.

    Handles formats like ``'2450875961: Jumbo'`` or ``'2450875961'``.
    Returns None if *loc* does not start with digits.
    """
    m = _POI_RE.match(loc)
    return int(m.group(1)) if m else None


def _load_transit_graph(path: Path) -> nx.DiGraph | None:
    """Load transit stop graph; return None if missing or empty."""
    if not path.exists():
        return None
    g: nx.DiGraph = nx.read_graphml(str(path))
    if g.number_of_nodes() == 0:
        return None
    return g


def _build_stop_walk_node_map(
    transit_graph: nx.DiGraph,
    walk_graph: nx.MultiDiGraph,
) -> dict[int, str]:
    """Map each walk-network node to the transit stop snapped to it.

    Only active stops (those with at least one edge in *transit_graph*)
    are included, so zones are never routed to isolated stub nodes.

    Returns {walk_node_id: stop_id}.
    """
    from pyproj import Transformer

    active_stop_ids = {str(u) for u, v in transit_graph.edges()} | {
        str(v) for u, v in transit_graph.edges()
    }
    if not active_stop_ids:
        return {}

    stop_ids: list[str] = []
    lats: list[float] = []
    lons: list[float] = []
    for nid, data in transit_graph.nodes(data=True):
        if str(nid) not in active_stop_ids:
            continue
        lats.append(float(data.get("lat", data.get("y", 0))))
        lons.append(float(data.get("lon", data.get("x", 0))))
        stop_ids.append(str(nid))

    if not stop_ids:
        return {}

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:28992", always_xy=True)
    eastings, northings = transformer.transform(lons, lats)
    walk_nodes = ox.nearest_nodes(walk_graph, eastings, northings)

    walk_node_to_stop: dict[int, str] = {}
    for stop_id, wnode in zip(stop_ids, walk_nodes):
        walk_node_to_stop[int(wnode)] = stop_id
    return walk_node_to_stop


def _snap_locs_to_transit_via_walk(
    loc_to_walk_node: dict[str, int],
    walk_graph: nx.MultiDiGraph,
    stop_walk_node_map: dict[int, str],
) -> dict[str, str | None]:
    """Find the nearest reachable transit stop for each location via the walk network.

    Runs Dijkstra from each unique walk node and picks the stop walk-node
    with the lowest travel time. Consistent with the transit skim builder.

    Returns {location_string: stop_id or None}.
    """
    stop_node_set = set(stop_walk_node_map.keys())
    loc_to_stop: dict[str, str | None] = {}

    # Group locations sharing a walk node to avoid duplicate Dijkstra runs.
    walk_node_to_locs: dict[int, list[str]] = {}
    for loc, wnode in loc_to_walk_node.items():
        walk_node_to_locs.setdefault(wnode, []).append(loc)

    for origin_wnode, locs in walk_node_to_locs.items():
        costs = nx.single_source_dijkstra_path_length(
            walk_graph, origin_wnode, weight="travel_time_min"
        )
        best_stop: str | None = None
        best_tt = float("inf")
        for wnode, tt in costs.items():
            if wnode in stop_node_set and tt < best_tt:
                best_tt = tt
                best_stop = stop_walk_node_map[wnode]
        for loc in locs:
            loc_to_stop[loc] = best_stop

    return loc_to_stop


def _route_transit_trip(
    origin: str,
    dest: str,
    loc_to_stop: dict[str, str | None],
    graph: nx.DiGraph,
) -> list[int]:
    """Shortest path through stop graph; returns [] on failure."""
    o_stop = loc_to_stop.get(origin)
    d_stop = loc_to_stop.get(dest)
    if o_stop is None or d_stop is None or o_stop == d_stop:
        return []
    try:
        path: list[str] = nx.shortest_path(
            graph,
            o_stop,
            d_stop,
            weight="travel_time_min",
        )
        return [int(n) for n in path]
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []


def assign_network(cfg: dict, scenario: str = "baseline") -> Path:
    """Route each trip and store the node sequence per agent.

    Each row in the output parquet corresponds to one trip from
    the input, enriched with a ``route_nodes`` column that holds
    the ordered list of network node IDs forming the shortest
    path.  Trips that cannot be routed (same O/D node, no path,
    non-zone locations) are included with an empty route list.
    """
    name = cfg["study_area"]["name"]
    net_cfg = cfg["network"]
    highway_speeds = {k: float(v) for k, v in net_cfg["highway_speeds"].items()}
    default_car_speed = float(net_cfg["default_car_speed_kmh"])
    bike_speed = float(net_cfg["bike_speed_kmh"])
    walk_speed = float(net_cfg["walk_speed_kmh"])

    trips = pd.read_parquet(f"data/processed/{name}_trips_{scenario}.parquet")

    # Build POI id → (easting, northing) lookup for snapping POI destinations.
    poi_coords: dict[str, tuple[float, float]] = {}
    poi_path = Path(f"data/processed/{name}_pois.parquet")
    if poi_path.exists():
        import geopandas as gpd

        pois_gdf = gpd.read_parquet(poi_path)
        for _, row in pois_gdf.iterrows():
            key = str(int(row["osmid"]))
            poi_coords[key] = (float(row.geometry.x), float(row.geometry.y))

    road_modes = [m for m in cfg["network"]["modes"] if m != "transit"]
    mode_graphs: dict[str, nx.MultiDiGraph] = {}
    for mode in road_modes:
        gpath = Path(f"data/processed/{name}_network_{mode}.graphml")
        g = ox.load_graphml(gpath)
        if mode == "car":
            _add_travel_time_car(g, highway_speeds, default_car_speed)
        elif mode == "bike":
            _add_travel_time_bike(g, bike_speed)
        else:
            _add_travel_time_walk(g, walk_speed)
        mode_graphs[mode] = ox.project_graph(g, to_crs="EPSG:28992")

    # Load transit stop graph if enabled.
    transit_cfg = cfg.get("transit", {})
    transit_graph: nx.DiGraph | None = None
    transit_loc_to_stop: dict[str, str | None] = {}
    if transit_cfg.get("enabled", False):
        tpath = Path(f"data/processed/{name}_transit_stops.graphml")
        transit_graph = _load_transit_graph(tpath)
        if transit_graph is not None:
            transit_trips = trips[trips["mode"] == "transit"]
            if not transit_trips.empty and "walk" in mode_graphs:
                walk_graph = mode_graphs["walk"]
                stop_walk_node_map = _build_stop_walk_node_map(
                    transit_graph, walk_graph
                )
                if stop_walk_node_map:
                    all_transit_locs = set(transit_trips["origin"].tolist()) | set(
                        transit_trips["destination"].tolist()
                    )

                    # Snap all transit locations (zones + POIs) to walk network.
                    loc_e: list[float] = []
                    loc_n: list[float] = []
                    valid_locs: list[str] = []
                    for loc in all_transit_locs:
                        if _is_zone_id(loc):
                            m = _ZONE_RE.match(loc)
                            assert m is not None
                            loc_e.append(int(m.group(1)) * 100 + 50)
                            loc_n.append(int(m.group(2)) * 100 + 50)
                            valid_locs.append(loc)
                        else:
                            osm_id = _parse_osm_node_id(loc)
                            key = str(osm_id) if osm_id is not None else None
                            if key and key in poi_coords:
                                loc_e.append(poi_coords[key][0])
                                loc_n.append(poi_coords[key][1])
                                valid_locs.append(loc)

                    if valid_locs:
                        walk_nodes = ox.nearest_nodes(walk_graph, loc_e, loc_n)
                        loc_to_walk_node = dict(zip(valid_locs, walk_nodes))
                        transit_loc_to_stop = _snap_locs_to_transit_via_walk(
                            loc_to_walk_node, walk_graph, stop_walk_node_map
                        )
                    # Locations not resolved get None.
                    for loc in all_transit_locs:
                        if loc not in transit_loc_to_stop:
                            transit_loc_to_stop[loc] = None

                    n_snapped = sum(
                        1 for v in transit_loc_to_stop.values() if v is not None
                    )
                    print(
                        f"Transit: snapped {n_snapped}/{len(transit_loc_to_stop)}"
                        " locations to stops via walk network"
                    )

    # Pre-compute zone-to-node mapping per road mode so we snap once.
    mode_zone_to_node: dict[str, dict[str, int]] = {}
    for mode, graph in mode_graphs.items():
        mode_trips = trips[trips["mode"] == mode]
        if mode_trips.empty:
            mode_zone_to_node[mode] = {}
            continue
        all_locs = set(mode_trips["origin"].tolist()) | set(
            mode_trips["destination"].tolist()
        )
        zone_locs = [loc for loc in all_locs if _is_zone_id(loc)]
        loc_to_node: dict[str, int] = {}
        if zone_locs:
            eastings, northings = _centroids_from_zone_ids(zone_locs)
            nearest = ox.nearest_nodes(graph, eastings, northings)
            loc_to_node.update(zip(zone_locs, nearest))

        # Also snap POI locations using their stored coordinates.
        poi_locs = [loc for loc in all_locs if not _is_zone_id(loc)]
        poi_e, poi_n, valid_poi_locs = [], [], []
        for loc in poi_locs:
            osm_id = _parse_osm_node_id(loc)
            if osm_id is not None:
                key = str(osm_id)
                if key in poi_coords:
                    poi_e.append(poi_coords[key][0])
                    poi_n.append(poi_coords[key][1])
                    valid_poi_locs.append(loc)
        if valid_poi_locs:
            nearest_poi = ox.nearest_nodes(graph, poi_e, poi_n)
            loc_to_node.update(zip(valid_poi_locs, nearest_poi))

        if not loc_to_node:
            mode_zone_to_node[mode] = {}
            continue
        mode_zone_to_node[mode] = loc_to_node

    def _route_distance(graph: nx.MultiDiGraph, path: list[int]) -> float:
        """Sum edge lengths (metres) along *path* in *graph*."""
        total = 0.0
        for u, v in zip(path[:-1], path[1:]):
            edge_data = graph.get_edge_data(u, v)
            if edge_data:
                # MultiDiGraph: edge_data is {key: attr_dict}; pick first key.
                total += min(d.get("length", 0.0) for d in edge_data.values())
        return total

    # Route each trip individually.
    route_nodes: list[list[int]] = []
    distances: list[float | None] = []
    for _, row in trips.iterrows():
        mode = row.get("mode")
        origin = str(row["origin"])
        dest = str(row["destination"])

        if mode == "transit":
            if transit_graph is not None:
                path_t = _route_transit_trip(
                    origin, dest, transit_loc_to_stop, transit_graph
                )
                route_nodes.append(path_t)
                distances.append(None)
            else:
                route_nodes.append([])
                distances.append(None)
            continue

        if mode not in mode_graphs:
            route_nodes.append([])
            distances.append(None)
            continue

        zone_to_node = mode_zone_to_node[mode]
        if origin not in zone_to_node or dest not in zone_to_node:
            route_nodes.append([])
            distances.append(None)
            continue

        o_node = zone_to_node[origin]
        d_node = zone_to_node[dest]
        if o_node == d_node:
            route_nodes.append([])
            distances.append(None)
            continue

        try:
            path = nx.shortest_path(
                mode_graphs[mode],
                o_node,
                d_node,
                weight="travel_time_min",
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            route_nodes.append([])
            distances.append(None)
            continue

        route_nodes.append(path)
        distances.append(_route_distance(mode_graphs[mode], path))

    result = trips.copy()
    result["route_nodes"] = route_nodes
    result["distance"] = distances

    # Add origin/destination buurt names from zone specs
    specs_path = Path(f"data/processed/{name}_zone_specs.parquet")
    if specs_path.exists():
        specs = pd.read_parquet(specs_path)
        if "buurt_name" in specs.columns:
            zone_buurt = specs.set_index("zone_id")["buurt_name"].to_dict()
            result["origin_buurt"] = (
                result["origin"].map(zone_buurt).fillna(result["origin"])
            )
            result["destination_buurt"] = (
                result["destination"].map(zone_buurt).fillna(result["destination"])
            )
            print("Added origin_buurt and destination_buurt columns")

    output = Path(f"data/processed/{name}_assigned_trips_{scenario}.parquet")
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(output, index=False)

    n_routed = sum(1 for r in route_nodes if r)
    print(f"Wrote {len(result)} trips ({n_routed} routed) to {output}")
    return output


if __name__ == "__main__":
    import argparse

    _parser = argparse.ArgumentParser(add_help=False)
    _parser.add_argument("--scenario", default="baseline")
    _args, _ = _parser.parse_known_args()
    assign_network(load_config(), scenario=_args.scenario)
