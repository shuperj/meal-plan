#!/usr/bin/env bash
# Deploy the meal-plan skill on an OpenClaw machine from GitHub.
#
# Usage (on OpenClaw PC):
#   curl -fsSL https://raw.githubusercontent.com/shuperj/meal-plan/master/deploy.sh | bash
#
# Or if repo is already cloned:
#   cd ~/openclaw/meal-plan && bash deploy.sh
#
# This script:
# 1. Fetches only necessary files from GitHub (execution/, references/, skills/)
# 2. Installs to ~/.openclaw/skills/meal-plan/
# 3. Installs Python dependencies with uv
# 4. Creates .env template

set -euo pipefail

REPO="shuperj/meal-plan"
BRANCH="master"
SKILL_DIR="${HOME}/.openclaw/skills/meal-plan"
INSTALL_DIR="${SKILL_DIR}"

echo "Deploying meal-plan skill from GitHub..."
echo "  Target: ${SKILL_DIR}"
echo ""

# Check if we're in the repo already
if [[ -f "skills/meal-plan/SKILL.md" ]]; then
    echo "Found local repo, using local files..."
    SCRIPT_DIR="$(pwd)"
else
    echo "Fetching files from GitHub..."
    # Create temp directory
    TEMP_DIR=$(mktemp -d)
    cd "$TEMP_DIR"

    # Clone just the directories and files we need (sparse checkout, no-cone for file-level paths)
    git clone --depth=1 --filter=blob:none --no-checkout "https://github.com/${REPO}.git" meal-plan
    cd meal-plan
    git sparse-checkout init --no-cone
    git sparse-checkout set execution/ references/ skills/ requirements.txt
    git checkout

    SCRIPT_DIR="$TEMP_DIR/meal-plan"
fi

# Create directories
mkdir -p "${SKILL_DIR}"
mkdir -p "${INSTALL_DIR}/execution"
mkdir -p "${INSTALL_DIR}/references"
mkdir -p "${INSTALL_DIR}/.tmp"

# Copy skill manifest
cp "${SCRIPT_DIR}/skills/meal-plan/SKILL.md" "${SKILL_DIR}/SKILL.md"
echo "✓ Copied SKILL.md"

# Copy execution scripts
for script in kroger_api.py meal_planner.py grocery_list.py meal_config.py; do
    if [[ -f "${SCRIPT_DIR}/execution/${script}" ]]; then
        cp "${SCRIPT_DIR}/execution/${script}" "${INSTALL_DIR}/execution/${script}"
        chmod +x "${INSTALL_DIR}/execution/${script}"
        echo "✓ Copied execution/${script}"
    fi
done

# Copy references
if [[ -f "${SCRIPT_DIR}/references/pcos.md" ]]; then
    cp "${SCRIPT_DIR}/references/pcos.md" "${INSTALL_DIR}/references/pcos.md"
    echo "✓ Copied references/pcos.md"
fi

# Copy requirements.txt
if [[ -f "${SCRIPT_DIR}/requirements.txt" ]]; then
    cp "${SCRIPT_DIR}/requirements.txt" "${INSTALL_DIR}/requirements.txt"
    echo "✓ Copied requirements.txt"
fi

# Install Python dependencies in a venv
VENV_DIR="${INSTALL_DIR}/.venv"
echo ""
echo "Setting up Python virtual environment..."
cd "${INSTALL_DIR}"
if [[ ! -d "${VENV_DIR}" ]]; then
    python3 -m venv "${VENV_DIR}"
    echo "✓ Created venv at ${VENV_DIR}"
fi
if command -v uv &> /dev/null; then
    uv pip install -r requirements.txt -p "${VENV_DIR}/bin/python"
    echo "✓ Dependencies installed (uv)"
else
    "${VENV_DIR}/bin/pip" install -r requirements.txt
    echo "✓ Dependencies installed (pip)"
fi

# Create .env template
ENV_FILE="${INSTALL_DIR}/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
    echo ""
    echo "Creating .env template..."
    cat > "${ENV_FILE}" <<'EOF'
# Kroger API (register at developer.kroger.com)
KROGER_CLIENT_ID=
KROGER_CLIENT_SECRET=
KROGER_REDIRECT_URI=http://localhost:8080/callback
KROGER_REFRESH_TOKEN=
KROGER_ZIP=
KROGER_LOCATION_ID=

# Anthropic (for meal plan generation)
ANTHROPIC_API_KEY=
EOF
    echo "✓ Created ${ENV_FILE}"
else
    echo ""
    echo "✓ .env already exists at ${ENV_FILE}"
fi

# Cleanup temp directory if we created one
if [[ -n "${TEMP_DIR:-}" ]]; then
    rm -rf "$TEMP_DIR"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✓ Installation complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
PYTHON="${VENV_DIR}/bin/python"
echo "Next steps:"
echo "  1. Fill in API keys: nano ${ENV_FILE}"
echo "  2. Configure household: ${PYTHON} ${INSTALL_DIR}/execution/meal_config.py setup"
echo "  3. Run Kroger auth: ${PYTHON} ${INSTALL_DIR}/execution/kroger_api.py auth"
echo "  4. Verify skill: openclaw skills list"
echo "  5. Use /meal-plan in OpenClaw to get started"
echo ""
