import logging
import os
import asyncio
import warnings
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

# Подавляем предупреждение о SSL
warnings.filterwarnings("ignore", 
    message="By default, AIOHTTPTransport does not verify SSL certificates")

# Фикс для RUVDS
os.environ['NO_PROXY'] = 'api.telegram.org,graphql.bitquery.io'

# Настройка логов
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot.log'
)
logger = logging.getLogger(__name__)

# Загрузка конфигурации
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
BITQUERY_KEY = os.getenv("BITQUERY_API_KEY")

async def analyze_address(address: str, network: str = "ethereum") -> str:
    """Анализ адреса в указанной сети (ethereum/bsc/polygon)"""
    transport = AIOHTTPTransport(
        url="https://graphql.bitquery.io",
        headers={"X-API-KEY": BITQUERY_KEY},
        timeout=30,
        ssl=True
    )

    try:
        async with Client(
                transport=transport,
                execute_timeout=45,
                fetch_schema_from_transport=False
        ) as session:
            query = gql(f"""
                query AnalyzeAddress($address: String!) {{
                  {network} {{
                    address(address: {{is: $address}}) {{
                      annotations
                      smartContract {{ contractType }}
                      balance {{
                        currency {{ symbol }}
                        value
                      }}
                    }}
                  }}
                }}
            """)
            result = await session.execute(query, variable_values={"address": address})
            
            if not result.get(network) or not result[network].get("address"):
                return "🔍 Адрес не найден в этой сети"
            
            data = result[network]["address"][0]
            risks = []
            
            # Анализ рисков
            if data["annotations"]:
                risks.extend(data["annotations"])
            if data["smartContract"]:
                risks.append(f"Контракт ({data['smartContract']['contractType']})")
            
            # Информация о балансе
            balance_info = ""
            if data.get("balance"):
                for bal in data["balance"]:
                    balance_info += f"\n💰 Баланс: {bal['value']} {bal['currency']['symbol']}"

            risk_msg = "⚠️ Риски: " + ", ".join(risks) if risks else "✅ Адрес чист"
            return f"{risk_msg}\nСеть: {network.upper()}{balance_info}"

    except Exception as e:
        logger.error(f"Bitquery error ({network}): {str(e)[:200]}")
        return f"⛔ Ошибка проверки в сети {network.upper()}"

async def full_analysis(address: str) -> str:
    """Полная проверка адреса во всех сетях"""
    networks = ["ethereum", "binance-smart-chain", "polygon"]
    results = []
    
    for network in networks:
        result = await analyze_address(address, network)
        results.append(result)
        await asyncio.sleep(0.5)  # Задержка между запросами
    
    return "\n\n".join(results)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    try:
        await update.message.reply_text(
            "🛡️ AML Bot для проверки криптоадресов\n\n"
            "Поддерживаемые сети: Ethereum, BSC, Polygon\n"
            "Отправьте адрес (формат 0x...) для полной проверки\n"
            "Пример: 0x1f9090aaE28b8a3dCeaDf281B0F12828e676c326"
        )
    except Exception as e:
        logger.error(f"Start error: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщений с адресами"""
    try:
        address = update.message.text.strip()

        if not (address.startswith("0x") and len(address) == 42):
            await update.message.reply_text("❌ Неверный формат адреса")
            return

        msg = await update.message.reply_text("🔍 Запускаю проверку во всех сетях...")
        result = await full_analysis(address)
        await msg.edit_text(result)

    except Exception as e:
        logger.error(f"Message error: {e}")
        await update.message.reply_text("⛔ Ошибка обработки запроса")

def main():
    """Точка входа"""
    try:
        logger.info("Starting bot...")

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
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    main()
