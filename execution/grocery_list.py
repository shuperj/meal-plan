#!/usr/bin/env python3
"""
Grocery list builder: takes a meal plan, searches Kroger for each item,
resolves to actual products with real prices, and builds a cart-ready list.

Usage:
    # From a meal plan JSON file
    python grocery_list.py --plan .tmp/meal_plan.json

    # With a specific store location
    python grocery_list.py --plan .tmp/meal_plan.json --location 01400943

    # Just resolve a simple item list
    python grocery_list.py --items '["chicken breast 1.5 lb", "broccoli 2 cups"]' --location 01400943

Output: JSON with resolved products and cart-ready items written to .tmp/grocery_cart.json
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

# Import our Kroger client
sys.path.insert(0, str(Path(__file__).resolve().parent))
from kroger_api import KrogerClient

# Kroger category → expected grocery categories mapping
_EXPECTED_KROGER_CATEGORIES = {
    "produce": ["produce"],
    "meat": ["meat", "seafood"],
    "dairy": ["dairy", "eggs"],
    "pantry": [
        "baking goods",
        "canned",
        "packaged",
        "condiments",
        "sauces",
        "pasta",
        "grains",
        "snacks",
        "breakfast",
        "spices",
    ],
    "frozen": ["frozen"],
    "bakery": ["bakery"],
}

# Kroger categories that indicate non-food products
_NON_FOOD_CATEGORIES = [
    "health & beauty",
    "personal care",
    "cleaning",
    "pet care",
    "baby",
    "pharmacy",
    "household",
    "office",
    "floral",
]


def _score_product(product, item_name, category):
    """
    Score a product match. Higher is better.
    Penalizes irrelevant matches (e.g. dog food for "brown rice").
    Uses Kroger metadata: categories, snapEligible, aisleLocations.
    """
    desc = (product.get("description") or "").lower()
    brand = (product.get("brand") or "").lower()
    kroger_cats = [c.lower() for c in product.get("categories", [])]
    snap_eligible = product.get("snapEligible", True)
    name_lower = item_name.lower()
    # Strip parentheses so "(fresh)" becomes "fresh" for word matching
    name_clean = re.sub(r"[()]", "", name_lower).strip()
    name_words = name_clean.split()

    score = 0

    # ── SNAP eligibility: strongest signal for "is this food?" ──
    food_categories = {"produce", "meat", "dairy", "pantry", "frozen", "bakery"}
    if category in food_categories and not snap_eligible:
        score -= 100

    # ── Kroger category validation ──
    expected = _EXPECTED_KROGER_CATEGORIES.get(category, [])
    if expected and kroger_cats:
        if any(exp in kc for exp in expected for kc in kroger_cats):
            score += 15
    for nf_cat in _NON_FOOD_CATEGORIES:
        if any(nf_cat in kc for kc in kroger_cats):
            score -= 30

    # ── Word matching ──
    matched_words = sum(1 for w in name_words if w in desc)
    score += matched_words * 10

    # Bonus: description starts with or closely matches the item name
    if name_clean in desc:
        score += 20
    if desc.startswith(name_clean) or desc.startswith(name_words[-1]):
        score += 10

    # ── Junk signals in description/brand ──
    junk_signals = [
        "dog",
        "cat",
        "pet",
        "puppy",
        "kitten",
        "cleaner",
        "detergent",
        "soap",
        "shampoo",
        "conditioner",
        "hair",
        "beauty",
        "body wash",
        "lotion",
        "skincare",
        "cosmetic",
        "toothpaste",
        "mouthwash",
        "deodorant",
        "diaper",
        "formula",
        "supplement",
        "vitamin",
        "wellness shot",
        "protein shake",
    ]
    for junk in junk_signals:
        if junk in desc or junk in brand:
            score -= 50

    # ── Beverage signals when searching for produce/pantry ingredients ──
    if category in {"produce", "pantry", "meat", "dairy"}:
        beverage_signals = [
            "juice",
            "blend",
            "cold-pressed",
            "smoothie",
            "drink",
            "soda",
            "water",
            "tea",
            "coffee",
            "lemonade",
        ]
        for sig in beverage_signals:
            if sig in desc and sig not in name_lower:
                score -= 20
                break

    # ── Freshness modifiers ──
    if "fresh" in name_lower:
        if any(x in desc for x in ["freeze dried", "frozen", "canned", "dried"]):
            # Only penalize "dried" if it's standalone, not part of the item name
            if "dried" not in name_lower:
                score -= 15
        if "fresh" in desc:
            score += 10

    # ── Penalize prepared items when searching for raw ingredients ──
    raw_categories = {"produce", "meat", "dairy", "pantry"}
    if category in raw_categories:
        prepared_signals = [
            "cup",
            "cups",
            "kit",
            "meal kit",
            "seasoning mix",
            "frozen dinner",
            "tv dinner",
        ]
        for sig in prepared_signals:
            if sig in desc and sig not in name_lower:
                score -= 10

    # ── Prefer items with pricing ──
    items_data = product.get("items", [{}])
    if items_data and items_data[0].get("price", {}).get("regular"):
        score += 5

    return score


def _clean_search_query(item_name):
    """
    Normalize item names for better Kroger search results.
    E.g. "ginger (fresh)" → "fresh ginger", "chicken thighs (boneless)" → "boneless chicken thighs"
    """
    match = re.match(r"^(.+?)\s*\((.+?)\)\s*$", item_name)
    if match:
        base, modifier = match.group(1).strip(), match.group(2).strip()
        return f"{modifier} {base}"
    return item_name


def resolve_grocery_item(
    client, item_name, quantity, unit, location_id, category="other"
):
    """
    Search Kroger for a grocery item and return the best match with pricing.
    Returns dict with product info or None if not found.
    """
    search_query = _clean_search_query(item_name)
    try:
        result = client.search_products(search_query, location_id, limit=10)
        products = result.get("data", [])
    except Exception as e:
        print(f"  Warning: Search failed for '{item_name}': {e}", file=sys.stderr)
        return None

    if not products:
        return None

    # Score and rank all candidates
    scored = []
    for p in products:
        items = p.get("items", [])
        if not items:
            continue
        item_data = items[0]
        stock = item_data.get("inventory", {}).get("stockLevel", "")
        if stock == "TEMPORARILY_OUT_OF_STOCK":
            continue
        score = _score_product(p, item_name, category)
        price = item_data.get("price", {}).get("regular") or 999
        scored.append((score, price, p, item_data))

    if not scored:
        return None

    # Sort by score descending, then price ascending (cheaper wins ties)
    scored.sort(key=lambda x: (-x[0], x[1]))
    best_score, _, best_product, best_item = scored[0]

    price_info = best_item.get("price", {})
    regular_price = price_info.get("regular")
    promo_price = price_info.get("promo")

    return {
        "productId": best_product.get("productId"),
        "upc": best_product.get("upc", best_product.get("productId")),
        "description": best_product.get("description", ""),
        "brand": best_product.get("brand", ""),
        "size": best_item.get("size", ""),
        "regular_price": regular_price,
        "promo_price": promo_price,
        "effective_price": promo_price if promo_price else regular_price,
        "in_stock": True,
        "fulfillment": best_item.get("fulfillment", {}),
        "search_query": item_name,
        "requested_quantity": quantity,
        "requested_unit": unit,
        "match_score": best_score,
    }


def build_grocery_cart(meal_plan_path, location_id, items_json=None):
    """
    Read a meal plan and resolve each grocery item to a Kroger product.
    Returns a structured cart-ready list.
    """
    client = KrogerClient()

    # If no location_id, find the nearest store
    if not location_id:
        zip_code = os.getenv("KROGER_ZIP", "")
        print(f"Finding nearest Kroger to {zip_code}...", file=sys.stderr)
        stores = client.find_stores(zip_code, limit=1)
        store_list = stores.get("data", [])
        if not store_list:
            raise ValueError(f"No Kroger stores found near {zip_code}")
        location_id = store_list[0]["locationId"]
        store_name = store_list[0].get("name", "")
        print(f"Using store: {store_name} (ID: {location_id})", file=sys.stderr)

    # Load grocery items
    if items_json:
        grocery_items = [
            {"item": i, "quantity": 1, "unit": "each"} for i in json.loads(items_json)
        ]
    elif meal_plan_path:
        plan = json.loads(Path(meal_plan_path).read_text())
        grocery_items = plan.get("grocery_list", [])
    else:
        raise ValueError("Provide --plan or --items")

    # Resolve each item
    resolved = []
    not_found = []
    total = 0

    for idx, gi in enumerate(grocery_items):
        item_name = gi.get("item", gi) if isinstance(gi, dict) else gi
        quantity = gi.get("quantity", 1) if isinstance(gi, dict) else 1
        unit = gi.get("unit", "each") if isinstance(gi, dict) else "each"
        category = gi.get("category", "other") if isinstance(gi, dict) else "other"

        print(
            f"  [{idx + 1}/{len(grocery_items)}] Searching: {item_name}...",
            file=sys.stderr,
        )

        product = resolve_grocery_item(
            client, item_name, quantity, unit, location_id, category
        )

        if product:
            product["category"] = category
            product["cart_quantity"] = 1  # Default to 1 unit; user can adjust
            if product["effective_price"]:
                total += product["effective_price"]
            resolved.append(product)
        else:
            not_found.append(
                {
                    "item": item_name,
                    "quantity": quantity,
                    "unit": unit,
                    "category": category,
                }
            )

        # Rate limit: Kroger allows 10k product calls/day, be polite
        time.sleep(0.3)

    result = {
        "location_id": location_id,
        "resolved_items": resolved,
        "not_found": not_found,
        "estimated_total": round(total, 2),
        "item_count": len(resolved),
        "missing_count": len(not_found),
    }

    return result


def main():
    parser = argparse.ArgumentParser(description="Build grocery cart from meal plan")
    parser.add_argument("--plan", help="Path to meal plan JSON (from meal_planner.py)")
    parser.add_argument("--items", help="JSON array of item strings to search")
    parser.add_argument("--location", help="Kroger store location ID")
    parser.add_argument(
        "--output", help="Output file (default: .tmp/grocery_cart.json)"
    )
    args = parser.parse_args()

    if not args.plan and not args.items:
        default_plan = (
            Path(__file__).resolve().parent.parent / ".tmp" / "meal_plan.json"
        )
        if default_plan.exists():
            args.plan = str(default_plan)
        else:
            print("Provide --plan or --items", file=sys.stderr)
            sys.exit(1)

    location_id = args.location or os.getenv("KROGER_LOCATION_ID")

    print("Building grocery cart...", file=sys.stderr)
    cart = build_grocery_cart(args.plan, location_id, items_json=args.items)

    output_path = (
        Path(args.output)
        if args.output
        else (Path(__file__).resolve().parent.parent / ".tmp" / "grocery_cart.json")
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(cart, indent=2))

    print(f"\nGrocery cart saved to {output_path}", file=sys.stderr)
    print(
        f"Resolved: {cart['item_count']} items | Missing: {cart['missing_count']} | Est. total: ${cart['estimated_total']}",
        file=sys.stderr,
    )

    if cart["not_found"]:
        print("\nItems not found (may need manual selection):", file=sys.stderr)
        for nf in cart["not_found"]:
            print(f"  - {nf['item']} ({nf['quantity']} {nf['unit']})", file=sys.stderr)

    print(json.dumps(cart, indent=2))


if __name__ == "__main__":
    main()
