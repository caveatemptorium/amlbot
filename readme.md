# AML Ethereum Analyzer Bot

## Функционал
- Полный AML-анализ Ethereum-адресов
- Управление чёрным списком
- Проверка через Etherscan API
- Детализированные отчёты

## Технологии
- Python 3.10+
- python-telegram-bot 20+
- Асинхронные запросы (aiohttp)
- Безопасное хранение данных

## Установка
1. `pip install -r requirements.txt`
2. Создать .env файл
   `TELEGRAM_TOKEN=ваш_токен_из_телеграмма # Токен от @BotFather`
   `ETHERSCAN_API_KEY=ваш_токен_из_etherscan  # Ключ Etherscan`
   `SECRET_PHRASE=ваша_секретная_фраза #Секретная фраза для доступа в ЧС`
6. Запустить `python bot.py`
