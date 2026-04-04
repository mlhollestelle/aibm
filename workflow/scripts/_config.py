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


def _resolve_iteration(cfg: dict, iteration_path: Path, config_dir: Path) -> dict:
    """Merge an iteration YAML (with prompt-config includes) into *cfg*."""
    with open(iteration_path) as f:
        iter_cfg = yaml.safe_load(f) or {}

    # Resolve include_prompt_configs before other overrides
    for pc_name in iter_cfg.pop("include_prompt_configs", []):
        pc_path = config_dir / "prompt_configs" / f"{pc_name}.yaml"
        with open(pc_path) as f:
            pc = yaml.safe_load(f) or {}
        sim = cfg.get("simulation", {})
        cfg["simulation"] = _deep_merge(sim, pc)

    # Merge remaining iteration overrides (e.g. direct simulation.prompts)
    if iter_cfg:
        cfg = _deep_merge(cfg, iter_cfg)
    return cfg


def build_scenarios(cfg: dict) -> list[str]:
    """Build the provider×iteration cross-product from *cfg*.

    Respects ``only_iterations`` in provider YAMLs to restrict
    which iterations a provider participates in.
    """
    providers = cfg.get("providers", [])
    iterations = cfg.get("iterations", ["baseline"])
    scenarios: list[str] = []
    for p in providers:
        p_path = Path("workflow/providers") / f"{p}.yaml"
        if p_path.exists():
            with open(p_path) as f:
                p_cfg = yaml.safe_load(f) or {}
            allowed = p_cfg.get("only_iterations", iterations)
        else:
            allowed = iterations
        for i in iterations:
            if i in allowed:
                scenarios.append(f"{p}__{i}")
    return scenarios


def load_config(default: str = "workflow/config.yaml") -> dict:
    """Parse ``--config`` and optional ``--scenario``; return merged
    config.

    The *scenario* value may use the ``{provider}__{iteration}``
    format (new matrix style) or a plain name that maps to
    ``workflow/scenarios/{name}.yaml`` (legacy).
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", default=default)
    parser.add_argument("--scenario", default=None)
    args, _ = parser.parse_known_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    if args.scenario is None:
        return cfg

    config_dir = Path(args.config).parent

    if "__" in args.scenario:
        provider, iteration = args.scenario.split("__", 1)

        # 1. Merge provider config
        provider_path = config_dir / "providers" / f"{provider}.yaml"
        with open(provider_path) as f:
            p_cfg = yaml.safe_load(f) or {}
        # Strip non-simulation keys before merging
        p_cfg.pop("only_iterations", None)
        cfg = _deep_merge(cfg, p_cfg)

        # 2. Merge iteration config (with prompt-config resolution)
        iteration_path = config_dir / "iterations" / f"{iteration}.yaml"
        cfg = _resolve_iteration(cfg, iteration_path, config_dir)
    else:
        # Legacy: flat scenario in workflow/scenarios/
        scenario_path = config_dir / "scenarios" / f"{args.scenario}.yaml"
        with open(scenario_path) as f:
            cfg = _deep_merge(cfg, yaml.safe_load(f) or {})

    return cfg
