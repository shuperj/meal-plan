# Meal Plan Directive

## Goal
Generate a weekly meal plan, build a grocery list, resolve items to real Kroger products with prices, and add approved items to the user's Kroger cart for pickup.

## Inputs
- **Budget**: Weekly budget in dollars (default: $120)
- **Meals**: Number of weeknight dinners (default: 5)
- **Household**: Description (default: 2 adults, 1 child)
- **Preferences**: Any additional dietary notes from user
- **Recipes**: Optional saved recipes to incorporate (URLs, text, or file paths)
- **ZIP code**: For store selection (default: 48837)

## Tools / Scripts

| Step | Script | Purpose |
|------|--------|---------|
| 1 | `execution/meal_planner.py` | Generate meal plan + grocery list via LLM |
| 2 | `execution/kroger_api.py stores` | Find nearest Kroger store |
| 3 | `execution/grocery_list.py` | Resolve items to real Kroger products with prices |
| 4 | `execution/kroger_api.py cart-add` | Add approved items to Kroger cart |

## Process

### Step 1: Generate Meal Plan
```bash
python execution/meal_planner.py --budget 120 --meals 5
```
- Reads `references/pcos.md` for dietary guidance
- Produces `.tmp/meal_plan.json` with 5 dinners + aggregated grocery list
- Show the user the plan and ask for approval/swaps before proceeding

### Step 2: Find Store
```bash
python execution/kroger_api.py stores --zip 48837
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

## First-Time Setup
User must complete these one-time steps:
1. Register app at developer.kroger.com
2. Set `KROGER_CLIENT_ID` and `KROGER_CLIENT_SECRET` in `.env`
3. Run `python execution/kroger_api.py auth` to authorize cart access
4. Set `ANTHROPIC_API_KEY` in `.env` for meal plan generation
