import logging
import os
import asyncio
import aiohttp
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
    CallbackQueryHandler
)
from dotenv import load_dotenv

# Состояния для ConversationHandler
ENTER_PHRASE, CHOOSE_ACTION, ENTER_ADDRESS, ENTER_REASON, CONFIRM_REMOVE = range(5)

# Настройки
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
SECRET_PHRASE = os.getenv("SECRET_PHRASE", "мойсекрет123")
BLACKLIST_FILE = "blacklist.json"

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def load_blacklist():
    """Загрузка чёрного списка"""
    try:
        if not os.path.exists(BLACKLIST_FILE):
            with open(BLACKLIST_FILE, 'w') as f:
                json.dump({}, f)
            return {}
        
        with open(BLACKLIST_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки blacklist.json: {str(e)}")
        return {}

def save_blacklist(data):
    """Сохранение чёрного списка"""
    try:
        with open(BLACKLIST_FILE, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения blacklist.json: {str(e)}")
        return False

async def generate_aml_report(address: str) -> str:
    """Генерация подробного AML-отчёта"""
    try:
        address_lower = address.lower()
        blacklist = load_blacklist()
        
        # Заголовок отчёта
        report = [
            "🔍 <b>Отчёт AML-анализа</b> 🔍",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"🆔 <b>Адрес:</b> <code>{address}</code>",
            ""
        ]
        
        # Раздел чёрного списка
        if address_lower in blacklist:
            reason = blacklist[address_lower].get('reason', 'Не указана')
            source = blacklist[address_lower].get('source', 'Неизвестный источник')
            report.extend([
                "⚡ <b>Статус в чёрном списке:</b> 🔴 <b>ВЫСОКИЙ РИСК</b>",
                "├─ 🚫 <b>Причина:</b> " + reason,
                "└─ 📡 <b>Источник:</b> " + source,
                ""
            ])
        else:
            report.append("⚡ <b>Статус в чёрном списке:</b> 🟢 <b>ЧИСТЫЙ</b>\n")
        
        # Раздел данных Etherscan
        if ETHERSCAN_API_KEY:
            async with aiohttp.ClientSession() as session:
                # Баланс
                balance_url = f"https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest&apikey={ETHERSCAN_API_KEY}"
                async with session.get(balance_url) as resp:
                    data = await resp.json()
                    balance = int(data['result']) / 10**18 if data.get('status') == '1' else 0
                
                # Транзакции
                tx_url = f"https://api.etherscan.io/api?module=account&action=txlist&address={address}&startblock=0&endblock=99999999&apikey={ETHERSCAN_API_KEY}"
                async with session.get(tx_url) as resp:
                    tx_data = await resp.json()
                    tx_count = len(tx_data.get('result', []))
                
                # Контракт
                contract_url = f"https://api.etherscan.io/api?module=contract&action=getabi&address={address}&apikey={ETHERSCAN_API_KEY}"
                async with session.get(contract_url) as resp:
                    contract_data = await resp.json()
                    is_contract = contract_data.get('status') == '1' and contract_data['result'] != 'Contract source code not verified'

            report.extend([
                "📊 <b>Анализ блокчейна:</b>",
                "├─ 💰 <b>Баланс:</b> {:.4f} ETH".format(balance),
                "├─ 🔄 <b>Транзакции:</b> {}".format(tx_count),
                "└─ 📜 <b>Тип:</b> {}".format("Смарт-контракт" if is_contract else "Внешний аккаунт (EOA)"),
                ""
            ])
        else:
            report.append("ℹ️ <i>Данные Etherscan недоступны (отсутствует API ключ)</i>\n")
        
        # Рекомендации
        if address_lower in blacklist:
            report.extend([
                "🚨 <b>Оценка рисков:</b>",
                "├─ ⚠️ <b>Обнаружен высокий риск</b>",
                "└─ 🔒 <b>Рекомендация:</b> Избегайте взаимодействия",
                ""
            ])
        else:
            report.extend([
                "✅ <b>Оценка рисков:</b>",
                "└─ 🟢 <b>Риски не обнаружены</b>",
                ""
            ])
        
        report.append("━━━━━━━━━━━━━━━━━━━━━━")
        report.append("🛡️ <i>Отчёт сгенерирован AML Security Bot</i>")
        
        return "\n".join(report)

    except Exception as e:
        logger.error(f"Ошибка генерации отчёта: {str(e)}")
        return "⚠️ <b>Ошибка генерации отчёта</b>\nПопробуйте позже."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное сообщение"""
    welcome_msg = """
✨ <b>Добро пожаловать в AML Security Bot</b> ✨

🔐 <i>Продвинутый инструмент анализа блокчейн-адресов</i>

📌 <b>Как использовать:</b>
Отправьте любой Ethereum-адрес (начинается с 0x)
Получите детальный отчёт о кошельке и рисках AML/CFT

🛡️ <b>Возможности:</b>
• Мониторинг чёрных списков
• Получение данных о балансе кошелька
• Количество транзакций кошелька
• Анализ транзакций
• Оценка рисков
• Определение смарт-контрактов

<i>Пример адреса:</i> <code>0x1f9090aaE28b8a3dCeaDf281B0F12828e676c326</code>
"""
    await update.message.reply_text(welcome_msg, parse_mode="HTML")

async def start_blacklist_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало управления чёрным списком"""
    await update.message.reply_text(
        "🔒 <b>Управление чёрным списком</b>\n\n"
        "Введите <b>кодовую фразу</b> для продолжения:",
        parse_mode="HTML"
    )
    return ENTER_PHRASE

async def check_phrase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка кодовой фразы"""
    user_phrase = update.message.text.strip()
    
    if user_phrase != SECRET_PHRASE:
        await update.message.reply_text("❌ <b>Неверная кодовая фраза!</b>\nОперация отменена.", parse_mode="HTML")
        return ConversationHandler.END
    
    context.user_data['phrase'] = user_phrase
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить адрес", callback_data='add')],
        [InlineKeyboardButton("➖ Удалить адрес", callback_data='remove')],
        [InlineKeyboardButton("❌ Отмена", callback_data='cancel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "✅ <b>Кодовая фраза верна</b>\n\n"
        "Выберите действие:",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )
    return CHOOSE_ACTION

async def handle_action_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора действия"""
    query = update.callback_query
    await query.answer()
    
    action = query.data
    
    if action == 'cancel':
        await query.edit_message_text("❌ Операция отменена")
        return ConversationHandler.END
    elif action == 'add':
        await query.edit_message_text(
            "📥 <b>Добавление в чёрный список</b>\n\n"
            "Введите <b>ETH-адрес</b> (начинается с 0x, 42 символа):",
            parse_mode="HTML"
        )
        return ENTER_ADDRESS
    elif action == 'remove':
        blacklist = load_blacklist()
        if not blacklist:
            await query.edit_message_text("ℹ️ Чёрный список пуст")
            return ConversationHandler.END
            
        await query.edit_message_text(
            "📤 <b>Удаление из чёрного списка</b>\n\n"
            "Введите <b>ETH-адрес</b> для удаления:",
            parse_mode="HTML"
        )
        return CONFIRM_REMOVE

async def check_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка адреса для добавления"""
    blacklist = load_blacklist()
    address = update.message.text.strip()
    
    if not (address.startswith('0x') and len(address) == 42):
        await update.message.reply_text("❌ <b>Неверный формат адреса!</b>\nПопробуйте снова или отправьте /cancel", parse_mode="HTML")
        return ENTER_ADDRESS
    
    address_lower = address.lower()
    
    if address_lower in blacklist:
        reason = blacklist[address_lower].get('reason', 'причина не указана')
        await update.message.reply_text(
            f"⚠️ <b>Адрес уже в чёрном списке</b>\n"
            f"Текущая причина: {reason}\n\n"
            "Операция отменена.",
            parse_mode="HTML"
        )
        return ConversationHandler.END
    
    context.user_data['address'] = address_lower
    await update.message.reply_text(
        "📝 Введите <b>причину</b> добавления в чёрный список:",
        parse_mode="HTML"
    )
    return ENTER_REASON

async def save_to_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранение адреса в чёрный список"""
    blacklist = load_blacklist()
    reason = update.message.text.strip()
    address = context.user_data['address']
    user = update.effective_user
    
    blacklist[address] = {
        'reason': reason,
        'source': "Ручное добавление",
        'added_by': user.id,
        'username': user.username,
        'date': str(asyncio.get_event_loop().time())
    }
    
    if save_blacklist(blacklist):
        await update.message.reply_text(
            f"✅ <b>Адрес добавлен в чёрный список!</b>\n\n"
            f"<code>{address}</code>\n"
            f"📝 Причина: {reason}",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("❌ Ошибка сохранения")
    
    return ConversationHandler.END

async def remove_from_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаление адреса из чёрного списка"""
    blacklist = load_blacklist()
    address = update.message.text.strip().lower()
    
    if address not in blacklist:
        await update.message.reply_text("❌ Адрес не найден в чёрном списке")
        return ConversationHandler.END
    
    removed_entry = blacklist.pop(address)
    
    if save_blacklist(blacklist):
        await update.message.reply_text(
            f"✅ <b>Адрес удалён из чёрного списка!</b>\n\n"
            f"<code>{address}</code>\n"
            f"🗑 Была причина: {removed_entry.get('reason', 'не указана')}",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("❌ Ошибка сохранения")
    
    return ConversationHandler.END

async def handle_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка запроса анализа адреса"""
    try:
        address = update.message.text.strip()
        
        if not (address.startswith("0x") and len(address) == 42):
            await update.message.reply_text(
                "❌ <b>Неверный формат адреса</b>\n"
                "Ethereum-адрес должен:\n"
                "• Начинаться с 0x\n"
                "• Содержать 42 символа\n"
                "• Пример: <code>0x1f9090aaE28b8a3dCeaDf281B0F12828e676c326</code>",
                parse_mode="HTML"
            )
            return
        
        msg = await update.message.reply_text("🔄 <i>Анализируем адрес...</i>", parse_mode="HTML")
        report = await generate_aml_report(address)
        await msg.edit_text(report, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка обработки адреса: {str(e)}")
        await update.message.reply_text(
            "⚠️ <b>Сервис временно недоступен</b>\n"
            "Высокая нагрузка. Пожалуйста, попробуйте позже.",
            parse_mode="HTML"
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена операции"""
    await update.message.reply_text("❌ Операция отменена")
    return ConversationHandler.END

def main():
    # Создаём файл blacklist.json если его нет
    if not os.path.exists(BLACKLIST_FILE):
        with open(BLACKLIST_FILE, 'w') as f:
            json.dump({}, f)
        logger.info("Создан новый файл чёрного списка")

    app = ApplicationBuilder().token(TOKEN).build()
    
    # Обработчик диалога для чёрного списка
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('blacklist', start_blacklist_management)],
        states={
            ENTER_PHRASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_phrase)],
            CHOOSE_ACTION: [CallbackQueryHandler(handle_action_choice)],
            ENTER_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_address)],
            ENTER_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_to_blacklist)],
            CONFIRM_REMOVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_from_blacklist)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Регистрация обработчиков
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_address))
    
    logger.info("Запуск AML Security Bot...")
    app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
