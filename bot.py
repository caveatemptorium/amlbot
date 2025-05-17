import logging
import os
import json
import asyncio
import aiohttp
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from dotenv import load_dotenv

# Загрузка конфигурации
load_dotenv()

# Проверка обязательных переменных
TOKEN = os.getenv("TELEGRAM_TOKEN")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
BLOCKED_FILE = "blocked_addresses.json"

if not TOKEN or not ETHERSCAN_API_KEY:
    raise ValueError("Необходимо установить TELEGRAM_TOKEN и ETHERSCAN_API_KEY в .env")

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class BlocklistManager:
    def __init__(self, file_path):
        self.file_path = file_path
        self.blocked_addresses = {}
        self.load_blocklist()
    
    def load_blocklist(self):
        """Загрузка списка заблокированных адресов из файла"""
        try:
            with open(self.file_path, 'r') as f:
                self.blocked_addresses = json.load(f)
            logger.info(f"Загружено {len(self.blocked_addresses)} заблокированных адресов")
        except FileNotFoundError:
            logger.warning("Файл с заблокированными адресами не найден, создан новый")
            self.blocked_addresses = {}
        except json.JSONDecodeError:
            logger.error("Ошибка чтения JSON файла")
            self.blocked_addresses = {}
    
    def is_blocked(self, address):
        """Проверка адреса в чёрном списке"""
        return self.blocked_addresses.get(address.lower())

    def add_to_blocklist(self, address, reason, source):
        """Добавление адреса в чёрный список"""
        self.blocked_addresses[address.lower()] = {
            "reason": reason,
            "source": source
        }
        self.save_blocklist()
    
    def save_blocklist(self):
        """Сохранение списка в файл"""
        with open(self.file_path, 'w') as f:
            json.dump(self.blocked_addresses, f, indent=2)

class EtherscanAPI:
    @staticmethod
    async def get_balance(address: str) -> float:
        """Получение баланса ETH"""
        url = f"https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest&apikey={ETHERSCAN_API_KEY}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    data = await resp.json()
                    if data.get('status') == '1':
                        return int(data['result']) / 10**18
        except Exception as e:
            logger.error(f"Balance error: {str(e)}")
        return 0.0

    @staticmethod
    async def is_contract(address: str) -> bool:
        """Проверка, является ли адрес контрактом"""
        url = f"https://api.etherscan.io/api?module=contract&action=getabi&address={address}&apikey={ETHERSCAN_API_KEY}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    data = await resp.json()
                    return data.get('status') == '1' and data['result'] != 'Contract source code not verified'
        except Exception as e:
            logger.error(f"Contract check error: {str(e)}")
        return False

async def analyze_address(address: str, blocklist: BlocklistManager) -> dict:
    """Полный анализ адреса"""
    address_lower = address.lower()
    
    # Проверка в чёрном списке
    blocked_info = blocklist.is_blocked(address_lower)
    
    # Параллельные запросы к Etherscan
    balance, is_contract = await asyncio.gather(
        EtherscanAPI.get_balance(address),
        EtherscanAPI.is_contract(address)
    )
    
    return {
        'address': address,
        'balance': balance,
        'is_contract': is_contract,
        'blocked': blocked_info if blocked_info else None,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

def format_report(data: dict) -> str:
    """Форматирование отчёта"""
    report = [
        f"🔍 <b>Анализ адреса</b> <code>{data['address']}</code>",
        f"💰 <b>Баланс:</b> {data['balance']:.6f} ETH",
        f"📜 <b>Тип:</b> {'Контракт' if data['is_contract'] else 'Кошелёк'}"
    ]
    
    if data['blocked']:
        report.append(
            f"🚨 <b>ВНИМАНИЕ: Адрес в чёрном списке!</b>\n"
            f"• Причина: {data['blocked']['reason']}\n"
            f"• Источник: {data['blocked']['source']}"
        )
    else:
        report.append("✅ <b>Адрес не найден в чёрных списках</b>")
    
    report.append(f"<i>Обновлено: {data['timestamp']}</i>")
    
    return "\n\n".join(report)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "🛡️ <b>ETH Address Analyzer</b>\n\n"
        "Отправьте ETH адрес для проверки:\n"
        "- Баланс ETH\n"
        "- Наличие в чёрном списке\n"
        "- Тип адреса\n\n"
        "Пример: <code>0x742d35Cc6634C0532925a3b844Bc454e4438f44e</code>",
        parse_mode="HTML"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик сообщений с адресами"""
    address = update.message.text.strip()
    
    if not (address.startswith('0x') and len(address) == 42):
        await update.message.reply_text(
            "❌ Неверный формат адреса! Должен начинаться с 0x и содержать 42 символа",
            parse_mode="HTML"
        )
        return
    
    blocklist = context.bot_data.get('blocklist')
    if not blocklist:
        await update.message.reply_text("⚠️ Ошибка загрузки чёрного списка")
        return
    
    msg = await update.message.reply_text("🔍 Проверяю адрес...")
    
    try:
        analysis = await analyze_address(address, blocklist)
        await msg.edit_text(format_report(analysis), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Analysis error: {str(e)}")
        await msg.edit_text("⚠️ Ошибка при анализе адреса")

async def add_blocked_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для добавления адреса в чёрный список (/block <address> <reason>)"""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Использование: /block <адрес> <причина> [источник]")
        return
    
    address = context.args[0]
    reason = context.args[1]
    source = context.args[2] if len(context.args) > 2 else "Ручное добавление"
    
    blocklist = context.bot_data.get('blocklist')
    if not blocklist:
        await update.message.reply_text("⚠️ Ошибка доступа к чёрному списку")
        return
    
    blocklist.add_to_blocklist(address, reason, source)
    await update.message.reply_text(
        f"✅ Адрес {address} добавлен в чёрный список\n"
        f"Причина: {reason}\n"
        f"Источник: {source}"
    )

async def post_init(application):
    """Инициализация после запуска бота"""
    blocklist = BlocklistManager(BLOCKED_FILE)
    application.bot_data['blocklist'] = blocklist
    logger.info("Бот инициализирован")

def main():
    """Запуск бота"""
    app = ApplicationBuilder() \
        .token(TOKEN) \
        .post_init(post_init) \
        .build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("block", add_blocked_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Бот запущен и готов к работе")
    app.run_polling()

if __name__ == "__main__":
    main()
