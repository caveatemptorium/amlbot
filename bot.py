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

# Проверка обязательных переменных
if not TOKEN or not ETHERSCAN_API_KEY:
    raise ValueError("Необходимо установить TELEGRAM_TOKEN и ETHERSCAN_API_KEY в .env файле")

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class EtherscanAPI:
    BASE_URL = "https://api.etherscan.io/api"
    
    @staticmethod
    async def _make_request(params: dict) -> dict:
        """Базовый метод для запросов к API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(EtherscanAPI.BASE_URL, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data if isinstance(data, dict) else {}
                    return {"status": "0", "message": f"HTTP error {resp.status}"}
        except Exception as e:
            logger.error(f"Request failed: {str(e)}")
            return {"status": "0", "message": str(e)}

    @staticmethod
    async def get_balance(address: str) -> dict:
        """Получение баланса ETH"""
        params = {
            'module': 'account',
            'action': 'balance',
            'address': address,
            'tag': 'latest',
            'apikey': ETHERSCAN_API_KEY
        }
        data = await EtherscanAPI._make_request(params)
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
        """Проверка на блокировку"""
        params = {
            'module': 'account',
            'action': 'txlist',
            'address': address,
            'startblock': 0,
            'endblock': 99999999,
            'sort': 'asc',
            'apikey': ETHERSCAN_API_KEY
        }
        data = await EtherscanAPI._make_request(params)
        
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
        """Количество транзакций"""
        params = {
            'module': 'account',
            'action': 'txlist',
            'address': address,
            'startblock': 0,
            'endblock': 99999999,
            'sort': 'asc',
            'apikey': ETHERSCAN_API_KEY
        }
        data = await EtherscanAPI._make_request(params)
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
        data = await EtherscanAPI._make_request(params)
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

async def analyze_address(address: str) -> dict:
    """Полный анализ адреса"""
    results = await asyncio.gather(
        EtherscanAPI.get_balance(address),
        EtherscanAPI.check_risk(address),
        EtherscanAPI.get_transaction_count(address),
        EtherscanAPI.is_contract(address),
        return_exceptions=True
    )
    
    # Обработка результатов
    balance_data = results[0] if not isinstance(results[0], Exception) else {
        'success': False,
        'error': str(results[0])
    }
    risk_data = results[1] if not isinstance(results[1], Exception) else {
        'success': False,
        'error': str(results[1]),
        'risk
