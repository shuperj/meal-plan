#!/usr/bin/env python3
"""
Meal plan configuration manager.

Usage:
    python meal_config.py setup          # Interactive setup
    python meal_config.py show           # Show current config
    python meal_config.py set KEY VALUE  # Update a single value
    python meal_config.py reset          # Delete config

Programmatic:
    from meal_config import load_config
    config = load_config()  # Returns dict with all defaults
"""

import argparse
import json
import os
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

GENERIC_DEFAULTS = {
    "zip": "",
    "household": "",
    "meals": 5,
    "budget": 100,
    "diet": "",
    "friday_rule": "",
    "leftovers": "",
}

FIELD_PROMPTS = {
    "zip": ("ZIP code", "e.g. 90210"),
    "household": ("Household description", "e.g. 2 adults, 1 child"),
    "meals": ("Number of weeknight dinners", "default: 5"),
    "budget": ("Weekly grocery budget ($)", "default: 100"),
    "diet": ("Dietary preferences", "e.g. PCOS-friendly, high-protein, low-carb"),
    "friday_rule": (
        "Friday meal rule",
        "e.g. crock-pot / slow-cooker meal, or leave blank",
    ),
    "leftovers": (
        "Leftover strategy",
        "e.g. plan enough for next-day lunches, or leave blank",
    ),
}


def load_config():
    """Load config with fallbacks: config.json > env vars (ZIP) > generic defaults."""
    config = dict(GENERIC_DEFAULTS)

    if CONFIG_PATH.exists():
        saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        for key in GENERIC_DEFAULTS:
            if key in saved and saved[key] != "":
                config[key] = saved[key]

    # Env var override for ZIP (since it's also in .env for Kroger API)
    env_zip = os.getenv("KROGER_ZIP", "")
    if env_zip and not config["zip"]:
        config["zip"] = env_zip

    return config


def save_config(config):
    """Save config to config.json."""
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def cmd_setup(_args):
    """Interactive setup — prompt for each field."""
    existing = load_config()
    config = {}

    print("Meal plan configuration setup")
    print("Press Enter to keep the current/default value.\n")

    for key, (label, hint) in FIELD_PROMPTS.items():
        current = existing.get(key, GENERIC_DEFAULTS[key])
        if current:
            prompt = f"  {label} [{current}] ({hint}): "
        else:
            prompt = f"  {label} ({hint}): "

        value = input(prompt).strip()

        if value:
            # Coerce numeric fields
            if key == "meals":
                value = int(value)
            elif key == "budget":
                value = float(value)
            config[key] = value
        else:
            config[key] = current

    save_config(config)
    print(f"\nConfig saved to {CONFIG_PATH}")


def cmd_show(_args):
    """Display current config."""
    config = load_config()
    if not CONFIG_PATH.exists():
        print("No config.json found. Run 'python meal_config.py setup' to create one.")
        print("\nCurrent defaults:")

    for key, value in config.items():
        label = FIELD_PROMPTS.get(key, (key, ""))[0]
        display = value if value else "(not set)"
        print(f"  {label}: {display}")


def cmd_set(args):
    """Update a single config value."""
    key = args.key
    value = args.value

    if key not in GENERIC_DEFAULTS:
        print(f"Unknown key: {key}")
        print(f"Valid keys: {', '.join(GENERIC_DEFAULTS.keys())}")
        sys.exit(1)

    config = load_config()

    # Coerce numeric fields
    if key == "meals":
        value = int(value)
    elif key == "budget":
        value = float(value)

    config[key] = value
    save_config(config)
    label = FIELD_PROMPTS.get(key, (key, ""))[0]
    print(f"Updated {label}: {value}")


def cmd_reset(_args):
    """Delete config.json."""
    if CONFIG_PATH.exists():
        CONFIG_PATH.unlink()
        print(f"Deleted {CONFIG_PATH}")
    else:
        print("No config.json to delete.")


def main():
    parser = argparse.ArgumentParser(description="Meal plan configuration")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup", help="Interactive setup")
    sub.add_parser("show", help="Show current config")

    set_parser = sub.add_parser("set", help="Set a config value")
    set_parser.add_argument(
        "key", help=f"Config key ({', '.join(GENERIC_DEFAULTS.keys())})"
    )
    set_parser.add_argument("value", help="New value")

    sub.add_parser("reset", help="Delete config")

    args = parser.parse_args()

    commands = {
        "setup": cmd_setup,
        "show": cmd_show,
        "set": cmd_set,
        "reset": cmd_reset,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
