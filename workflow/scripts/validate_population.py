"""Validate synthesised population and produce a summary report.

Reads the population parquet and zone specs parquet, runs hard checks
(exits non-zero on failure) and prints a human-readable summary report.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# isort: split

import pandas as pd
from _config import load_config

VALID_EMPLOYMENT = {"employed", "student", "retired", "unemployed"}
VALID_INCOME = {"low", "medium", "high"}


def _section(title: str) -> str:
    bar = "=" * 60
    return f"\n{bar}\n{title}\n{bar}"


def validate(pop_path: Path, specs_path: Path, output_path: Path) -> None:
    """Run hard checks and write a summary report.

    Exits with code 1 if any hard check fails.
    """
    pop = pd.read_parquet(pop_path)
    specs = pd.read_parquet(specs_path)

    lines: list[str] = []
    errors: list[str] = []

    # ------------------------------------------------------------------
    # Hard checks
    # ------------------------------------------------------------------

    # Age range
    bad_age = pop[(pop["age"] < 0) | (pop["age"] > 120)]
    if not bad_age.empty:
        errors.append(f"Age outside 0–120: {len(bad_age)} agent(s) affected.")

    # Employment values
    bad_emp = pop[~pop["employment"].isin(VALID_EMPLOYMENT)]
    if not bad_emp.empty:
        errors.append(
            f"Invalid employment value(s): {bad_emp['employment'].unique().tolist()}"
        )

    # Income values
    hh = pop.drop_duplicates("household_id")
    bad_inc = hh[~hh["income_level"].isin(VALID_INCOME)]
    if not bad_inc.empty:
        errors.append(
            f"Invalid income_level value(s): "
            f"{bad_inc['income_level'].unique().tolist()}"
        )

    # Missing home_zone
    missing_zone = pop[pop["home_zone"].isna()]
    if not missing_zone.empty:
        errors.append(f"Missing home_zone: {len(missing_zone)} agent(s) affected.")

    # Under-18 with license
    underage_licensed = pop[(pop["age"] < 18) & (pop["has_license"])]
    if not underage_licensed.empty:
        errors.append(
            f"Agent(s) under 18 with has_license=True: {len(underage_licensed)} found."
        )

    # 65+ not retired
    senior_not_retired = pop[(pop["age"] >= 65) & (pop["employment"] != "retired")]
    if not senior_not_retired.empty:
        errors.append(
            f"Agent(s) aged ≥65 not retired: {len(senior_not_retired)} found."
        )

    # Age 4–17 not student
    youth_not_student = pop[
        (pop["age"] >= 4) & (pop["age"] <= 17) & (pop["employment"] != "student")
    ]
    if not youth_not_student.empty:
        errors.append(
            f"Agent(s) aged 4–17 not a student: {len(youth_not_student)} found."
        )

    # Household with no adult (18+)
    adults_per_hh = pop[pop["age"] >= 18].groupby("household_id").size()
    all_hh_ids = pop["household_id"].unique()
    childonly_hh = set(all_hh_ids) - set(adults_per_hh.index)
    if childonly_hh:
        errors.append(f"Household(s) with no adult (18+): {len(childonly_hh)} found.")

    # ------------------------------------------------------------------
    # Summary sections
    # ------------------------------------------------------------------

    n_agents = len(pop)
    n_households = pop["household_id"].nunique()
    n_zones = specs["zone_id"].nunique() if "zone_id" in specs.columns else "n/a"

    lines.append(_section("Population Summary"))
    lines.append(f"  Total zones      : {n_zones}")
    lines.append(f"  Total households : {n_households}")
    lines.append(f"  Total agents     : {n_agents}")

    # Household size distribution
    hh_size = pop.groupby("household_id").size()
    lines.append(_section("Household Size Distribution"))
    size_counts = hh_size.value_counts().sort_index()
    for size, count in size_counts.items():
        pct = 100 * count / n_households
        lines.append(f"  {size} person(s) : {count:>6}  ({pct:.1f}%)")

    # Age bracket breakdown
    lines.append(_section("Age Bracket Breakdown"))
    brackets = [
        ("0–17", (0, 17)),
        ("18–64", (18, 64)),
        ("65+", (65, 120)),
    ]
    for label, (lo, hi) in brackets:
        n = ((pop["age"] >= lo) & (pop["age"] <= hi)).sum()
        pct = 100 * n / n_agents
        lines.append(f"  {label:>6} : {n:>6}  ({pct:.1f}%)")

    # Employment breakdown
    lines.append(_section("Employment Breakdown"))
    emp_counts = pop["employment"].value_counts()
    for emp, count in emp_counts.items():
        pct = 100 * count / n_agents
        lines.append(f"  {emp:<12} : {count:>6}  ({pct:.1f}%)")

    # License rate (adults 18+)
    adults = pop[pop["age"] >= 18]
    license_rate = adults["has_license"].mean() * 100
    lines.append(_section("Driving Licence Rate (Adults 18+)"))
    lines.append(
        f"  {adults['has_license'].sum()} / {len(adults)} adults  ({license_rate:.1f}%)"
    )

    # Vehicle distribution per household
    lines.append(_section("Vehicles per Household"))
    veh_counts = hh["num_vehicles"].value_counts().sort_index()
    for n_veh, count in veh_counts.items():
        pct = 100 * count / n_households
        lines.append(f"  {n_veh} vehicle(s) : {count:>6}  ({pct:.1f}%)")

    # Income distribution per household
    lines.append(_section("Income Distribution (Households)"))
    inc_counts = hh["income_level"].value_counts()
    for inc, count in inc_counts.items():
        pct = 100 * count / n_households
        lines.append(f"  {inc:<8} : {count:>6}  ({pct:.1f}%)")

    # Zone summary
    agents_per_zone = pop.groupby("home_zone").size()
    lines.append(_section("Zone Summary (Agents per Zone)"))
    lines.append(f"  Mean   : {agents_per_zone.mean():.1f}")
    lines.append(
        f"  Min    : {agents_per_zone.min()} (zone {agents_per_zone.idxmin()})"
    )
    lines.append(
        f"  Max    : {agents_per_zone.max()} (zone {agents_per_zone.idxmax()})"
    )

    # ------------------------------------------------------------------
    # Hard-check result
    # ------------------------------------------------------------------

    lines.append(_section("Validation Result"))
    if errors:
        lines.append("  FAILED — the following hard checks did not pass:")
        for err in errors:
            lines.append(f"    ✗ {err}")
    else:
        lines.append("  PASSED — all hard checks OK.")

    report = "\n".join(lines) + "\n"

    print(report)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"Report written to {output_path}")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    cfg = load_config()
    name = cfg["study_area"]["name"]
    validate(
        pop_path=Path(f"data/processed/{name}_population.parquet"),
        specs_path=Path(f"data/processed/{name}_zone_specs.parquet"),
        output_path=Path(f"data/processed/{name}_population_report.txt"),
    )
