#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────
#  CodeCompass — Interactive Setup Script (Linux / macOS)
# ──────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Colors ───────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

ok()   { echo -e "  ${GREEN}✓${NC} $*"; }
fail() { echo -e "  ${RED}✗${NC} $*"; }
info() { echo -e "  ${BLUE}→${NC} $*"; }
warn() { echo -e "  ${YELLOW}!${NC} $*"; }

header() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}  $*${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ── Resolve script directory ─────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

header "🧭 CodeCompass Setup"
echo ""
echo -e "  This script will set up CodeCompass on your machine."
echo -e "  It creates a virtual environment, installs dependencies,"
echo -e "  and configures GitHub Copilot authentication."
echo ""

# ── Step 1: Check Python ────────────────────────────────────────
header "Step 1/5 — Checking Python"

PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+')
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [[ "$major" -ge 3 && "$minor" -ge 10 ]]; then
            PYTHON_CMD="$cmd"
            ok "Found $cmd $("$cmd" --version 2>&1)"
            break
        else
            warn "$cmd is version $version (need 3.10+)"
        fi
    fi
done

if [[ -z "$PYTHON_CMD" ]]; then
    fail "Python 3.10+ is required but not found."
    echo ""
    echo "  Install Python from: https://www.python.org/downloads/"
    exit 1
fi

# ── Step 2: Check Git ───────────────────────────────────────────
header "Step 2/5 — Checking Git"

if command -v git &>/dev/null; then
    ok "Found git $(git --version | grep -oP '\d+\.\d+\.\d+')"
else
    fail "Git is required but not found."
    echo ""
    echo "  Install Git from: https://git-scm.com/downloads"
    exit 1
fi

# ── Step 3: Virtual Environment ─────────────────────────────────
header "Step 3/5 — Virtual Environment"

VENV_DIR="$SCRIPT_DIR/.venv"

if [[ -d "$VENV_DIR" ]]; then
    ok "Virtual environment already exists at .venv/"
    read -rp "  Recreate it? [y/N] " recreate
    if [[ "$recreate" =~ ^[Yy]$ ]]; then
        info "Removing existing virtual environment..."
        rm -rf "$VENV_DIR"
        info "Creating new virtual environment..."
        "$PYTHON_CMD" -m venv "$VENV_DIR"
        ok "Virtual environment created"
    else
        ok "Keeping existing virtual environment"
    fi
else
    info "Creating virtual environment..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    ok "Virtual environment created at .venv/"
fi

# Activate
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
ok "Virtual environment activated"

# ── Step 4: Install CodeCompass ─────────────────────────────────
header "Step 4/5 — Installing CodeCompass"

info "Upgrading pip..."
pip install --upgrade pip --quiet 2>/dev/null
ok "pip upgraded"

info "Installing CodeCompass and dependencies..."
pip install -e . --quiet 2>/dev/null
ok "CodeCompass installed"

# Verify
VERSION=$(codecompass --version 2>/dev/null || echo "unknown")
ok "codecompass $VERSION"

# ── Step 5: Copilot Authentication ──────────────────────────────
header "Step 5/5 — GitHub Copilot Authentication"

# Find the bundled Copilot CLI
COPILOT_BIN=$("$PYTHON_CMD" -c "
import copilot, pathlib, sys
bin_dir = pathlib.Path(copilot.__file__).parent / 'bin'
for name in ['copilot', 'copilot.exe']:
    p = bin_dir / name
    if p.exists():
        print(p)
        sys.exit(0)
print('')
" 2>/dev/null || echo "")

if [[ -z "$COPILOT_BIN" || ! -x "$COPILOT_BIN" ]]; then
    warn "Could not find bundled Copilot CLI binary."
    warn "You may need to authenticate manually later."
else
    # Check if already authenticated
    AUTH_STATUS=$("$COPILOT_BIN" --headless --no-auto-update version 2>/dev/null || echo "")

    echo ""
    echo -e "  CodeCompass needs to authenticate with GitHub Copilot."
    echo -e "  This uses OAuth device-flow (opens your browser)."
    echo ""
    read -rp "  Authenticate now? [Y/n] " do_auth

    if [[ ! "$do_auth" =~ ^[Nn]$ ]]; then
        info "Starting Copilot login..."
        echo ""
        "$COPILOT_BIN" login
        echo ""
        ok "Authentication complete"
    else
        warn "Skipped authentication. Run later:"
        echo "    $COPILOT_BIN login"
    fi
fi

# ── Done ────────────────────────────────────────────────────────
header "🎉 Setup Complete!"

echo ""
echo -e "  ${BOLD}Getting Started:${NC}"
echo ""
echo -e "  ${CYAN}# Activate the virtual environment${NC}"
echo -e "  source .venv/bin/activate"
echo ""
echo -e "  ${CYAN}# Scan and onboard a repository${NC}"
echo -e "  codecompass onboard --repo /path/to/repo"
echo ""
echo -e "  ${CYAN}# Start interactive chat${NC}"
echo -e "  codecompass chat --repo /path/to/repo"
echo ""
echo -e "  ${CYAN}# Launch the full TUI${NC}"
echo -e "  codecompass tui --repo /path/to/repo"
echo ""
echo -e "  ${CYAN}# Ask a question about any codebase${NC}"
echo -e "  codecompass ask \"How does authentication work?\" --repo /path/to/repo"
echo ""
echo -e "  ${CYAN}# Export onboarding docs${NC}"
echo -e "  codecompass export --format markdown -o onboarding.md --repo /path/to/repo"
echo ""
echo -e "  Run ${BOLD}codecompass --help${NC} for all commands."
echo ""
