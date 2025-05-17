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
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY") or "Y6WZ1814MY9EUZHUQ2KIUKJJ7P652PWRW3"  # Ваш рабочий ключ

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def analyze_address(address: str) -> str:
    """Проверка адреса через Etherscan API"""
    try:
        async with aiohttp.ClientSession() as session:
            # 1. Получаем баланс
            balance_url = f"https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest&apikey={ETHERSCAN_API_KEY}"
            async with session.get(balance_url) as resp:
                data = await resp.json()
                
                if data.get('status') != '1':
                    return f"⛔ Ошибка: {data.get('message', 'Unknown error')}"
                
                balance = int(data['result']) / 10**18

            # 2. Проверяем контракт
            contract_url = f"https://api.etherscan.io/api?module=contract&action=getabi&address={address}&apikey={ETHERSCAN_API_KEY}"
            async with session.get(contract_url) as resp:
                contract_data = await resp.json()
                is_contract = contract_data.get('status') == '1' and contract_data['result'] != 'Contract source code not verified'

            # 3. Проверка рисков
            risky_addresses = {
                "0x8576acc5c05d6ce88f4e49bf65bdf0c62f91353c": "❗ В чёрном списке",
                "0x1da5821544e25c636c1417ba96ade4cf6d2f9b5a": "❗ Подозрительный"
            }
            risk = risky_addresses.get(address.lower(), "✅ Чистый")

            return (
                f"🔍 <b>Анализ адреса</b> <code>{address}</code>\n\n"
                f"💰 <b>Баланс:</b> {balance:.4f} ETH\n"
                f"📜 <b>Тип:</b> {'Контракт' if is_contract else 'Кошелёк'}\n"
                f"🛡️ <b>Статус:</b> {risk}\n\n"
                f"<i>Данные: Etherscan API</i>"
            )

    except Exception as e:
        logger.error(f"Ошибка анализа: {str(e)}")
        return "⚠️ Ошибка сервера. Попробуйте позже."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ <b>ETH Address Analyzer</b>\n\n"
        "Отправьте ETH-адрес (0x...) для проверки\n"
        "Пример: <code>0x1f9090aaE28b8a3dCeaDf281B0F12828e676c326</code>",
        parse_mode="HTML"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        address = update.message.text.strip()
        if not (address.startswith("0x") and len(address) == 42):
            await update.message.reply_text("❌ Неверный формат адреса!")
            return

        msg = await update.message.reply_text("🔍 Проверяю...")
        report = await analyze_address(address)
        await msg.edit_text(report, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка обработки: {str(e)}")
        await update.message.reply_text("⚠️ Ошибка. Попробуйте позже.")

def main():
    app = ApplicationBuilder() \
        .token(TOKEN) \
        .http_version("1.1") \
        .get_updates_http_version("1.1") \
        .pool_timeout(30) \
        .build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запускается...")
    app.run_polling(
        poll_interval=1.0,
        timeout=30,
        drop_pending_updates=True
    )

if __name__ == "__main__":
    asyncio.run(main())
