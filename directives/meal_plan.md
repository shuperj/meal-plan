# Meal Plan Directive

## Goal
Generate a weekly meal plan, build a grocery list, resolve items to real Kroger products with prices, and add approved items to the user's Kroger cart for pickup.

## Inputs
All defaults are loaded from `config.json` (run `python execution/meal_config.py setup` to configure).
- **Budget**: Weekly budget in dollars
- **Meals**: Number of weeknight dinners
- **Household**: Description
- **Preferences**: Any additional dietary notes from user
- **Recipes**: Optional saved recipes from the Obsidian vault (`~/Documents/ShuperBrain/30 Resources/Recipes/`). Use `execution/recipe_manager.py list` to browse, `export` to select.
- **ZIP code**: For store selection

## Tools / Scripts

| Step | Script | Purpose |
|------|--------|---------|
| 0 | `execution/recipe_manager.py list` | List saved recipes from Obsidian vault |
| 0 | `execution/recipe_manager.py export` | Export selected recipes as JSON for planner |
| 1 | `execution/meal_planner.py` | Generate meal plan + grocery list via LLM |
| 2 | `execution/kroger_api.py stores` | Find nearest Kroger store |
| 3 | `execution/grocery_list.py` | Resolve items to real Kroger products with prices |
| 4 | `execution/kroger_api.py cart-add` | Add approved items to Kroger cart |
| 5 | `execution/recipe_manager.py update-used` | Update last_used date on incorporated recipes |

## Process

### Step 0 (optional): Select Saved Recipes
```bash
python execution/recipe_manager.py list --sort last_used
```
- Show user their saved recipes from the Obsidian vault
- If they want to include any, export the selected ones:
```bash
python execution/recipe_manager.py export --names "Recipe 1,Recipe 2" > .tmp/selected_recipes.json
```

### Step 1: Generate Meal Plan
```bash
# With selected recipes
python execution/meal_planner.py --recipes-file .tmp/selected_recipes.json

# Without saved recipes
python execution/meal_planner.py
```
- Reads `references/pcos.md` for dietary guidance
- Produces `.tmp/meal_plan.json` with 5 dinners + aggregated grocery list
- Show the user the plan and ask for approval/swaps before proceeding

### Step 2: Find Store
```bash
python execution/kroger_api.py stores --zip <ZIP>
```
- Returns nearby stores with location IDs
- Use the closest store, or let user pick
- Save location ID for product searches

### Step 3: Resolve Grocery List
```bash
python execution/grocery_list.py --plan .tmp/meal_plan.json --location <LOCATION_ID>
```
- Searches Kroger for each grocery item
- Returns real products with actual prices
- Identifies items not found (need substitutes or manual selection)
- Produces `.tmp/grocery_cart.json`

### Step 4: Review & Approve Cart
- Present the resolved grocery list with real prices to user
- Highlight any items not found and suggest substitutes
- Show total cost vs. budget
- **Wait for explicit user approval before adding to cart**

### Step 5: Add to Cart
```bash
python execution/kroger_api.py cart-add --items '[{"upc":"...","quantity":1},...]'
```
- Requires prior OAuth authorization (one-time setup via `kroger_api.py auth`)
- Adds approved items to Kroger cart for pickup
- **Never checkout without explicit approval**

### Step 6: Update Recipe Usage
If saved recipes from the vault were incorporated into the approved plan:
```bash
python execution/recipe_manager.py update-used "Recipe Name 1" "Recipe Name 2"
```
- Updates `last_used` in YAML frontmatter to today's date

## Outputs
- `.tmp/meal_plan.json` - The meal plan with recipes and grocery list
- `.tmp/grocery_cart.json` - Resolved products with real Kroger prices
- Items added to user's Kroger cart (ready for pickup scheduling on kroger.com)

## Edge Cases
- **Item not found**: Suggest substitute, ask user. Try broader search terms.
- **Over budget**: Offer 1-2 swap suggestions (cheaper protein, frozen vs fresh).
- **Out of stock**: Note it, suggest alternative or different store trip.
- **Auth expired**: Prompt user to re-run `kroger_api.py auth`.
- **Rate limits**: Kroger allows 10k product calls/day and 5k cart calls/day. The grocery list script adds 300ms delay between searches.

## Product Matching Notes
The grocery list builder uses a multi-signal scoring system to filter Kroger search results:
- **SNAP eligibility**: Non-SNAP products are heavily penalized for food categories (eliminates beauty/household products).
- **Kroger categories**: Products are validated against expected category (e.g. "produce" items should be in Kroger's Produce category). Non-food categories like "Health & Beauty" are penalized.
- **Junk signals**: Known non-food keywords (pet, hair, conditioner, etc.) in description/brand trigger heavy penalties.
- **Beverage filter**: Juice, smoothie, cold-pressed, etc. are penalized when searching for raw ingredients.
- **Freshness modifiers**: "freeze dried" penalized when searching for "fresh" items.
- **Query cleanup**: Parenthetical modifiers are moved to the front of the search query (e.g. "ginger (fresh)" → "fresh ginger") for better Kroger search results.
- **Tie-breaking**: Same-score products are sorted by price (cheaper wins).

## First-Time Setup
User must complete these one-time steps:
1. Run `python execution/meal_config.py setup` to configure household preferences
2. Register app at developer.kroger.com
3. Set `KROGER_CLIENT_ID` and `KROGER_CLIENT_SECRET` in `.env`
4. Set `ANTHROPIC_API_KEY` in `.env` for meal plan generation
5. Run `python execution/kroger_api.py auth` to authorize cart access
