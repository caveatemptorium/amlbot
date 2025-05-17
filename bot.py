import logging
import os
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

# Загрузка переменных окружения
load_dotenv()

# Проверка переменных
TOKEN = os.getenv("TELEGRAM_TOKEN")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")

if not TOKEN or not ETHERSCAN_API_KEY:
    print("ОШИБКА: Создайте файл .env с переменными TELEGRAM_TOKEN и ETHERSCAN_API_KEY")
    print("Пример содержимого .env файла:")
    print("TELEGRAM_TOKEN=ваш_токен_бота")
    print("ETHERSCAN_API_KEY=ваш_ключ_etherscan")
    exit(1)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class EtherscanAPI:
    BASE_URL = "https://api.etherscan.io/api"
    
    @staticmethod
    async def get_balance(address: str) -> float:
        """Получение баланса ETH"""
        params = {
            'module': 'account',
            'action': 'balance',
            'address': address,
            'tag': 'latest',
            'apikey': ETHERSCAN_API_KEY
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(EtherscanAPI.BASE_URL, params=params) as resp:
                    data = await resp.json()
                    if data['status'] == '1':
                        return int(data['result']) / 10**18
                    logger.error(f"Balance error: {data.get('message')}")
                    return 0.0
        except Exception as e:
            logger.error(f"Balance fetch failed: {str(e)}")
            return 0.0

    @staticmethod
    async def check_blacklist(address: str) -> dict:
        """Проверка адреса в чёрном списке Etherscan"""
        # Получаем список заблокированных адресов через tags API
        params = {
            'module': 'account',
            'action': 'txlist',
            'address': address,
            'startblock': 0,
            'endblock': 99999999,
            'sort': 'asc',
            'apikey': ETHERSCAN_API_KEY
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                # Проверка 1: через список транзакций
                async with session.get(EtherscanAPI.BASE_URL, params=params) as resp:
                    data = await resp.json()
                    if isinstance(data.get('result'), str) and 'blocked' in data['result'].lower():
                        return {
                            'risk': True,
                            'reason': 'Заблокирован Etherscan (основной список)',
                            'source': 'Etherscan API'
                        }
                
                # Проверка 2: через список токенов (часто содержит блокировки USDT/USDC)
                token_params = params.copy()
                token_params['action'] = 'tokentx'
                async with session.get(EtherscanAPI.BASE_URL, params=token_params) as resp:
                    token_data = await resp.json()
                    if isinstance(token_data.get('result'), str) and 'blocked' in token_data['result'].lower():
                        return {
                            'risk': True,
                            'reason': 'Заблокирован для токенов (USDT/USDC)',
                            'source': 'Etherscan Token API'
                        }
        
        except Exception as e:
            logger.error(f"Blacklist check failed: {str(e)}")
        
        return {'risk': False}

    @staticmethod
    async def is_contract(address: str) -> bool:
        """Проверка, является ли адрес контрактом"""
        params = {
            'module': 'contract',
            'action': 'getabi',
            'address': address,
            'apikey': ETHERSCAN_API_KEY
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(EtherscanAPI.BASE_URL, params=params) as resp:
                    data = await resp.json()
                    return data.get('status') == '1' and data['result'] != 'Contract source code not verified'
        except Exception as e:
            logger.error(f"Contract check failed: {str(e)}")
            return False

async def analyze_address(address: str) -> dict:
    """Полный анализ адреса"""
    balance, risk, is_contract = await asyncio.gather(
        EtherscanAPI.get_balance(address),
        EtherscanAPI.check_blacklist(address),
        EtherscanAPI.is_contract(address)
    )
    return {
        'address': address,
        'balance': balance,
        'risk': risk,
        'is_contract': is_contract,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

def format_report(data: dict) -> str:
    """Форматирование отчета"""
    balance_msg = f"{data['balance']:.6f} ETH"
    if data['balance'] == 0:
        balance_msg += " (пустой)"
    
    risk_msg = (
        f"🚨 <b>ВНИМАНИЕ: Адрес в чёрном списке!</b>\n"
        f"• Причина: {data['risk']['reason']}\n"
        f"• Источник: {data['risk']['source']}"
    ) if data['risk']['risk'] else "✅ <b>Не найден в чёрных списках</b>"
    
    return (
        f"🔍 <b>Анализ адреса</b> <code>{data['address']}</code>\n\n"
        f"💰 <b>Баланс:</b> {balance_msg}\n"
        f"📜 <b>Тип:</b> {'Контракт' if data['is_contract'] else 'Кошелек'}\n\n"
        f"{risk_msg}\n\n"
        f"<i>Обновлено: {data['timestamp']}</i>"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ <b>Анализатор ETH кошельков</b>\n\n"
        "Отправьте ETH адрес (начинается с 0x, 42 символа) для проверки:\n"
        "- Текущий баланс\n"
        "- Наличие в чёрных списках\n"
        "- Тип адреса\n\n"
        "Пример: <code>0x742d35Cc6634C0532925a3b844Bc454e4438f44e</code>",
        parse_mode="HTML"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = update.message.text.strip()
    
    if not (address.startswith('0x') and len(address) == 42):
        await update.message.reply_text(
            "❌ Неверный формат адреса! Должен начинаться с 0x и содержать 42 символа",
            parse_mode="HTML"
        )
        return
    
    msg = await update.message.reply_text("🔍 Проверяю адрес...")
    
    try:
        analysis = await analyze_address(address)
        report = format_report(analysis)
        await msg.edit_text(report, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Analysis failed: {str(e)}")
        await msg.edit_text(
            "⚠️ Ошибка при проверке адреса. Попробуйте позже.",
            parse_mode="HTML"
        )

def main():
    """Запуск бота"""
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Бот запущен и готов к работе")
    application.run_polling()

if __name__ == "__main__":
    main()
