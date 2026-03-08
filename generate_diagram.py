"""Generate a Mermaid diagram illustrating the LLM-based ABM simulation workflow.

Run with:
    python generate_diagram.py [--output MODEL_DIAGRAM.md]

The output is a Markdown file containing multiple Mermaid diagrams plus
example LLM prompts and responses that demonstrate how agents make decisions.
"""

import argparse
from textwrap import dedent


# ---------------------------------------------------------------------------
# Example data – a small fictional household used throughout the diagrams
# ---------------------------------------------------------------------------

HOUSEHOLD = {
    "id": "HH-042",
    "home_zone": "zone:1042",
    "num_vehicles": 1,
    "income_level": "middle",
    "members": [
        {
            "name": "Emma",
            "age": 38,
            "employment": "employed",
            "has_license": True,
        },
        {
            "name": "Liam",
            "age": 40,
            "employment": "employed",
            "has_license": True,
        },
        {
            "name": "Sophie",
            "age": 9,
            "employment": "student",
            "has_license": False,
        },
    ],
}

EXAMPLES = {
    "persona": {
        "prompt": dedent("""\
            You are modelling a person in an agent-based travel demand model.

            ## Agent
            Name: Emma | Age: 38 | Employment: employed | Has licence: true

            ## Household
            Home zone: zone:1042 | Vehicles: 1 | Income: middle
            Members: Emma (38, employed), Liam (40, employed), Sophie (9, student)

            Generate a short behavioural persona (1–2 sentences) for this agent.
            Respond with JSON matching the schema: {"persona": string}
        """),
        "response": dedent("""\
            {
              "persona": "Emma is a pragmatic working mother who carefully
                balances professional commitments with family duties,
                preferring efficient routes and reliable modes of transport
                to keep her day on schedule."
            }
        """),
    },
    "activities": {
        "prompt": dedent("""\
            You are modelling a person in an agent-based travel demand model.

            ## Agent
            Name: Emma | Age: 38 | Employment: employed | Has licence: true
            Persona: Emma is a pragmatic working mother who carefully balances
            professional commitments with family duties …

            List the activities Emma is likely to perform today (work is mandatory).
            Respond with JSON matching the schema:
            {"activities": [{"type": string, "is_flexible": boolean}]}
            Activity types: work | school | shopping | leisure |
                            eating_out | personal_business | escort
        """),
        "response": dedent("""\
            {
              "activities": [
                {"type": "escort",   "is_flexible": false},
                {"type": "work",     "is_flexible": false},
                {"type": "shopping", "is_flexible": true},
                {"type": "escort",   "is_flexible": false}
              ]
            }
        """),
    },
    "schedule": {
        "prompt": dedent("""\
            You are modelling a person in an agent-based travel demand model.

            ## Agent
            Name: Emma | Age: 38 | Employment: employed

            ## Activities to schedule
            1. escort       – not flexible
            2. work         – not flexible  (duration: 360–540 min)
            3. escort       – not flexible

            ## Travel times from home (minutes)
            school zone → 8 min (bike) | work zone → 22 min (car/transit)

            Assign realistic start and end times (minutes from midnight).
            Respond with JSON:
            {"activities": [{"type": string, "start_time": int, "end_time": int}]}
        """),
        "response": dedent("""\
            {
              "activities": [
                {"type": "escort",  "start_time": 465, "end_time": 490},
                {"type": "work",    "start_time": 510, "end_time": 1020},
                {"type": "escort",  "start_time": 915, "end_time": 940}
              ]
            }
        """),
    },
    "discretionary": {
        "prompt": dedent("""\
            You are modelling a person in an agent-based travel demand model.

            ## Agent
            Name: Emma | Age: 38 | Employment: employed

            ## Fixed schedule
            07:45  drop-off Sophie at school
            08:30  work  →  17:00
            15:15  pick-up Sophie

            ## Free time windows
            Window A: 07:45 – 08:30  (45 min, near school)
            Window B: 17:00 – 22:00  (300 min, at work zone)

            ## Nearby POIs
            Window A – shopping: Albert Heijn (4 min), Jumbo (7 min)
            Window B – eating_out: Pizzeria Roma (3 min), De Kaai (8 min)
                        leisure: Sportcentrum Middelburg (12 min)

            Plan 0–2 discretionary activities that fit the windows.
            Respond with JSON:
            {"activities": [{"type": string, "destination_id": string,
                             "start_time": int, "end_time": int}]}
        """),
        "response": dedent("""\
            {
              "activities": [
                {
                  "type": "shopping",
                  "destination_id": "poi:albert_heijn_1",
                  "start_time": 470,
                  "end_time": 500
                },
                {
                  "type": "eating_out",
                  "destination_id": "poi:pizzeria_roma_1",
                  "start_time": 1020,
                  "end_time": 1065
                }
              ]
            }
        """),
    },
    "mode_choice": {
        "prompt": dedent("""\
            You are modelling a person in an agent-based travel demand model.

            ## Agent
            Name: Emma | Age: 38 | Has licence: true

            ## Household
            Vehicles available for this tour: 1 of 1

            ## Tour
            home (zone:1042) → work (zone:2011) → home (zone:1042)
            Distance: ~18 km

            ## Available modes and travel times
            car:     28 min   (door-to-door)
            transit: 41 min   (bus + walk)
            bike:    62 min

            Choose a mode. Respond with JSON:
            {"choice": string, "reasoning": string}
        """),
        "response": dedent("""\
            {
              "choice": "car",
              "reasoning": "Given the 18 km distance and the tight morning
                schedule with school drop-off, the car is the most practical
                choice to stay on time. Transit would add 13 extra minutes
                each way."
            }
        """),
    },
    "vehicle_allocation": {
        "prompt": dedent("""\
            You are modelling a household in an agent-based travel demand model.

            ## Household
            Vehicles: 1 | Licensed adults: Emma, Liam

            ## Tours today
            Emma  – tour 0: home → school → work → home  (needs car: likely)
            Liam  – tour 0: home → work → home            (needs car: likely)

            Allocate the single vehicle across competing tours.
            Respond with JSON:
            {"allocations": [{"agent_id": string, "tour_idx": int,
                               "has_vehicle": boolean, "reasoning": string}]}
        """),
        "response": dedent("""\
            {
              "allocations": [
                {
                  "agent_id": "emma",
                  "tour_idx": 0,
                  "has_vehicle": true,
                  "reasoning": "Emma needs the car to drop Sophie at school
                    on time before work."
                },
                {
                  "agent_id": "liam",
                  "tour_idx": 0,
                  "has_vehicle": false,
                  "reasoning": "Liam's workplace is well-served by transit;
                    he can manage without the car today."
                }
              ]
            }
        """),
    },
}


# ---------------------------------------------------------------------------
# Diagram builders
# ---------------------------------------------------------------------------

def phase_flowchart() -> str:
    return dedent("""\
        ```mermaid
        flowchart TD
            HH([🏠 Household HH-042\\n1 vehicle · 3 members])

            HH --> A1[👩 Emma\\nemployed · licensed]
            HH --> A2[👨 Liam\\nemployed · licensed]
            HH --> A3[👧 Sophie\\nstudent]

            subgraph P1["Phase 1 — Individual day planning (per agent)"]
                direction TB
                S1["🤖 LLM: generate_persona()\\n→ behavioural profile"]
                S2["🤖 LLM: generate_activities()\\n→ activity list"]
                S3["🤖 LLM: schedule_activities()\\n→ timed mandatory schedule"]
                S4["compute_time_windows()\\n→ free gaps"]
                S5["🤖 LLM: plan_discretionary_activities()\\n→ fill gaps with optional stops"]
                S6["build_tours()\\n→ home-based tour chains"]
                S1 --> S2 --> S3 --> S4 --> S5 --> S6
            end

            subgraph P1a["Phase 1a — Joint activities (household)"]
                J1["🤖 LLM: plan_joint_activities()\\n→ shared trips (0-2)"]
                J2["Inject into member plans\\n& rebuild tours"]
                J1 --> J2
            end

            subgraph P1b["Phase 1b — Escort planning (household)"]
                E1["🤖 LLM: plan_escort_trips()\\n→ assign drop-off / pick-up"]
                E2["Modify parent DayPlans\\n& rebuild tours"]
                E1 --> E2
            end

            subgraph P2["Phase 2 — Vehicle allocation (household)"]
                V1["🤖 LLM: allocate_vehicles()\\n→ who gets the car per tour"]
            end

            subgraph P3["Phase 3 — Mode choice (per agent × tour)"]
                M1["🤖 LLM: choose_tour_mode()\\n→ car / bike / transit + reasoning"]
            end

            subgraph OUT["Output (Parquet)"]
                O1[("📦 trips\\nOD · mode · times · reasoning")]
                O2[("📦 day_plans\\nactivities · tours · prompts")]
                O3[("📦 activities\\ntype · location · times")]
            end

            A1 & A2 & A3 --> P1
            P1 --> P1a --> P1b --> P2 --> P3
            P3 --> OUT
        ```
    """)


def sequence_diagram() -> str:
    return dedent("""\
        ```mermaid
        sequenceDiagram
            autonumber
            participant SIM as Simulator
            participant HH  as Household HH-042
            participant EM  as Agent: Emma
            participant LI  as Agent: Liam
            participant SP  as Agent: Sophie
            participant LLM as 🤖 LLM (Claude / Gemini / GPT)

            Note over SIM,LLM: Phase 1 — Individual day planning

            SIM ->> EM: generate_persona()
            EM ->> LLM: prompt: demographics + household context
            LLM -->> EM: {"persona": "pragmatic working mother …"}

            SIM ->> EM: generate_activities()
            EM ->> LLM: prompt: persona + employment status
            LLM -->> EM: {"activities": [escort, work, shopping, escort]}

            SIM ->> EM: schedule_activities(mandatory)
            EM ->> LLM: prompt: activities + travel times
            LLM -->> EM: {"activities": [{escort 07:45}, {work 08:30-17:00}, …]}

            SIM ->> EM: plan_discretionary_activities()
            EM ->> LLM: prompt: schedule + free windows + nearby POIs
            LLM -->> EM: {"activities": [{shopping 07:50}, {eating_out 17:00}]}

            Note over EM: build_tours() — no LLM call

            SIM ->> LI: generate_persona() … schedule_activities() … build_tours()
            LI ->> LLM: (same flow as Emma, omitted for brevity)
            LLM -->> LI: day plan

            SIM ->> SP: generate_persona() … build_tours()
            SP ->> LLM: (student flow)
            LLM -->> SP: day plan

            Note over SIM,LLM: Phase 1a — Joint activities

            SIM ->> HH: plan_joint_activities()
            HH ->> LLM: prompt: member schedules + POI candidates
            LLM -->> HH: {"activities": [{eating_out, Pizzeria Roma, 17:00, [Emma,Liam]}]}
            HH ->> EM: inject joint activity + rebuild tours
            HH ->> LI: inject joint activity + rebuild tours

            Note over SIM,LLM: Phase 1b — Escort planning

            SIM ->> HH: plan_escort_trips()
            HH ->> LLM: prompt: Sophie needs escort · available parents
            LLM -->> HH: {escort: Emma drops off, Emma picks up}
            HH ->> EM: insert escort activities + rebuild tours

            Note over SIM,LLM: Phase 2 — Vehicle allocation

            SIM ->> HH: allocate_vehicles()
            HH ->> LLM: prompt: 1 vehicle · Emma + Liam tours
            LLM -->> HH: {"allocations": [Emma=true, Liam=false]}

            Note over SIM,LLM: Phase 3 — Mode choice

            SIM ->> EM: choose_tour_mode(tour 0, has_vehicle=true)
            EM ->> LLM: prompt: tour OD + travel times + vehicle access
            LLM -->> EM: {"choice": "car", "reasoning": "tight morning schedule …"}

            SIM ->> LI: choose_tour_mode(tour 0, has_vehicle=false)
            LI ->> LLM: prompt: tour OD + travel times (no car available)
            LLM -->> LI: {"choice": "transit", "reasoning": "well-served by bus …"}

            SIM ->> SIM: write trips / day_plans / activities → Parquet
        ```
    """)


def prompt_example_block(title: str, key: str) -> str:
    ex = EXAMPLES[key]
    prompt_lines = ex["prompt"].rstrip()
    response_lines = ex["response"].rstrip()
    return dedent(f"""\
        ### {title}

        **Prompt sent to LLM**

        ```
        {prompt_lines}
        ```

        **LLM response (structured JSON)**

        ```json
        {response_lines}
        ```
    """)


# ---------------------------------------------------------------------------
# Full document
# ---------------------------------------------------------------------------

def build_document() -> str:
    sections: list[str] = []

    sections.append(dedent("""\
        # AIBM — LLM-Based Agent-Based Travel Demand Model

        > Every behavioural decision in this model — persona, activity list,
        > schedule, destination, and mode — is made by an LLM via a structured
        > JSON prompt.  The diagrams and examples below walk through one
        > household's day from start to finish.

        ---

        ## Household used in the examples

        | | Emma | Liam | Sophie |
        |---|---|---|---|
        | Age | 38 | 40 | 9 |
        | Employment | employed | employed | student |
        | Licence | ✓ | ✓ | — |

        **Household:** 1 vehicle · middle income · home zone 1042

        ---

        ## 1 · Simulation phases
    """))

    sections.append(phase_flowchart())

    sections.append(dedent("""\
        ---

        ## 2 · End-to-end sequence for household HH-042
    """))

    sections.append(sequence_diagram())

    sections.append(dedent("""\
        ---

        ## 3 · Example LLM interactions

        Each step below shows the exact prompt sent to the language model and
        the structured JSON it returns.  Outputs feed directly into the next
        step — no hand-coded rules.
    """))

    sections.append(
        prompt_example_block("3.1 Persona generation (Emma)", "persona")
    )
    sections.append(
        prompt_example_block("3.2 Activity list (Emma)", "activities")
    )
    sections.append(
        prompt_example_block(
            "3.3 Schedule mandatory activities (Emma)", "schedule"
        )
    )
    sections.append(
        prompt_example_block(
            "3.4 Plan discretionary activities (Emma)", "discretionary"
        )
    )
    sections.append(
        prompt_example_block("3.5 Mode choice — Emma's morning tour", "mode_choice")
    )
    sections.append(
        prompt_example_block(
            "3.6 Vehicle allocation (household)", "vehicle_allocation"
        )
    )

    sections.append(dedent("""\
        ---

        ## 4 · What makes this approach powerful

        * **No hand-coded rules** — behavioural heterogeneity emerges from the
          LLM's world knowledge conditioned on demographics and context.
        * **Traceable reasoning** — every decision comes with a `reasoning`
          field, making the model interpretable by design.
        * **Any LLM back-end** — swap Claude, Gemini, or GPT by changing one
          config value; the `LLMClient` protocol keeps the rest of the code
          identical.
        * **Rich context** — prompts can include land-use labels, POI names,
          real travel times, and household dynamics that would be painful to
          encode in traditional utility functions.
        * **Incremental refinement** — improving a decision step means editing
          a prompt template, not retraining a model.
    """))

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a Mermaid diagram of the AIBM simulation workflow."
    )
    parser.add_argument(
        "--output",
        default="MODEL_DIAGRAM.md",
        help="Output Markdown file (default: MODEL_DIAGRAM.md)",
    )
    args = parser.parse_args()

    content = build_document()

    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(content)

    print(f"Diagram written to {args.output}")


if __name__ == "__main__":
    main()
