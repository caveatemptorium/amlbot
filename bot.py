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

class EtherscanClient:
    BASE_URL = "https://api.etherscan.io/api"
    
    @staticmethod
    async def _make_request(params: dict) -> dict:
        """Базовый метод для запросов к API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(EtherscanClient.BASE_URL, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data if isinstance(data, dict) else {}
                    return {"status": "0", "message": f"HTTP error {resp.status}"}
        except Exception as e:
            logger.error(f"Request failed: {str(e)}")
            return {"status": "0", "message": str(e)}

    @staticmethod
    async def get_balance(address: str) -> dict:
        """Получение баланса с обработкой ошибок"""
        params = {
            'module': 'account',
            'action': 'balance',
            'address': address,
            'tag': 'latest',
            'apikey': ETHERSCAN_API_KEY
        }
        data = await EtherscanClient._make_request(params)
        if data.get('status') == '1' and data.get('result'):
            try:
                balance_wei = int(data['result'])
                return {
                    'success': True,
                    'balance': balance_wei / 10**18,
                    'raw': data
                }
            except (ValueError, TypeError) as e:
                logger.error(f"Balance conversion error: {str(e)}")
        return {
            'success': False,
            'error': data.get('message', 'Unknown error'),
            'raw': data
        }

    @staticmethod
    async def check_risk(address: str) -> dict:
        """Проверка рисков с обработкой ошибок"""
        params = {
            'module': 'account',
            'action': 'txlist',
            'address': address,
            'startblock': 0,
            'endblock': 99999999,
            'sort': 'asc',
            'apikey': ETHERSCAN_API_KEY
        }
        data = await EtherscanClient._make_request(params)
        
        if isinstance(data.get('result'), str) and 'blocked' in data['result'].lower():
            return {
                'risk': True,
                'reason': 'Заблокирован Etherscan',
                'source': 'Transaction API',
                'success': True
            }
        
        return {
            'risk': False,
            'success': True if data.get('status') == '1' else False,
            'error': data.get('message', 'No risk detected')
        }

    @staticmethod
    async def get_transaction_count(address: str) -> dict:
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
        data = await EtherscanClient._make_request(params)
        if data.get('status') == '1' and isinstance(data.get('result'), list):
            return {
                'success': True,
                'count': len(data['result']),
                'raw': data
            }
        return {
            'success': False,
            'error': data.get('message', 'Unknown error'),
            'raw': data
        }

    @staticmethod
    async def is_contract(address: str) -> dict:
        """Проверка на контракт"""
        params = {
            'module': 'contract',
            'action': 'getabi',
            'address': address,
            'apikey': ETHERSCAN_API_KEY
        }
        data = await EtherscanClient._make_request(params)
        if data.get('status') == '1':
            return {
                'success': True,
                'is_contract': data['result'] != 'Contract source code not verified',
                'raw': data
            }
        return {
            'success': False,
            'error': data.get('message', 'Unknown error'),
            'raw': data
        }

async def full_analysis(address: str) -> dict:
    """Полный анализ адреса с обработкой ошибок"""
    results = await asyncio.gather(
        EtherscanClient.get_balance(address),
        EtherscanClient.check_risk(address),
        EtherscanClient.get_transaction_count(address),
        EtherscanClient.is_contract(address)
    )
    
    balance_data, risk_data, tx_data, contract_data = results
    
    return {
        'address': address,
        'balance': balance_data.get('balance', 0.0) if balance_data['success'] else None,
        'risk': risk_data if risk_data['success'] else {'risk': False, 'reason': 'Error during check'},
        'tx_count': tx_data.get('count', 0) if tx_data['success'] else None,
        'is_contract': contract_data.get('is_contract', False) if contract_data['success'] else None,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'errors': [
            err for data in results 
            if not data['success'] 
            for err in [data.get('error')] 
            if err
        ]
    }

def format_report(data: dict) -> str:
    """Форматирование отчета с учетом возможных ошибок"""
    parts = [f"🔍 <b>Анализ адреса</b> <code>{data['address']}</code>\n"]
    
    # Баланс
    if data['balance'] is not None:
        balance_msg = f"{data['balance']:.6f} ETH"
        if data['balance'] == 0:
            balance_msg += " (пустой)"
        parts.append(f"💰 <b>Баланс:</b> {balance_msg}")
    else:
        parts.append("💰 <b>Баланс:</b> ❌ Не удалось получить")
    
    # Тип адреса
    if data['is_contract'] is not None:
        parts.append(f"📜 <b>Тип:</b> {'Контракт' if data['is_contract'] else 'Кошелек'}")
    else:
        parts.append("📜 <b>Тип:</b> ❌ Не удалось определить")
    
    # Количество транзакций
    if data['tx_count'] is not None:
        parts.append(f"📊 <b>Транзакций:</b> {data['tx_count']}")
    else:
        parts.append("📊 <b>Транзакций:</b> ❌ Не удалось получить")
    
    # Риски
    if data['risk']['success']:
        if data['risk']['risk']:
            parts.append(
                f"🚨 <b>ВНИМАНИЕ: Адрес заблокирован!</b>\n"
                f"• Причина: {data['risk']['reason']}\n"
                f"• Источник: {data['risk']['source']}"
            )
        else:
            parts.append("✅ <b>Риски не обнаружены</b>")
    else:
        parts.append("⚠️ <b>Проверка рисков:</b> Не удалось выполнить")
    
    # Ошибки
    if data.get('errors'):
        parts.append("\n⚠️ <i>Некоторые данные могут быть неполными из-за ошибок:</i>")
        for error in data['errors'][:3]:  # Показываем не более 3 ошибок
            parts.append(f"• {error}")
    
    parts.append(f"\n<i>Обновлено: {data['timestamp']}</i>")
    
    return "\n".join(parts)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ <b>Анализатор ETH кошельков</b>\n\n"
        "Отправьте ETH адрес (начинается с 0x, 42 символа) для проверки:\n"
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
    
    msg = await update.message.reply_text("🔄 Запрашиваю данные с Etherscan...")
    
    try:
        analysis = await full_analysis(address)
        report = format_report(analysis)
        await msg.edit_text(report, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Analysis failed: {str(e)}")
        await msg.edit_text(
            "⚠️ Произошла критическая ошибка при анализе адреса. Пожалуйста, попробуйте позже.",
            parse_mode="HTML"
        )

def main():
    if not ETHERSCAN_API_KEY:
        logger.error("ETHERSCAN_API_KEY не установлен!")
        return
    
    app = ApplicationBuilder() \
        .token(TOKEN) \
        .http_version("1.1") \
        .get_updates_http_version("1.1") \
        .build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен и готов к работе")
    app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
