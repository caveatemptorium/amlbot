import logging
import os
import asyncio
import aiohttp
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from dotenv import load_dotenv

# Настройки
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def analyze_address(address: str) -> str:
    """Проверяет адрес через Etherscan с полной обработкой ошибок"""
    try:
        async with aiohttp.ClientSession() as session:
            # 1. Проверка баланса
            balance_url = f"https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest&apikey={ETHERSCAN_API_KEY}"
            async with session.get(balance_url) as response:
                balance_data = await response.json()
                
                if balance_data.get('status') != '1':
                    error_msg = balance_data.get('message', 'Unknown Etherscan error')
                    logger.error(f"Etherscan balance error: {error_msg}")
                    return f"⛔ Ошибка Etherscan: {error_msg}"
                
                try:
                    balance_wei = int(balance_data["result"])
                    balance_eth = balance_wei / 10**18
                except (ValueError, KeyError) as e:
                    logger.error(f"Balance data error: {str(e)}")
                    return "⚠️ Ошибка обработки данных о балансе"

            # 2. Проверка контракта
            contract_url = f"https://api.etherscan.io/api?module=contract&action=getabi&address={address}&apikey={ETHERSCAN_API_KEY}"
            async with session.get(contract_url) as response:
                contract_data = await response.json()
                
                if contract_data.get('status') != '1':
                    is_contract = False
                else:
                    is_contract = contract_data['result'] not in ['Contract source code not verified', 'Invalid API Key']

            # 3. AML-проверка
            risky_addresses = {
                "0x8576acc5c05d6ce88f4e49bf65bdf0c62f91353c": "❗ Известный мошеннический адрес",
                "0x1da5821544e25c636c1417ba96ade4cf6d2f9b5a": "❗ Фишинг",
                "0xf4919cE7EaF4659cE27e5f8E6dbc3A427862cC02": "❗ Mixer"
            }
            aml_status = risky_addresses.get(address.lower(), "✅ Рисков не обнаружено")

            # Формирование отчета
            return (
                f"🔍 <b>Анализ адреса:</b> <code>{address}</code>\n\n"
                f"💰 <b>Баланс:</b> {balance_eth:.4f} ETH\n"
                f"📜 <b>Тип:</b> {'Контракт ✅' if is_contract else 'Кошелек'}\n"
                f"🛡️ <b>Безопасность:</b> {aml_status}\n\n"
                f"<i>Данные предоставлены Etherscan API</i>"
            )

    except aiohttp.ClientError as e:
        logger.error(f"Network error: {str(e)}")
        return "⚠️ Ошибка подключения к Etherscan"
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return "⛔ Внутренняя ошибка сервера"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ <b>AML Ethereum Checker</b>\n\n"
        "Отправьте ETH-адрес (начинается с 0x) для проверки\n"
        "Пример: <code>0x1f9090aaE28b8a3dCeaDf281B0F12828e676c326</code>",
        parse_mode="HTML"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        address = update.message.text.strip()
        
        if not (address.startswith("0x") and len(address) == 42):
            await update.message.reply_text("❌ Неверный формат адреса! Должен начинаться с 0x и содержать 42 символа.")
            return
        
        msg = await update.message.reply_text("🔍 Проверяю адрес...")
        result = await analyze_address(address)
        await msg.edit_text(result, parse_mode="HTML")
    
    except Exception as e:
        logger.error(f"Handler error: {str(e)}")
        await update.message.reply_text("🔥 Ошибка обработки запроса")

def main():
    app = ApplicationBuilder() \
        .token(TOKEN) \
        .http_version("1.1") \
        .get_updates_http_version("1.1") \
        .pool_timeout(30) \
        .build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Бот запущен")
    app.run_polling(
        poll_interval=1.0,
        timeout=30,
        drop_pending_updates=True
    )

if __name__ == "__main__":
    asyncio.run(main())
