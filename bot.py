import os
import asyncio
import smtplib
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler
)

# ─── НАСТРОЙКИ ───────────────────────────────────────────────
GMAIL          = os.environ.get("GMAIL", "your_email@gmail.com")
APP_PASSWORD   = os.environ.get("APP_PASSWORD", "xxxx xxxx xxxx xxxx")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "your_bot_token")
ADMIN_ID       = int(os.environ.get("ADMIN_ID", "0"))
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "your_username")  # без @

EMAILS_FILE   = "emails.txt"
PROGRESS_FILE = "progress.json"
SENT_FILE     = "sent.txt"
PAUSE_SECONDS = 40
# ─────────────────────────────────────────────────────────────

# Состояния ConversationHandler
LANG, ONBOARD, WAIT_APPROVE, CHOOSE_LIMIT = range(4)

# Глобальное состояние рассылки
state = {
    "running": False,
    "approved": False,
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
    "about": {
        "ru": (
            "📨 *Green\\&Legal — Email Рассылка*\n\n"
            "Этот бот автоматически отправляет профессиональные письма от компании "
            "*Green\\&Legal* на тысячи адресов — каждый день, без остановок\\.\n\n"
            "⚙️ *Возможности:*\n"
            "• Умный дневной лимит без блокировок\n"
            "• Пауза между письмами для защиты аккаунта\n"
            "• Прогресс сохраняется при перезапуске\n"
            "• Повторная отправка исключена автоматически\n"
            "• Управление одной кнопкой\n\n"
            "Для начала работы — свяжитесь с администратором:"
        ),
        "uz": (
            "📨 *Green\\&Legal — Email Tarqatish*\n\n"
            "Ushbu bot *Green\\&Legal* kompaniyasidan minglab manzillarga "
            "professional xatlarni avtomatik ravishda har kuni yuboradi\\.\n\n"
            "⚙️ *Imkoniyatlar:*\n"
            "• Bloklarsiz aqlli kunlik limit\n"
            "• Hisobni himoya qilish uchun xatlar orasida pauza\n"
            "• Qayta ishga tushirilganda jarayon saqlanadi\n"
            "• Takroriy yuborish avtomatik chiqarib tashlanadi\n"
            "• Bitta tugma bilan boshqarish\n\n"
            "Boshlash uchun administrator bilan bog'laning:"
        ),
    },
    "contact_btn": {
        "ru": "✉️ Написать администратору",
        "uz": "✉️ Administrator bilan bog'lanish",
    },
    "approved_msg": {
        "ru": (
            "✅ *Доступ одобрен\\!*\n\n"
            "Отлично\\! Вы можете запустить рассылку\\.\n"
            "Выберите количество писем в день:"
        ),
        "uz": (
            "✅ *Ruxsat berildi\\!*\n\n"
            "Ajoyib\\! Siz tarqatishni boshlashingiz mumkin\\.\n"
            "Kunlik xatlar sonini tanlang:"
        ),
    },
    "wait_approve": {
        "ru": "⏳ Ваш запрос отправлен администратору\\. Ожидайте одобрения\\.",
        "uz": "⏳ So'rovingiz administratorga yuborildi\\. Tasdiqlashni kuting\\.",
    },
    "started": {
        "ru": "▶️ *Рассылка запущена\\!*\n\n📧 Адресов в базе: {total}\n✅ Уже отправлено: {sent}\n⏭ Пропущено \\(уже получили\\): {skipped}\n📅 Лимит: {limit} писем/день\n\nБот будет отправлять письма каждый день автоматически\\.",
        "uz": "▶️ *Tarqatish boshlandi\\!*\n\n📧 Bazadagi manzillar: {total}\n✅ Allaqachon yuborilgan: {sent}\n⏭ O'tkazib yuborilgan \\(allaqachon olgan\\): {skipped}\n📅 Limit: {limit} xat/kun\n\nBot har kuni avtomatik ravishda xat yuboradi\\.",
    },
    "stopped": {
        "ru": "⏹️ *Рассылка остановлена\\.*\n\nПрогресс сохранён\\. При следующем запуске выберите новый лимит\\.",
        "uz": "⏹️ *Tarqatish to'xtatildi\\.*\n\nJarayon saqlandi\\. Keyingi ishga tushirishda yangi limit tanlang\\.",
    },
    "status_text": {
        "ru": "📊 *Статус рассылки*\n\n{icon} Состояние: {status}\n✅ Всего отправлено: {total}\n📅 Сегодня: {today}/{limit}\n📋 Осталось: {remaining}\n⏭ Уже получили ранее: {skipped}\n❌ Ошибок: {errors}",
        "uz": "📊 *Tarqatish holati*\n\n{icon} Holat: {status}\n✅ Jami yuborilgan: {total}\n📅 Bugun: {today}/{limit}\n📋 Qolgan: {remaining}\n⏭ Oldin olgan: {skipped}\n❌ Xatolar: {errors}",
    },
    "status_run":  {"ru": "Работает 🟢",       "uz": "Ishlayapti 🟢"},
    "status_stop": {"ru": "Остановлен 🔴",     "uz": "To'xtatilgan 🔴"},
    "already_running": {
        "ru": "⚠️ Рассылка уже запущена! Нажмите «Стоп» чтобы остановить.",
        "uz": "⚠️ Tarqatish allaqachon boshlangan! To'xtatish uchun «Stop» ni bosing.",
    },
    "not_running": {
        "ru": "⚠️ Рассылка не запущена.",
        "uz": "⚠️ Tarqatish boshlanmagan.",
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

# ─── ОТПРАВКА ПИСЬМА ─────────────────────────────────────────
def send_email(to_email: str) -> bool:
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Green&Legal — Zamonaviy va barqaror huquqiy yechimlar"
        msg["From"]    = f"Green&Legal <{GMAIL}>"
        msg["To"]      = to_email
        msg.attach(MIMEText(get_email_html(), "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL, APP_PASSWORD)
            s.sendmail(GMAIL, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[ERROR] {to_email}: {e}")
        return False

# ─── ЦИКЛ РАССЫЛКИ ───────────────────────────────────────────
async def sending_loop(bot, chat_id):
    emails    = load_emails()
    sent_set  = load_sent()
    lang      = state["lang"]
    limit     = state["daily_limit"]
    skipped   = 0

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

    while state["running"]:
        today = datetime.now().strftime("%Y-%m-%d")

        # Новый день — сброс дневного счётчика
        if state["last_date"] != today:
            state["sent_today"] = 0
            state["last_date"]  = today
            await bot.send_message(
                chat_id,
                t("new_day", lang).format(limit=limit),
                parse_mode="MarkdownV2"
            )

        # Дневной лимит выполнен
        if state["sent_today"] >= limit:
            await bot.send_message(
                chat_id,
                t("daily_done", lang).format(limit=limit),
                parse_mode="MarkdownV2"
            )
            while state["running"] and state["last_date"] == datetime.now().strftime("%Y-%m-%d"):
                await asyncio.sleep(300)
            continue

        # Все адреса пройденыInlineKeyboardButton("🇷🇺 Русский",
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

        # Пропускаем уже отправленные
        if email.lower() in sent_set:
            skipped += 1
            save_progress()
            continue

        # Отправляем
        if send_email(email):
            sent_set.add(email.lower())
            mark_sent(email)
            state["sent_today"] += 1
            state["total_sent"] += 1
            print(f"[OK] {email} | Today: {state['sent_today']}/{limit} | Total: {state['total_sent']}")
        else:
            state["errors"] += 1

        save_progress()

        # Прогресс каждые 50 отправленных
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

        # Пауза между письмами
        for _ in range(PAUSE_SECONDS):
            if not state["running"]:
                break
            await asyncio.sleep(1)

# ─── КЛАВИАТУРЫ ──────────────────────────────────────────────
def main_keyboard(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_start", lang),  callback_data="do_start")],
        [InlineKeyboardButton(t("btn_stop",  lang),  callback_data="do_stop"),
         InlineKeyboardButton(t("btn_status",lang),  callback_data="do_status")],
    ])

def limit_keyboard(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 100 писем/день", callback_data="limit_100"),
         InlineKeyboardButton("📩 200 писем/день", callback_data="limit_200")],
        [InlineKeyboardButton("📩 300 писем/день", callback_data="limit_300"),
         InlineKeyboardButton("📩 500 писем/день", callback_data="limit_500")],
    ])

# ─── /start ──────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
         InlineKeyboardButton("🇺🇿 O'zbek",  callback_data="lang_uz")],
    ])
    await update.message.reply_text(
        t("welcome", "ru"),
        reply_markup=lang_keyboard,
    )

# ─── CALLBACK HANDLER ────────────────────────────────────────
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    data    = query.data
    user_id = query.from_user.id
    lang    = state.get("lang", "ru")

    # ── Выбор языка ──
    if data in ("lang_ru", "lang_uz"):
        chosen = data.split("_")[1]
        state["lang"] = chosen
        save_progress()
        lang = chosen

        contact_btn = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                t("contact_btn", lang),
                url=f"https://t.me/{ADMIN_USERNAME}"
            )]
        ])
        await query.edit_message_text(
            t("about", lang),
            reply_markup=contact_btn,
            parse_mode="MarkdownV2"
        )

        if user_id != ADMIN_ID:
            try:
                await context.bot.send_message(
                    ADMIN_ID,
                    f"🔔 Новый пользователь хочет доступ к боту\\!\n"
                    f"ID: `{user_id}`\n"
                    f"Имя: {query.from_user.full_name}\n\n"
                    f"Если хотите одобрить — нажмите:",
                    parse_mode="MarkdownV2",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            "✅ Одобрить",
                            callback_data=f"approve_{user_id}"
                        )
                    ]])
                )
            except Exception:
                pass
        return

    # ── Одобрение пользователя ──
    if data.startswith("approve_") and user_id == ADMIN_ID:
        target_id = int(data.split("_")[1])
        await query.edit_message_text("✅ Пользователь одобрен\\!", parse_mode="MarkdownV2")
        try:
            await context.bot.send_message(
                target_id,
                t("approved_msg", lang),
                reply_markup=limit_keyboard(lang),
                parse_mode="MarkdownV2"
            )
        except Exception:
            pass
        return

    # ── Остальное — только для админа ──
    if user_id != ADMIN_ID:
        return

    # ── Выбор лимита ──
    if data.startswith("limit_"):
        limit = int(data.split("_")[1])
        state["daily_limit"] = limit
        save_progress()
        await query.edit_message_text(
            f"✅ Установлен лимит: *{limit} писем/день*\n\nНажмите кнопку ниже чтобы запустить рассылку:",
            reply_markup=main_keyboard(lang),
            parse_mode="MarkdownV2"
        )
        return

    # ── Запуск ──
    if data == "do_start":
        if state["running"]:
            await query.answer(t("already_running", lang), show_alert=True)
            return
        emails = load_emails()
        if not emails:
            await query.answer("❌ emails.txt пуст!", show_alert=True)
            return
        state["running"] = True
        asyncio.create_task(sending_loop(context.bot, query.message.chat_id))
        return

    # ── Стоп ──
    if data == "do_stop":
        if not state["running"]:
            await query.answer(t("not_running", lang), show_alert=True)
            return
        state["running"] = False
        save_progress()
        await query.edit_message_text(
            t("stopped", lang),
            reply_markup=limit_keyboard(lang),
            parse_mode="MarkdownV2"
        )
        return

    # ── Статус ──
    if data == "do_status":
        emails    = load_emails()
        total     = len(emails)
        sent_set  = load_sent()
        remaining = max(0, total - state["current_index"])
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
    load_progress()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_callback))
    print("✅ Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
