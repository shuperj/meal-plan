---
name: meal-plan
description: Plan weekly meals, generate grocery lists with real Kroger prices, and add items to the Kroger cart for pickup.
user-invocable: true
metadata: {"openclaw":{"requires":{"env":["KROGER_CLIENT_ID","KROGER_CLIENT_SECRET","ANTHROPIC_API_KEY"],"bins":["python3"]},"primaryEnv":"KROGER_CLIENT_ID"},"install":[{"type":"uv","path":"requirements.txt"}]}
---

# Meal Plan Skill

Plan weekly meals, build a grocery list, price it against Kroger, and draft a pickup cart.

## Configuration

Household preferences are stored in `config.json`. On first use, run setup:
```bash
python execution/meal_config.py setup
```
This prompts for: ZIP code, household size, number of meals, weekly budget, dietary preferences, Friday meal rule, and leftover strategy.

To view current config: `python execution/meal_config.py show`
To update a single value: `python execution/meal_config.py set budget 150`

## Workflow

When the user says `/meal-plan` (or asks for meal planning help), follow these steps in order. **Stop and ask the user before proceeding to the next step.**

**Before starting:** Check if `config.json` exists by running `python execution/meal_config.py show`. If key fields (ZIP, household) are empty, ask the user to run `python execution/meal_config.py setup` first, or collect their preferences and run it for them.

### 1. Generate Meal Plan
Run the meal planner (it reads defaults from `config.json`):
```bash
python execution/meal_planner.py
```
Override any config values with CLI flags if the user requests changes:
```bash
python execution/meal_planner.py --budget <BUDGET> --meals <MEALS> --household "<DESC>"
```
This outputs `.tmp/meal_plan.json` with recipes and an aggregated grocery list.

Present the plan to the user as a formatted table:
| Day | Dinner | Prep Time | Tags |
Show ingredients per recipe and the estimated total.

Ask: "Does this plan look good? Any swaps?"

### 2. Find Kroger Store
```bash
python execution/kroger_api.py stores --zip <ZIP>
```
Pick the nearest store. Confirm with user if multiple options.

### 3. Resolve Grocery List
```bash
python execution/grocery_list.py --plan .tmp/meal_plan.json --location <LOCATION_ID>
```
This searches Kroger for each ingredient and returns real products with actual prices.

Present results:
- Resolved items with prices
- Items not found (suggest substitutes)
- Total cost vs. budget

Ask: "Here's your cart at $X. Want to adjust anything before I add to Kroger?"

### 4. Add to Cart
After explicit approval:
```bash
python execution/kroger_api.py cart-add --items '<JSON_ARRAY>'
```
Format: `[{"upc":"<ID>","quantity":<N>,"modality":"PICKUP"}]`

Confirm: "Added X items to your Kroger cart. Go to kroger.com to schedule pickup."

**NEVER checkout or submit an order. Only add to cart.**

## Recipe Capture
When the user shares a recipe (URL, text, or image):
1. Parse and format it as Markdown
2. Save to `~/Documents/ShuperBrain/30 Resources/Recipes/<recipe-name>.md`
3. Use YAML frontmatter: source, tags (pcos, high-protein, low-carb, crock-pot), servings
4. Optionally incorporate into the next meal plan

## First-Time Setup
1. Run `python execution/meal_config.py setup` to configure household preferences
2. Register at developer.kroger.com and set KROGER_CLIENT_ID and KROGER_CLIENT_SECRET in .env
3. Set ANTHROPIC_API_KEY in .env
4. Run `python execution/kroger_api.py auth` and follow the OAuth flow (one-time; refresh tokens are saved automatically)

## Error Handling
- **Item not found:** Try broader search terms, then suggest substitutes
- **Over budget:** Suggest 1-2 cheaper swaps (frozen veg, different protein cut)
- **Out of stock:** Flag it, suggest alternative
- **Auth expired:** Prompt user to re-run `python execution/kroger_api.py auth`
- **API error:** Show the error, don't retry paid operations without asking
