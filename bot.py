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

class EtherscanAPI:
    BASE_URL = "https://api.etherscan.io/api"
    
    @staticmethod
    async def fetch_balance(address: str) -> float:
        """Получение точного баланса ETH"""
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
    async def check_risk(address: str) -> dict:
        """Проверка на блокировку через API"""
        # Проверяем через список транзакций
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
                async with session.get(EtherscanAPI.BASE_URL, params=params) as resp:
                    data = await resp.json()
                    if isinstance(data.get('result'), str) and 'blocked' in data['result'].lower():
                        return {
                            'risk': True,
                            'reason': 'Заблокирован Etherscan',
                            'source': 'Transaction API'
                        }
        except Exception as e:
            logger.error(f"Risk check failed: {str(e)}")
        
        return {'risk': False}

    @staticmethod
    async def get_transactions(address: str) -> int:
        """Получение количества транзакций"""
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
                async with session.get(EtherscanAPI.BASE_URL, params=params) as resp:
                    data = await resp.json()
                    return len(data.get('result', [])) if data.get('status') == '1' else 0
        except Exception as e:
            logger.error(f"Tx count error: {str(e)}")
            return 0

    @staticmethod
    async def is_contract(address: str) -> bool:
        """Проверка на контракт"""
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
            logger.error(f"Contract check error: {str(e)}")
            return False

async def analyze_address(address: str) -> dict:
    """Полный анализ адреса"""
    balance, risk, tx_count, is_contract = await asyncio.gather(
        EtherscanAPI.fetch_balance(address),
        EtherscanAPI.check_risk(address),
        EtherscanAPI.get_transactions(address),
        EtherscanAPI.is_contract(address)
    )
    
    return {
        'address': address,
        'balance': balance,
        'risk': risk,
        'tx_count': tx_count,
        'is_contract': is_contract,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

def format_report(data: dict) -> str:
    """Форматирование отчета"""
    balance_msg = f"{data['balance']:.6f} ETH"
    if data['balance'] == 0:
        balance_msg += " (пустой)"
    
    risk_msg = (
        f"🚨 <b>ВНИМАНИЕ: Адрес заблокирован!</b>\n"
        f"• Причина: {data['risk']['reason']}\n"
        f"• Источник: {data['risk']['source']}"
    ) if data['risk']['risk'] else "✅ <b>Риски не обнаружены</b>"
    
    return (
        f"🔍 <b>Анализ адреса</b> <code>{data['address']}</code>\n\n"
        f"💰 <b>Баланс:</b> {balance_msg}\n"
        f"📜 <b>Тип:</b> {'Контракт' if data['is_contract'] else 'Кошелек'}\n"
        f"📊 <b>Транзакций:</b> {data['tx_count']}\n\n"
        f"{risk_msg}\n\n"
        f"<i>Обновлено: {data['timestamp']}</i>"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ <b>Анализатор ETH кошельков</b>\n\n"
        "Отправьте ETH адрес для проверки:\n"
        "- Текущий баланс\n"
        "- Количество транзакций\n"
        "- Статус блокировки\n\n"
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
    
    msg = await update.message.reply_text("🔄 Запрашиваю данные...")
    
    try:
        analysis = await analyze_address(address)
        report = format_report(analysis)
        await msg.edit_text(report, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Analysis failed: {str(e)}")
        await msg.edit_text(
            "⚠️ Не удалось получить данные. Проверьте адрес и попробуйте позже.",
            parse_mode="HTML"
        )

def main():
    app = ApplicationBuilder() \
        .token(TOKEN) \
        .http_version("1.1") \
        .get_updates_http_version("1.1") \
        .build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
