"""Convert pipeline parquet outputs to JSON/GeoJSON for the web app.

Usage:
    uv run python webapp/prepare_data.py --config workflow/config.yaml
"""

import json
import re
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


def export_network(edges_path: Path, out_path: Path) -> None:
    """Write simplified network.geojson from car edges parquet."""
    gdf = gpd.read_parquet(edges_path)

    # Keep only geometry — drop all attribute columns
    gdf = gdf[["geometry"]].copy()

    # Simplify geometries to reduce file size (~1m tolerance)
    gdf["geometry"] = gdf["geometry"].simplify(0.00001)

    # Drop empty geometries
    gdf = gdf[~gdf.geometry.is_empty]

    gdf.to_file(out_path, driver="GeoJSON")
    size_mb = out_path.stat().st_size / 1_048_576
    print(f"Wrote {len(gdf)} edges to {out_path} ({size_mb:.1f} MB)")


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


def export_agents(
    day_plans_path: Path,
    zone_lut: dict[str, list[float]],
    out_path: Path,
) -> None:
    """Write agents.json from day plans parquet."""
    dp = pd.read_parquet(day_plans_path)
    agents = []
    for _, row in dp.iterrows():
        home = zone_lut.get(row["home_zone"])
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
    trips = []
    for _, row in df.iterrows():
        route_nodes = row["route_nodes"]
        departure = row["departure_time"]
        mode = row["mode"]

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

        # Compute arrival time from graph edge weights
        arrival = None
        if len(route_nodes) >= 2 and mode in mode_graphs:
            tt = _compute_route_travel_time(mode_graphs[mode], route_nodes)
            arrival = round(departure + tt, 1)
        if arrival is None:
            # Fallback: assume 10 min travel
            arrival = departure + 10

        trips.append(
            {
                "agent_id": row["agent_id"],
                "tour_idx": int(row["tour_idx"]),
                "trip_seq": int(row["trip_seq"]),
                "origin": str(row["origin"]),
                "destination": str(row["destination"]),
                "mode": mode,
                "departure": departure,
                "arrival": round(arrival, 1),
                "route": coords,
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
            }
        )
    with open(out_path, "w") as f:
        json.dump(activities, f)
    print(f"Wrote {len(activities)} activities to {out_path}")


# ── main ─────────────────────────────────────────────


def main() -> None:
    cfg = load_config()
    name = cfg["study_area"]["name"]
    data_dir = Path("data/processed")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Node lookup — merge car + bike nodes
    node_lut: dict[int, list[float]] = {}
    for mode in ("car", "bike"):
        nodes_path = data_dir / f"{name}_network_{mode}_nodes.parquet"
        mode_lut = _node_lookup(nodes_path)
        node_lut.update(mode_lut)
    print(f"Node lookup: {len(node_lut)} nodes")

    # 2. Zone centroid lookup
    specs = pd.read_parquet(data_dir / f"{name}_zone_specs.parquet")
    zone_ids = specs["zone_id"].tolist()
    zone_lut = _zone_centroids_wgs84(zone_ids)
    print(f"Zone lookup: {len(zone_lut)} zones")

    # Save lookups for debugging / later use
    with open(OUT_DIR / "node_lookup.json", "w") as f:
        json.dump(
            {str(k): v for k, v in node_lut.items()},
            f,
        )

    with open(OUT_DIR / "zone_lookup.json", "w") as f:
        json.dump(zone_lut, f)

    # 3. Network GeoJSON
    edges_path = data_dir / f"{name}_network_car_edges.parquet"
    export_network(edges_path, OUT_DIR / "network.geojson")

    # 4. Load graphs with travel time weights (for trip arrival)
    net_cfg = cfg["network"]
    highway_speeds = {k: float(v) for k, v in net_cfg["highway_speeds"].items()}
    mode_graphs: dict[str, nx.MultiDiGraph] = {}
    for mode in ("car", "bike"):
        gpath = data_dir / f"{name}_network_{mode}.graphml"
        g = ox.load_graphml(gpath)
        if mode == "car":
            _add_travel_time_car(g, highway_speeds, net_cfg["default_car_speed_kmh"])
        else:
            _add_travel_time_bike(g, net_cfg["bike_speed_kmh"])
        mode_graphs[mode] = g
    print(f"Loaded {len(mode_graphs)} mode graphs")

    # 5. Agents
    export_agents(
        data_dir / f"{name}_day_plans.parquet",
        zone_lut,
        OUT_DIR / "agents.json",
    )

    # 6. Trips (with route geometry + computed arrival)
    export_trips(
        data_dir / f"{name}_assigned_trips.parquet",
        node_lut,
        zone_lut,
        mode_graphs,
        OUT_DIR / "trips.json",
    )

    # 7. Activities
    export_activities(
        data_dir / f"{name}_activities.parquet",
        zone_lut,
        OUT_DIR / "activities.json",
    )


if __name__ == "__main__":
    main()
