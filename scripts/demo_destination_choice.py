"""Demo: travel-time-enriched destination choice prompt.

Builds a small mock scenario and prints the exact prompt that
would be sent to the LLM, so you can verify travel times and
sampled candidates appear correctly.

Run with:
    uv run python scripts/demo_destination_choice.py
"""

from __future__ import annotations

import json
import random

import numpy as np

from aibm.activity import Activity
from aibm.agent import Agent
from aibm.poi import POI
from aibm.skim import Skim
from aibm.zone import Zone


class _CapturingClient:
    """Fake LLM client that captures the prompt."""

    def __init__(self) -> None:
        self.last_prompt: str | None = None

    def generate_json(
        self,
        *,
        model: str,
        prompt: str,
        schema: dict,  # type: ignore[type-arg]
    ) -> str:
        self.last_prompt = prompt
        return json.dumps(
            {
                "destination_id": "zone:Z1",
                "reasoning": "(mock — not a real LLM call)",
            }
        )


def main() -> None:
    # 1. Build a 3-zone skim (minutes).
    car_matrix = np.array(
        [
            [0.0, 8.0, 22.0],
            [8.0, 0.0, 15.0],
            [22.0, 15.0, 0.0],
        ]
    )
    bike_matrix = np.array(
        [
            [0.0, 18.0, 45.0],
            [18.0, 0.0, 30.0],
            [45.0, 30.0, 0.0],
        ]
    )
    zone_ids = ["Z1", "Z2", "Z3"]
    skims = [
        Skim(mode="car", matrix=car_matrix, zone_ids=zone_ids),
        Skim(mode="bike", matrix=bike_matrix, zone_ids=zone_ids),
    ]

    # 2. Create zones and POIs.
    zones = [
        Zone(
            id="Z1",
            name="Middelburg Centre",
            x=0.0,
            y=0.0,
            land_use={"commercial": True, "residential": True},
        ),
        Zone(
            id="Z2",
            name="Vlissingen",
            x=1.0,
            y=1.0,
            land_use={"commercial": True, "residential": False},
        ),
        Zone(
            id="Z3",
            name="Veere",
            x=2.0,
            y=2.0,
            land_use={
                "commercial": False,
                "residential": True,
            },
        ),
    ]
    pois = [
        POI(
            id="p1",
            name="Albert Heijn Middelburg",
            x=0.0,
            y=0.0,
            activity_type="shopping",
            zone_id="Z1",
        ),
        POI(
            id="p2",
            name="Jumbo Vlissingen",
            x=1.0,
            y=1.0,
            activity_type="shopping",
            zone_id="Z2",
        ),
    ]

    # 3. Create agent and activity.
    agent = Agent(
        name="Jan",
        age=35,
        employment="employed",
        has_license=True,
        home_zone="Z1",
        work_zone="Z2",
        persona="Practical commuter who prefers short trips.",
    )
    activity = Activity(type="shopping")

    # 4. Call choose_destination with a capturing client.
    client = _CapturingClient()
    agent.choose_destination(
        activity,
        candidates=zones,
        pois=pois,
        client=client,  # type: ignore[arg-type]
        skims=skims,
        current_zone="Z2",  # agent is at work
        n_candidates=10,
        rng=random.Random(42),
    )

    # 5. Print the captured prompt.
    print("=" * 60)
    print("PROMPT SENT TO LLM")
    print("=" * 60)
    print(client.last_prompt)
    print("=" * 60)


if __name__ == "__main__":
    main()
