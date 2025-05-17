
import json
import random
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# Список возможных причин блокировки
REASONS = [
    "Фишинг",
    "Отмывание денег",
    "Мошенничество",
    "Взломанный кошелек",
    "Незаконные операции",
    "Скам проект",
    "Участие в схеме Понци"
    "Tornado Cash"
]

# Список возможных источников
SOURCES = [
    "Etherscan Blacklist",
    "Chainalysis Report",
    "CertiK Alert",
    "Жалоба пользователя",
    "Внутренняя база",
    "TRM Labs Data",
    "OpenSanctions"
]

async def handle_wallets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик сообщений с кошельками"""
    try:
        # Получаем текст сообщения
        wallets_text = update.message.text
        
        # Разбиваем на отдельные кошельки (предполагаем, что каждый на новой строке)
        wallets = [w.strip() for w in wallets_text.split('\n') if w.strip()]
        
        # Создаем словарь с рандомными причинами
        result = {}
        for wallet in wallets:
            if wallet.startswith('0x') and len(wallet) == 42:
                result[wallet.lower()] = {
                    "reason": random.choice(REASONS),
                    "source": random.choice(SOURCES)
                }
        
        # Форматируем в красивый JSON
        formatted_json = json.dumps(result, indent=4, ensure_ascii=False)
        
        # Отправляем результат
        await update.message.reply_text(f"<pre>{formatted_json}</pre>", parse_mode='HTML')
        
    except Exception as e:
        await update.message.reply_text(f"Ошибка обработки: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное сообщение"""
    await update.message.reply_text(
        "Отправьте список ETH кошельков (каждый с новой строки), "
        "и я верну их в формате JSON с рандомными причинами блокировки.\n\n"
        "Пример:\n"
        "0x8576acc5c05d6ce88f4e49bf65bdf0c62f91353c\n"
        "0x1da5821544e25c636c1417ba96ade4cf6d2f9b5a"
    )

def main():
    """Запуск бота"""
    app = ApplicationBuilder().token("7865332518:AAGeQppEvQeI0cvM8-QAlE1MXc0_voRUjIg").build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_wallets))
    
    app.run_polling()

if __name__ == "__main__":
    main()
