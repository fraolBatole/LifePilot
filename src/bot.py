import os
import json
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes,
)

from db.database import Database
from llm.provider import LLMProvider
from memory.manager import MemoryManager
from tools.registry import ToolRegistry
from tools.web_search import WEB_SEARCH_TOOL
from tools.schedule_task import SCHEDULE_TASK_TOOL, set_scheduler
from scheduler.engine import JobScheduler
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
tool_registry: ToolRegistry = None
job_scheduler: JobScheduler = None
agents: dict = {}
user_state: dict = {}  # telegram_id -> current agent_id

# ── Bio conversation states ─────────────────────────────────────────
(BIO_NAME, BIO_AGE, BIO_GENDER, BIO_HEIGHT, BIO_WEIGHT, BIO_ACTIVITY,
 BIO_EDUCATION, BIO_FIELD, BIO_COUNTRY, BIO_EXPERIENCE, BIO_GOALS) = range(11)

BIO_FIELDS = [
    ("name", "What's your name (or nickname)?", None),
    ("age", "How old are you?", None),
    ("gender", "What's your gender?", [
        [InlineKeyboardButton("👨 Male", callback_data="bio_gender:Male"),
         InlineKeyboardButton("👩 Female", callback_data="bio_gender:Female")],
        [InlineKeyboardButton("🧑 Non-binary", callback_data="bio_gender:Non-binary"),
         InlineKeyboardButton("🤐 Prefer not to say", callback_data="bio_gender:Not specified")],
    ]),
    ("height", "What's your height? (e.g., 5'10\" or 178cm)", None),
    ("weight", "What's your weight? (e.g., 165 lbs or 75 kg)", None),
    ("activity_level", "What's your activity level?", [
        [InlineKeyboardButton("🛋️ Sedentary", callback_data="bio_activity:Sedentary")],
        [InlineKeyboardButton("🚶 Lightly active", callback_data="bio_activity:Lightly active")],
        [InlineKeyboardButton("🏃 Moderately active", callback_data="bio_activity:Moderately active")],
        [InlineKeyboardButton("💪 Very active", callback_data="bio_activity:Very active")],
    ]),
    ("education", "What's your education level?", [
        [InlineKeyboardButton("🎓 High School", callback_data="bio_education:High School"),
         InlineKeyboardButton("🎓 B.Sc / B.A.", callback_data="bio_education:Bachelor's")],
        [InlineKeyboardButton("🎓 M.Sc / M.A.", callback_data="bio_education:Master's"),
         InlineKeyboardButton("🎓 Ph.D.", callback_data="bio_education:PhD")],
        [InlineKeyboardButton("📚 Bootcamp / Self-taught", callback_data="bio_education:Bootcamp/Self-taught"),
         InlineKeyboardButton("🤐 Skip", callback_data="bio_education:skip")],
    ]),
    ("field_of_study", "What's your field of study or expertise? (e.g., Computer Science, Marketing, Nursing)", None),
    ("country", "Where are you based? (country or city, e.g., USA, London, Germany)", None),
    ("work_experience", "How many years of work experience do you have?", [
        [InlineKeyboardButton("🆕 Student / None", callback_data="bio_experience:Student/None"),
         InlineKeyboardButton("1️⃣ 0-2 years", callback_data="bio_experience:0-2 years")],
        [InlineKeyboardButton("2️⃣ 3-5 years", callback_data="bio_experience:3-5 years"),
         InlineKeyboardButton("3️⃣ 5-10 years", callback_data="bio_experience:5-10 years")],
        [InlineKeyboardButton("4️⃣ 10+ years", callback_data="bio_experience:10+ years"),
         InlineKeyboardButton("🤐 Skip", callback_data="bio_experience:skip")],
    ]),
    ("goals", "Any health, fitness, career, or financial goals you'd like your agents to know about? (or type 'skip')", None),
]

# ── Menus ────────────────────────────────────────────────────────────

MAIN_MENU = ReplyKeyboardMarkup(
    [["🥗 Nutrition", "💪 Fitness"],
     ["💰 Finance", "🎯 Career"],
     ["🧠 Personal Manager", "📝 My Bio"]],
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
        [InlineKeyboardButton("📅 Scheduled Jobs", callback_data="manager:jobs")],
        [InlineKeyboardButton("📤 Export Data", callback_data="settings:export")],
        [InlineKeyboardButton("🗑️ Delete Agent Data", callback_data="settings:delete")],
    ]
    return InlineKeyboardMarkup(buttons)


def get_user_id(update: Update) -> int:
    tg_id = update.effective_user.id
    username = update.effective_user.username
    return db.get_or_create_user(tg_id, username)


# ── Bio helpers ──────────────────────────────────────────────────────

def _format_bio_display(bio: dict) -> str:
    """Format bio dict for Telegram display."""
    if not bio:
        return "No bio saved yet."

    LABELS = {
        "name": "👤 Name",
        "age": "🎂 Age",
        "gender": "⚧ Gender",
        "height": "📏 Height",
        "weight": "⚖️ Weight",
        "activity_level": "🏃 Activity",
        "education": "🎓 Education",
        "field_of_study": "📚 Field",
        "country": "🌍 Location",
        "work_experience": "💼 Experience",
        "goals": "🎯 Goals",
    }
    lines = []
    for key, label in LABELS.items():
        val = bio.get(key)
        if val:
            lines.append(f"{label}: {val}")
    return "\n".join(lines) if lines else "No bio saved yet."


def _bio_action_keyboard(has_bio: bool) -> InlineKeyboardMarkup:
    buttons = [] 
    if has_bio:
        buttons.append([InlineKeyboardButton("✏️ Update Bio", callback_data="bio:update")])
        buttons.append([InlineKeyboardButton("🗑️ Clear Bio", callback_data="bio:clear")])
    else:
        buttons.append([InlineKeyboardButton("📝 Fill Out Bio", callback_data="bio:start")])
    return InlineKeyboardMarkup(buttons)


# ── Bio conversation flow ────────────────────────────────────────────

async def bio_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current bio and action buttons."""
    user_state[update.effective_user.id] = None  # exit any active agent
    user_id = get_user_id(update)
    bio = db.get_bio(user_id)

    text = f"📝 *Your Bio*\n\n{_format_bio_display(bio)}"
    await update.message.reply_text(
        text,
        reply_markup=_bio_action_keyboard(bool(bio)),
        parse_mode="Markdown",
    )


async def bio_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the bio questionnaire from a callback button."""
    query = update.callback_query
    await query.answer()

    if query.data == "bio:clear":
        user_id = get_user_id(update)
        db.set_bio(user_id, {})
        await query.edit_message_text("🗑️ Bio cleared! You can fill it out again anytime from the menu.")
        return ConversationHandler.END

    # bio:start or bio:update — begin the questionnaire
    context.user_data["bio_draft"] = {}
    user_id = get_user_id(update)
    existing = db.get_bio(user_id)
    if existing and query.data == "bio:update":
        context.user_data["bio_draft"] = dict(existing)

    await query.edit_message_text(
        "📝 *Let's set up your bio!*\n\n"
        "I'll ask you a few quick questions. Your answers help all your agents "
        "give better, personalized advice.\n\n"
        "Type 'skip' to skip any question.\n\n"
        "─ ─ ─ ─ ─ ─ ─ ─\n\n"
        f"👤 {BIO_FIELDS[0][1]}",
        parse_mode="Markdown",
    )
    return BIO_NAME


async def bio_receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() != "skip":
        context.user_data["bio_draft"]["name"] = text

    await update.message.reply_text(f"🎂 {BIO_FIELDS[1][1]}")
    return BIO_AGE


async def bio_receive_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() != "skip":
        context.user_data["bio_draft"]["age"] = text

    # Gender has inline buttons
    await update.message.reply_text(
        f"⚧ {BIO_FIELDS[2][1]}",
        reply_markup=InlineKeyboardMarkup(BIO_FIELDS[2][2]),
    )
    return BIO_GENDER


async def bio_receive_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    value = query.data.split(":")[1]
    context.user_data["bio_draft"]["gender"] = value

    await query.edit_message_text(f"📏 {BIO_FIELDS[3][1]}")
    return BIO_HEIGHT


async def bio_receive_gender_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle gender typed as text instead of button."""
    text = update.message.text.strip()
    if text.lower() != "skip":
        context.user_data["bio_draft"]["gender"] = text

    await update.message.reply_text(f"📏 {BIO_FIELDS[3][1]}")
    return BIO_HEIGHT


async def bio_receive_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() != "skip":
        context.user_data["bio_draft"]["height"] = text

    await update.message.reply_text(f"⚖️ {BIO_FIELDS[4][1]}")
    return BIO_WEIGHT


async def bio_receive_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() != "skip":
        context.user_data["bio_draft"]["weight"] = text

    # Activity level has inline buttons
    await update.message.reply_text(
        f"🏃 {BIO_FIELDS[5][1]}",
        reply_markup=InlineKeyboardMarkup(BIO_FIELDS[5][2]),
    )
    return BIO_ACTIVITY


async def bio_receive_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    value = query.data.split(":")[1]
    context.user_data["bio_draft"]["activity_level"] = value

    # Next: education (inline buttons)
    await query.edit_message_text(
        f"🎓 {BIO_FIELDS[6][1]}",
        reply_markup=InlineKeyboardMarkup(BIO_FIELDS[6][2]),
    )
    return BIO_EDUCATION


async def bio_receive_activity_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle activity level typed as text instead of button."""
    text = update.message.text.strip()
    if text.lower() != "skip":
        context.user_data["bio_draft"]["activity_level"] = text

    await update.message.reply_text(
        f"🎓 {BIO_FIELDS[6][1]}",
        reply_markup=InlineKeyboardMarkup(BIO_FIELDS[6][2]),
    )
    return BIO_EDUCATION


async def bio_receive_education(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    value = query.data.split(":")[1]
    if value.lower() != "skip":
        context.user_data["bio_draft"]["education"] = value

    await query.edit_message_text(f"📚 {BIO_FIELDS[7][1]}")
    return BIO_FIELD


async def bio_receive_education_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() != "skip":
        context.user_data["bio_draft"]["education"] = text

    await update.message.reply_text(f"📚 {BIO_FIELDS[7][1]}")
    return BIO_FIELD


async def bio_receive_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() != "skip":
        context.user_data["bio_draft"]["field_of_study"] = text

    await update.message.reply_text(f"🌍 {BIO_FIELDS[8][1]}")
    return BIO_COUNTRY


async def bio_receive_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() != "skip":
        context.user_data["bio_draft"]["country"] = text

    # Next: work experience (inline buttons)
    await update.message.reply_text(
        f"💼 {BIO_FIELDS[9][1]}",
        reply_markup=InlineKeyboardMarkup(BIO_FIELDS[9][2]),
    )
    return BIO_EXPERIENCE


async def bio_receive_experience(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    value = query.data.split(":")[1]
    if value.lower() != "skip":
        context.user_data["bio_draft"]["work_experience"] = value

    await query.edit_message_text(f"🎯 {BIO_FIELDS[10][1]}")
    return BIO_GOALS


async def bio_receive_experience_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() != "skip":
        context.user_data["bio_draft"]["work_experience"] = text

    await update.message.reply_text(f"🎯 {BIO_FIELDS[10][1]}")
    return BIO_GOALS


async def bio_receive_goals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() != "skip":
        context.user_data["bio_draft"]["goals"] = text

    # Save to DB
    user_id = get_user_id(update)
    bio = context.user_data.get("bio_draft", {})
    db.set_bio(user_id, bio)

    display = _format_bio_display(bio)
    await update.message.reply_text(
        f"✅ *Bio saved!*\n\n{display}\n\n"
        "─ ─ ─ ─ ─ ─ ─ ─\n\n"
        "All your agents now have access to this info for personalized advice. "
        "You can update it anytime from the 📝 My Bio button.",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU,
    )
    return ConversationHandler.END


async def bio_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bio setup cancelled. You can come back anytime!",
        reply_markup=MAIN_MENU,
    )
    return ConversationHandler.END


# ── Core handlers ────────────────────────────────────────────────────

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
            f"{agent.emoji} Fresh start! What's on your mind regarding {agent.name.replace('Bot', '').lower()}?",
            parse_mode="Markdown",
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

    elif data == "manager:jobs":
        user_id = get_user_id(update)
        jobs = job_scheduler.get_user_jobs(user_id)
        if not jobs:
            await query.edit_message_text(
                "📅 *Scheduled Jobs*\n\nNo scheduled jobs yet.\n\n"
                "💡 You can ask any agent to schedule a recurring task. "
                "For example, tell CareerBot:\n"
                '"Find me 5 job postings every day at 7 AM"',
                parse_mode="Markdown",
            )
        else:
            AGENT_EMOJIS = {"nutrition": "🥗", "fitness": "💪", "finance": "💰", "career": "🎯"}
            lines = ["📅 *Scheduled Jobs*\n"]
            buttons = []
            for j in jobs:
                emoji = AGENT_EMOJIS.get(j["agent_id"], "📌")
                status = "✅" if j["enabled"] else "⏸️"
                lines.append(
                    f"{status} *Job #{j['id']}* — {emoji} {j['agent_id'].title()}\n"
                    f"   ⏰ Schedule: `{j['cron_expression']}`\n"
                    f"   📝 {j['task_description'][:80]}"
                )
                buttons.append([
                    InlineKeyboardButton(
                        f"🗑️ Delete Job #{j['id']}",
                        callback_data=f"deljob:{j['id']}",
                    )
                ])
            await query.edit_message_text(
                "\n\n".join(lines),
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode="Markdown",
            )

    elif data.startswith("deljob:"):
        job_id = int(data.split(":")[1])
        confirm_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, delete", callback_data=f"confirmdeljob:{job_id}"),
             InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
        ])
        await query.edit_message_text(
            f"Are you sure you want to delete scheduled job #{job_id}?",
            reply_markup=confirm_kb,
        )

    elif data.startswith("confirmdeljob:"):
        job_id = int(data.split(":")[1])
        job_scheduler.remove_job(job_id)
        await query.edit_message_text(f"🗑️ Scheduled job #{job_id} has been deleted.")

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
    chat_id = update.effective_chat.id

    # Show typing indicator
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    response = await agent.handle_message(user_id, update.message.text, chat_id=chat_id)
    try:
        await update.message.reply_text(response, parse_mode="Markdown")
    except Exception:
        # Fallback if the LLM response has invalid Markdown
        await update.message.reply_text(response)


def _build_tool_registry() -> ToolRegistry:
    """Create the tool registry and configure per-agent permissions."""
    registry = ToolRegistry()

    # Register available tools
    registry.register(WEB_SEARCH_TOOL)
    registry.register(SCHEDULE_TASK_TOOL)

    # Set per-agent permissions (manager has no tools)
    registry.set_permissions("nutrition", ["web_search", "schedule_task"])
    registry.set_permissions("fitness", ["web_search", "schedule_task"])
    registry.set_permissions("finance", ["web_search", "schedule_task"])
    registry.set_permissions("career", ["web_search", "schedule_task"])
    registry.set_permissions("manager", [])

    return registry


async def post_init(app: Application):
    """Called after the Application is initialized — start the scheduler."""
    global job_scheduler
    job_scheduler = JobScheduler(db, agents, app)
    set_scheduler(job_scheduler)
    job_scheduler.start()


async def post_shutdown(app: Application):
    """Called on shutdown — stop the scheduler."""
    if job_scheduler:
        job_scheduler.stop()


def main():
    global db, llm, memory, tool_registry, agents

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        log.error("TELEGRAM_BOT_TOKEN not set. Run setup.sh first.")
        return

    db = Database()
    llm = LLMProvider()
    memory = MemoryManager(db, llm)
    tool_registry = _build_tool_registry()

    agents = {
        "nutrition": NutritionAgent(db, llm, memory, tool_registry),
        "fitness": FitnessAgent(db, llm, memory, tool_registry),
        "finance": FinanceAgent(db, llm, memory, tool_registry),
        "career": CareerAgent(db, llm, memory, tool_registry),
        "manager": ManagerAgent(db, llm, memory, tool_registry),
    }

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Bio conversation handler (must be added before generic handlers)
    bio_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(bio_start_callback, pattern=r"^bio:(start|update|clear)$"),
        ],
        states={
            BIO_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, bio_receive_name)],
            BIO_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, bio_receive_age)],
            BIO_GENDER: [
                CallbackQueryHandler(bio_receive_gender, pattern=r"^bio_gender:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, bio_receive_gender_text),
            ],
            BIO_HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bio_receive_height)],
            BIO_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bio_receive_weight)],
            BIO_ACTIVITY: [
                CallbackQueryHandler(bio_receive_activity, pattern=r"^bio_activity:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, bio_receive_activity_text),
            ],
            BIO_EDUCATION: [
                CallbackQueryHandler(bio_receive_education, pattern=r"^bio_education:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, bio_receive_education_text),
            ],
            BIO_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, bio_receive_field)],
            BIO_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, bio_receive_country)],
            BIO_EXPERIENCE: [
                CallbackQueryHandler(bio_receive_experience, pattern=r"^bio_experience:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, bio_receive_experience_text),
            ],
            BIO_GOALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, bio_receive_goals)],
        },
        fallbacks=[
            CommandHandler("start", bio_cancel),
            MessageHandler(filters.Regex(r"^(🥗 Nutrition|💪 Fitness|💰 Finance|🎯 Career|🧠 Personal Manager|📝 My Bio)$"), bio_cancel),
        ],
        per_message=False,
    )
    app.add_handler(bio_conv)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    # Menu button handlers
    app.add_handler(MessageHandler(filters.Regex(r"^📝 My Bio$"), bio_menu))
    app.add_handler(MessageHandler(
        filters.Regex(r"^(🥗 Nutrition|💪 Fitness|💰 Finance|🎯 Career|🧠 Personal Manager)$"),
        handle_menu,
    ))
    # Free text handler — routes to active agent
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("LifePilot is running (ReAct agents + scheduler). Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
