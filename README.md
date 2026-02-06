# meal-plan

AI-powered weekly meal planner that generates recipes, builds a grocery list with real Kroger prices, and adds items to your Kroger cart for pickup.

## What it does

1. **Generates a meal plan** tailored to your household size, budget, and dietary preferences using Claude
2. **Resolves ingredients** against the Kroger product catalog at your nearest store with real prices
3. **Adds items to your Kroger cart** for pickup (never checks out without your approval)

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

# Find nearest Kroger
python execution/kroger_api.py stores --zip 90210

# Resolve grocery list to real products with prices
python execution/grocery_list.py --plan .tmp/meal_plan.json --location STORE_ID

# Add items to cart
python execution/kroger_api.py cart-add --items '[{"upc":"0001111041700","quantity":1}]'
```

## Project structure

```
execution/
  meal_config.py      # Household config management (setup/show/set/reset)
  meal_planner.py     # LLM meal plan generation
  grocery_list.py     # Resolve ingredients to Kroger products
  kroger_api.py       # Kroger API client (auth, stores, search, cart)
directives/
  meal_plan.md        # Workflow SOP for AI orchestration
references/
  pcos.md             # PCOS dietary guidelines reference
skills/meal-plan/
  SKILL.md            # OpenClaw skill manifest
```

## Requirements

- Python 3.10+
- `requests`, `anthropic`, `python-dotenv` (installed automatically by `deploy.sh`)

## License

MIT
