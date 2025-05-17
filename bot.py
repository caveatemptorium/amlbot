import logging
import os
import asyncio
import aiohttp
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from dotenv import load_dotenv

# Конфигурация
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
BITQUERY_KEY = os.getenv("BITQUERY_API_KEY")

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot.log'
)
logger = logging.getLogger(__name__)

NETWORKS = {
    'ethereum': {'name': 'Ethereum', 'currency': 'ETH'},
    'binance-smart-chain': {'name': 'BSC', 'currency': 'BNB'},
    'polygon': {'name': 'Polygon', 'currency': 'MATIC'}
}

async def fetch_bitquery(address: str, network: str) -> dict:
    """Новый надежный запрос к Bitquery с aiohttp"""
    query = f"""
    {{
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
    """
    
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": BITQUERY_KEY
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                "https://graphql.bitquery.io",
                json={"query": query},
                headers=headers,
                timeout=30,
                ssl=True
            ) as response:
                if response.status != 200:
                    raise Exception(f"HTTP Error {response.status}")
                return await response.json()
        except Exception as e:
            logger.error(f"Network {network} error: {str(e)}")
            return None

async def analyze_address(address: str, network: str) -> str:
    """Улучшенный анализ с обработкой всех ошибок"""
    try:
        result = await fetch_bitquery(address, network)
        if not result:
            return f"🔴 Ошибка подключения к {NETWORKS[network]['name']}"
        
        data = result.get('data', {}).get(network, {}).get('address', [])
        if not data:
            return f"🔍 Адрес не найден в {NETWORKS[network]['name']}"
        
        address_data = data[0]
        risks = []
        
        if address_data.get('annotations'):
            risks.extend(address_data['annotations'])
        if address_data.get('smartContract'):
            risks.append(f"Контракт ({address_data['smartContract']['contractType']})")
        
        balance = next(
            (b['value'] for b in address_data.get('balance', []) 
             if b['currency']['symbol'] == NETWORKS[network]['currency']),
            "0"
        )
        
        status = "⚠️ Риски: " + ", ".join(risks) if risks else "✅ Нет рисков"
        return f"{status}\nБаланс: {balance} {NETWORKS[network]['currency']}"
    
    except Exception as e:
        logger.error(f"Analysis error in {network}: {str(e)}")
        return f"🔴 Ошибка анализа в {NETWORKS[network]['name']}"

async def full_analysis(address: str) -> str:
    """Параллельная проверка во всех сетях"""
    tasks = [analyze_address(address, net) for net in NETWORKS]
    results = await asyncio.gather(*tasks)
    
    report = []
    for (net, result) in zip(NETWORKS.values(), results):
        report.append(f"<b>{net['name']}</b>\n{result}")
    
    return "\n\n".join(report)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ <b>AML Bot для проверки криптоадресов</b>\n\n"
        "Поддерживаемые сети: Ethereum, BSC, Polygon\n"
        "Отправьте адрес (формат 0x...) для проверки\n"
        "Пример: <code>0x1f9090aaE28b8a3dCeaDf281B0F12828e676c326</code>",
        parse_mode="HTML"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        address = update.message.text.strip()
        
        if not (address.startswith("0x") and len(address) == 42):
            await update.message.reply_text("❌ Неверный формат адреса")
            return
        
        msg = await update.message.reply_text("🔍 Запускаю проверку...")
        report = await full_analysis(address)
        await msg.edit_text(
            f"<b>Результаты проверки:</b>\n<code>{address}</code>\n\n{report}",
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(f"Handler error: {str(e)}")
        await update.message.reply_text("⛔ Системная ошибка. Попробуйте позже.")

def main():
    app = ApplicationBuilder() \
        .token(TOKEN) \
        .http_version("1.1") \
        .get_updates_http_version("1.1") \
        .pool_timeout(60) \
        .build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
