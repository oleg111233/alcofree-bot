import os
import logging
from threading import Thread
from flask import Flask

from telegram import ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# Конфигурация
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8336691136:AAGo_htB8Shysi6AW0p3ZpJvyGtJb8TJF3E')
WEB_PORT = int(os.environ.get('PORT', 10000))

logging.basicConfig(level=logging.INFO)

# ---------- КЛАВИАТУРЫ ----------
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Тяга сейчас"), KeyboardButton(text="Моя статистика")],
            [KeyboardButton(text="Сорвался(ась)"), KeyboardButton(text="Настройки")]
        ],
        resize_keyboard=True
    )

def get_intro_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="В путь в трезвую жизнь")]
        ],
        resize_keyboard=True
    )

# ---------- КОМАНДЫ БОТА ----------
async def start(update, context):
    await update.message.reply_text(
        "Привет! Я бот, который помогает работать с алкогольной тягой.\n\n"
        "⚠️ Я не врач и не заменяю лечение.\n"
        "Нажми «В путь в трезвую жизнь», чтобы начать.",
        reply_markup=get_intro_keyboard()
    )

async def start_journey(update, context):
    await update.message.reply_text(
        "Отлично! Трекер трезвости запущен. 🎉\n\n"
        "Теперь ты можешь:\n"
        "• Отслеживать дни трезвости\n"
        "• Получать помощь при тяге\n"
        "• Видеть свою статистику\n\n"
        "Используй кнопки ниже:",
        reply_markup=get_main_keyboard()
    )

async def stats_command(update, context):
    stats_text = """
🎉 ТРЕЗВОСТЬ: 1 ДЕНЬ

💰 Сэкономлено денег: 500 руб
⏰ Сэкономлено времени: 2 часов
📈 Улучшение здоровья: +2%

Ты делаешь огромные шаги! 💪
"""
    await update.message.reply_text(stats_text)

async def craving_handler(update, context):
    await update.message.reply_text(
        "🆘 ПОМОЩЬ ПРИ ТЯГЕ\n\n"
        "1. Дыши глубоко - 4 секунды вдох, 4 задержка, 6 выдох\n"
        "2. Выпей воды - стакан холодной воды\n" 
        "3. Позвони другу - поговори 5 минут\n"
        "4. Сделай 10 приседаний - займи тело\n"
        "5. Вспомни причины - почему ты начал этот путь\n\n"
        "Тяга пройдет через 15-20 минут! Ты сильнее! 💪"
    )

async def relapse_handler(update, context):
    await update.message.reply_text(
        "Не осуждаю тебя 🙏\n"
        "Это не конец, а опыт. Ты справишься.\n\n"
        "Нажми «В путь в трезвую жизнь», чтобы начать заново.",
        reply_markup=get_intro_keyboard()
    )

async def handle_message(update, context):
    text = update.message.text
    
    if text == "В путь в трезвую жизнь":
        await start_journey(update, context)
    elif text == "Моя статистика":
        await stats_command(update, context)
    elif text == "Тяга сейчас":
        await craving_handler(update, context)
    elif text == "Сорвался(ась)":
        await relapse_handler(update, context)
    elif text == "Настройки":
        await update.message.reply_text(
            "Настройки:\n"
            "• Трекер трезвости: активен\n"
            "• Ежедневные уведомления: включены\n"
            "• Статистика: собирается\n\n"
            "В будущих версиях здесь можно будет настроить время уведомлений и цели.",
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text("Используй кнопки меню 👇", reply_markup=get_main_keyboard())

# ---------- ВЕБ-СЕРВЕР ДЛЯ RENDER ----------
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "🤖 Бот трезвости работает! Открой Telegram и напиши /start"

@web_app.route('/health')
def health():
    return "OK"

def run_web_server():
    web_app.run(host='0.0.0.0', port=WEB_PORT)

# ---------- ОСНОВНАЯ ФУНКЦИЯ ----------
def main():
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запускаем веб-сервер в отдельном потоке
    web_thread = Thread(target=run_web_server)
    web_thread.daemon = True
    web_thread.start()
    
    # Запускаем бота
    print(f"🤖 Бот запущен на порту {WEB_PORT}")
    print("🌐 Веб-сервер работает")
    application.run_polling()

if __name__ == "__main__":
    main()