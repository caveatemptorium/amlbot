import logging
import os
import asyncio
import aiohttp
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
    CallbackQueryHandler
)
from dotenv import load_dotenv

# Состояния для ConversationHandler
ENTER_PHRASE, CHOOSE_ACTION, ENTER_ADDRESS, ENTER_REASON, CONFIRM_REMOVE = range(5)

# Настройки
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
SECRET_PHRASE = os.getenv("SECRET_PHRASE", "mysecret123")
BLACKLIST_FILE = "blacklist.json"

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def load_blacklist():
    """Загрузка чёрного списка с созданием файла при отсутствии"""
    try:
        if not os.path.exists(BLACKLIST_FILE):
            with open(BLACKLIST_FILE, 'w') as f:
                json.dump({}, f)
            return {}
        
        with open(BLACKLIST_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки blacklist.json: {str(e)}")
        return {}

def save_blacklist(data):
    """Сохранение чёрного списка"""
    try:
        with open(BLACKLIST_FILE, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения blacklist.json: {str(e)}")
        return False

async def analyze_address(address: str) -> str:
    """Полная проверка адреса"""
    try:
        address_lower = address.lower()
        report = []
        blacklist = load_blacklist()
        
        # Проверка в чёрном списке
        if address_lower in blacklist:
            reason = blacklist[address_lower].get('reason', 'причина не указана')
            source = blacklist[address_lower].get('source', 'источник не указан')
            report.append("🔴 <b>АДРЕС В ЧЁРНОМ СПИСКЕ</b>")
            report.append(f"📛 Причина: {reason}")
            report.append(f"🔍 Источник: {source}")
        else:
            report.append("🟢 Адрес не найден в чёрном списке")
        
        # Проверка через Etherscan
        if ETHERSCAN_API_KEY:
            async with aiohttp.ClientSession() as session:
                # Баланс
                balance_url = f"https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest&apikey={ETHERSCAN_API_KEY}"
                async with session.get(balance_url) as resp:
                    data = await resp.json()
                    balance = int(data['result']) / 10**18 if data.get('status') == '1' else 0
                
                # Проверка контракта
                contract_url = f"https://api.etherscan.io/api?module=contract&action=getabi&address={address}&apikey={ETHERSCAN_API_KEY}"
                async with session.get(contract_url) as resp:
                    contract_data = await resp.json()
                    is_contract = contract_data.get('status') == '1' and contract_data['result'] != 'Contract source code not verified'

            report.extend([
                f"\n🔍 <b>Анализ адреса:</b> <code>{address}</code>",
                f"💰 <b>Баланс:</b> {balance:.4f} ETH",
                f"📜 <b>Тип:</b> {'Контракт' if is_contract else 'Кошелёк'}"
            ])
        else:
            report.append("\nℹ️ Проверка через Etherscan недоступна (отсутствует API ключ)")
        
        return "\n".join(report)

    except Exception as e:
        logger.error(f"Ошибка анализа: {str(e)}")
        return "⚠️ Ошибка проверки адреса"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "🛡️ <b>AML Ethereum Analyzer</b>\n\n"
        "Отправьте ETH-адрес для проверки (начинается с 0x, 42 символа)\n"
        "/blacklist - управление чёрным списком\n\n"
        "Пример адреса: <code>0x1f9090aaE28b8a3dCeaDf281B0F12828e676c326</code>",
        parse_mode="HTML"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщений с адресами"""
    try:
        address = update.message.text.strip()
        
        if not (address.startswith("0x") and len(address) == 42):
            await update.message.reply_text("❌ Неверный формат адреса! Должен начинаться с 0x и содержать 42 символа.")
            return
        
        msg = await update.message.reply_text("🔍 Проверяю адрес...")
        result = await analyze_address(address)
        await msg.edit_text(result, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка обработки: {str(e)}")
        await update.message.reply_text("⚠️ Ошибка. Попробуйте позже.")

def main():
    # Проверка наличия файла blacklist.json
    if not os.path.exists(BLACKLIST_FILE):
        with open(BLACKLIST_FILE, 'w') as f:
            json.dump({}, f)
        logger.info("Создан новый файл blacklist.json")

    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Бот запускается...")
    app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
