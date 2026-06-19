import os
import asyncio
import json
import base64
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes
)
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest

# ─── НАСТРОЙКИ ───────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "your_bot_token")

# Gmail API OAuth2 (получить через Google Cloud Console)
GMAIL_ADDRESS      = os.environ.get("GMAIL_ADDRESS", "your_email@gmail.com")
GMAIL_CLIENT_ID    = os.environ.get("GMAIL_CLIENT_ID", "")
GMAIL_CLIENT_SECRET= os.environ.get("GMAIL_CLIENT_SECRET", "")
GMAIL_REFRESH_TOKEN= os.environ.get("GMAIL_REFRESH_TOKEN", "")

EMAILS_FILE   = "emails.txt"
PROGRESS_FILE = "progress.json"
SENT_FILE     = "sent.txt"
PAUSE_SECONDS = 40

# ─────────────────────────────────────────────────────────────
state = {
    "running": False,
    "lang": "ru",
    "daily_limit": 100,
    "sent_today": 0,
    "total_sent": 0,
    "current_index": 0,
    "last_date": "",
    "errors": 0,
}

# ─── ТЕКСТЫ (RU / UZ) ────────────────────────────────────────
T = {
    "welcome": {
        "ru": "🌿 *Добро пожаловать\\!*\n\nВыберите язык интерфейса:",
        "uz": "🌿 *Xush kelibsiz\\!*\n\nInterfeys tilini tanlang:",
    },
    "choose_limit": {
        "ru": (
            "📨 *Green\\&Legal — Email Рассылка*\n\n"
            "⚙️ *Возможности:*\n"
            "• Умный дневной лимит без блокировок\n"
            "• Пауза между письмами для защиты аккаунта\n"
            "• Прогресс сохраняется при перезапуске\n"
            "• Повторная отправка исключена автоматически\n\n"
            "Выберите количество писем в день:"
        ),
        "uz": (
            "📨 *Green\\&Legal — Email Tarqatish*\n\n"
            "⚙️ *Imkoniyatlar:*\n"
            "• Bloklarsiz aqlli kunlik limit\n"
            "• Hisobni himoya qilish uchun pauza\n"
            "• Qayta ishga tushirilganda jarayon saqlanadi\n"
            "• Takroriy yuborish avtomatik chiqarib tashlanadi\n\n"
            "Kunlik xatlar sonini tanlang:"
        ),
    },
    "started": {
        "ru": "▶️ *Рассылка запущена\\!*\n\n📧 Адресов в базе: {total}\n✅ Уже отправлено: {sent}\n⏭ Пропущено \\(уже получили\\): {skipped}\n📅 Лимит: {limit} писем/день\n\nБот будет отправлять письма каждый день автоматически\\.",
        "uz": "▶️ *Tarqatish boshlandi\\!*\n\n📧 Bazadagi manzillar: {total}\n✅ Allaqachon yuborilgan: {sent}\n⏭ O'tkazib yuborilgan: {skipped}\n📅 Limit: {limit} xat/kun\n\nBot har kuni avtomatik ravishda xat yuboradi\\.",
    },
    "stopped": {
        "ru": "⏹️ *Рассылка остановлена\\.*\n\nПрогресс сохранён\\. При следующем запуске выберите новый лимит\\.",
        "uz": "⏹️ *Tarqatish to'xtatildi\\.*\n\nJarayon saqlandi\\. Keyingi ishga tushirishda yangi limit tanlang\\.",
    },
    "status_text": {
        "ru": "📊 *Статус рассылки*\n\n{icon} Состояние: {status}\n✅ Всего отправлено: {total}\n📅 Сегодня: {today}/{limit}\n📋 Осталось: {remaining}\n⏭ Уже получили ранее: {skipped}\n❌ Ошибок: {errors}",
        "uz": "📊 *Tarqatish holati*\n\n{icon} Holat: {status}\n✅ Jami yuborilgan: {total}\n📅 Bugun: {today}/{limit}\n📋 Qolgan: {remaining}\n⏭ Oldin olgan: {skipped}\n❌ Xatolar: {errors}",
    },
    "status_run":  {"ru": "Работает 🟢",   "uz": "Ishlayapti 🟢"},
    "status_stop": {"ru": "Остановлен 🔴", "uz": "To'xtatilgan 🔴"},
    "already_running": {
        "ru": "⚠️ Рассылка уже запущена\\! Нажмите «Стоп» чтобы остановить\\.",
        "uz": "⚠️ Tarqatish allaqachon boshlangan\\! To'xtatish uchun «Stop» ni bosing\\.",
    },
    "not_running": {
        "ru": "⚠️ Рассылка не запущена\\.",
        "uz": "⚠️ Tarqatish boshlanmagan\\.",
    },
    "daily_done": {
        "ru": "💤 Дневной лимит {limit} писем выполнен\\. Жду следующего дня\\.\\.\\.",
        "uz": "💤 Kunlik limit {limit} xat bajarildi\\. Keyingi kunni kutaman\\.\\.\\.",
    },
    "new_day": {
        "ru": "🌅 Новый день — начинаю следующую порцию {limit} писем\\!",
        "uz": "🌅 Yangi kun — keyingi {limit} ta xat yuborishni boshlayman\\!",
    },
    "progress_update": {
        "ru": "📬 Отправлено {sent} из {total} \\(пропущено дублей: {skipped}\\)",
        "uz": "📬 {total} tadan {sent} tasi yuborildi \\(o'tkazib yuborildi: {skipped}\\)",
    },
    "finished": {
        "ru": "🎉 *Рассылка завершена\\!*\n\n✅ Всего отправлено: {sent}\n⏭ Пропущено дублей: {skipped}\n❌ Ошибок: {errors}",
        "uz": "🎉 *Tarqatish yakunlandi\\!*\n\n✅ Jami yuborilgan: {sent}\n⏭ O'tkazib yuborilgan: {skipped}\n❌ Xatolar: {errors}",
    },
    "btn_start":  {"ru": "🚀 Начать рассылку",  "uz": "🚀 Tarqatishni boshlash"},
    "btn_stop":   {"ru": "⏹ Остановить",        "uz": "⏹ To'xtatish"},
    "btn_status": {"ru": "📊 Статус",            "uz": "📊 Holat"},
    "btn_change": {"ru": "🔄 Сменить лимит",     "uz": "🔄 Limitni o'zgartirish"},
}

def t(key, lang=None):
    lang = lang or state.get("lang", "ru")
    return T[key][lang]

# ─── ПРОГРЕСС ────────────────────────────────────────────────
def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            state.update(json.load(f))

def save_progress():
    to_save = {k: v for k, v in state.items() if k != "running"}
    with open(PROGRESS_FILE, "w") as f:
        json.dump(to_save, f)

def load_emails():
    if not os.path.exists(EMAILS_FILE):
        return []
    with open(EMAILS_FILE) as f:
        return [l.strip() for l in f if l.strip() and "@" in l]

def get_email_html():
    with open("email_template.html", encoding="utf-8") as f:
        return f.read()

# ─── ОТПРАВЛЕННЫЕ АДРЕСА ─────────────────────────────────────
def load_sent() -> set:
    if not os.path.exists(SENT_FILE):
        return set()
    with open(SENT_FILE) as f:
        return set(l.strip().lower() for l in f if l.strip())

def mark_sent(email: str):
    with open(SENT_FILE, "a") as f:
        f.write(email.lower() + "\n")

# ─── GMAIL API: получение свежего access_token ───────────────
def get_access_token() -> str:
    """
    Обновляет access_token через refresh_token (HTTPS на 443 — Railway не блокирует).
    Требует переменных окружения: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN
    """
    creds = Credentials(
        token=None,
        refresh_token=GMAIL_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GMAIL_CLIENT_ID,
        client_secret=GMAIL_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/gmail.send"],
    )
    creds.refresh(GoogleRequest())
    return creds.token

# ─── ОТПРАВКА ПИСЬМА через Gmail API ─────────────────────────
def send_email(to_email: str) -> bool:
    """
    Отправляет письмо через Gmail REST API (HTTPS/443).
    Не использует SMTP — работает на Railway и любом хостинге.
    """
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Green&Legal — Zamonaviy va barqaror huquqiy yechimlar"
        msg["From"]    = f"Green&Legal <{GMAIL_ADDRESS}>"
        msg["To"]      = to_email
        msg.attach(MIMEText(get_email_html(), "html", "utf-8"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        access_token = get_access_token()

        resp = requests.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"raw": raw},
            timeout=30,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[ERROR] {to_email}: {e}")
        return False

# ─── ЦИКЛ РАССЫЛКИ ───────────────────────────────────────────
async def sending_loop(bot, chat_id):
    emails   = load_emails()
    sent_set = load_sent()
    lang     = state["lang"]
    limit    = state["daily_limit"]
    skipped  = 0

    today = datetime.now().strftime("%Y-%m-%d")
    if state["last_date"] != today:
        state["sent_today"] = 0
        state["last_date"]  = today

    await bot.send_message(
        chat_id,
        t("started", lang).format(
            total=len(emails),
            sent=state["total_sent"],
            skipped=len(sent_set),
            limit=limit,
        ),
        parse_mode="MarkdownV2"
    )

    first_email = True

    while state["running"]:
        today = datetime.now().strftime("%Y-%m-%d")

        if state["last_date"] != today:
            state["sent_today"] = 0
            state["last_date"]  = today
            await bot.send_message(
                chat_id,
                t("new_day", lang).format(limit=limit),
                parse_mode="MarkdownV2"
            )

        if state["sent_today"] >= limit:
            await bot.send_message(
                chat_id,
                t("daily_done", lang).format(limit=limit),
                parse_mode="MarkdownV2"
            )
            while state["running"] and state["last_date"] == datetime.now().strftime("%Y-%m-%d"):
                await asyncio.sleep(300)
            continue

        if state["current_index"] >= len(emails):
            await bot.send_message(
                chat_id,
                t("finished", lang).format(
                    sent=state["total_sent"],
                    skipped=skipped,
                    errors=state["errors"]
                ),
                parse_mode="MarkdownV2"
            )
            state["running"] = False
            save_progress()
            break

        email = emails[state["current_index"]]
        state["current_index"] += 1

        if email.lower() in sent_set:
            skipped += 1
            save_progress()
            continue

        if send_email(email):
            sent_set.add(email.lower())
            mark_sent(email)
            state["sent_today"] += 1
            state["total_sent"] += 1
            print(f"[OK] {email} | Today: {state['sent_today']}/{limit} | Total: {state['total_sent']}")
        else:
            state["errors"] += 1

        save_progress()

        if state["total_sent"] % 50 == 0 and state["total_sent"] > 0:
            await bot.send_message(
                chat_id,
                t("progress_update", lang).format(
                    sent=state["total_sent"],
                    total=len(emails),
                    skipped=skipped,
                ),
                parse_mode="MarkdownV2"
            )

        if first_email:
            first_email = False
        else:
            for _ in range(PAUSE_SECONDS):
                if not state["running"]:
                    break
                await asyncio.sleep(1)

# ─── КЛАВИАТУРЫ ──────────────────────────────────────────────
def main_keyboard(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_start",  lang), callback_data="do_start")],
        [InlineKeyboardButton(t("btn_stop",   lang), callback_data="do_stop"),
         InlineKeyboardButton(t("btn_status", lang), callback_data="do_status")],
        [InlineKeyboardButton(t("btn_change", lang), callback_data="change_limit")],
    ])

def limit_keyboard(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 100 писем/день", callback_data="limit_100"),
         InlineKeyboardButton("📩 200 писем/день", callback_data="limit_200")],
        [InlineKeyboardButton("📩 300 писем/день", callback_data="limit_300"),
         InlineKeyboardButton("📩 500 писем/день", callback_data="limit_500")],
    ])

def lang_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
         InlineKeyboardButton("🇺🇿 O'zbek",  callback_data="lang_uz")],
    ])

# ─── /start ──────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        t("welcome", "ru"),
        reply_markup=lang_keyboard(),
        parse_mode="MarkdownV2"
    )

# ─── CALLBACK HANDLER ────────────────────────────────────────
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    lang  = state.get("lang", "ru")

    # ── FIX: "Query is too old" не крашит бот ──
    try:
        await query.answer()
    except Exception:
        pass  # Telegram отклонил answer() — callback устарел, продолжаем

    data = query.data

    if data in ("lang_ru", "lang_uz"):
        state["lang"] = data.split("_")[1]
        save_progress()
        lang = state["lang"]
        await query.edit_message_text(
            t("choose_limit", lang),
            reply_markup=limit_keyboard(lang),
            parse_mode="MarkdownV2"
        )
        return

    if data.startswith("limit_"):
        limit = int(data.split("_")[1])
        state["daily_limit"] = limit
        save_progress()
        await query.edit_message_text(
            f"✅ Установлен лимит: *{limit} писем/день*\n\nВыберите действие:",
            reply_markup=main_keyboard(lang),
            parse_mode="MarkdownV2"
        )
        return

    if data == "change_limit":
        if state["running"]:
            try:
                await query.answer("⚠️ Сначала остановите рассылку!", show_alert=True)
            except Exception:
                pass
            return
        await query.edit_message_text(
            t("choose_limit", lang),
            reply_markup=limit_keyboard(lang),
            parse_mode="MarkdownV2"
        )
        return

    if data == "do_start":
        if state["running"]:
            try:
                await query.answer(t("already_running", lang), show_alert=True)
            except Exception:
                pass
            return
        emails = load_emails()
        if not emails:
            try:
                await query.answer("❌ emails.txt пуст!", show_alert=True)
            except Exception:
                pass
            return
        state["running"] = True
        asyncio.create_task(sending_loop(context.bot, query.message.chat_id))
        return

    if data == "do_stop":
        if not state["running"]:
            try:
                await query.answer(t("not_running", lang), show_alert=True)
            except Exception:
                pass
            return
        state["running"] = False
        save_progress()
        await query.edit_message_text(
            t("stopped", lang),
            reply_markup=limit_keyboard(lang),
            parse_mode="MarkdownV2"
        )
        return

    if data == "do_status":
        emails    = load_emails()
        sent_set  = load_sent()
        remaining = max(0, len(emails) - state["current_index"])
        icon      = "🟢" if state["running"] else "🔴"
        status    = t("status_run", lang) if state["running"] else t("status_stop", lang)
        await query.edit_message_text(
            t("status_text", lang).format(
                icon=icon,
                status=status,
                total=state["total_sent"],
                today=state["sent_today"],
                limit=state["daily_limit"],
                remaining=remaining,
                skipped=len(sent_set),
                errors=state["errors"],
            ),
            reply_markup=main_keyboard(lang),
            parse_mode="MarkdownV2"
        )
        return

# ─── ЗАПУСК ──────────────────────────────────────────────────
def main():
    import time
    time.sleep(3)
    load_progress()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_callback))
    print("✅ Бот запущен")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )

if __name__ == "__main__":
    main()
