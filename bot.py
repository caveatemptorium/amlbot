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
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")  # Добавьте в .env

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def analyze_address(address: str) -> str:
    """Проверяет адрес через Etherscan и базовую AML-проверку"""
    try:
        async with aiohttp.ClientSession() as session:
            # 1. Проверка баланса через Etherscan
            balance_url = f"https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest&apikey={ETHERSCAN_API_KEY}"
            async with session.get(balance_url) as response:
                balance_data = await response.json()
                balance_wei = int(balance_data.get("result", 0))
                balance_eth = balance_wei / 10**18
            
            # 2. Проверка контракта
            contract_url = f"https://api.etherscan.io/api?module=contract&action=getabi&address={address}&apikey={ETHERSCAN_API_KEY}"
            async with session.get(contract_url) as response:
                contract_data = await response.json()
                is_contract = contract_data.get("result") not in ["Contract source code not verified", "Invalid API Key"]
            
            # 3. Базовая AML-проверка (пример)
            risky_addresses = {
                "0x8576acc5c05d6ce88f4e49bf65bdf0c62f91353c": "❗ Известный мошеннический адрес",
                "0x1da5821544e25c636c1417ba96ade4cf6d2f9b5a": "❗ Фишинг"
            }
            aml_status = risky_addresses.get(address.lower(), "✅ Рисков не обнаружено")

            # Формирование отчёта
            return (
                f"🔍 <b>Анализ адреса:</b> <code>{address}</code>\n\n"
                f"💰 <b>Баланс:</b> {balance_eth:.4f} ETH\n"
                f"📜 <b>Контракт:</b> {'✅ Да' if is_contract else '❌ Нет'}\n"
                f"🛡️ <b>AML-статус:</b> {aml_status}\n\n"
                f"<i>Проверено через Etherscan API</i>"
            )
    
    except Exception as e:
        logger.error(f"Ошибка анализа: {str(e)}")
        return "⚠️ Ошибка при проверке адреса. Попробуйте позже."

# Остальные функции (start, handle_message, main) остаются без изменений
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
        logger.error(f"Ошибка: {str(e)}")
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")

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
    app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
