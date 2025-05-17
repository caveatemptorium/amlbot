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
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY") or "YOUR_API_KEY"

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class AddressValidator:
    @staticmethod
    def is_valid_eth_address(address: str) -> bool:
        """Проверка валидности ETH адреса"""
        if not isinstance(address, str):
            return False
        if not address.startswith('0x'):
            return False
        if len(address) != 42:
            return False
        try:
            int(address, 16)
            return True
        except ValueError:
            return False

class RiskAnalyzer:
    BLACKLIST = {
        "0x8576acc5c05d6ce88f4e49bf65bdf0c62f91353c": "Фишинг",
        "0x1da5821544e25c636c1417ba96ade4cf6d2f9b5a": "Отмывание денег",
        "0xae2fc483527b8ef99eb5d9b44875f005ba1fae13": "Взлом"
    }

    @staticmethod
    async def check_risk(address: str) -> dict:
        """Проверка адреса на рискованность"""
        address_lower = address.lower()
        if address_lower in RiskAnalyzer.BLACKLIST:
            return {
                "risk": True,
                "reason": RiskAnalyzer.BLACKLIST[address_lower],
                "source": "Локальный чёрный список"
            }
        
        # Проверка через Etherscan API
        try:
            url = f"https://api.etherscan.io/api?module=account&action=txlist&address={address}&startblock=0&endblock=99999999&page=1&offset=1&sort=asc&apikey={ETHERSCAN_API_KEY}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    data = await resp.json()
                    if data.get('message') == 'NOTOK' and 'blocked' in str(data.get('result', '')).lower():
                        return {
                            "risk": True,
                            "reason": "Заблокирован Etherscan",
                            "source": "Etherscan API"
                        }
        except Exception as e:
            logger.error(f"Risk check error: {str(e)}")
        
        return {"risk": False}

class EtherscanClient:
    @staticmethod
    async def get_balance(address: str) -> float:
        """Получение баланса ETH"""
        url = f"https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest&apikey={ETHERSCAN_API_KEY}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if data.get('status') == '1':
                    return int(data['result']) / 10**18
                return 0.0

    @staticmethod
    async def is_contract(address: str) -> bool:
        """Проверка, является ли адрес контрактом"""
        url = f"https://api.etherscan.io/api?module=contract&action=getabi&address={address}&apikey={ETHERSCAN_API_KEY}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                return data.get('status') == '1' and data['result'] != 'Contract source code not verified'

    @staticmethod
    async def get_transaction_count(address: str) -> int:
        """Получение количества транзакций"""
        url = f"https://api.etherscan.io/api?module=account&action=txlist&address={address}&startblock=0&endblock=99999999&page=1&offset=1&sort=asc&apikey={ETHERSCAN_API_KEY}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                return len(data.get('result', [])) if data.get('status') == '1' else 0

class AddressAnalyzer:
    @staticmethod
    async def analyze_address(address: str) -> dict:
        """Полный анализ адреса"""
        if not AddressValidator.is_valid_eth_address(address):
            raise ValueError("Invalid ETH address")

        balance = await EtherscanClient.get_balance(address)
        is_contract = await EtherscanClient.is_contract(address)
        tx_count = await EtherscanClient.get_transaction_count(address)
        risk_info = await RiskAnalyzer.check_risk(address)

        return {
            'address': address,
            'balance': balance,
            'is_contract': is_contract,
            'tx_count': tx_count,
            'risk': risk_info,
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

def format_report(analysis: dict) -> str:
    """Форматирование отчета"""
    risk_msg = (
        f"🚨 <b>ВНИМАНИЕ: Риск обнаружен!</b>\n"
        f"• Причина: {analysis['risk']['reason']}\n"
        f"• Источник: {analysis['risk']['source']}"
    ) if analysis['risk']['risk'] else "✅ <b>Риски не обнаружены</b>"

    return (
        f"🔍 <b>Анализ адреса</b> <code>{analysis['address']}</code>\n\n"
        f"💰 <b>Баланс:</b> {analysis['balance']:.6f} ETH\n"
        f"📜 <b>Тип:</b> {'Контракт' if analysis['is_contract'] else 'Кошелёк'}\n"
        f"📊 <b>Транзакций:</b> {analysis['tx_count']}\n\n"
        f"{risk_msg}\n\n"
        f"<i>Обновлено: {analysis['timestamp']}</i>"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ <b>ETH Address Analyzer Bot</b>\n\n"
        "Отправьте ETH-адрес (начинается с 0x, 42 символа) для проверки\n"
        "Пример: <code>0x1f9090aaE28b8a3dCeaDf281B0F12828e676c326</code>",
        parse_mode="HTML"
    )

async def analyze_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        address = update.message.text.strip()
        
        if not AddressValidator.is_valid_eth_address(address):
            await update.message.reply_text(
                "❌ <b>Неверный формат адреса!</b>\n"
                "ETH адрес должен:\n"
                "- Начинаться с 0x\n"
                "- Содержать ровно 42 символа\n"
                "- Состоять из hex-символов (0-9, a-f)\n\n"
                "Пример: <code>0x742d35Cc6634C0532925a3b844Bc454e4438f44e</code>",
                parse_mode="HTML"
            )
            return

        msg = await update.message.reply_text("🔍 Анализирую адрес...")
        
        try:
            analysis = await AddressAnalyzer.analyze_address(address)
            report = format_report(analysis)
            await msg.edit_text(report, parse_mode="HTML")
            
        except Exception as e:
            logger.error(f"Analysis error: {str(e)}")
            await msg.edit_text(
                "⚠️ <b>Ошибка анализа</b>\n"
                "Не удалось получить данные. Возможные причины:\n"
                "- Неправильный адрес\n"
                "- Проблемы с API Etherscan\n"
                "- Превышен лимит запросов",
                parse_mode="HTML"
            )
            
    except Exception as e:
        logger.error(f"Handler error: {str(e)}")
        await update.message.reply_text("🚫 Внутренняя ошибка бота. Попробуйте позже.")

def main():
    app = ApplicationBuilder() \
        .token(TOKEN) \
        .http_version("1.1") \
        .get_updates_http_version("1.1") \
        .build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_handler))

    logger.info("Бот запущен и готов к работе")
    app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
