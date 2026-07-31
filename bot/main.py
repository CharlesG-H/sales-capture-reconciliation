"""Bot entry point: long-polling listener that routes sale captions to the sheet."""

import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from bot.config import load_config
from bot.models import MixedCart, Quarantine, SingleSale, Trade
from bot.parser import parse_message
from bot.sheets import SheetsClient, SheetTopicStore
from bot.topics import GENERAL_TOPIC_ID, JsonTopicStore, TopicRegistry, sanitize_tab_title

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("sales-capture")

LOCAL_TZ = ZoneInfo("Asia/Singapore")
TOPIC_CACHE_FILE = Path("topic_names.json")


def sale_to_rows(sale: SingleSale, timestamp: str, msg_id: int, link: str) -> list[list[str]]:
    return [[
        timestamp, sale.line.item, str(sale.line.qty), sale.line.amount_text,
        sale.method.value, sale.sale_type.value, "", sale.note,
        str(msg_id), link,
    ]]


def trade_to_rows(trade: Trade, timestamp: str, msg_id: int, link: str) -> list[list[str]]:
    # Amount carries the signed top-up as typed ("+50" / "-50"); blank = even trade
    cash = f"{trade.cash_sign}{trade.cash_text}" if trade.cash_text else ""
    return [[
        timestamp, "", "", cash,
        trade.method.value, "Trade", f"{trade.gave} -> {trade.got}", "",
        str(msg_id), link,
    ]]


def cart_to_rows(cart: MixedCart, timestamp: str, msg_id: int, link: str) -> list[list[str]]:
    # One cart = one row = one payment (FR-5): the itemization folds into
    # Item name, Qty is total pieces, Amount is exactly the total as typed.
    items = " + ".join(f"{ln.qty}x {ln.item} ${ln.amount_text}" for ln in cart.lines)
    total_qty = str(sum(ln.qty for ln in cart.lines))
    return [[
        timestamp, items, total_qty, cart.total_text,
        cart.method.value, "Sell", "", cart.note,  # carts are implicitly Sell
        str(msg_id), link,
    ]]


def build_rows(result, timestamp: str, msg_id: int, link: str) -> list[list[str]]:
    if isinstance(result, SingleSale):
        return sale_to_rows(result, timestamp, msg_id, link)
    if isinstance(result, Trade):
        return trade_to_rows(result, timestamp, msg_id, link)
    return cart_to_rows(result, timestamp, msg_id, link)


def _tracked_sale_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Common gate for new and edited messages: right chat, tracked topic,
    non-empty text. Returns (msg, text, topics, sheets) or None."""
    msg = update.effective_message
    config = context.bot_data["config"]
    if config.allowed_chat_id is not None and msg.chat_id != config.allowed_chat_id:
        log.info("ignored: chat %s is not ALLOWED_CHAT_ID %s", msg.chat_id, config.allowed_chat_id)
        return None
    topics: TopicRegistry = context.bot_data["topics"]
    topics.observe(msg)  # harvest topic names even off tracked topics
    if not topics.is_tracked(msg.message_thread_id or GENERAL_TOPIC_ID):
        return None  # bot is opt-in per topic (/track)
    text = (msg.text or msg.caption or "").strip()
    if not text:
        return None
    return msg, text, topics, context.bot_data["sheets"]


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    log.info(
        "received msg %s from chat %s (%s) thread %s: %.60r",
        msg.message_id, msg.chat_id, msg.chat.title, msg.message_thread_id,
        msg.text or msg.caption or "<no text>",
    )
    gate = _tracked_sale_context(update, context)
    if gate is None:
        return
    msg, text, topics, sheets = gate

    result = parse_message(text)
    if result is None:
        return  # ordinary chat

    timestamp = msg.date.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")
    tab = topics.tab_for(msg)  # FR-15: tab = topic title
    link = msg.link or ""  # FR-11: permalink to the source message

    if isinstance(result, Quarantine):
        sheets.append_review_row([timestamp, tab, link, result.raw_text, result.reason, ""])
        log.info("quarantined msg %s: %.60s", msg.message_id, text)
        return
    rows = build_rows(result, timestamp, msg.message_id, link)
    sheets.append_sale_rows(tab, rows)
    log.info("logged msg %s to tab %r: %.60s", msg.message_id, tab, text)


async def handle_edited_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """FR-9: an edited sale message updates its row in place (keyed by Msg ID).
    An edit that no longer parses leaves the row alone and flags Needs Review;
    an edit that fixes a previously unparseable message logs it fresh."""
    gate = _tracked_sale_context(update, context)
    if gate is None:
        return
    msg, text, topics, sheets = gate

    result = parse_message(text)
    timestamp = msg.date.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")
    tab = topics.tab_for(msg)
    link = msg.link or ""

    if result is None or isinstance(result, Quarantine):
        if not sheets.has_sale_row(tab, msg.message_id):
            # never logged: an edited chat message is still just chat; an
            # edited sale-shaped mess re-quarantines like a new message
            if isinstance(result, Quarantine):
                sheets.append_review_row([timestamp, tab, link, text, result.reason, ""])
                log.info("edit of msg %s quarantined: %.60r", msg.message_id, text)
            return
        reason = (
            result.reason if isinstance(result, Quarantine)
            else "Edited message no longer looks like a sale."
        )
        sheets.append_review_row(
            [timestamp, tab, link, text,
             "EDIT — existing row NOT changed. " + reason, ""]
        )
        log.info("edit of logged msg %s no longer parses: %.60r", msg.message_id, text)
        return

    row = build_rows(result, timestamp, msg.message_id, link)[0]
    if sheets.update_sale_row(tab, msg.message_id, row):
        log.info("updated row for edited msg %s in tab %r: %.60s", msg.message_id, tab, text)
    else:
        sheets.append_sale_rows(tab, [row])
        log.info("edited msg %s had no row; logged fresh in tab %r", msg.message_id, tab)


async def handle_topic_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """FR-15: cache topic names from create/rename service messages. The sheet
    is only touched for tracked topics — a rename carries the tab along."""
    msg = update.effective_message
    config = context.bot_data["config"]
    if config.allowed_chat_id is not None and msg.chat_id != config.allowed_chat_id:
        return
    if msg.message_thread_id is None:
        return

    topics: TopicRegistry = context.bot_data["topics"]
    sheets: SheetsClient = context.bot_data["sheets"]
    old_name = topics.name_for(msg.message_thread_id)
    topics.observe(msg)
    new_name = topics.name_for(msg.message_thread_id)
    if new_name is None or not topics.is_tracked(msg.message_thread_id):
        return
    if old_name is not None and old_name != new_name:
        sheets.rename_sale_tab(sanitize_tab_title(old_name), sanitize_tab_title(new_name))
        log.info("topic %s renamed: tab %r -> %r", msg.message_thread_id, old_name, new_name)
    else:
        sheets.ensure_sale_tab(sanitize_tab_title(new_name))
        log.info("topic %s: ensured tab %r", msg.message_thread_id, new_name)


async def cmd_track(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/track inside a topic: opt this topic in and create its tab."""
    msg = update.effective_message
    config = context.bot_data["config"]
    if config.allowed_chat_id is not None and msg.chat_id != config.allowed_chat_id:
        return
    topics: TopicRegistry = context.bot_data["topics"]
    sheets: SheetsClient = context.bot_data["sheets"]
    topics.track(msg.message_thread_id or GENERAL_TOPIC_ID)
    tab = topics.tab_for(msg)
    sheets.ensure_sale_tab(tab)
    log.info("tracking topic %s -> tab %r", msg.message_thread_id, tab)
    await msg.reply_text(f"Tracking this topic — sales will log to tab '{tab}'.")


async def cmd_void(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/void <msg id> — the Bot API sends no delete events, so deletions are
    flagged manually: the row is kept, Notes records the deletion (FR-10)."""
    msg = update.effective_message
    config = context.bot_data["config"]
    if config.allowed_chat_id is not None and msg.chat_id != config.allowed_chat_id:
        return
    if not context.args or not context.args[0].isdigit():
        await msg.reply_text(
            "Usage: /void <Msg ID> — the Msg ID is in the sheet row you want to flag."
        )
        return
    msg_id = int(context.args[0])
    tab = context.bot_data["topics"].tab_for(msg)
    if context.bot_data["sheets"].mark_deleted(tab, msg_id):
        log.info("voided msg %s in tab %r", msg_id, tab)
        await msg.reply_text(f"Noted — row for Msg ID {msg_id} marked MESSAGE DELETED (row kept).")
    else:
        await msg.reply_text(f"No row with Msg ID {msg_id} in tab '{tab}'.")


async def cmd_untrack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/untrack inside a topic: stop reading it (existing rows stay)."""
    msg = update.effective_message
    config = context.bot_data["config"]
    if config.allowed_chat_id is not None and msg.chat_id != config.allowed_chat_id:
        return
    context.bot_data["topics"].untrack(msg.message_thread_id or GENERAL_TOPIC_ID)
    log.info("untracked topic %s", msg.message_thread_id)
    await msg.reply_text("Stopped tracking this topic.")


def main() -> None:
    config = load_config()
    application = Application.builder().token(config.telegram_bot_token).build()
    application.bot_data["config"] = config
    sheets = SheetsClient(config.google_service_account_file, config.spreadsheet_id)
    application.bot_data["sheets"] = sheets
    # Webhook mode = Cloud Run = no durable disk: topic state lives in the
    # spreadsheet. Polling mode = local run: the JSON file keeps working.
    store = SheetTopicStore(sheets) if config.webhook_url else JsonTopicStore(TOPIC_CACHE_FILE)
    application.bot_data["topics"] = TopicRegistry(store)
    application.add_handler(CommandHandler("track", cmd_track))
    application.add_handler(CommandHandler("untrack", cmd_untrack))
    application.add_handler(CommandHandler("void", cmd_void))
    application.add_handler(
        MessageHandler(
            filters.StatusUpdate.FORUM_TOPIC_CREATED | filters.StatusUpdate.FORUM_TOPIC_EDITED,
            handle_topic_update,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE & (filters.TEXT | filters.CAPTION), handle_message
        )
    )
    application.add_handler(
        MessageHandler(
            filters.UpdateType.EDITED_MESSAGE & (filters.TEXT | filters.CAPTION),
            handle_edited_message,
        )
    )
    if config.webhook_url:
        # Cloud Run: Telegram pushes each update to us; the service scales to
        # zero between messages. PTB registers the webhook (with the secret
        # token) on startup and serves it on $PORT.
        log.info("starting webhook server for %s", config.webhook_url)
        application.run_webhook(
            listen="0.0.0.0",
            port=config.port,
            webhook_url=config.webhook_url,
            secret_token=config.webhook_secret_token,
            allowed_updates=["message", "edited_message"],
        )
    else:
        log.info("starting long polling")
        application.run_polling(allowed_updates=["message", "edited_message"])


if __name__ == "__main__":
    main()
