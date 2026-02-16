"""Generate a synthetic population for Veere and write outputs to data/."""

from pathlib import Path

from synth_pop import fetch_residential_buildings, generate_population, write_outputs

PLACE = "Veere, Zeeland, Netherlands"
OUTPUT_DIR = Path(__file__).parent.parent / "data"


def main() -> None:
    print(f"Fetching residential buildings for '{PLACE}'...")
    buildings = fetch_residential_buildings(PLACE)
    print(f"  Found {len(buildings)} buildings.")

    print("Generating synthetic population...")
    households, persons = generate_population(buildings, seed=42)
    print(f"  Generated {len(households)} households and {len(persons)} persons.")

    print(f"Writing outputs to {OUTPUT_DIR} ...")
    write_outputs(households, persons, buildings, OUTPUT_DIR)
    print("Done.")


if __name__ == "__main__":
    main()
