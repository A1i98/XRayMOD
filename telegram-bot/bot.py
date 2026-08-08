"""
XRayMOD Telegram Bot
--------------------
ساخت، فهرست، حذف و به‌روزرسانی پنل روی Cloudflare Workers.

راه‌اندازی:
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  cp .env.example .env   # BOT_TOKEN
  python bot.py

نیازمندی میزبان: node, npm, git, دسترسی شبکه به Cloudflare و GitHub
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
from pathlib import Path

from dotenv import load_dotenv
from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from db import delete_panel, init_db, list_panels, save_panel
from deploy import create_panel, destroy_panel, update_panel

load_dotenv()

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("xraymod-bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
REPO_URL = os.getenv("REPO_URL", "https://github.com/askarniroomand/XRayMOD.git").strip()
WORK_ROOT = Path(os.getenv("WORK_ROOT", str(Path.home() / ".xraymod-bot"))).expanduser()
ALLOWLIST = {
    int(x.strip())
    for x in os.getenv("ALLOW_USER_IDS", "").split(",")
    if x.strip().isdigit()
}

TOKEN, USER, PASS = range(3)

BTN_CREATE = "ساخت پنل جدید"
BTN_LIST = "پنل‌های من"
BTN_UPDATE = "آپدیت همه"
BTN_HELP = "راهنما"
BTN_CANCEL = "انصراف"


def allowed(user_id: int | None) -> bool:
    if not ALLOWLIST:
        return True
    return bool(user_id and user_id in ALLOWLIST)


def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_CREATE)],
            [KeyboardButton(BTN_LIST), KeyboardButton(BTN_UPDATE)],
            [KeyboardButton(BTN_HELP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="از منو انتخاب کنید",
    )


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(BTN_CANCEL)]],
        resize_keyboard=True,
        input_field_placeholder="یا انصراف",
    )


def welcome_text() -> str:
    return (
        "ربات مدیریت پنل *XRayMOD*\n\n"
        "از دکمه‌های پایین استفاده کنید:\n"
        f"• {BTN_CREATE}\n"
        f"• {BTN_LIST}\n"
        f"• {BTN_UPDATE}\n"
        f"• {BTN_HELP}\n\n"
        "دستورها: /start · /help · /create · /cancel"
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("handler error: %s", context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "خطایی رخ داد. دوباره /start بزنید.",
                reply_markup=main_kb(),
            )
        except Exception:
            pass


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not allowed(user.id if user else None):
        await update.effective_message.reply_text("دسترسی ندارید.")
        return
    await update.effective_message.reply_text(
        welcome_text(),
        reply_markup=main_kb(),
        parse_mode="Markdown",
    )


async def help_msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "*راهنما*\n\n"
        f"۱) *{BTN_CREATE}*\n"
        "   توکن Cloudflare → نام کاربری → رمز\n"
        "   توکن: قالب Edit Cloudflare Workers (+ D1)\n\n"
        f"۲) *{BTN_LIST}*\n"
        "   لینک ورود و مشخصات\n"
        "   حذف: `حذف 1`\n"
        "   آپدیت یکی: `آپدیت 1`\n\n"
        f"۳) *{BTN_UPDATE}*\n"
        "   آخرین کد `main` روی همه پنل‌ها\n\n"
        "توکن و رمز را فقط در چت خصوصی بفرستید.",
        reply_markup=main_kb(),
        parse_mode="Markdown",
    )


async def list_msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    panels = list_panels(uid)
    if not panels:
        await update.effective_message.reply_text(
            f"هنوز پنلی ندارید.\nبا «{BTN_CREATE}» شروع کنید.",
            reply_markup=main_kb(),
        )
        return

    chunks = [f"*پنل‌های شما* ({len(panels)})\n"]
    for p in panels:
        chunks.append(
            "────────────\n"
            f"*#{p['id']}* `{p['worker_name']}`\n"
            f"کاربر: `{p['username']}`\n"
            f"رمز: `{p['password']}`\n"
            f"ورود:\n{p['login_url']}\n"
            f"حذف: `حذف {p['id']}`\n"
            f"آپدیت: `آپدیت {p['id']}`"
        )
    await update.effective_message.reply_text(
        "\n".join(chunks),
        reply_markup=main_kb(),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


async def create_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not allowed(update.effective_user.id if update.effective_user else None):
        await update.effective_message.reply_text("دسترسی ندارید.")
        return ConversationHandler.END
    context.user_data.clear()
    await update.effective_message.reply_text(
        "*مرحله ۱ از ۳ — توکن*\n\n"
        "Cloudflare API Token را ارسال کنید.\n"
        "قالب پیشنهادی: Edit Cloudflare Workers\n\n"
        f"برای لغو: «{BTN_CANCEL}» یا /cancel",
        reply_markup=cancel_kb(),
        parse_mode="Markdown",
    )
    return TOKEN


async def got_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == BTN_CANCEL:
        return await cancel(update, context)
    if len(text) < 20:
        await update.message.reply_text(
            "توکن کوتاه است. دوباره ارسال کنید یا انصراف بزنید.",
            reply_markup=cancel_kb(),
        )
        return TOKEN
    context.user_data["cf_token"] = text
    try:
        await update.message.delete()
    except Exception:
        pass
    await update.effective_message.reply_text(
        "توکن دریافت و از چت حذف شد.\n\n"
        "*مرحله ۲ از ۳ — نام کاربری*\n"
        "نام کاربری پنل را بفرستید (مثلاً `admin`).",
        reply_markup=cancel_kb(),
        parse_mode="Markdown",
    )
    return USER


async def got_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    username = (update.message.text or "").strip()
    if username == BTN_CANCEL:
        return await cancel(update, context)
    if not re.match(r"^[\w.-]{3,32}$", username):
        await update.message.reply_text(
            "نام کاربری: ۳ تا ۳۲ کاراکتر لاتین، عدد، `.` یا `-`.",
            reply_markup=cancel_kb(),
        )
        return USER
    context.user_data["username"] = username
    await update.message.reply_text(
        f"نام کاربری: `{username}`\n\n"
        "*مرحله ۳ از ۳ — رمز*\n"
        "رمز عبور را بفرستید.\n"
        "برای ساخت خودکار رمز قوی فقط `.` بفرستید.",
        reply_markup=cancel_kb(),
        parse_mode="Markdown",
    )
    return PASS


async def _progress_loop(status_msg, queue: asyncio.Queue, stop: asyncio.Event) -> None:
    lines = ["*در حال اجرا…*\n"]
    while not stop.is_set() or not queue.empty():
        try:
            item = await asyncio.wait_for(queue.get(), timeout=0.4)
            lines.append(item)
            body = "\n".join(lines[-14:])
            try:
                await status_msg.edit_text(body, parse_mode="Markdown")
            except Exception:
                pass
        except asyncio.TimeoutError:
            continue


async def got_pass(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = (update.message.text or "").strip()
    if raw == BTN_CANCEL:
        return await cancel(update, context)
    password = secrets.token_urlsafe(12) if raw in {".", "-", ""} else raw
    if len(password) < 6:
        await update.message.reply_text(
            "رمز حداقل ۶ کاراکتر باشد.",
            reply_markup=cancel_kb(),
        )
        return PASS
    context.user_data["password"] = password
    auto = raw in {".", "-", ""}
    try:
        await update.message.delete()
    except Exception:
        pass

    tip = "رمز به‌صورت خودکار ساخته شد." if auto else "رمز دریافت شد."
    status = await update.message.reply_text(
        f"{tip}\n\n*در حال ساخت پنل…*\nوضعیت مرحله‌به‌مرحله به‌روز می‌شود.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown",
    )

    token = context.user_data["cf_token"]
    username = context.user_data["username"]
    worker_name = f"xraymod-{secrets.token_hex(3)}"

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str] = asyncio.Queue()
    stop = asyncio.Event()

    def progress(msg: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, msg)

    progress_task = asyncio.create_task(_progress_loop(status, queue, stop))

    try:
        result = await asyncio.to_thread(
            create_panel,
            token=token,
            username=username,
            password=password,
            worker_name=worker_name,
            work_root=WORK_ROOT,
            repo_url=REPO_URL,
            progress=progress,
        )
    except Exception as e:
        log.exception("create failed")
        stop.set()
        await progress_task
        await status.reply_text(
            f"ساخت ناموفق شد.\n`{e}`\n\nاز منو دوباره تلاش کنید.",
            reply_markup=main_kb(),
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    stop.set()
    await progress_task

    save_panel(
        tg_user_id=update.effective_user.id,
        worker_name=result["worker_name"],
        d1_id=result["d1_id"],
        account_id=result["account_id"],
        panel_url=result["panel_url"],
        login_url=result["login_url"],
        username=username,
        password=password,
        access_uuid=result["access_uuid"],
        cf_token=token,
        sub_url=result.get("sub_url", ""),
    )

    text = (
        "*پنل آماده شد*\n\n"
        f"Worker: `{result['worker_name']}`\n"
        f"کاربر: `{username}`\n"
        f"رمز: `{password}`\n"
        f"Access UUID:\n`{result['access_uuid']}`\n\n"
        f"ورود:\n{result['login_url']}\n\n"
        f"پنل:\n{result['panel_url']}\n"
    )
    if result.get("sub_url"):
        text += f"\nسابسکریپشن:\n{result['sub_url']}\n"
    text += "\n_لینک‌ها را خصوصی نگه دارید._"

    await status.reply_text(
        text,
        reply_markup=main_kb(),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.effective_message.reply_text("لغو شد.", reply_markup=main_kb())
    return ConversationHandler.END


async def delete_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    m = re.match(r"^حذف\s+(\d+)$", (update.message.text or "").strip())
    if not m:
        return
    pid = int(m.group(1))
    panels = list_panels(update.effective_user.id)
    panel = next((p for p in panels if p["id"] == pid), None)
    if not panel:
        await update.message.reply_text("پنل پیدا نشد.", reply_markup=main_kb())
        return

    status = await update.message.reply_text(
        f"در حال حذف `{panel['worker_name']}`…",
        parse_mode="Markdown",
    )
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str] = asyncio.Queue()
    stop = asyncio.Event()

    def progress(msg: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, msg)

    progress_task = asyncio.create_task(_progress_loop(status, queue, stop))
    try:
        await asyncio.to_thread(destroy_panel, panel, progress)
        stop.set()
        await progress_task
        delete_panel(pid, update.effective_user.id)
        await status.reply_text("حذف شد.", reply_markup=main_kb())
    except Exception as e:
        stop.set()
        await progress_task
        await status.reply_text(
            f"حذف ناموفق.\n`{e}`",
            reply_markup=main_kb(),
            parse_mode="Markdown",
        )


async def update_one_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    m = re.match(r"^آپدیت\s+(\d+)$", (update.message.text or "").strip())
    if not m:
        return
    pid = int(m.group(1))
    panels = list_panels(update.effective_user.id)
    panel = next((p for p in panels if p["id"] == pid), None)
    if not panel:
        await update.message.reply_text("پنل پیدا نشد.", reply_markup=main_kb())
        return

    status = await update.message.reply_text(
        f"آپدیت `{panel['worker_name']}` از GitHub…",
        parse_mode="Markdown",
    )
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str] = asyncio.Queue()
    stop = asyncio.Event()

    def progress(msg: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, msg)

    progress_task = asyncio.create_task(_progress_loop(status, queue, stop))
    try:
        url = await asyncio.to_thread(update_panel, panel, WORK_ROOT, REPO_URL, progress)
        stop.set()
        await progress_task
        await status.reply_text(
            f"آپدیت شد.\n{url}",
            reply_markup=main_kb(),
            disable_web_page_preview=True,
        )
    except Exception as e:
        stop.set()
        await progress_task
        await status.reply_text(
            f"آپدیت ناموفق.\n`{e}`",
            reply_markup=main_kb(),
            parse_mode="Markdown",
        )


async def update_all_msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    panels = list_panels(update.effective_user.id)
    if not panels:
        await update.message.reply_text("پنلی برای آپدیت نیست.", reply_markup=main_kb())
        return

    status = await update.message.reply_text(
        f"آپدیت {len(panels)} پنل از GitHub main…"
    )
    ok_n = 0
    errors = []
    for idx, p in enumerate(panels, 1):
        try:
            await status.edit_text(
                f"آپدیت همه ({idx}/{len(panels)})\n"
                f"فعلی: `{p['worker_name']}`",
                parse_mode="Markdown",
            )
            await asyncio.to_thread(update_panel, p, WORK_ROOT, REPO_URL)
            ok_n += 1
        except Exception as e:
            errors.append(f"{p['worker_name']}: {e}")

    text = f"پایان.\n{ok_n}/{len(panels)} آپدیت شد."
    if errors:
        text += "\n\nخطاها:\n" + "\n".join(f"• {e}" for e in errors[:5])
    await status.reply_text(text, reply_markup=main_kb())


def build_app() -> Application:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN missing — set in .env")

    init_db()
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .build()
    )
    app.add_error_handler(on_error)

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f"^{re.escape(BTN_CREATE)}$"), create_start),
            CommandHandler("create", create_start),
        ],
        states={
            TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_token)],
            USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_user)],
            PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_pass)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex(f"^{re.escape(BTN_CANCEL)}$"), cancel),
        ],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_msg))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_HELP)}$"), help_msg))
    app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_LIST)}$"), list_msg))
    app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_UPDATE)}$"), update_all_msg))
    app.add_handler(MessageHandler(filters.Regex(r"^حذف\s+\d+$"), delete_text))
    app.add_handler(MessageHandler(filters.Regex(r"^آپدیت\s+\d+$"), update_one_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, start))
    return app


def main() -> None:
    app = build_app()
    log.info("XRayMOD bot running")
    app.run_polling(
        drop_pending_updates=False,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()
