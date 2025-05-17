import logging
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from gql import gql, Client
from gql.transport.aiohttp import AIOHTTPTransport
import os
from dotenv import load_dotenv

# Загрузка конфигурации
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
BITQUERY_KEY = os.getenv("BITQUERY_API_KEY")

# Настройка логов
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot.log'  # Логи в файл
)
logger = logging.getLogger(__name__)


async def analyze_address(address: str) -> dict:
    """Запрос к Bitquery API"""
    transport = AIOHTTPTransport(
        url="https://graphql.bitquery.io",
        headers={"X-API-KEY": BITQUERY_KEY},
        timeout=30
    )

    query = gql("""
        query AnalyzeAddress($address: String!) {
          ethereum {
            address(address: {is: $address}) {
              smartContract { 
                contractType 
              }
              annotations
              balance
            }
          }
        }
    """)

    try:
        async with Client(
                transport=transport,
                execute_timeout=45,
                fetch_schema_from_transport=False
        ) as session:
            result = await session.execute(query, variable_values={"address": address})
            return result["ethereum"]["address"][0]
    except Exception as e:
        logger.error(f"Bitquery error: {str(e)[:200]}")
        return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ AML Bot (Bitquery)\n\n"
        "Отправьте ETH/BSC адрес для проверки\n"
        "Пример: 0x1f9090aaE28b8a3dCeaDf281B0F12828e676c326"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = update.message.text.strip()

    if not (address.startswith("0x") and len(address) == 42):
        await update.message.reply_text("❌ Неверный формат адреса")
        return

    msg = await update.message.reply_text("🔍 Запрос к Bitquery...")

    data = await analyze_address(address)
    if not data:
        await msg.edit_text("⛔ Ошибка подключения к Bitquery")
        return

    response = []
    if data["smartContract"]:
        response.append(f"📄 Контракт: {data['smartContract']['contractType']}")
    if data["annotations"]:
        response.append(f"⚠️ Риски: {', '.join(data['annotations'])}")

    await msg.edit_text("\n".join(response) if response else "✅ Адрес чист")


def main():
    app = ApplicationBuilder() \
        .token(TOKEN) \
        .http_version("1.1") \
        .get_updates_http_version("1.1") \
        .build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling(
        poll_interval=1.0,
        timeout=10,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()