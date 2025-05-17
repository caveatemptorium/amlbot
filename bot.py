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
        address = address.strip()
        if not address.startswith('0x'):
            return False
        if len(address) != 42:
            return False
        try:
            int(address, 16)
            return True
        except ValueError:
            return False

class EtherscanAPI:
    @staticmethod
    async def fetch_data(url: str) -> dict:
        """Общий метод для запросов к API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return {"status": "0", "message": f"HTTP error {resp.status}"}
        except Exception as e:
            logger.error(f"API request failed: {str(e)}")
            return {"status": "0", "message": str(e)}

    @staticmethod
    async def get_balance(address: str) -> float:
        """Получение точного баланса"""
        url = f"https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest&apikey={ETHERSCAN_API_KEY}"
        data = await EtherscanAPI.fetch_data(url)
        if data.get('status') == '1':
            return int(data['result']) / 10**18
        logger.error(f"Balance check failed: {data.get('message')}")
        return 0.0

    @staticmethod
    async def get_risk_data(address: str) -> dict:
        """Проверка на блокировку через Etherscan"""
        # Проверка через список токенов (часто показывает блокировки)
        url = f"https://api.etherscan.io/api?module=account&action=tokentx&address={address}&startblock=0&endblock=99999999&sort=asc&apikey={ETHERSCAN_API_KEY}"
        data = await EtherscanAPI.fetch_data(url)
        
        if isinstance(data.get('result'), str) and "blocked" in data['result'].lower():
            return {
                "risk": True,
                "reason": "Заблокирован Etherscan",
                "source": "Etherscan Token API"
            }
        
        # Дополнительная проверка через обычные транзакции
        tx_url = f"https://api.etherscan.io/api?module=account&action=txlist&address={address}&startblock=0&endblock=99999999&sort=asc&apikey={ETHERSCAN_API_KEY}"
        tx_data = await EtherscanAPI.fetch_data(tx_url)
        
        if isinstance(tx_data.get('result'), str) and "blocked" in tx_data['result'].lower():
            return {
                "risk": True,
                "reason": "Заблокирован для ETH переводов",
                "source": "Etherscan Transaction API"
            }
        
        return {"risk": False}

    @staticmethod
    async def get_contract_info(address: str) -> bool:
        """Проверка, является ли адрес контрактом"""
        url = f"https://api.etherscan.io/api?module=contract&action=getabi&address={address}&apikey={ETHERSCAN_API_KEY}"
        data = await EtherscanAPI.fetch_data(url)
        return data.get('status') == '1' and data['result'] != 'Contract source code not verified'

    @staticmethod
    async def get_transaction_count(address: str) -> int:
        """Получение реального количества транзакций"""
        url = f"https://api.etherscan.io/api?module=account&action=txlist&address={address}&startblock=0&endblock=99999999&sort=asc&apikey={ETHERSCAN_API_KEY}"
        data = await EtherscanAPI.fetch_data(url)
        return len(data.get('result', [])) if data.get('status') == '1' else 0

class AddressAnalyzer:
    @staticmethod
    async def full_analysis(address: str) -> dict:
        """Комплексный анализ адреса"""
        if not AddressValidator.is_valid_eth_address(address):
            raise ValueError("Invalid ETH address format")

        # Параллельные запросы для скорости
        balance, risk, is_contract, tx_count = await asyncio.gather(
            EtherscanAPI.get_balance(address),
            EtherscanAPI.get_risk_data(address),
            EtherscanAPI.get_contract_info(address),
            EtherscanAPI.get_transaction_count(address)
        )

        return {
            'address': address,
            'balance': balance,
            'risk': risk,
            'is_contract': is_contract,
            'tx_count': tx_count,
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'success': True
        }

def format_report(analysis: dict) -> str:
    """Генерация красивого отчета"""
    # Форматирование баланса
    balance_msg = f"{analysis['balance']:.6f} ETH"
    if analysis['balance'] == 0:
        balance_msg += " (пустой)"

    # Форматирование информации о рисках
    if analysis['risk']['risk']:
        risk_msg = (
            f"🚨 <b>ВНИМАНИЕ: Адрес опасен!</b>\n"
            f"• Причина: {analysis['risk']['reason']}\n"
            f"• Источник: {analysis['risk']['source']}\n\n"
            f"⚠️ <i>Рекомендуется прекратить любые операции с этим адресом</i>"
        )
    else:
        risk_msg = "✅ <b>Проверка безопасности пройдена</b>"

    return (
        f"🔍 <b>Анализ адреса</b> <code>{analysis['address']}</code>\n\n"
        f"💰 <b>Баланс:</b> {balance_msg}\n"
        f"📜 <b>Тип:</b> {'Контракт' if analysis['is_contract'] else 'Обычный кошелек'}\n"
        f"📊 <b>Транзакций:</b> {analysis['tx_count']}\n\n"
        f"{risk_msg}\n\n"
        f"<i>Данные актуальны на: {analysis['timestamp']}</i>"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ <b>Анализатор ETH кошельков</b>\n\n"
        "Отправьте мне ETH адрес (начинается с 0x, 42 символа) и я проверю:\n"
        "- Точный баланс в ETH\n"
        "- Является ли адрес контрактом\n"
        "- Количество транзакций\n"
        "- Наличие блокировок\n\n"
        "Пример: <code>0x742d35Cc6634C0532925a3b844Bc454e4438f44e</code>",
        parse_mode="HTML"
    )

async def analyze_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        address = update.message.text.strip()
        
        if not AddressValidator.is_valid_eth_address(address):
            await update.message.reply_text(
                "❌ <b>Неправильный формат адреса!</b>\n"
                "ETH адрес должен:\n"
                "- Начинаться с 0x\n"
                "- Содержать ровно 42 символа\n"
                "- Использовать только 0-9 и a-f\n\n"
                "Пример корректного адреса:\n"
                "<code>0x742d35Cc6634C0532925a3b844Bc454e4438f44e</code>",
                parse_mode="HTML"
            )
            return

        msg = await update.message.reply_text("🔍 Запрашиваю данные с Etherscan...")
        
        try:
            analysis = await AddressAnalyzer.full_analysis(address)
            if not analysis.get('success', True):
                raise ValueError("Analysis failed")
                
            report = format_report(analysis)
            await msg.edit_text(report, parse_mode="HTML")
            
        except Exception as e:
            logger.error(f"Analysis failed: {str(e)}")
            await msg.edit_text(
                "⚠️ <b>Ошибка при анализе</b>\n"
                "Не удалось получить данные. Возможные причины:\n"
                "- Адрес не существует\n"
                "- Проблемы с API Etherscan\n"
                "- Превышен лимит запросов\n\n"
                "Попробуйте позже или проверьте правильность адреса.",
                parse_mode="HTML"
            )
            
    except Exception as e:
        logger.error(f"Handler error: {str(e)}")
        await update.message.reply_text(
            "🚫 Произошла внутренняя ошибка. Пожалуйста, попробуйте позже.",
            parse_mode="HTML"
        )

def main():
    app = ApplicationBuilder() \
        .token(TOKEN) \
        .http_version("1.1") \
        .get_updates_http_version("1.1") \
        .build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_address))

    logger.info("Бот успешно запущен")
    app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
