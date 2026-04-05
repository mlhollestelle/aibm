"""Convert pipeline parquet outputs to JSON/GeoJSON for the web app.

Usage:
    uv run python webapp/prepare_data.py --config workflow/config.yaml
    uv run python webapp/prepare_data.py --config workflow/config.yaml \
        --scenario baseline
"""

import argparse
import json
import math
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "workflow" / "scripts"))

# isort: split

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd
from _config import load_config
from pyproj import Transformer

_ZONE_RE = re.compile(r"E(\d+)N(\d+)")

OUT_DIR = Path(__file__).parent / "static" / "data"


# ── helpers ──────────────────────────────────────────


def _zone_centroids_wgs84(
    zone_ids: list[str],
) -> dict[str, list[float]]:
    """Parse E{X}N{Y} zone IDs → {zone_id: [lon, lat]} in WGS84."""
    transformer = Transformer.from_crs("EPSG:28992", "EPSG:4326", always_xy=True)
    result: dict[str, list[float]] = {}
    for zid in zone_ids:
        m = _ZONE_RE.match(zid)
        if m is None:
            continue
        easting = int(m.group(1)) * 100 + 50
        northing = int(m.group(2)) * 100 + 50
        lon, lat = transformer.transform(easting, northing)
        result[zid] = [round(lon, 6), round(lat, 6)]
    return result


def _node_lookup(nodes_path: Path) -> dict[int, list[float]]:
    """Build {osmid: [lon, lat]} from car nodes parquet."""
    gdf = gpd.read_parquet(nodes_path)
    lookup: dict[int, list[float]] = {}
    for _, row in gdf.iterrows():
        geom = row.geometry
        lookup[int(row["osmid"])] = [round(geom.x, 6), round(geom.y, 6)]
    return lookup


# ── exports ──────────────────────────────────────────


def _add_travel_time_car(
    graph: nx.MultiDiGraph,
    highway_speeds: dict[str, float],
    default_speed: float,
) -> None:
    """Add ``travel_time_min`` to car graph edges."""
    for _, _, data in graph.edges(data=True):
        length_km = data["length"] / 1000.0
        speed: float | None = None
        maxspeed = data.get("maxspeed")
        if maxspeed is not None:
            raw = maxspeed[0] if isinstance(maxspeed, list) else maxspeed
            m = re.search(r"(\d+)", str(raw))
            if m:
                speed = float(m.group(1))
        if speed is None:
            hw = data.get("highway", "")
            if isinstance(hw, list):
                hw = hw[0]
            speed = highway_speeds.get(hw, default_speed)
        data["travel_time_min"] = (length_km / speed) * 60.0


def _add_travel_time_bike(
    graph: nx.MultiDiGraph,
    bike_speed: float,
) -> None:
    """Add ``travel_time_min`` to bike graph edges."""
    for _, _, data in graph.edges(data=True):
        length_km = data["length"] / 1000.0
        data["travel_time_min"] = (length_km / bike_speed) * 60.0


def _add_travel_time_walk(
    graph: nx.MultiDiGraph,
    walk_speed: float,
) -> None:
    """Add ``travel_time_min`` to walk graph edges."""
    for _, _, data in graph.edges(data=True):
        length_km = data["length"] / 1000.0
        data["travel_time_min"] = (length_km / walk_speed) * 60.0


def _compute_route_travel_time(
    graph: nx.MultiDiGraph,
    route_nodes: list[int],
) -> float:
    """Sum travel_time_min along a route's edges."""
    total = 0.0
    for u, v in zip(route_nodes[:-1], route_nodes[1:]):
        edge_data = graph.get_edge_data(u, v)
        if edge_data is None:
            continue
        # MultiDiGraph: take first edge (key 0)
        first = next(iter(edge_data.values()))
        total += first.get("travel_time_min", 0.0)
    return total


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in km between two WGS84 points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + (
        math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def _compute_route_length_km(
    graph: nx.MultiDiGraph,
    route_nodes: list[int],
) -> float:
    """Sum OSM edge lengths (metres) along a route, return km."""
    total = 0.0
    for u, v in zip(route_nodes[:-1], route_nodes[1:]):
        edge_data = graph.get_edge_data(u, v)
        if edge_data is None:
            continue
        first = next(iter(edge_data.values()))
        total += first.get("length", 0.0)
    return total / 1000.0


def export_agents(
    day_plans_path: Path,
    zone_lut: dict[str, list[float]],
    zone_name_lut: dict[str, str],
    out_path: Path,
) -> None:
    """Write agents.json from day plans parquet."""
    dp = pd.read_parquet(day_plans_path)
    agents = []
    for _, row in dp.iterrows():
        home_zone = row["home_zone"]
        home = zone_lut.get(home_zone)
        if home is None:
            continue
        agents.append(
            {
                "id": row["agent_id"],
                "name": row["name"],
                "age": int(row["age"]),
                "employment": row["employment"],
                "persona": row["persona"],
                "home": home,
                "home_name": zone_name_lut.get(home_zone, home_zone),
            }
        )
    with open(out_path, "w") as f:
        json.dump(agents, f)
    print(f"Wrote {len(agents)} agents to {out_path}")


def export_trips(
    trips_path: Path,
    node_lut: dict[int, list[float]],
    zone_lut: dict[str, list[float]],
    mode_graphs: dict[str, nx.MultiDiGraph],
    out_path: Path,
) -> None:
    """Write trips.json with route coords and arrival times."""
    df = pd.read_parquet(trips_path)
    has_buurt = "origin_buurt" in df.columns
    trips = []
    for _, row in df.iterrows():
        route_nodes = row["route_nodes"]
        departure = row["departure_time"]
        mode = row["mode"] if pd.notna(row["mode"]) else None

        # Build route coordinates from node IDs
        coords = []
        for nid in route_nodes:
            pt = node_lut.get(int(nid))
            if pt:
                coords.append(pt)

        # Fallback: straight line from origin to destination
        if len(coords) < 2:
            o = zone_lut.get(str(row["origin"]))
            d = zone_lut.get(str(row["destination"]))
            if o and d:
                coords = [o, d]
            else:
                print(
                    f"Warning: no route for trip {row['agent_id']} "
                    f"{row['origin']} → {row['destination']}, skipping"
                )
                continue

        # Compute arrival time from graph edge weights
        arrival = None
        if len(route_nodes) >= 2 and mode in mode_graphs:
            tt = _compute_route_travel_time(mode_graphs[mode], route_nodes)
            arrival = round(departure + tt, 1)
        if arrival is None:
            # Fallback: assume 10 min travel
            arrival = departure + 10

        origin = str(row["origin"])
        destination = str(row["destination"])

        # Compute distance_km from network edges or straight line
        distance_km = None
        if len(route_nodes) >= 2 and mode in mode_graphs:
            d = _compute_route_length_km(mode_graphs[mode], route_nodes)
            distance_km = round(d, 3)
        elif len(coords) >= 2:
            o_lon, o_lat = coords[0]
            d_lon, d_lat = coords[-1]
            distance_km = round(_haversine_km(o_lon, o_lat, d_lon, d_lat), 3)

        trips.append(
            {
                "agent_id": row["agent_id"],
                "tour_idx": int(row["tour_idx"]),
                "trip_seq": int(row["trip_seq"]),
                "origin": origin,
                "destination": destination,
                "origin_name": (str(row["origin_buurt"]) if has_buurt else origin),
                "destination_name": (
                    str(row["destination_buurt"]) if has_buurt else destination
                ),
                "mode": mode,
                "mode_reasoning": (
                    str(row["mode_reasoning"])
                    if "mode_reasoning" in df.columns
                    and pd.notna(row["mode_reasoning"])
                    else None
                ),
                "departure": departure,
                "arrival": round(arrival, 1),
                "distance_km": distance_km,
                "route": coords,
                "joint_ride_id": (
                    str(row["joint_ride_id"])
                    if "joint_ride_id" in df.columns and pd.notna(row["joint_ride_id"])
                    else None
                ),
            }
        )
    with open(out_path, "w") as f:
        json.dump(trips, f)
    print(f"Wrote {len(trips)} trips to {out_path}")


def export_activities(
    activities_path: Path,
    zone_lut: dict[str, list[float]],
    out_path: Path,
) -> None:
    """Write activities.json with WGS84 locations."""
    df = pd.read_parquet(activities_path)
    activities = []
    for _, row in df.iterrows():
        loc = zone_lut.get(str(row["location"]))
        if loc is None:
            continue
        activities.append(
            {
                "agent_id": row["agent_id"],
                "activity_seq": int(row["activity_seq"]),
                "type": row["activity_type"],
                "location": loc,
                "start": row["start_time"],
                "end": row["end_time"],
                "reasoning": (
                    str(row["reasoning"])
                    if "reasoning" in df.columns
                    and pd.notna(row["reasoning"])
                    and row["reasoning"]
                    else None
                ),
            }
        )
    with open(out_path, "w") as f:
        json.dump(activities, f)
    print(f"Wrote {len(activities)} activities to {out_path}")


# ── main ─────────────────────────────────────────────


def main() -> None:
    _parser = argparse.ArgumentParser(add_help=False)
    _parser.add_argument("--scenario", default="baseline")
    _args, _ = _parser.parse_known_args()
    scenario = _args.scenario

    cfg = load_config()
    name = cfg["study_area"]["name"]
    data_dir = Path("data/processed")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Node lookup — merge car + bike + walk nodes
    node_lut: dict[int, list[float]] = {}
    for mode in ("car", "bike", "walk"):
        nodes_path = data_dir / f"{name}_network_{mode}_nodes.parquet"
        if nodes_path.exists():
            mode_lut = _node_lookup(nodes_path)
            node_lut.update(mode_lut)
    print(f"Node lookup: {len(node_lut)} nodes")

    # 2. Zone centroid lookup
    specs = pd.read_parquet(data_dir / f"{name}_zone_specs.parquet")
    zone_ids = specs["zone_id"].tolist()
    zone_lut = _zone_centroids_wgs84(zone_ids)
    print(f"Zone lookup: {len(zone_lut)} zones")

    # 3. Zone name lookup — buurt_name added to zone specs during pipeline
    zone_name_lut: dict[str, str] = {}
    if "buurt_name" in specs.columns:
        zone_name_lut = specs.set_index("zone_id")["buurt_name"].to_dict()
        print(f"Zone name lookup: {len(zone_name_lut)} zones from pipeline")
    else:
        print("Warning: buurt_name not in zone specs, using zone IDs as names")

    # Save lookups for debugging / later use
    with open(OUT_DIR / "node_lookup.json", "w") as f:
        json.dump(
            {str(k): v for k, v in node_lut.items()},
            f,
        )

    with open(OUT_DIR / "zone_lookup.json", "w") as f:
        json.dump(zone_lut, f)

    # 4. Load graphs with travel time weights (for trip arrival)
    net_cfg = cfg["network"]
    highway_speeds = {k: float(v) for k, v in net_cfg["highway_speeds"].items()}
    mode_graphs: dict[str, nx.MultiDiGraph] = {}
    for mode in ("car", "bike", "walk"):
        gpath = data_dir / f"{name}_network_{mode}.graphml"
        if not gpath.exists():
            continue
        g = ox.load_graphml(gpath)
        if mode == "car":
            _add_travel_time_car(g, highway_speeds, net_cfg["default_car_speed_kmh"])
        elif mode == "bike":
            _add_travel_time_bike(g, net_cfg["bike_speed_kmh"])
        else:
            _add_travel_time_walk(g, net_cfg["walk_speed_kmh"])
        mode_graphs[mode] = g
    print(f"Loaded {len(mode_graphs)} mode graphs")

    # 6. Agents
    export_agents(
        data_dir / f"{name}_day_plans_{scenario}.parquet",
        zone_lut,
        zone_name_lut,
        OUT_DIR / "agents.json",
    )

    # 7. Trips (with route geometry + computed arrival)
    export_trips(
        data_dir / f"{name}_assigned_trips_{scenario}.parquet",
        node_lut,
        zone_lut,
        mode_graphs,
        OUT_DIR / "trips.json",
    )

    # 8. Activities
    export_activities(
        data_dir / f"{name}_activities_{scenario}.parquet",
        zone_lut,
        OUT_DIR / "activities.json",
    )

    # 9. Copy plots to webapp static assets
    figures_dir = Path(__file__).parent / "static" / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    for src_name, dest_name in [
        (f"{name}_mode_shares.png", "mode_shares.png"),
        (f"{name}_trip_lengths.png", "trip_lengths.png"),
        (f"{name}_trips_per_person.png", "trips_per_person.png"),
    ]:
        src = data_dir / src_name
        if src.exists():
            shutil.copy2(src, figures_dir / dest_name)
            print(f"Copied {dest_name} to {figures_dir / dest_name}")


if __name__ == "__main__":
    main()
