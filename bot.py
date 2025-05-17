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
    exit(1)

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class BlockedAddressChecker:
    # Актуальный список известных заблокированных адресов
    KNOWN_BLOCKED = {
        "0x8576acc5c05d6ce88f4e49bf65bdf0c62f91353c": "Фишинг",
        "0x1da5821544e25c636c1417ba96ade4cf6d2f9b5a": "Взлом",
        "0x9f4cda013e354b8fc285bf4b9a60460cee7f7ea9": "Отмывание денег"
    }

    @staticmethod
    async def is_blocked(address: str) -> dict:
        """Проверка адреса на блокировку"""
        address_lower = address.lower()
        
        # 1. Проверка по локальному списку
        if address_lower in BlockedAddressChecker.KNOWN_BLOCKED:
            return {
                'blocked': True,
                'reason': BlockedAddressChecker.KNOWN_BLOCKED[address_lower],
                'source': 'Локальная база'
            }
        
        # 2. Проверка через API токенов (косвенный метод)
        async with aiohttp.ClientSession() as session:
            url = f"https://api.etherscan.io/api?module=account&action=tokentx&address={address}&apikey={ETHERSCAN_API_KEY}"
            try:
                async with session.get(url) as resp:
                    data = await resp.json()
                    if data.get('message') == 'NOTOK' and 'blocked' in str(data.get('result', '')).lower():
                        return {
                            'blocked': True,
                            'reason': 'Заблокирован для токенов',
                            'source': 'Etherscan API'
                        }
            except Exception as e:
                logger.error(f"Blocked check error: {str(e)}")
        
        return {'blocked': False}

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

async def analyze_address(address: str) -> dict:
    """Полный анализ адреса"""
    balance, is_blocked, is_contract = await asyncio.gather(
        EtherscanAPI.get_balance(address),
        BlockedAddressChecker.is_blocked(address),
        EtherscanAPI.is_contract(address)
    )
    return {
        'address': address,
        'balance': balance,
        'is_blocked': is_blocked,
        'is_contract': is_contract,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

def format_report(data: dict) -> str:
    """Форматирование отчета"""
    report = [
        f"🔍 <b>Анализ адреса</b> <code>{data['address']}</code>",
        f"💰 <b>Баланс:</b> {data['balance']:.6f} ETH",
        f"📜 <b>Тип:</b> {'Контракт' if data['is_contract'] else 'Кошелек'}"
    ]
    
    if data['is_blocked']['blocked']:
        report.append(
            f"🚨 <b>ВНИМАНИЕ: АДРЕС ЗАБЛОКИРОВАН!</b>\n"
            f"• Причина: {data['is_blocked']['reason']}\n"
            f"• Источник: {data['is_blocked']['source']}\n\n"
            f"⚠️ <i>Рекомендуется прекратить любые операции с этим адресом</i>"
        )
    else:
        report.append("✅ <b>Адрес не найден в чёрных списках</b>")
    
    report.append(f"\n<i>Обновлено: {data['timestamp']}</i>")
    
    return "\n\n".join(report)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ <b>Анализатор ETH кошельков</b>\n\n"
        "Отправьте ETH адрес (0x...) для проверки:\n"
        "- Баланс ETH\n"
        "- Наличие в чёрных списках\n"
        "- Тип адреса\n\n"
        "Пример: <code>0x742d35Cc6634C0532925a3b844Bc454e4438f44e</code>",
        parse_mode="HTML"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = update.message.text.strip()
    
    if not (address.startswith('0x') and len(address) == 42):
        await update.message.reply_text("❌ Неверный формат адреса! Должен начинаться с 0x и содержать 42 символа")
        return
    
    msg = await update.message.reply_text("🔍 Проверяю адрес...")
    
    try:
        analysis = await analyze_address(address)
        await msg.edit_text(format_report(analysis), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        await msg.edit_text("⚠️ Ошибка при проверке адреса. Попробуйте позже.")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
