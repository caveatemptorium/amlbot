import os
import json
import random
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()
TOKEN = os.getenv("7865332518:AAGeQppEvQeI0cvM8-QAlE1MXc0_voRUjIg")

# Возможные причины и источники
REASONS = [
    "Фишинг",
    "Отмывание денег",
    "Мошенничество",
    "Взломанный кошелек",
    "Незаконные операции",
    "Скам проект",
    "Участие в схеме Понци",
    "Tornado Cash"
]

SOURCES = [
    "Etherscan Blacklist",
    "Chainalysis Report",
    "CertiK Alert",
    "Жалоба пользователя",
    "Внутренняя база",
    "TRM Labs Data",
    "OpenSanctions"
]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное сообщение"""
    await update.message.reply_text(
        "🛠️ <b>Генератор чёрного списка</b>\n\n"
        "Отправьте мне <b>txt-файл</b> с адресами (каждый адрес на новой строке), "
        "и я сгенерирую для них JSON для чёрного списка с рандомными причинами.",
        parse_mode="HTML"
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка полученного файла"""
    try:
        # Получаем файл
        file = await context.bot.get_file(update.message.document)
        file_path = f"temp_{update.message.document.file_name}"
        await file.download_to_drive(file_path)
        
        # Проверяем расширение
        if not file_path.endswith('.txt'):
            await update.message.reply_text("❌ Пожалуйста, отправьте файл в формате .txt")
            os.remove(file_path)
            return
        
        # Читаем адреса из файла
        with open(file_path, 'r') as f:
            addresses = [line.strip() for line in f.readlines() if line.strip()]
        
        # Проверяем валидность адресов
        valid_addresses = []
        for addr in addresses:
            if addr.startswith('0x') and len(addr) == 42:
                valid_addresses.append(addr.lower())
        
        if not valid_addresses:
            await update.message.reply_text("❌ В файле не найдено валидных ETH-адресов (должны начинаться с 0x и содержать 42 символа)")
            os.remove(file_path)
            return
        
        # Генерируем чёрный список
        blacklist = {}
        for addr in valid_addresses:
            blacklist[addr] = {
                "reason": random.choice(REASONS),
                "source": random.choice(SOURCES),
                "added_by": "generator_bot"
            }
        
        # Сохраняем результат
        output_file = "blacklist_generated.json"
        with open(output_file, 'w') as f:
            json.dump(blacklist, f, indent=2, ensure_ascii=False)
        
        # Отправляем результат
        await update.message.reply_document(
            document=open(output_file, 'rb'),
            caption=f"✅ Сгенерирован чёрный список для {len(valid_addresses)} адресов"
        )
        
        # Удаляем временные файлы
        os.remove(file_path)
        os.remove(output_file)
        
    except Exception as e:
        await update.message.reply_text(f"⚠️ Произошла ошибка: {str(e)}")
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        if 'output_file' in locals() and os.path.exists(output_file):
            os.remove(output_file)

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
