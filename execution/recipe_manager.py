#!/usr/bin/env python3
"""
Recipe manager for Obsidian vault integration.

Usage:
    # List all recipes
    python recipe_manager.py list

    # Filter by tags, sort by last used
    python recipe_manager.py list --tags high-protein,pcos --sort last_used

    # Show a specific recipe
    python recipe_manager.py show "Chicken Stir Fry"

    # Save a new recipe (reads markdown body from stdin)
    echo "## Ingredients\n- 1 lb chicken" | python recipe_manager.py save \
        --name "Chicken Stir Fry" --servings 4 --tags "high-protein,quick" --source "manual"

    # Export recipes as JSON for meal_planner.py
    python recipe_manager.py export --names "Chicken Stir Fry,Taco Bowl"

    # Update last_used after incorporating into a meal plan
    python recipe_manager.py update-used "Chicken Stir Fry" "Taco Bowl"

Environment:
    RECIPE_VAULT_PATH - Path to Obsidian recipes folder
                        (default: ~/Documents/ShuperBrain/30 Resources/Recipes)
"""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from meal_config import load_env

load_env()

DEFAULT_VAULT_PATH = os.path.join(
    os.path.expanduser("~"), "Documents", "ShuperBrain", "30 Resources", "Recipes"
)

# --- YAML frontmatter parsing ---
# Try PyYAML for robust parsing, fall back to simple regex parser

try:
    import yaml

    def _parse_yaml(text):
        return yaml.safe_load(text) or {}

    def _dump_yaml(data):
        return yaml.dump(data, default_flow_style=False, sort_keys=False).rstrip()

except ImportError:

    def _parse_yaml(text):
        """Minimal YAML parser for flat key-value frontmatter."""
        result = {}
        for line in text.strip().split("\n"):
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                result[key] = [
                    v.strip().strip("\"'") for v in value[1:-1].split(",") if v.strip()
                ]
            elif value.isdigit():
                result[key] = int(value)
            elif value.startswith('"') and value.endswith('"'):
                result[key] = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                result[key] = value[1:-1]
            else:
                result[key] = value
        return result

    def _dump_yaml(data):
        """Minimal YAML serializer for flat key-value frontmatter."""
        lines = []
        for key, value in data.items():
            if isinstance(value, list):
                formatted = "[" + ", ".join(f'"{v}"' for v in value) + "]"
                lines.append(f"{key}: {formatted}")
            elif isinstance(value, int):
                lines.append(f"{key}: {value}")
            else:
                lines.append(f'{key}: "{value}"')
        return "\n".join(lines)


def get_vault_path():
    return Path(os.getenv("RECIPE_VAULT_PATH", DEFAULT_VAULT_PATH))


def parse_frontmatter(content):
    """Extract YAML frontmatter dict and markdown body from file content."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", content, re.DOTALL)
    if not match:
        return {}, content
    return _parse_yaml(match.group(1)), match.group(2)


def write_frontmatter(metadata, body):
    """Combine metadata dict and markdown body into a full file string."""
    return f"---\n{_dump_yaml(metadata)}\n---\n\n{body}"


def slugify(text):
    """Convert text to a filename-safe slug."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s]+", "-", text)
    return text.strip("-")


def load_all_recipes(vault_path):
    """Load all .md recipes from the vault directory."""
    if not vault_path.exists():
        return []
    recipes = []
    for md_file in sorted(vault_path.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(content)
        recipes.append(
            {
                "file_path": str(md_file),
                "filename": md_file.name,
                "metadata": metadata,
                "body": body,
            }
        )
    return recipes


def find_recipe(vault_path, name):
    """Find a recipe by name (checks frontmatter name and filename slug)."""
    slug = slugify(name)
    for recipe in load_all_recipes(vault_path):
        meta_name = recipe["metadata"].get("name", "")
        file_slug = Path(recipe["filename"]).stem
        if meta_name.lower() == name.lower() or file_slug == slug:
            return recipe
    return None


def extract_section(body, heading):
    """Extract content under a ## heading from markdown body."""
    pattern = rf"##\s+{re.escape(heading)}\s*\n(.*?)(?=\n##|\Z)"
    match = re.search(pattern, body, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def recipe_to_export_dict(recipe):
    """Convert a vault recipe to the JSON format meal_planner.py expects."""
    meta = recipe["metadata"]
    body = recipe["body"]
    ingredients_text = extract_section(body, "Ingredients")
    ingredients = [
        line.strip("- ").strip()
        for line in ingredients_text.split("\n")
        if line.strip().startswith("-")
    ]
    instructions = extract_section(body, "Instructions")
    return {
        "name": meta.get("name", ""),
        "servings": meta.get("servings", 4),
        "tags": meta.get("tags", []),
        "prep_time_min": meta.get("prep_time_min", ""),
        "ingredients": ingredients,
        "instructions": instructions,
    }


# --- Subcommands ---


def cmd_list(args):
    vault_path = get_vault_path()
    recipes = load_all_recipes(vault_path)

    if not recipes:
        print("[]")
        return

    if args.tags:
        tag_filter = {t.strip() for t in args.tags.split(",")}
        recipes = [
            r
            for r in recipes
            if tag_filter.intersection(set(r["metadata"].get("tags", [])))
        ]

    sort_key = args.sort or "name"
    if sort_key == "name":
        recipes.sort(key=lambda r: r["metadata"].get("name", "").lower())
    elif sort_key == "created":
        recipes.sort(key=lambda r: r["metadata"].get("created", ""), reverse=True)
    elif sort_key == "last_used":
        recipes.sort(key=lambda r: r["metadata"].get("last_used", ""), reverse=True)

    output = [
        {
            "name": r["metadata"].get("name", ""),
            "tags": r["metadata"].get("tags", []),
            "servings": r["metadata"].get("servings", ""),
            "last_used": r["metadata"].get("last_used", ""),
            "created": r["metadata"].get("created", ""),
            "source": r["metadata"].get("source", ""),
            "file_path": r["file_path"],
        }
        for r in recipes
    ]
    print(json.dumps(output, indent=2))


def cmd_show(args):
    vault_path = get_vault_path()
    recipe = find_recipe(vault_path, args.name)
    if not recipe:
        print(f"Recipe not found: {args.name}", file=sys.stderr)
        sys.exit(1)
    # Print the full file content
    content = Path(recipe["file_path"]).read_text(encoding="utf-8")
    print(content)


def cmd_save(args):
    vault_path = get_vault_path()
    vault_path.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else []

    metadata = {
        "name": args.name,
        "created": today,
        "last_used": today,
        "tags": tags,
        "servings": int(args.servings) if args.servings else 4,
        "prep_time_min": int(args.prep_time) if args.prep_time else "",
        "source": args.source or "manual",
    }
    # Remove empty optional fields
    metadata = {k: v for k, v in metadata.items() if v != ""}

    body = sys.stdin.read()

    filename = slugify(args.name) + ".md"
    file_path = vault_path / filename

    if file_path.exists():
        print(f"Recipe already exists: {file_path}", file=sys.stderr)
        print("Use a different name or delete the existing file.", file=sys.stderr)
        sys.exit(1)

    file_path.write_text(write_frontmatter(metadata, body), encoding="utf-8")
    print(f"Saved: {file_path}", file=sys.stderr)
    print(json.dumps({"file_path": str(file_path), "name": args.name}))


def cmd_export(args):
    vault_path = get_vault_path()

    if args.names:
        names = [n.strip() for n in args.names.split(",")]
        recipes = []
        for name in names:
            recipe = find_recipe(vault_path, name)
            if recipe:
                recipes.append(recipe)
            else:
                print(f"Warning: recipe not found: {name}", file=sys.stderr)
    else:
        recipes = load_all_recipes(vault_path)

    output = [recipe_to_export_dict(r) for r in recipes]
    print(json.dumps(output, indent=2))


def cmd_update_used(args):
    vault_path = get_vault_path()
    today = date.today().isoformat()

    for name in args.names:
        recipe = find_recipe(vault_path, name)
        if not recipe:
            print(f"Warning: recipe not found: {name}", file=sys.stderr)
            continue

        file_path = Path(recipe["file_path"])
        metadata = recipe["metadata"]
        metadata["last_used"] = today

        file_path.write_text(
            write_frontmatter(metadata, recipe["body"]), encoding="utf-8"
        )
        print(f"Updated last_used: {name} -> {today}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Recipe vault manager")
    sub = parser.add_subparsers(dest="command")

    # list
    list_p = sub.add_parser("list", help="List recipes in vault")
    list_p.add_argument("--tags", help="Filter by tags (comma-separated)")
    list_p.add_argument(
        "--sort", choices=["name", "created", "last_used"], help="Sort order"
    )

    # show
    show_p = sub.add_parser("show", help="Show a recipe")
    show_p.add_argument("name", help="Recipe name")

    # save
    save_p = sub.add_parser("save", help="Save a recipe (reads body from stdin)")
    save_p.add_argument("--name", required=True, help="Recipe name")
    save_p.add_argument("--tags", help="Tags (comma-separated)")
    save_p.add_argument("--servings", help="Number of servings")
    save_p.add_argument("--source", help="Source URL or description")
    save_p.add_argument("--prep-time", help="Prep time in minutes")

    # export
    export_p = sub.add_parser("export", help="Export recipes as JSON")
    export_p.add_argument(
        "--names", help="Recipe names to export (comma-separated, or all)"
    )

    # update-used
    update_p = sub.add_parser("update-used", help="Update last_used date")
    update_p.add_argument("names", nargs="+", help="Recipe names to update")

    args = parser.parse_args()
    commands = {
        "list": cmd_list,
        "show": cmd_show,
        "save": cmd_save,
        "export": cmd_export,
        "update-used": cmd_update_used,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
