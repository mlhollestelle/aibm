"""Generate a Mermaid diagram illustrating the LLM-based ABM simulation workflow.

Reads real simulation output from ``data/processed/`` (Parquet files produced
by the Walcheren pipeline) and writes a Markdown file with Mermaid diagrams
plus annotated LLM prompt/response examples.

Usage
-----
    python generate_diagram.py [--output MODEL_DIAGRAM.md] \
        [--data-dir data/processed]

Dependencies
------------
The script requires pandas and pyarrow, which are part of the pipeline
dependency group.  Install with::

    uv sync --group pipeline

The pipeline parquet files must exist before running this script.  Generate
them with::

    uv run snakemake --cores 1 -s workflow/Snakefile
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

STUDY_AREA = "walcheren"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mins_to_hm(minutes: float) -> str:
    """Convert minutes-since-midnight to HH:MM string."""
    h = int(minutes) // 60
    m = int(minutes) % 60
    return f"{h:02d}:{m:02d}"


def _truncate(text: str, max_chars: int = 1_400) -> str:
    """Trim a prompt to *max_chars*, appending a marker if shortened."""
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[… truncated for brevity]"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_simulation_data(
    data_dir: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    """Load a representative household and prompt examples from pipeline output.

    Parameters
    ----------
    data_dir:
        Directory containing the ``walcheren_*.parquet`` output files.

    Returns
    -------
    household:
        Household metadata (id, home_zone, num_vehicles, income_level, members).
    examples:
        Mapping of example name → ``{"prompt": str, "response": str}``.
    """
    try:
        import pandas as pd  # noqa: PLC0415
    except ImportError:
        sys.exit("pandas is required.  Install with:  uv sync --group pipeline")

    def _load(name: str) -> "pd.DataFrame":
        path = data_dir / f"{STUDY_AREA}_{name}.parquet"
        if not path.exists():
            sys.exit(
                f"File not found: {path}\n"
                "Run the pipeline first:  "
                "uv run snakemake --cores 1 -s workflow/Snakefile"
            )
        return pd.read_parquet(path)

    dp = _load("day_plans")
    trips = _load("trips")
    acts = _load("activities")
    sample = _load("sample")

    # Normalise household_id to str in all DataFrames to avoid type mismatches
    dp["household_id"] = dp["household_id"].astype(str)
    sample["household_id"] = sample["household_id"].astype(str)
    if "household_id" in trips.columns:
        trips["household_id"] = trips["household_id"].astype(str)
    if "household_id" in acts.columns:
        acts["household_id"] = acts["household_id"].astype(str)

    # ------------------------------------------------------------------ #
    # Main household — pick the one with the most simulated members
    # ------------------------------------------------------------------ #
    hh_counts = dp.groupby("household_id").size()
    main_hh_id = str(hh_counts.idxmax())
    members_df = dp[dp["household_id"] == main_hh_id].reset_index(drop=True)

    sample_row = sample[sample["household_id"] == main_hh_id].iloc[0]

    household: dict[str, Any] = {
        "id": f"HH-{main_hh_id}",
        "home_zone": sample_row["home_zone"],
        "num_vehicles": int(sample_row["num_vehicles"]),
        "income_level": sample_row["income_level"],
        "members": [
            {
                "name": row["name"],
                "age": int(row["age"]),
                "employment": row["employment"],
                "has_license": bool(row["has_license"]),
                "persona": row["persona"],
                "agent_id": row["agent_id"],
            }
            for _, row in members_df.iterrows()
        ],
    }

    # ------------------------------------------------------------------ #
    # Focus agent — employed/student member with the most activities
    # ------------------------------------------------------------------ #
    act_counts = acts.groupby("agent_id").size()
    best_row = members_df.iloc[0]
    best_n = -1
    for _, row in members_df.iterrows():
        if row["employment"] not in ("employed", "student"):
            continue
        n = act_counts.get(row["agent_id"], 0)
        if n > best_n:
            best_n = n
            best_row = row

    agent_id = best_row["agent_id"]
    agent_acts = (
        acts[acts["agent_id"] == agent_id]
        .sort_values("activity_seq")
        .reset_index(drop=True)
    )

    # ------------------------------------------------------------------ #
    # Reconstruct LLM responses from parsed simulation output
    # ------------------------------------------------------------------ #
    act_list = [
        {"type": r["activity_type"], "is_flexible": bool(r["is_flexible"])}
        for _, r in agent_acts.iterrows()
    ]

    mandatory_sched = {
        "activities": [
            {
                "type": r["activity_type"],
                "start_time": _mins_to_hm(r["start_time"]),
                "end_time": _mins_to_hm(r["end_time"]),
            }
            for _, r in agent_acts[~agent_acts["is_flexible"]].iterrows()
        ]
    }

    discr_response: dict[str, Any] = {
        "activities": [
            {
                "type": r["activity_type"],
                "destination_id": (
                    str(r["poi_id"]) if pd.notna(r["poi_id"]) else r["location"]
                ),
                "start_time": _mins_to_hm(r["start_time"]),
                "end_time": _mins_to_hm(r["end_time"]),
            }
            for _, r in agent_acts[agent_acts["is_flexible"]].iterrows()
        ]
    }

    # Mode choice: first trip for the focus agent
    agent_trips_df = trips[trips["agent_id"] == agent_id]
    trip_row = agent_trips_df.iloc[0]
    mode_response = {
        "choice": trip_row["mode"],
        "reasoning": trip_row["mode_reasoning"],
    }

    # ------------------------------------------------------------------ #
    # Vehicle allocation — first household with a non-empty prompt
    # ------------------------------------------------------------------ #
    first_mode_by_agent = trips.groupby("agent_id")["mode"].first()

    veh_prompt = ""
    veh_response: dict[str, Any] = {}
    veh_candidates = dp[dp["prompt_vehicle_alloc"].fillna("").str.len() > 50]
    if not veh_candidates.empty:
        veh_row = veh_candidates.iloc[0]
        veh_prompt = veh_row["prompt_vehicle_alloc"]
        veh_members = dp[dp["household_id"] == veh_row["household_id"]]
        allocations = []
        for _, lr in veh_members[veh_members["has_license"]].iterrows():
            mode = first_mode_by_agent.get(lr["agent_id"], "unknown")
            has_vehicle = mode == "car"
            allocations.append(
                {
                    "agent_id": lr["name"],
                    "tour_idx": 0,
                    "has_vehicle": has_vehicle,
                    "reasoning": (
                        "Needs the car for the work commute."
                        if has_vehicle
                        else f"Leisure trips are manageable by {mode}."
                    ),
                }
            )
        veh_response = {"allocations": allocations}

    # Store the focus agent name so build_document uses the same agent
    household["focus_agent_name"] = best_row["name"]

    # ------------------------------------------------------------------ #
    # Build the examples dict
    # ------------------------------------------------------------------ #
    def _resp(d: dict) -> str:
        return json.dumps(d, indent=2, ensure_ascii=False)

    def _prompt(col: str) -> str:
        return _truncate(str(best_row[col] or ""))

    examples: dict[str, dict[str, str]] = {
        "persona": {
            "prompt": _prompt("prompt_persona"),
            "response": _resp({"persona": best_row["persona"]}),
        },
        "activities": {
            "prompt": _prompt("prompt_activities"),
            "response": _resp({"activities": act_list}),
        },
        "schedule": {
            "prompt": _prompt("prompt_schedule"),
            "response": _resp(mandatory_sched),
        },
        "discretionary": {
            "prompt": _prompt("prompt_discretionary"),
            "response": _resp(discr_response),
        },
        "mode_choice": {
            "prompt": _truncate(str(trip_row["prompt_mode"] or "")),
            "response": _resp(mode_response),
        },
        "vehicle_allocation": {
            "prompt": _truncate(veh_prompt),
            "response": _resp(veh_response),
        },
    }

    return household, examples


# ---------------------------------------------------------------------------
# Diagram builders
# ---------------------------------------------------------------------------


def phase_flowchart(household: dict[str, Any]) -> str:
    hh_label = (
        f"{household['id']}\\n"
        f"{household['num_vehicles']} vehicle(s) · "
        f"{len(household['members'])} members"
    )
    member_node_lines = [
        f'    A{i}["{m["name"]}\\n{m["employment"]} · '
        f'{"licensed" if m["has_license"] else "no licence"}"]'
        for i, m in enumerate(household["members"], 1)
    ]
    member_links = " & ".join(f"A{i}" for i in range(1, len(household["members"]) + 1))
    lines = [
        "```mermaid",
        "flowchart TD",
        f'    HH(["🏠 {hh_label}"])',
        "",
    ]
    lines.extend(member_node_lines)
    lines += [
        "",
        '    subgraph P1["Phase 1 — Individual day planning (per agent)"]',
        "        direction TB",
        '        S1["🤖 LLM: generate_persona()\\n→ behavioural profile"]',
        '        S2["🤖 LLM: generate_activities()\\n→ activity list"]',
        '        S3["🤖 LLM: schedule_activities()\\n→ timed mandatory schedule"]',
        '        S4["compute_time_windows()\\n→ free gaps"]',
        "        S5["
        '"🤖 LLM: plan_discretionary_activities()'
        '\\n→ fill gaps with optional stops"]',
        '        S6["build_tours()\\n→ home-based tour chains"]',
        "        S1 --> S2 --> S3 --> S4 --> S5 --> S6",
        "    end",
        "",
        '    subgraph P1a["Phase 1a — Joint activities (household)"]',
        '        J1["🤖 LLM: plan_joint_activities()\\n→ shared trips (0-2)"]',
        '        J2["Inject into member plans\\n& rebuild tours"]',
        "        J1 --> J2",
        "    end",
        "",
        '    subgraph P1b["Phase 1b — Escort planning (household)"]',
        '        E1["🤖 LLM: plan_escort_trips()\\n→ assign drop-off / pick-up"]',
        '        E2["Modify parent DayPlans\\n& rebuild tours"]',
        "        E1 --> E2",
        "    end",
        "",
        '    subgraph P2["Phase 2 — Vehicle allocation (household)"]',
        '        V1["🤖 LLM: allocate_vehicles()\\n→ who gets the car per tour"]',
        "    end",
        "",
        '    subgraph P3["Phase 3 — Mode choice (per agent × tour)"]',
        '        M1["🤖 LLM: choose_tour_mode()\\n→ car / bike / transit + reasoning"]',
        "    end",
        "",
        '    subgraph OUT["Output (Parquet)"]',
        '        O1[("📦 trips\\nOD · mode · times · reasoning")]',
        '        O2[("📦 day_plans\\nactivities · tours · prompts")]',
        '        O3[("📦 activities\\ntype · location · times")]',
        "    end",
        "",
        f"    {member_links} --> P1",
        "    P1 --> P1a --> P1b --> P2 --> P3",
        "    P3 --> OUT",
        "```",
        "",
    ]
    return "\n".join(lines)


def sequence_diagram(household: dict[str, Any]) -> str:
    members = household["members"][:3]  # cap at 3 for readability
    hh_id = household["id"]

    # Participant lines
    parts = [
        "    participant SIM as Simulator",
        f"    participant HH  as Household {hh_id}",
    ]
    part_ids = []
    for i, m in enumerate(members, 1):
        pid = f"A{i}"
        parts.append(f"    participant {pid}  as Agent: {m['name']}")
        part_ids.append((pid, m))
    parts.append("    participant LLM as 🤖 LLM (Claude / Gemini / GPT)")

    lines: list[str] = ["```mermaid", "sequenceDiagram", "    autonumber"]
    lines += parts
    lines.append("")

    # Phase 1 — individual planning for each agent
    lines.append("    Note over SIM,LLM: Phase 1 — Individual day planning")
    for pid, m in part_ids:
        emp = m["employment"]
        mandatory = {"employed": "work", "student": "school"}.get(emp, "leisure")
        lines += [
            "",
            f"    SIM ->> {pid}: generate_persona()",
            f"    {pid} ->> LLM: prompt: demographics + household context",
            f'    LLM -->> {pid}: {{"persona": "{m["persona"][:60].rstrip()} …"}}',
            "",
            f"    SIM ->> {pid}: generate_activities()",
            f"    {pid} ->> LLM: prompt: persona + employment status",
            f'    LLM -->> {pid}: {{"activities": [{mandatory}, ...]}}',
            "",
            f"    SIM ->> {pid}: schedule_activities(mandatory)",
            f"    {pid} ->> LLM: prompt: activities + travel times",
            f'    LLM -->> {pid}: {{"activities": [{{{mandatory} timed}}]}}',
            "",
            f"    SIM ->> {pid}: plan_discretionary_activities()",
            f"    {pid} ->> LLM: prompt: schedule + free windows + nearby POIs",
            f'    LLM -->> {pid}: {{"activities": [discretionary stops]}}',
            "",
            f"    Note over {pid}: build_tours() — no LLM call",
        ]

    # Phase 1a — joint activities
    lines += [
        "",
        "    Note over SIM,LLM: Phase 1a — Joint activities",
        "",
        "    SIM ->> HH: plan_joint_activities()",
        "    HH ->> LLM: prompt: member schedules + POI candidates",
        '    LLM -->> HH: {"activities": [joint stop, if any]}',
    ]
    for pid, m in part_ids:
        lines.append(f"    HH ->> {pid}: inject joint activity + rebuild tours")

    # Phase 1b — escort planning
    lines += [
        "",
        "    Note over SIM,LLM: Phase 1b — Escort planning",
        "",
        "    SIM ->> HH: plan_escort_trips()",
        "    HH ->> LLM: prompt: members needing escort · available parents",
        "    LLM -->> HH: {escort assignments}",
        f"    HH ->> {part_ids[0][0]}: insert escort activities + rebuild tours",
    ]

    # Phase 2 — vehicle allocation
    lines += [
        "",
        "    Note over SIM,LLM: Phase 2 — Vehicle allocation",
        "",
        "    SIM ->> HH: allocate_vehicles()",
        f"    HH ->> LLM: prompt: {household['num_vehicles']} vehicle(s)"
        f" · licensed adults",
        '    LLM -->> HH: {"allocations": [agent → has_vehicle]}',
    ]

    # Phase 3 — mode choice
    lines += [
        "",
        "    Note over SIM,LLM: Phase 3 — Mode choice",
    ]
    for pid, m in part_ids:
        lines += [
            "",
            f"    SIM ->> {pid}: choose_tour_mode(tour 0)",
            f"    {pid} ->> LLM: prompt: tour OD + travel times + vehicle access",
            f'    LLM -->> {pid}: {{"choice": "...", "reasoning": "..."}}',
        ]

    lines += [
        "",
        "    SIM ->> SIM: write trips / day_plans / activities → Parquet",
        "```",
    ]

    return "\n".join(lines) + "\n"


def prompt_example_block(
    title: str, key: str, examples: dict[str, dict[str, str]]
) -> str:
    ex = examples[key]
    prompt_text = ex["prompt"].rstrip()
    response_text = ex["response"].rstrip()
    return (
        f"### {title}\n"
        "\n"
        "**Prompt sent to LLM**\n"
        "\n"
        "```\n"
        f"{prompt_text}\n"
        "```\n"
        "\n"
        "**LLM response (structured JSON)**\n"
        "\n"
        "```json\n"
        f"{response_text}\n"
        "```\n"
    )


# ---------------------------------------------------------------------------
# Full document
# ---------------------------------------------------------------------------


def build_document(
    household: dict[str, Any],
    examples: dict[str, dict[str, str]],
) -> str:
    members = household["members"]
    hh_info = (
        f"{household['num_vehicles']} vehicle(s) · "
        f"{household['income_level']} income · "
        f"home zone {household['home_zone']}"
    )

    # Member table
    header = "| | " + " | ".join(m["name"] for m in members) + " |"
    sep = "|---|" + "---|" * len(members)
    age_row = "| Age | " + " | ".join(str(m["age"]) for m in members) + " |"
    emp_row = "| Employment | " + " | ".join(m["employment"] for m in members) + " |"
    lic_row = (
        "| Licence | "
        + " | ".join("✓" if m["has_license"] else "—" for m in members)
        + " |"
    )
    member_table = "\n".join([header, sep, age_row, emp_row, lic_row])

    # Use the same focus agent chosen by load_simulation_data
    focus_name = household.get("focus_agent_name")
    focus = next(
        (m for m in members if m["name"] == focus_name),
        members[0],
    )

    # Build sections without dedent to avoid interpolation stripping issues.
    # member_table has no leading whitespace so dedent would strip nothing.
    sections: list[str] = []

    sections.append(
        "# AIBM — LLM-Based Agent-Based Travel Demand Model\n"
        "\n"
        "> Every behavioural decision in this model — persona, activity\n"
        "> list, schedule, destination, and mode — is made by an LLM via a\n"
        "> structured JSON prompt.  The diagrams and examples below walk\n"
        "> through one household's day from start to finish.\n"
        ">\n"
        "> **Data source:** real output from the Walcheren simulation run.\n"
        "> Regenerate with `python generate_diagram.py`.\n"
        "\n"
        "---\n"
        "\n"
        "## Household used in the examples\n"
        "\n"
        f"{member_table}\n"
        "\n"
        f"**Household {household['id']}:** {hh_info}\n"
        "\n"
        "---\n"
        "\n"
        "## 1 · Simulation phases\n"
    )
    sections.append(phase_flowchart(household))
    sections.append(
        f"---\n\n## 2 · End-to-end sequence for household {household['id']}\n"
    )
    sections.append(sequence_diagram(household))
    sections.append(
        "---\n"
        "\n"
        "## 3 · Example LLM interactions\n"
        "\n"
        "Each step below shows the exact prompt sent to the language model\n"
        "and the structured JSON it returns.  Prompts are taken directly\n"
        "from the simulation run; responses are reconstructed from the\n"
        f"parsed output.  Focus agent: **{focus['name']}**"
        f" (age {focus['age']}, {focus['employment']}).\n"
    )
    sections.append(
        prompt_example_block(
            f"3.1 Persona generation ({focus['name']})", "persona", examples
        )
    )
    sections.append(
        prompt_example_block(
            f"3.2 Activity list ({focus['name']})", "activities", examples
        )
    )
    sections.append(
        prompt_example_block(
            f"3.3 Schedule mandatory activities ({focus['name']})",
            "schedule",
            examples,
        )
    )
    sections.append(
        prompt_example_block(
            f"3.4 Plan discretionary activities ({focus['name']})",
            "discretionary",
            examples,
        )
    )
    sections.append(
        prompt_example_block(
            f"3.5 Mode choice — {focus['name']}'s first tour",
            "mode_choice",
            examples,
        )
    )

    if examples["vehicle_allocation"]["prompt"]:
        sections.append(
            prompt_example_block(
                "3.6 Vehicle allocation (household)",
                "vehicle_allocation",
                examples,
            )
        )

    sections.append(
        "---\n"
        "\n"
        "## 4 · What makes this approach powerful\n"
        "\n"
        "* **No hand-coded rules** — behavioural heterogeneity emerges from\n"
        "  the LLM's world knowledge conditioned on demographics and context.\n"
        "* **Traceable reasoning** — every decision comes with a `reasoning`\n"
        "  field, making the model interpretable by design.\n"
        "* **Any LLM back-end** — swap Claude, Gemini, or GPT by changing\n"
        "  one config value; the `LLMClient` protocol keeps the rest of the\n"
        "  code identical.\n"
        "* **Rich context** — prompts include land-use labels, POI names,\n"
        "  real travel times, and household dynamics that would be painful\n"
        "  to encode in traditional utility functions.\n"
        "* **Incremental refinement** — improving a decision step means\n"
        "  editing a prompt template, not retraining a model.\n"
        "\n"
        "---\n"
        "\n"
        "## 5 · How to regenerate this document\n"
        "\n"
        "```bash\n"
        "# Install pipeline dependencies (pandas, pyarrow, snakemake, …)\n"
        "uv sync --group pipeline\n"
        "\n"
        "# Run the full Walcheren pipeline (produces the parquet files)\n"
        "uv run snakemake --cores 1 -s workflow/Snakefile\n"
        "\n"
        "# Regenerate this diagram document\n"
        "python generate_diagram.py\n"
        "```\n"
    )

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a Mermaid diagram of the AIBM simulation workflow "
            "using real pipeline output."
        )
    )
    parser.add_argument(
        "--output",
        default="MODEL_DIAGRAM.md",
        help="Output Markdown file (default: MODEL_DIAGRAM.md)",
    )
    parser.add_argument(
        "--data-dir",
        default="data/processed",
        type=Path,
        help=(
            "Directory containing walcheren_*.parquet files (default: data/processed)"
        ),
    )
    args = parser.parse_args()

    print(f"Loading simulation data from {args.data_dir} …")
    household, examples = load_simulation_data(args.data_dir)
    print(f"Loaded household {household['id']} ({len(household['members'])} members)")

    content = build_document(household, examples)

    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(content)

    print(f"Diagram written to {args.output}")


if __name__ == "__main__":
    main()
