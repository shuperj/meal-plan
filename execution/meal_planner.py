#!/usr/bin/env python3
"""
Meal plan generator: produces a weekly meal plan and unified grocery list.

Usage:
    # Generate meal plan with defaults
    python meal_planner.py

    # Custom budget and preferences
    python meal_planner.py --budget 100 --meals 5 --preferences "no dairy"

    # With saved recipes from a JSON file
    python meal_planner.py --recipes-file recipes.json

    # With saved recipes from Obsidian vault
    python meal_planner.py --recipes-vault ~/Documents/ShuperBrain/30\ Resources/Recipes

Output: JSON with meal_plan and grocery_list written to .tmp/meal_plan.json

Environment:
    ANTHROPIC_API_KEY - Required for LLM generation
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from meal_config import load_config, load_env

load_env()

import anthropic
from recipe_manager import load_all_recipes, recipe_to_export_dict

SYSTEM_PROMPT = """You are a meal planning assistant. You create practical, budget-conscious weekly meal plans.

Key rules:
- Follow the dietary preferences and meal rules provided by the user
- Prefer whole foods, lean proteins, healthy fats, vegetables
- Maximize ingredient overlap across meals to minimize waste and cost
- Stay within the weekly budget

Output ONLY valid JSON matching this schema:
{
  "meal_plan": [
    {
      "day": "Monday",
      "dinner": {
        "name": "Recipe Name",
        "servings": 4,
        "prep_time_min": 30,
        "tags": ["high-protein", "skillet", "mexican", "sheet-pan"],
        "ingredients": [
          {"item": "chicken breast", "quantity": 1.5, "unit": "lb"},
          {"item": "broccoli", "quantity": 2, "unit": "cups"}
        ],
        "instructions_summary": "Brief 2-3 sentence cooking summary"
      },
      "leftover_lunch": true
    }
  ],
  "grocery_list": [
    {"item": "chicken breast", "quantity": 3, "unit": "lb", "category": "meat", "estimated_price": 8.99}
  ],
  "estimated_total": 95.50,
  "budget_notes": "Under budget by $24.50. Could upgrade to organic chicken."
}

Categories for grocery items: meat, produce, dairy, pantry, frozen, bakery, other

Aggregate ingredients across all meals into a single grocery_list (combine duplicates).
Estimate prices based on typical US grocery prices."""


def load_pcos_reference():
    """Load PCOS dietary reference if available."""
    ref_path = Path(__file__).resolve().parent.parent / "references" / "pcos.md"
    if ref_path.exists():
        return ref_path.read_text(encoding="utf-8")
    return None


def generate_meal_plan(
    budget=None,
    meals=None,
    household=None,
    preferences=None,
    saved_recipes=None,
    zip_code=None,
):
    """Generate a meal plan using the LLM."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required")

    config = load_config()
    budget = budget or config["budget"]
    meals = meals or config["meals"]
    household = household or config["household"]
    zip_code = zip_code or config["zip"]

    user_msg = f"""Create a {meals}-meal weekly dinner plan.

Household: {household}
Budget: ${budget}/week
Location ZIP: {zip_code}"""

    if config["diet"]:
        user_msg += f"\nDiet: {config['diet']}"
    if config["friday_rule"]:
        user_msg += f"\nFriday rule: {config['friday_rule']}"
    if config["leftovers"]:
        user_msg += f"\nLeftovers: {config['leftovers']}"

    if preferences:
        user_msg += f"\nAdditional preferences: {preferences}"

    pcos_ref = load_pcos_reference()
    if pcos_ref:
        user_msg += f"\n\nPCOS Dietary Reference:\n{pcos_ref}"

    if saved_recipes:
        user_msg += f"\n\nIncorporate these saved recipes if appropriate:\n{json.dumps(saved_recipes, indent=2)}"

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    text = response.content[0].text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    return json.loads(text)


def main():
    parser = argparse.ArgumentParser(description="Generate weekly meal plan")
    parser.add_argument(
        "--budget", type=float, help="Weekly budget (from config if not set)"
    )
    parser.add_argument(
        "--meals", type=int, help="Number of dinners (from config if not set)"
    )
    parser.add_argument(
        "--household", help="Household description (from config if not set)"
    )
    parser.add_argument("--preferences", help="Additional dietary preferences")
    parser.add_argument(
        "--recipes-file", help="JSON file with saved recipes to incorporate"
    )
    parser.add_argument(
        "--recipes-vault", help="Path to Obsidian recipe vault directory"
    )
    parser.add_argument("--zip", help="ZIP code (from config if not set)")
    parser.add_argument("--output", help="Output file (default: .tmp/meal_plan.json)")
    args = parser.parse_args()

    saved_recipes = None
    if args.recipes_file:
        saved_recipes = json.loads(Path(args.recipes_file).read_text())
    elif args.recipes_vault:
        vault_recipes = load_all_recipes(Path(args.recipes_vault))
        if vault_recipes:
            saved_recipes = [recipe_to_export_dict(r) for r in vault_recipes]

    print("Generating meal plan...", file=sys.stderr)
    plan = generate_meal_plan(
        budget=args.budget,
        meals=args.meals,
        household=args.household,
        preferences=args.preferences,
        saved_recipes=saved_recipes,
        zip_code=args.zip,
    )

    output_path = (
        Path(args.output)
        if args.output
        else (Path(__file__).resolve().parent.parent / ".tmp" / "meal_plan.json")
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(plan, indent=2))

    print(f"Meal plan saved to {output_path}", file=sys.stderr)

    # Also print to stdout for piping
    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
