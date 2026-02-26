"""Download public transport stop graph for the study area from OSM.

Queries the Overpass API for PT route relations, extracts stop sequences,
builds a stop-to-stop directed graph, and saves it as GraphML.

Usage:
    uv run python workflow/scripts/download_transit.py
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# isort: split

import networkx as nx
import requests
from _config import load_config


def _build_polygon_str(boundaries: Path) -> str:
    """Convert boundary GeoJSON to Overpass poly: string (lat lon pairs)."""
    with open(boundaries) as f:
        geojson = json.load(f)

    coords: list[tuple[float, float]] = []
    for feature in geojson.get("features", []):
        geom = feature.get("geometry", {})
        geom_type = geom.get("type")
        if geom_type == "Polygon":
            rings = [geom["coordinates"]]
        elif geom_type == "MultiPolygon":
            rings = geom["coordinates"]
        else:
            continue
        for polygon in rings:
            for lon, lat in polygon[0]:  # outer ring only
                coords.append((lat, lon))

    if not coords:
        raise ValueError("No polygon coordinates found in boundaries file")

    return " ".join(f"{lat} {lon}" for lat, lon in coords)


def _query_overpass(poly_str: str, route_types: list[str]) -> dict:
    """POST query to Overpass API and return parsed JSON response."""
    route_filter = "|".join(route_types)
    query = (
        f"[out:json][timeout:120];\n"
        f"(\n"
        f'  relation["route"~"{route_filter}"](poly:"{poly_str}");\n'
        f");\n"
        f"out body;\n"
        f">;\n"
        f"out skel qt;\n"
    )
    url = "https://overpass-api.de/api/interpreter"
    for attempt in range(3):
        try:
            resp = requests.post(url, data={"data": query}, timeout=180)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            if attempt == 2:
                raise
            wait = 10 * (attempt + 1)
            print(f"Overpass request failed ({exc}), retrying in {wait}s …")
            time.sleep(wait)
    return {}


def _extract_stops(response: dict) -> dict[int, dict]:
    """Return {osm_id: {lat, lon}} for all node elements in the response."""
    stops: dict[int, dict] = {}
    for element in response.get("elements", []):
        if element.get("type") == "node":
            stops[element["id"]] = {
                "lat": element["lat"],
                "lon": element["lon"],
            }
    return stops


def _extract_routes(response: dict) -> list[tuple[str, list[int]]]:
    """Return [(route_type, [stop_node_ids_in_order])] per relation.

    Only members with role "stop" or "stop_position" are included.
    """
    routes: list[tuple[str, list[int]]] = []
    for element in response.get("elements", []):
        if element.get("type") != "relation":
            continue
        route_type = element.get("tags", {}).get("route", "unknown")
        stop_ids: list[int] = []
        for member in element.get("members", []):
            if member.get("type") == "node" and member.get("role") in {
                "stop",
                "stop_position",
            }:
                stop_ids.append(member["ref"])
        if len(stop_ids) >= 2:
            routes.append((route_type, stop_ids))
    return routes


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two WGS84 points."""
    r = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return r * 2 * math.asin(math.sqrt(a))


def _build_stop_graph(
    routes: list[tuple[str, list[int]]],
    stops: dict[int, dict],
    speeds: dict[str, float],
) -> nx.DiGraph:
    """Build a directed stop graph.

    Nodes are OSM stop node IDs; edges carry ``travel_time_min`` based on
    haversine distance divided by route-type speed.
    """
    graph = nx.DiGraph()

    for node_id, coords in stops.items():
        graph.add_node(node_id, lat=coords["lat"], lon=coords["lon"])

    for route_type, stop_ids in routes:
        speed = speeds.get(route_type, 20.0)
        for i in range(len(stop_ids) - 1):
            u = stop_ids[i]
            v = stop_ids[i + 1]
            if u not in stops or v not in stops:
                continue
            dist_km = _haversine_km(
                stops[u]["lat"],
                stops[u]["lon"],
                stops[v]["lat"],
                stops[v]["lon"],
            )
            tt_min = (dist_km / speed) * 60.0
            # Keep shortest edge if multiple routes connect the same stops.
            if graph.has_edge(u, v):
                if tt_min < graph[u][v]["travel_time_min"]:
                    graph[u][v]["travel_time_min"] = tt_min
            else:
                graph.add_edge(u, v, travel_time_min=tt_min)

    return graph


def download_transit(cfg: dict) -> Path:
    """Download stop graph and save as GraphML."""
    name = cfg["study_area"]["name"]
    transit_cfg = cfg.get("transit", {})
    route_types: list[str] = transit_cfg.get(
        "route_types", ["bus", "train", "tram", "ferry"]
    )
    speeds: dict[str, float] = {
        rt: float(transit_cfg.get(f"{rt}_speed_kmh", 20.0)) for rt in route_types
    }

    output = Path(f"data/processed/{name}_transit_stops.graphml")
    output.parent.mkdir(parents=True, exist_ok=True)

    boundaries = Path(f"data/raw/{name}_gemeenten.geojson")
    poly_str = _build_polygon_str(boundaries)

    print(f"Querying Overpass for route types: {route_types} …")
    response = _query_overpass(poly_str, route_types)

    stops = _extract_stops(response)
    routes = _extract_routes(response)
    print(f"Found {len(stops)} stop nodes and {len(routes)} route relations")

    graph = _build_stop_graph(routes, stops, speeds)

    if graph.number_of_nodes() == 0:
        print("Warning: no transit stops found — writing empty graph")

    nx.write_graphml(graph, str(output))
    print(
        f"Saved transit stop graph "
        f"({graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges)"
        f" to {output}"
    )
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download transit stop graph.")
    parser.parse_known_args()
    cfg = load_config()
    download_transit(cfg)
