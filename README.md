# meal-plan

AI-powered weekly meal planner that generates recipes, builds a grocery list with real Kroger prices, and adds items to your Kroger cart for pickup.

## What it does

1. **Saves recipes** as markdown files in your Obsidian vault with YAML frontmatter (tags, dates, source)
2. **Generates a meal plan** tailored to your household size, budget, and dietary preferences using Claude — optionally incorporating saved recipes from your vault
3. **Resolves ingredients** against the Kroger product catalog at your nearest store with real prices
4. **Adds items to your Kroger cart** for pickup (never checks out without your approval)

## Quick install

```bash
curl -fsSL https://raw.githubusercontent.com/shuperj/meal-plan/master/deploy.sh | bash
```

Or clone and run:

```bash
git clone https://github.com/shuperj/meal-plan.git
cd meal-plan
bash deploy.sh
```

After installing, restart the gateway to load the new skill:

```bash
openclawd gateway restart
```

## Updating

Re-run the install one-liner from any directory:

```bash
curl -fsSL https://raw.githubusercontent.com/shuperj/meal-plan/master/deploy.sh | bash
```

Or if you have the repo cloned locally:

```bash
cd ~/meal-plan && git pull && bash deploy.sh
```

This re-copies all scripts, updates the SKILL.md manifest, and reinstalls dependencies. Your `config.json`, `.env`, and Kroger tokens are preserved.

Restart the gateway after updating:

```bash
openclawd gateway restart
```

## Setup

### 1. Get API keys

- **Kroger**: Register an app at [developer.kroger.com](https://developer.kroger.com). You need a client ID and secret.
- **Anthropic**: Get an API key at [console.anthropic.com](https://console.anthropic.com).

### 2. Configure environment

Edit `.env` in the install directory (`~/.openclaw/skills/meal-plan/.env`):

```
KROGER_CLIENT_ID=your_client_id
KROGER_CLIENT_SECRET=your_client_secret
ANTHROPIC_API_KEY=your_api_key
```

### 3. Set your household defaults

```bash
python execution/meal_config.py setup
```

This prompts for your ZIP code, household size, weekly budget, dietary preferences, and meal rules. Run `meal_config.py show` to view or `meal_config.py set budget 150` to update individual values.

### 4. Authorize Kroger cart access

```bash
python execution/kroger_api.py auth
```

This opens a browser for OAuth login. One-time step -- refresh tokens are saved automatically.

## Usage

### With OpenClaw

If you use [OpenClaw](https://github.com/anthropics/openclaw), the skill is available as `/meal-plan` after install.

### Standalone

```bash
# Generate a meal plan
python execution/meal_planner.py

# Override config defaults
python execution/meal_planner.py --budget 80 --meals 3

# With saved recipes from your Obsidian vault
python execution/meal_planner.py --recipes-file .tmp/selected_recipes.json

# Find nearest Kroger
python execution/kroger_api.py stores --zip 90210

# Resolve grocery list to real products with prices
python execution/grocery_list.py --plan .tmp/meal_plan.json --location STORE_ID

# Add items to cart
python execution/kroger_api.py cart-add --items '[{"upc":"0001111041700","quantity":1}]'
```

### Recipe vault

Recipes are stored as markdown files in your [Obsidian](https://obsidian.md) vault with YAML frontmatter (name, tags, created/last_used dates, servings, source). The default path is `~/Documents/ShuperBrain/30 Resources/Recipes/` — set `RECIPE_VAULT_PATH` in your `.env` or OpenClaw config to use a different location.

**Important**: `RECIPE_VAULT_PATH` should point to the exact folder where you want recipes saved, not just the vault root. For example: `/home/user/ObsidianVault/Recipes/`, not `/home/user/ObsidianVault/`.

```bash
# List saved recipes
python execution/recipe_manager.py list --sort last_used

# Filter by tag
python execution/recipe_manager.py list --tags high-protein,pcos

# Save a new recipe (body from stdin)
echo '## Ingredients
- 1 lb chicken
## Instructions
1. Cook it' | python execution/recipe_manager.py save \
  --name "Simple Chicken" --servings 4 --tags "high-protein,quick" --source "manual"

# Export recipes as JSON for the meal planner
python execution/recipe_manager.py export --names "Simple Chicken" > .tmp/selected_recipes.json

# Update last_used after a plan is approved
python execution/recipe_manager.py update-used "Simple Chicken"
```

Recipes are viewable and editable directly in Obsidian. The YAML frontmatter is fully compatible with Obsidian properties, and you can use Obsidian's tag search, dataview queries, or daily notes to organize and discover your recipe collection.

## Project structure

```
execution/
  meal_config.py      # Household config management (setup/show/set/reset)
  meal_planner.py     # LLM meal plan generation
  grocery_list.py     # Resolve ingredients to Kroger products
  kroger_api.py       # Kroger API client (auth, stores, search, cart)
  recipe_manager.py   # Obsidian vault recipe management
directives/
  meal_plan.md        # Workflow SOP for AI orchestration
references/
  pcos.md             # PCOS dietary guidelines reference
skills/meal-plan/
  SKILL.md            # OpenClaw skill manifest
```

## Requirements

- Python 3.10+
- `requests`, `anthropic`, `python-dotenv`, `pyyaml` (installed automatically by `deploy.sh`)

## License

MIT
