"""Shared config-loading helper for workflow scripts."""

import argparse

import yaml


def load_config(default: str = "workflow/config.yaml") -> dict:
    """Parse --config flag and return the loaded YAML as a dict."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", default=default)
    args, _ = parser.parse_known_args()
    with open(args.config) as f:
        return yaml.safe_load(f)
