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


def _snap_coord_to_transit(
    lat: float,
    lon: float,
    node_coords: list[tuple[int, float, float]],
    max_walk_m: float,
) -> int | None:
    """Return the nearest stop node ID within *max_walk_m* metres, or None."""
    import math

    best_id: int | None = None
    best_dist = float("inf")
    for nid, nlat, nlon in node_coords:
        dlat = (nlat - lat) * 111320
        dlon = (nlon - lon) * 111320 * math.cos(math.radians(lat))
        dist = math.hypot(dlat, dlon)
        if dist < best_dist:
            best_dist = dist
            best_id = nid
    return best_id if best_dist <= max_walk_m else None


def _snap_zones_to_transit(
    zone_ids: list[str],
    graph: nx.DiGraph,
    walk_speed_kmh: float,
    max_walk_m: float,
) -> dict[str, int | None]:
    """Map each zone centroid to the nearest stop node within walk distance.

    Returns {zone_id: osm_node_id or None}.
    """
    import math

    zone_to_stop: dict[str, int | None] = {}
    node_coords: list[tuple[int, float, float]] = []
    for nid, data in graph.nodes(data=True):
        lat = float(data.get("lat", data.get("y", 0)))
        lon = float(data.get("lon", data.get("x", 0)))
        node_coords.append((int(nid), lat, lon))

    for zid in zone_ids:
        m = _ZONE_RE.match(zid)
        if m is None:
            zone_to_stop[zid] = None
            continue
        # EPSG:28992 → approximate WGS84 (good enough for snapping)
        e = int(m.group(1)) * 100 + 50
        n = int(m.group(2)) * 100 + 50
        # Simple RD → WGS84 approximation (Zeeland area)
        lat_z = 51.5 + (n - 392000) / 111320
        lon_z = 3.7 + (e - 21000) / (111320 * math.cos(math.radians(51.5)))
        zone_to_stop[zid] = _snap_coord_to_transit(
            lat_z, lon_z, node_coords, max_walk_m
        )

    return zone_to_stop


def _route_transit_trip(
    origin: str,
    dest: str,
    zone_to_stop: dict[str, int | None],
    graph: nx.DiGraph,
) -> list[int]:
    """Shortest path through stop graph; returns [] on failure."""
    o_stop = zone_to_stop.get(origin)
    d_stop = zone_to_stop.get(dest)
    if o_stop is None or d_stop is None or o_stop == d_stop:
        return []
    try:
        path: list[int] = nx.shortest_path(
            graph,
            str(o_stop),
            str(d_stop),
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
    transit_zone_to_stop: dict[str, int | None] = {}
    if transit_cfg.get("enabled", False):
        tpath = Path(f"data/processed/{name}_transit_stops.graphml")
        transit_graph = _load_transit_graph(tpath)
        if transit_graph is not None:
            transit_trips = trips[trips["mode"] == "transit"]
            if not transit_trips.empty:
                all_transit_locs = set(transit_trips["origin"].tolist()) | set(
                    transit_trips["destination"].tolist()
                )
                max_walk_m = float(transit_cfg.get("max_walk_to_stop_m", 800))
                zone_locs_t = [loc for loc in all_transit_locs if _is_zone_id(loc)]
                transit_zone_to_stop = _snap_zones_to_transit(
                    zone_locs_t,
                    transit_graph,
                    float(transit_cfg.get("walk_speed_kmh", 5.0)),
                    max_walk_m,
                )
                # Also snap POI transit locations using stored coordinates.
                import math

                t_node_coords: list[tuple[int, float, float]] = []
                for nid, data in transit_graph.nodes(data=True):
                    t_node_coords.append(
                        (
                            int(nid),
                            float(data.get("lat", data.get("y", 0))),
                            float(data.get("lon", data.get("x", 0))),
                        )
                    )
                for loc in all_transit_locs:
                    if _is_zone_id(loc):
                        continue
                    osm_id = _parse_osm_node_id(loc)
                    key = str(osm_id) if osm_id is not None else None
                    if key and key in poi_coords:
                        e_rd, n_rd = poi_coords[key]
                        lat_p = 51.5 + (n_rd - 392000) / 111320
                        lon_p = 3.7 + (e_rd - 21000) / (
                            111320 * math.cos(math.radians(51.5))
                        )
                        transit_zone_to_stop[loc] = _snap_coord_to_transit(
                            lat_p, lon_p, t_node_coords, max_walk_m
                        )
                    else:
                        transit_zone_to_stop[loc] = None

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
                    origin, dest, transit_zone_to_stop, transit_graph
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
