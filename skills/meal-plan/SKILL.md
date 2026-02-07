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

## Recipe Management

Recipes are saved as markdown files in the Obsidian vault at `~/Documents/ShuperBrain/30 Resources/Recipes/`. Each file has YAML frontmatter with metadata (name, created date, last used date, tags, servings, source).

### List saved recipes
```bash
python execution/recipe_manager.py list
```
Filter by tags or sort:
```bash
python execution/recipe_manager.py list --tags high-protein,pcos --sort last_used
```

### Show a recipe
```bash
python execution/recipe_manager.py show "Chicken Stir Fry"
```

### Export recipes as JSON (for meal planner)
```bash
python execution/recipe_manager.py export --names "Chicken Stir Fry,Taco Bowl" > .tmp/selected_recipes.json
```

### Update last_used after a plan is approved
```bash
python execution/recipe_manager.py update-used "Chicken Stir Fry" "Taco Bowl"
```

### Update recipe index
Regenerate the Obsidian recipe index note (`_Recipe Index.md`) with tag-based sections and this week's meals:
```bash
python execution/recipe_manager.py update-index
```
This runs automatically when recipes are saved or `update-used` is called.

## Workflow

When the user says `/meal-plan` (or asks for meal planning help), follow these steps in order. **Stop and ask the user before proceeding to the next step.**

**Before starting:** Check if `config.json` exists by running `python execution/meal_config.py show`. If key fields (ZIP, household) are empty, ask the user to run `python execution/meal_config.py setup` first, or collect their preferences and run it for them.

### 1. Check Saved Recipes
List the user's saved recipes:
```bash
python execution/recipe_manager.py list --sort last_used
```
If the vault has recipes, present them as a table:
| Name | Tags | Last Used |

Ask: "Would you like to include any saved recipes this week?"

If the user selects recipes, export them:
```bash
python execution/recipe_manager.py export --names "Recipe 1,Recipe 2" > .tmp/selected_recipes.json
```

If the vault is empty or the user declines, skip to step 2.

### 2. Generate Meal Plan
Run the meal planner (it reads defaults from `config.json`):
```bash
# With selected recipes from step 1
python execution/meal_planner.py --recipes-file .tmp/selected_recipes.json

# Without saved recipes
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

Once the user approves the plan, present next steps:

"Your plan is locked in! Here's what we can do next:"
- **Save new recipes to Obsidian** — Save any new (non-vault) recipes from this plan to your recipe vault
- **Proceed to Kroger** — Find your store, get real prices, and add to cart
- **Both** — Save recipes first, then proceed to Kroger

If the user wants to save recipes, follow the "Recipe Capture > From the current meal plan" steps for each new recipe before continuing to Step 3. Only offer to save recipes that are NEW (not ones already selected from the vault in Step 1).

### 3. Find Kroger Store
```bash
python execution/kroger_api.py stores --zip <ZIP>
```
Pick the nearest store. Confirm with user if multiple options.

### 4. Resolve Grocery List
```bash
python execution/grocery_list.py --plan .tmp/meal_plan.json --location <LOCATION_ID>
```
This searches Kroger for each ingredient and returns real products with actual prices.

Present results:
- Resolved items with prices
- Items not found (suggest substitutes)
- Total cost vs. budget

Ask: "Here's your cart at $X. Want to adjust anything before I add to Kroger?"

### 5. Add to Cart
After explicit approval:
```bash
python execution/kroger_api.py cart-add --items '<JSON_ARRAY>'
```
Format: `[{"upc":"<ID>","quantity":<N>,"modality":"PICKUP"}]`

Confirm: "Added X items to your Kroger cart. Go to kroger.com to schedule pickup."

**NEVER checkout or submit an order. Only add to cart.**

### 6. Update Recipe Usage
If any saved recipes from the vault were included in the approved plan, update their `last_used` date:
```bash
python execution/recipe_manager.py update-used "Recipe Name 1" "Recipe Name 2"
```
This also auto-updates the `_Recipe Index.md` note in the vault with the current week's meals and tag index.

## Recipe Capture

When the user shares a recipe to save (outside of the /meal-plan workflow), follow these steps:

### From a URL
1. Fetch the recipe page using browser tools
2. Extract: title, ingredients list, instructions, servings, prep time
3. Ask the user for tags (suggest relevant ones: pcos, high-protein, low-carb, crock-pot, quick, kid-friendly, skillet, mexican, sheet-pan, etc.)
4. Format the body as markdown (see template below)
5. Save to vault:
```bash
echo '<MARKDOWN_BODY>' | python execution/recipe_manager.py save \
  --name "Recipe Name" \
  --servings 4 \
  --tags "pcos,high-protein" \
  --prep-time 30 \
  --source "https://example.com/recipe"
```

### From plain text or conversation
1. Collect recipe details from the user (name, ingredients, steps)
2. Format into markdown template
3. Ask for tags and metadata
4. Save using the same command above with `--source "manual"`

### From the current meal plan
If the user wants to save a recipe from the generated plan:
1. Extract the recipe details from `.tmp/meal_plan.json`
2. Format as markdown
3. Save with `--source "meal-plan-YYYY-MM-DD"`

### Markdown body template
```markdown
# Recipe Name

## Ingredients
- 1.5 lb chicken breast
- 2 tbsp olive oil
- 2 cups broccoli

## Instructions
1. Preheat oven to 375°F
2. Season chicken and roast 25 min
3. Steam broccoli

## Notes
Optional substitutions, tips, variations
```

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
