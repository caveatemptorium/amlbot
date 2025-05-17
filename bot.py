import logging
import os
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
from dotenv import load_dotenv

# Фикс для RUVDS: отключаем проверку прокси для Telegram
os.environ['NO_PROXY'] = 'api.telegram.org,graphql.bitquery.io'

# Настройка логов
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot.log'  # Логи в файл
)
logger = logging.getLogger(__name__)

# Загрузка конфигурации
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
BITQUERY_KEY = os.getenv("BITQUERY_API_KEY")

async def analyze_address(address: str) -> str:
    """Безопасный запрос к Bitquery с обработкой ошибок"""
    transport = AIOHTTPTransport(
        url="https://graphql.bitquery.io",
        headers={"X-API-KEY": BITQUERY_KEY},
        timeout=30
    )
    
    try:
        async with Client(
            transport=transport,
            execute_timeout=45,
            fetch_schema_from_transport=False
        ) as session:
            query = gql("""
                query AnalyzeAddress($address: String!) {
                  ethereum {
                    address(address: {is: $address}) {
                      annotations
                      smartContract { contractType }
                    }
                  }
                }
            """)
            result = await session.execute(query, variable_values={"address": address})
            data = result["ethereum"]["address"][0]
            
            if not data:
                return "🔍 Адрес не найден"
                
            risks = []
            if data["annotations"]:
                risks.extend(data["annotations"])
            if data["smartContract"]:
                risks.append(f"Контракт ({data['smartContract']['contractType']})")
                
            return "⚠️ Риски: " + ", ".join(risks) if risks else "✅ Адрес чист"
            
    except Exception as e:
        logger.error(f"Bitquery error: {str(e)[:200]}")
        return "⛔ Ошибка проверки. Попробуйте позже."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    try:
        await update.message.reply_text(
            "🛡️ AML Bot для проверки криптоадресов\n\n"
            "Отправьте ETH/BSC адрес для анализа\n"
            "Пример: 0x1f9090aaE28b8a3dCeaDf281B0F12828e676c326"
        )
    except Exception as e:
        logger.error(f"Start error: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Безопасная обработка сообщений"""
    try:
        address = update.message.text.strip()
        
        if not (address.startswith("0x") and len(address) == 42):
            await update.message.reply_text("❌ Неверный формат адреса")
            return
        
        msg = await update.message.reply_text("🔍 Проверяю адрес...")
        result = await analyze_address(address)
        await msg.edit_text(result)
        
    except Exception as e:
        logger.error(f"Message error: {e}")
        await update.message.reply_text("⛔ Ошибка обработки запроса")

def main():
    """Точка входа с обработкой исключений"""
    try:
        logger.info("Starting bot...")
        
        # Фикс для RUVDS: настройка keepalive
        application = ApplicationBuilder() \
            .token(TOKEN) \
            .http_version("1.1") \
            .get_updates_http_version("1.1") \
            .pool_timeout(30) \
            .connect_timeout(30) \
            .build()
        
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        ))
        
        application.run_polling(
            poll_interval=1.0,
            timeout=30,
            drop_pending_updates=True
        )
        
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    # Фикс для asyncio на RUVDS
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    main()
