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

# Настройка окружения
warnings.filterwarnings("ignore", message="Unverified HTTPS request")
os.environ['NO_PROXY'] = 'api.telegram.org,graphql.bitquery.io'

# Логирование
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

async def analyze_address(address: str, network: str) -> str:
    """Анализ адреса в указанной сети"""
    transport = AIOHTTPTransport(
        url="https://graphql.bitquery.io",
        headers={"X-API-KEY": BITQUERY_KEY},
        timeout=30,
        ssl=True,  # Явное включение проверки SSL
        verify_ssl=True
    )

    try:
        async with Client(
            transport=transport,
            execute_timeout=60,
            fetch_schema_from_transport=False
        ) as session:
            query = gql(f"""
                query {{
                  {network} {{
                    address(address: {{is: "{address}"}}) {{
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
            result = await session.execute(query)
            
            if not result.get(network):
                return f"🔍 Адрес не найден в сети {network.upper()}"
            
            data = result[network]["address"][0] if result[network]["address"] else None
            if not data:
                return f"🔍 Нет данных по адресу в сети {network.upper()}"
            
            risks = []
            if data.get("annotations"):
                risks.extend(data["annotations"])
            if data.get("smartContract"):
                risks.append(f"Контракт ({data['smartContract']['contractType']})")
            
            balance = ""
            if data.get("balance"):
                for bal in data["balance"]:
                    balance += f"\n💰 Баланс: {bal['value']} {bal['currency']['symbol']}"
            
            return ("⚠️ Риски: " + ", ".join(risks) if risks else "✅ Адрес чист") + balance

    except Exception as e:
        logger.error(f"Ошибка в сети {network}: {str(e)[:200]}")
        return f"⛔ Ошибка API в сети {network.upper()}"

async def full_analysis(address: str) -> str:
    """Полная проверка во всех сетях"""
    networks = {
        "ethereum": "Ethereum",
        "binance-smart-chain": "BSC",
        "polygon": "Polygon"
    }
    
    results = []
    for network_id, network_name in networks.items():
        try:
            result = await analyze_address(address, network_id)
            results.append(f"<b>{network_name}</b>\n{result}")
            await asyncio.sleep(1)  # Задержка между запросами
        except Exception as e:
            logger.error(f"Critical error in {network_id}: {e}")
            results.append(f"<b>{network_name}</b>\n🔴 Критическая ошибка проверки")
    
    return "\n\n".join(results)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ <b>AML Bot для проверки криптоадресов</b>\n\n"
        "Поддерживаемые сети: Ethereum, BSC, Polygon\n"
        "Отправьте адрес (формат 0x...) для полной проверки\n"
        "Пример: <code>0x1f9090aaE28b8a3dCeaDf281B0F12828e676c326</code>",
        parse_mode="HTML"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        address = update.message.text.strip()
        
        if not (address.startswith("0x") and len(address) == 42):
            await update.message.reply_text("❌ Неверный формат адреса. Должен начинаться с 0x и содержать 42 символа.")
            return
        
        msg = await update.message.reply_text("🔄 Запускаю проверку в 3 сетях...")
        result = await full_analysis(address)
        await msg.edit_text(
            f"🔍 <b>Результаты проверки адреса</b> <code>{address}</code>:\n\n{result}",
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")
        await update.message.reply_text("🔥 Произошла критическая ошибка. Попробуйте позже.")

def main():
    try:
        app = ApplicationBuilder() \
            .token(TOKEN) \
            .http_version("1.1") \
            .get_updates_http_version("1.1") \
            .pool_timeout(60) \
            .connect_timeout(60) \
            .build()
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        app.run_polling(
            poll_interval=1.5,
            timeout=60,
            drop_pending_updates=True
        )
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    main()
