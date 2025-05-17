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

class RiskAnalyzer:
    @staticmethod
    async def check_address_risk(address: str) -> dict:
        """Проверка адреса на блокировку через Etherscan API"""
        try:
            # Проверка через API транзакций
            url = f"https://api.etherscan.io/api?module=account&action=txlist&address={address}&startblock=0&endblock=99999999&page=1&offset=1&sort=asc&apikey={ETHERSCAN_API_KEY}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    data = await resp.json()
                    
                    # Косвенные признаки блокировки
                    if data.get("message") == "NOTOK" and "blocked" in data.get("result", "").lower():
                        return {
                            "risk": True,
                            "reason": "Заблокирован (Etherscan API)",
                            "source": "Etherscan Transaction API"
                        }
                
                # Дополнительная проверка через API токенов
                token_url = f"https://api.etherscan.io/api?module=account&action=tokentx&address={address}&startblock=0&endblock=99999999&sort=asc&apikey={ETHERSCAN_API_KEY}"
                async with session.get(token_url) as token_resp:
                    token_data = await token_resp.json()
                    if token_data.get("message") == "NOTOK" and "blocked" in token_data.get("result", "").lower():
                        return {
                            "risk": True,
                            "reason": "Заблокирован для токенов",
                            "source": "Etherscan Token API"
                        }
            
            return {"risk": False}
            
        except Exception as e:
            logger.error(f"Risk check error: {str(e)}")
            return {"risk": False, "error": str(e)}

class AddressAnalyzer:
    @staticmethod
    async def get_transactions(address: str) -> list:
        url = f"https://api.etherscan.io/api?module=account&action=txlist&address={address}&startblock=0&endblock=99999999&sort=asc&apikey={ETHERSCAN_API_KEY}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                return data.get('result', []) if data.get('status') == '1' else []

    @staticmethod
    async def analyze_address(address: str) -> dict:
        try:
            async with aiohttp.ClientSession() as session:
                # Получаем баланс
                balance_url = f"https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest&apikey={ETHERSCAN_API_KEY}"
                async with session.get(balance_url) as resp:
                    data = await resp.json()
                    balance = int(data['result']) / 10**18 if data.get('status') == '1' else 0

                # Проверяем контракт
                contract_url = f"https://api.etherscan.io/api?module=contract&action=getabi&address={address}&apikey={ETHERSCAN_API_KEY}"
                async with session.get(contract_url) as resp:
                    contract_data = await resp.json()
                    is_contract = contract_data.get('status') == '1' and contract_data['result'] != 'Contract source code not verified'

                # Проверка рисков
                risk_info = await RiskAnalyzer.check_address_risk(address)
                
                # Получаем транзакции
                transactions = await AddressAnalyzer.get_transactions(address)
                tx_count = len(transactions)
                first_seen = datetime.fromtimestamp(int(transactions[0]['timeStamp'])) if tx_count > 0 else None

                return {
                    'address': address,
                    'balance': balance,
                    'is_contract': is_contract,
                    'risk': risk_info,
                    'tx_count': tx_count,
                    'first_seen': first_seen,
                    'transactions': transactions
                }

        except Exception as e:
            logger.error(f"Address analysis error: {str(e)}")
            raise

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ <b>Etherscan Address Analyzer</b>\n\n"
        "Отправьте ETH-адрес (0x...) для проверки на блокировки\n"
        "Пример: <code>0x000000000000000880620000000203571704007</code>",
        parse_mode="HTML"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        address = update.message.text.strip()
        if not (address.startswith("0x") and len(address) == 42):
            await update.message.reply_text("❌ Неверный формат адреса! Должен начинаться с 0x и иметь 42 символа")
            return

        msg = await update.message.reply_text("🔍 Анализирую адрес...")
        analysis = await AddressAnalyzer.analyze_address(address)
        
        # Формируем отчет
        report = (
            f"🔍 <b>Анализ адреса</b> <code>{address}</code>\n\n"
            f"💰 <b>Баланс:</b> {analysis['balance']:.4f} ETH\n"
            f"📜 <b>Тип:</b> {'Контракт' if analysis['is_contract'] else 'Кошелёк'}\n"
            f"📊 <b>Транзакций:</b> {analysis['tx_count']}\n"
            f"📅 <b>Первая активность:</b> {analysis['first_seen'].strftime('%Y-%m-%d') if analysis['first_seen'] else 'Нет данных'}\n\n"
        )
        
        # Добавляем информацию о блокировке
        if analysis['risk']['risk']:
            report += (
                f"🚨 <b>ВНИМАНИЕ: Адрес заблокирован!</b>\n"
                f"• Причина: {analysis['risk']['reason']}\n"
                f"• Источник: {analysis['risk']['source']}\n\n"
                f"⚠️ Возможные последствия:\n"
                f"- Блокировка переводов стейблкоинов (USDT, USDC)\n"
                f"- Отказ от обслуживания биржами\n"
            )
        else:
            report += "✅ <b>Блокировки не обнаружены</b> (по данным Etherscan API)"
        
        await msg.edit_text(report, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Message handling error: {str(e)}")
        await update.message.reply_text("⚠️ Произошла ошибка при анализе адреса")

def main():
    app = ApplicationBuilder() \
        .token(TOKEN) \
        .http_version("1.1") \
        .get_updates_http_version("1.1") \
        .pool_timeout(30) \
        .build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запускается...")
    app.run_polling(
        poll_interval=1.0,
        timeout=30,
        drop_pending_updates=True
    )

if __name__ == "__main__":
    asyncio.run(main())
