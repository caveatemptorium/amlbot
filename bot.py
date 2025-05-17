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

# Настройки
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
BLACKLIST_FILE = "blacklist.json"

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def load_blacklist():
    """Загрузка чёрного списка"""
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

async def generate_aml_report(address: str) -> str:
    """Генерация AML-отчёта"""
    try:
        address_lower = address.lower()
        blacklist = load_blacklist()
        
        # Заголовок отчёта
        report = [
            "🔍 <b>Отчёт AML-анализа</b> 🔍",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"🆔 <b>Адрес:</b> <code>{address}</code>",
            ""
        ]
        
        # Раздел чёрного списка
        if address_lower in blacklist:
            reason = blacklist[address_lower].get('reason', 'Не указана')
            source = blacklist[address_lower].get('source', 'Неизвестный источник')
            report.extend([
                "⚡ <b>Результат проверки:</b> 🔴 <b>ВЫСОКИЙ РИСК</b>",
                "├─ 🚫 <b>Причина:</b> " + reason,
                "└─ 📡 <b>Источник:</b> " + source,
                ""
            ])
        else:
            report.append("⚡ <b>Результат проверки:</b> 🟢 <b>ЧИСТЫЙ</b>\n")
        
        # Раздел данных Etherscan
        if ETHERSCAN_API_KEY:
            async with aiohttp.ClientSession() as session:
                # Баланс
                balance_url = f"https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest&apikey={ETHERSCAN_API_KEY}"
                async with session.get(balance_url) as resp:
                    data = await resp.json()
                    balance = int(data['result']) / 10**18 if data.get('status') == '1' else 0
                
                # Транзакции
                tx_url = f"https://api.etherscan.io/api?module=account&action=txlist&address={address}&startblock=0&endblock=99999999&apikey={ETHERSCAN_API_KEY}"
                async with session.get(tx_url) as resp:
                    tx_data = await resp.json()
                    tx_count = len(tx_data.get('result', []))
                
                # Контракт
                contract_url = f"https://api.etherscan.io/api?module=contract&action=getabi&address={address}&apikey={ETHERSCAN_API_KEY}"
                async with session.get(contract_url) as resp:
                    contract_data = await resp.json()
                    is_contract = contract_data.get('status') == '1' and contract_data['result'] != 'Contract source code not verified'

            report.extend([
                "📊 <b>Анализ блокчейна:</b>",
                "├─ 💰 <b>Баланс:</b> {:.4f} ETH".format(balance),
                "├─ 🔄 <b>Транзакции:</b> {}".format(tx_count),
                "└─ 📜 <b>Тип:</b> {}".format("Смарт-контракт" if is_contract else "Внешний аккаунт (EOA)"),
                ""
            ])
        else:
            report.append("ℹ️ <i>Данные Etherscan недоступны (отсутствует API ключ)</i>\n")
        
        # Рекомендации
        if address_lower in blacklist:
            report.extend([
                "🚨 <b>Оценка рисков:</b>",
                "├─ ⚠️ <b>Обнаружен высокий риск</b>",
                "└─ 🔒 <b>Рекомендация:</b> Избегайте взаимодействия",
                ""
            ])
        else:
            report.extend([
                "✅ <b>Оценка рисков:</b>",
                "└─ 🟢 <b>Риски не обнаружены</b>",
                ""
            ])
        
        report.append("━━━━━━━━━━━━━━━━━━━━━━")
        report.append("🛡️ <i>Отчёт сгенерирован AML Security Bot</i>")
        
        return "\n".join(report)

    except Exception as e:
        logger.error(f"Ошибка генерации отчёта: {str(e)}")
        return "⚠️ <b>Ошибка генерации отчёта</b>\nПопробуйте позже."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное сообщение"""
    welcome_msg = """
✨ <b>Добро пожаловать в AML Security Bot</b> ✨

🔐 <i>Продвинутый инструмент анализа блокчейн-адресов</i>

📌 <b>Как использовать:</b>
1. Отправьте любой Ethereum-адрес (начинается с 0x)
2. Получите детальный отчёт о рисках AML/CFT
3. Узнайте дополнительную информацию о кошельке

🛡️ <b>Возможности:</b>
• Мониторинг чёрных списков
• Проверка баланса кошелька
• Анализ транзакций
• Оценка рисков
• Определение смарт-контрактов

<i>Пример адреса:</i> <code>0x1f9090aaE28b8a3dCeaDf281B0F12828e676c326</code>
"""
    await update.message.reply_text(welcome_msg, parse_mode="HTML")

async def handle_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка адресов"""
    try:
        address = update.message.text.strip()
        
        if not (address.startswith("0x") and len(address) == 42):
            await update.message.reply_text(
                "❌ <b>Неверный формат адреса</b>\n"
                "Ethereum-адрес должен:\n"
                "• Начинаться с 0x\n"
                "• Содержать 42 символа\n"
                "• Пример: <code>0x1f9090aaE28b8a3dCeaDf281B0F12828e676c326</code>",
                parse_mode="HTML"
            )
            return
        
        # Анимация загрузки
        msg = await update.message.reply_text("🔄 <i>Анализируем адрес...</i>", parse_mode="HTML")
        
        # Генерация отчёта
        report = await generate_aml_report(address)
        
        # Отправка результата
        await msg.edit_text(report, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка обработки адреса: {str(e)}")
        await update.message.reply_text(
            "⚠️ <b>Сервис временно недоступен</b>\n"
            "Высокая нагрузка. Пожалуйста, попробуйте позже.",
            parse_mode="HTML"
        )

def main():
    # Инициализация чёрного списка
    if not os.path.exists(BLACKLIST_FILE):
        with open(BLACKLIST_FILE, 'w') as f:
            json.dump({}, f)
        logger.info("Создан новый файл чёрного списка")

    app = ApplicationBuilder().token(TOKEN).build()
    
    # Обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_address))
    
    logger.info("Запуск AML Security Bot...")
    app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
