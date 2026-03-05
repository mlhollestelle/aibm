"""Shared config-loading helper for workflow scripts."""

import argparse
from pathlib import Path

import yaml


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*, returning a new dict."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(default: str = "workflow/config.yaml") -> dict:
    """Parse --config and optional --scenario flags; return merged config."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", default=default)
    parser.add_argument("--scenario", default=None)
    args, _ = parser.parse_known_args()
    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    if args.scenario is not None:
        scenario_path = Path(args.config).parent / "scenarios" / f"{args.scenario}.yaml"
        with open(scenario_path) as f:
            overrides = yaml.safe_load(f) or {}
        cfg = _deep_merge(cfg, overrides)
    return cfg
