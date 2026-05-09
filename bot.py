# bot.py
import os, json, re
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler,
    ContextTypes, filters,
)
import httpx

BOT_TOKEN  = os.environ["BOT_TOKEN"]
GH_TOKEN   = os.environ["GH_PAT"]              # PAT with workflow scope
ALLOWED    = set(int(x) for x in os.environ["ALLOWED_USER_IDS"].split(","))

STEAM_REPO = "poli0981/steam-f2p-tracker"
ITCH_REPO  = "poli0981/itchio-f2p-tracker"
WF_FILE    = "bot-ingest.yml"

# Conversation states
CHOOSE, COLLECT, CONFIRM = range(3)

# ── Link classifier ─────────────────────────────────────────────
STEAM_RE = re.compile(r"https?://store\.steampowered\.com/app/(\d+)", re.I)
ITCH_RE  = re.compile(r"https?://[\w-]+\.itch\.io/[\w-]+", re.I)

def classify(line: str) -> tuple[str, str]:
    """Return (kind, normalized_url). kind ∈ {steam, itch, invalid}."""
    line = line.strip()
    if not line:
        return ("invalid", "")
    m = STEAM_RE.search(line)
    if m:
        return ("steam", f"https://store.steampowered.com/app/{m.group(1)}/")
    if ITCH_RE.match(line):
        return ("itch", line.rstrip("/"))
    if line.isdigit():  # bare appid
        return ("steam", f"https://store.steampowered.com/app/{line}/")
    return ("invalid", line)


# ── /start, /scrape ─────────────────────────────────────────────
def auth(fn):
    async def wrapper(update, ctx):
        if update.effective_user.id not in ALLOWED:
            return await update.message.reply_text("⛔ Not authorized.")
        return await fn(update, ctx)
    return wrapper

@auth
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = ReplyKeyboardMarkup(
        [["/steam"], ["/itch"], ["/mixed"], ["/cancel"]],
        resize_keyboard=True, one_time_keyboard=True,
    )
    await update.message.reply_text(
        "Pick scraper mode:\n"
        "• /steam — Steam links only\n"
        "• /itch — itch.io links only\n"
        "• /mixed — auto-route by URL",
        reply_markup=kb,
    )
    return CHOOSE

@auth
async def choose(update, ctx):
    cmd = update.message.text.lstrip("/").lower()
    if cmd not in ("steam", "itch", "mixed"):
        return CHOOSE
    ctx.user_data["mode"] = cmd
    await update.message.reply_text(
        f"Mode: {cmd}. Paste links (1 per line, max 100). Send /done when finished.",
        reply_markup=ReplyKeyboardRemove(),
    )
    ctx.user_data["buffer"] = []
    return COLLECT

@auth
async def collect(update, ctx):
    """Each text message = batch of links. Accumulate until /done."""
    text = update.message.text or ""
    if update.message.document:
        # User uploaded .txt or .json file
        f = await update.message.document.get_file()
        text = (await f.download_as_bytearray()).decode("utf-8", "replace")
        try:
            data = json.loads(text)
            if isinstance(data, list):
                text = "\n".join(d if isinstance(d, str) else d.get("link", "")
                                 for d in data)
        except json.JSONDecodeError:
            pass  # treat as plain text
    ctx.user_data["buffer"].extend(text.splitlines())
    await update.message.reply_text(
        f"Got {len(ctx.user_data['buffer'])} lines so far. Send more or /done."
    )
    return COLLECT

@auth
async def done(update, ctx):
    mode = ctx.user_data.get("mode", "mixed")
    raw = ctx.user_data.get("buffer", [])
    classified = [classify(line) for line in raw if line.strip()]

    # Filter by mode
    steam, itch, invalid = [], [], []
    for kind, url in classified:
        if kind == "invalid":
            invalid.append(url)
        elif kind == "steam" and mode in ("steam", "mixed"):
            steam.append(url)
        elif kind == "itch" and mode in ("itch", "mixed"):
            itch.append(url)
        else:
            invalid.append(f"{url} (wrong mode)")

    # Dedupe
    steam = list(dict.fromkeys(steam))
    itch  = list(dict.fromkeys(itch))

    if not steam and not itch:
        await update.message.reply_text("Nothing valid to process. /start to retry.")
        return ConversationHandler.END

    total = len(steam) + len(itch)
    if total > 100:
        await update.message.reply_text(f"⚠ {total} links > 100 limit. Trim and retry.")
        return ConversationHandler.END

    ctx.user_data["payload"] = {"steam": steam, "itch": itch}
    summary = (
        f"📋 Preview:\n"
        f"  Steam: {len(steam)}\n"
        f"  itch:  {len(itch)}\n"
        f"  Invalid (skipped): {len(invalid)}\n\n"
        f"Confirm? /yes or /cancel"
    )
    if invalid[:5]:
        summary += "\n\nInvalid samples:\n" + "\n".join(f"  • {x[:60]}" for x in invalid[:5])
    await update.message.reply_text(summary)
    return CONFIRM

@auth
async def yes(update, ctx):
    payload = ctx.user_data.get("payload", {})
    msg = await update.message.reply_text("⏳ Dispatching to GitHub Actions...")

    async with httpx.AsyncClient(timeout=30) as cli:
        for kind, links in (("steam", payload.get("steam", [])),
                            ("itch",  payload.get("itch", []))):
            if not links:
                continue
            repo = STEAM_REPO if kind == "steam" else ITCH_REPO
            r = await cli.post(
                f"https://api.github.com/repos/{repo}/actions/workflows/{WF_FILE}/dispatches",
                headers={
                    "Authorization": f"Bearer {GH_TOKEN}",
                    "Accept": "application/vnd.github+json",
                },
                json={
                    "ref": "main",
                    "inputs": {
                        "links": "\n".join(links),
                        "chat_id": str(update.effective_chat.id),
                        "message_id": str(msg.message_id),
                    },
                },
            )
            if r.status_code != 204:
                await msg.edit_text(f"❌ Dispatch failed for {kind}: {r.status_code}\n{r.text[:200]}")
                return ConversationHandler.END

    await msg.edit_text(
        f"🚀 Dispatched.\n"
        f"  Steam: {len(payload.get('steam', []))}\n"
        f"  itch:  {len(payload.get('itch', []))}\n\n"
        f"Workflow will edit this message with results in ~1–8 min."
    )
    return ConversationHandler.END

@auth
async def cancel(update, ctx):
    ctx.user_data.clear()
    await update.message.reply_text("Cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start),
                      CommandHandler("scrape", start)],
        states={
            CHOOSE:  [CommandHandler(["steam", "itch", "mixed"], choose)],
            COLLECT: [CommandHandler("done", done),
                      MessageHandler(filters.TEXT | filters.Document.ALL, collect)],
            CONFIRM: [CommandHandler("yes", yes),
                      CommandHandler("cancel", cancel)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv)
    app.run_polling()

if __name__ == "__main__":
    main()