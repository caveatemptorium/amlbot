import logging
import os
import asyncio
import aiohttp
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
    level=logging.INFO,
    filename='bot.log'
)
logger = logging.getLogger(__name__)

async def fetch_etherscan(address: str, action: str) -> dict:
    """Запрос к Etherscan API"""
    url = f"https://api.etherscan.io/api?module=account&action={action}&address={address}&tag=latest&apikey={ETHERSCAN_API_KEY}"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as response:
                return await response.json() if response.status == 200 else None
        except Exception as e:
            logger.error(f"Etherscan error: {str(e)}")
            return None

async def check_aml_risks(address: str) -> list:
    """Проверка AML-рисков через несколько источников"""
    risks = []
    
    # 1. Проверка через Etherscan (если есть теги)
    etherscan_data = await fetch_etherscan(address, "getsourcecode")
    if etherscan_data and etherscan_data.get('result'):
        if etherscan_data['result'][0].get('Proxy') == '1':
            risks.append("⚠️ Контракт-прокси")
        if "phish" in etherscan_data['result'][0].get('ContractName', '').lower():
            risks.append("🚨 Возможный фишинг")

    # 2. Проверка через открытые AML-базы (пример)
    try:
        async with aiohttp.ClientSession() as session:
            # Пример запроса к открытой базе AML (замените на реальный API)
            async with session.get(
                f"https://api.amlbot.com/v1/check/{address}",
                timeout=5
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('risk_score', 0) > 70:
                        risks.append(f"🔴 Высокий риск AML ({data['risk_score']}/100)")
    except:
        pass

    # 3. Локальная база рискованных адресов (пример)
    risky_addresses = {
        "0x8576acc5c05d6ce88f4e49bf65bdf0c62f91353c": "❗ Известный мошеннический адрес",
        "0x1da5821544e25c636c1417ba96ade4cf6d2f9b5a": "❗ Фишинг"
    }
    if address.lower() in risky_addresses:
        risks.append(risky_addresses[address.lower()])

    return risks if risks else ["✅ AML-рисков не обнаружено"]

async def analyze_address(address: str) -> str:
    """Полный анализ адреса"""
    try:
        # Базовая информация
        balance_data = await fetch_etherscan(address, "balance")
        contract_data = await fetch_etherscan(address, "getabi")
        tx_data = await fetch_etherscan(address, "txlist")
        
        # Обработка данных
        balance = int(balance_data['result']) / 10**18 if balance_data else 0
        is_contract = contract_data['result'] != "Contract source code not verified" if contract_data else False
        tx_count = len(tx_data['result']) if tx_data and tx_data['status'] == '1' else 0
        
        # AML-проверка
        aml_risks = await check_aml_risks(address)
        
        # Формирование отчета
        report = [
            f"🔍 <b>Анализ адреса</b> <code>{address}</code>",
            f"💰 <b>Баланс:</b> {balance:.4f} ETH",
            f"📜 <b>Контракт:</b> {'✅' if is_contract else '❌'}",
            f"📊 <b>Транзакций:</b> {tx_count}",
            "\n🛡️ <b>AML-проверка:</b>",
            *[f"• {risk}" for risk in aml_risks]
        ]
        
        return "\n".join(report)
    
    except Exception as e:
        logger.error(f"Analysis error: {str(e)}")
        return "⛔ Ошибка анализа адреса"

# Остальные функции без изменений
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ <b>ETH AML Analyzer</b>\n\n"
        "Отправьте Ethereum-адрес (0x...) для проверки\n"
        "Пример: <code>0x1f9090aaE28b8a3dCeaDf281B0F12828e676c326</code>",
        parse_mode="HTML"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        address = update.message.text.strip()
        if not (address.startswith("0x") and len(address) == 42):
            await update.message.reply_text("❌ Неверный формат адреса")
            return
        
        msg = await update.message.reply_text("🔍 Запускаю проверку...")
        result = await analyze_address(address)
        await msg.edit_text(result, parse_mode="HTML")
    
    except Exception as e:
        logger.error(f"Handler error: {str(e)}")
        await update.message.reply_text("🔥 Ошибка обработки запроса")

def main():
    app = ApplicationBuilder() \
        .token(TOKEN) \
        .http_version("1.1") \
        .get_updates_http_version("1.1") \
        .pool_timeout(60) \
        .build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
