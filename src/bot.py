import os
import json
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)

from db.database import Database
from llm.provider import LLMProvider
from memory.manager import MemoryManager
from agents.nutrition import NutritionAgent
from agents.fitness import FitnessAgent
from agents.finance import FinanceAgent
from agents.career import CareerAgent
from agents.manager import ManagerAgent

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# Globals initialized in main()
db: Database = None
llm: LLMProvider = None
memory: MemoryManager = None
agents: dict = {}
user_state: dict = {}  # telegram_id -> current agent_id


MAIN_MENU = ReplyKeyboardMarkup(
    [["🥗 Nutrition", "💪 Fitness"], ["💰 Finance", "🎯 Career"], ["🧠 Personal Manager"]],
    resize_keyboard=True,
)

BUTTON_TO_AGENT = {
    "🥗 Nutrition": "nutrition",
    "💪 Fitness": "fitness",
    "💰 Finance": "finance",
    "🎯 Career": "career",
    "🧠 Personal Manager": "manager",
}


def agent_action_keyboard(agent_id: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("💬 Continue Conversation", callback_data=f"continue:{agent_id}")],
        [InlineKeyboardButton("📋 Session Summary", callback_data=f"summary:{agent_id}")],
        [InlineKeyboardButton("🆕 Start Fresh Topic", callback_data=f"fresh:{agent_id}")],
    ]
    return InlineKeyboardMarkup(buttons)


def manager_action_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("📊 Full Weekly Digest", callback_data="manager:digest")],
        [InlineKeyboardButton("🔗 Cross-Domain Insights", callback_data="manager:insights")],
        [InlineKeyboardButton("📤 Export Data", callback_data="settings:export")],
        [InlineKeyboardButton("🗑️ Delete Agent Data", callback_data="settings:delete")],
    ]
    return InlineKeyboardMarkup(buttons)


def get_user_id(update: Update) -> int:
    tg_id = update.effective_user.id
    username = update.effective_user.username
    return db.get_or_create_user(tg_id, username)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state[update.effective_user.id] = None
    await update.message.reply_text(
        "🤖 *Welcome to LifePilot!*\n\n"
        "I'm your personal assistant ecosystem. Choose an area to get started:",
        reply_markup=MAIN_MENU,
        parse_mode="Markdown",
    )


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    agent_id = BUTTON_TO_AGENT.get(text)
    if not agent_id:
        return

    tg_id = update.effective_user.id
    user_state[tg_id] = agent_id
    agent = agents[agent_id]

    if agent_id == "manager":
        manager: ManagerAgent = agent
        digest_preview = manager.get_digest(get_user_id(update))
        await update.message.reply_text(
            digest_preview,
            reply_markup=manager_action_keyboard(),
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            agent.get_greeting(),
            reply_markup=agent_action_keyboard(agent_id),
        )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = get_user_id(update)
    tg_id = update.effective_user.id

    if data.startswith("continue:"):
        agent_id = data.split(":")[1]
        user_state[tg_id] = agent_id
        agent = agents[agent_id]
        await query.edit_message_text(agent.get_continue_greeting(user_id))

    elif data.startswith("summary:"):
        agent_id = data.split(":")[1]
        agent = agents[agent_id]
        summary = agent.get_summary(user_id)
        await query.edit_message_text(f"📋 *Session Summary*\n\n{summary}", parse_mode="Markdown")

    elif data.startswith("fresh:"):
        agent_id = data.split(":")[1]
        user_state[tg_id] = agent_id
        agent = agents[agent_id]
        await query.edit_message_text(
            f"{agent.emoji} Fresh start! What's on your mind regarding {agent.name.replace('Bot', '').lower()}?"
        )

    elif data == "manager:digest":
        manager: ManagerAgent = agents["manager"]
        digest = manager.get_digest(user_id)
        await query.edit_message_text(f"📊 *Weekly Digest*\n\n{digest}", parse_mode="Markdown")

    elif data == "manager:insights":
        manager: ManagerAgent = agents["manager"]
        insights = manager.get_cross_insights(user_id)
        await query.edit_message_text(f"🔗 *Cross-Domain Insights*\n\n{insights}", parse_mode="Markdown")

    elif data == "settings:export":
        agent_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{a.emoji} {a.name}", callback_data=f"doexport:{a.agent_id}")]
            for a in agents.values() if a.agent_id != "manager"
        ])
        await query.edit_message_text("Which agent's data would you like to export?", reply_markup=agent_keyboard)

    elif data.startswith("doexport:"):
        agent_id = data.split(":")[1]
        export = db.export_agent_data(user_id, agent_id)
        export_json = json.dumps(export, indent=2, default=str)
        # Send as a document
        from io import BytesIO
        buf = BytesIO(export_json.encode())
        buf.name = f"lifepilot_{agent_id}_export.json"
        await context.bot.send_document(chat_id=update.effective_chat.id, document=buf)

    elif data == "settings:delete":
        agent_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{a.emoji} {a.name}", callback_data=f"confirmdelete:{a.agent_id}")]
            for a in agents.values() if a.agent_id != "manager"
        ])
        await query.edit_message_text(
            "⚠️ Which agent's data would you like to *permanently delete*?",
            reply_markup=agent_keyboard,
            parse_mode="Markdown",
        )

    elif data.startswith("confirmdelete:"):
        agent_id = data.split(":")[1]
        confirm_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, delete", callback_data=f"dodelete:{agent_id}"),
             InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
        ])
        await query.edit_message_text(
            f"Are you sure you want to delete all {agents[agent_id].emoji} {agents[agent_id].name} data?",
            reply_markup=confirm_kb,
        )

    elif data.startswith("dodelete:"):
        agent_id = data.split(":")[1]
        db.delete_agent_data(user_id, agent_id)
        await query.edit_message_text(f"🗑️ All {agents[agent_id].name} data has been deleted.")

    elif data == "cancel":
        await query.edit_message_text("Cancelled.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    agent_id = user_state.get(tg_id)

    if not agent_id or agent_id == "manager":
        await update.message.reply_text(
            "Please select an agent from the menu below to start chatting.",
            reply_markup=MAIN_MENU,
        )
        return

    user_id = get_user_id(update)
    agent = agents[agent_id]

    # Show typing indicator
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    response = await agent.handle_message(user_id, update.message.text)
    await update.message.reply_text(response)


def main():
    global db, llm, memory, agents

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        log.error("TELEGRAM_BOT_TOKEN not set. Run setup.sh first.")
        return

    db = Database()
    llm = LLMProvider()
    memory = MemoryManager(db, llm)

    agents = {
        "nutrition": NutritionAgent(db, llm, memory),
        "fitness": FitnessAgent(db, llm, memory),
        "finance": FinanceAgent(db, llm, memory),
        "career": CareerAgent(db, llm, memory),
        "manager": ManagerAgent(db, llm, memory),
    }

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    # Menu button handler — matches the exact button labels
    app.add_handler(MessageHandler(
        filters.Regex(r"^(🥗 Nutrition|💪 Fitness|💰 Finance|🎯 Career|🧠 Personal Manager)$"),
        handle_menu,
    ))
    # Free text handler — routes to active agent
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("LifePilot is running. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
