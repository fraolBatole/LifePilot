#!/usr/bin/env bash
set -e

echo "═══════════════════════════════════════════════════════"
echo "  🤖 LifePilot Setup — Personal Telegram Assistant"
echo "═══════════════════════════════════════════════════════"
echo ""

ENV_FILE=".env"
cp .env.example "$ENV_FILE" 2>/dev/null || true

# ─── Step 1: LLM Provider ───────────────────────────────
echo "Step 1/4: LLM API Configuration"
echo "─────────────────────────────────"
echo "Which LLM provider would you like to use?"
echo "  1) OpenAI (GPT-4o)"
echo "  2) Google Gemini"
echo "  3) Anthropic Claude"
read -rp "> " provider_choice

case $provider_choice in
    1)
        provider="openai"
        read -rp "Enter your OpenAI API key: " api_key
        sed -i.bak "s/^LLM_PROVIDER=.*/LLM_PROVIDER=openai/" "$ENV_FILE"
        sed -i.bak "s/^OPENAI_API_KEY=.*/OPENAI_API_KEY=$api_key/" "$ENV_FILE"
        ;;
    2)
        provider="gemini"
        read -rp "Enter your Gemini API key: " api_key
        sed -i.bak "s/^LLM_PROVIDER=.*/LLM_PROVIDER=gemini/" "$ENV_FILE"
        sed -i.bak "s/^GEMINI_API_KEY=.*/GEMINI_API_KEY=$api_key/" "$ENV_FILE"
        ;;
    3)
        provider="claude"
        read -rp "Enter your Anthropic API key: " api_key
        sed -i.bak "s/^LLM_PROVIDER=.*/LLM_PROVIDER=claude/" "$ENV_FILE"
        sed -i.bak "s/^ANTHROPIC_API_KEY=.*/ANTHROPIC_API_KEY=$api_key/" "$ENV_FILE"
        ;;
    *)
        echo "Invalid choice. Exiting."
        exit 1
        ;;
esac
echo "✅ $provider configured!"
echo ""

# ─── Step 2: Telegram Bot ───────────────────────────────
echo "Step 2/4: Create Your Telegram Bot"
echo "────────────────────────────────────"
echo "To create a Telegram bot, follow these steps:"
echo ""
echo "  1. Open Telegram and search for @BotFather"
echo "  2. Send /newbot"
echo "  3. Choose a name, e.g. \"My LifePilot\""
echo "  4. Choose a username, e.g. \"my_lifepilot_bot\""
echo "  5. BotFather will give you an API token"
echo ""
read -rp "📋 Paste your Telegram Bot Token: " bot_token
sed -i.bak "s/^TELEGRAM_BOT_TOKEN=.*/TELEGRAM_BOT_TOKEN=$bot_token/" "$ENV_FILE"
echo "✅ Bot token saved!"
echo ""

# ─── Step 3: MCP Configuration ──────────────────────────
echo "Step 3/4: MCP Configuration (Optional)"
echo "────────────────────────────────────────"
echo "MCP servers allow agents to use external tools (web search, calculator, etc.)."
echo "You can configure these later in config/mcp_permissions.yaml"
echo "✅ Default MCP config ready."
echo ""

# ─── Step 4: Dependencies & Database ────────────────────
echo "Step 4/4: Dependencies & Database"
echo "──────────────────────────────────"

if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required. Please install it first."
    exit 1
fi

python3 -m pip install -r requirements.txt --quiet
echo "✅ Dependencies installed!"

mkdir -p data
python3 -c "
import sys; sys.path.insert(0, 'src')
from db.database import Database
Database('data/lifepilot.db')
print('✅ SQLite database created at ./data/lifepilot.db')
"

# Clean up sed backup files
rm -f .env.bak

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✅ Setup complete!"
echo ""
echo "  To start LifePilot:  ./start.sh"
echo "  To stop:             Ctrl+C"
echo "═══════════════════════════════════════════════════════"
