import os
import sqlite3
import json
import logging
from datetime import datetime, date, timedelta
from threading import Thread
from flask import Flask

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackContext

# Конфигурация
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8336691136:AAGo_htB8Shysi6AW0p3ZpJvyGtJb8TJF3E')
WEB_PORT = int(os.environ.get('PORT', 10000))

logging.basicConfig(level=logging.INFO)

# ---------- БАЗА ДАННЫХ ----------
DB_PATH = "alcofree.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row

def init_db():
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                created_at TEXT,
                last_sober_date TEXT,
                streak INTEGER,
                goal TEXT,
                sober_since_date TEXT,
                weekly_alcohol_spend REAL,
                weekly_alcohol_hours REAL,
                morning_time TEXT,
                evening_time TEXT,
                last_morning_sent_date TEXT,
                last_evening_sent_date TEXT,
                onboarding_completed INTEGER DEFAULT 0,
                motivation TEXT,
                triggers TEXT,
                goals TEXT,
                reasons TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT
            )
        """)

def row_to_user(row):
    if row is None:
        return None
    d = dict(row)
    
    # Конвертация дат
    for field in ['last_sober_date', 'sober_since_date', 'last_morning_sent_date', 'last_evening_sent_date']:
        if d.get(field):
            d[field] = date.fromisoformat(d[field])
        else:
            d[field] = None
    
    # Конвертация JSON полей
    for json_field in ['triggers', 'goals', 'reasons']:
        if d.get(json_field):
            try:
                d[json_field] = json.loads(d[json_field])
            except:
                d[json_field] = []
        else:
            d[json_field] = []
    
    return d

def get_or_create_user(user_id):
    row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if row:
        return row_to_user(row)
    
    # Создаем нового пользователя
    now = datetime.now().isoformat()
    user_data = {
        'user_id': user_id,
        'created_at': now,
        'last_sober_date': None,
        'streak': 0,
        'goal': 'не задана',
        'sober_since_date': None,
        'weekly_alcohol_spend': None,
        'weekly_alcohol_hours': None,
        'morning_time': None,
        'evening_time': None,
        'last_morning_sent_date': None,
        'last_evening_sent_date': None,
        'onboarding_completed': 0,
        'motivation': '',
        'triggers': '[]',
        'goals': '[]',
        'reasons': '[]'
    }
    
    with conn:
        conn.execute("""
            INSERT INTO users VALUES (
                :user_id, :created_at, :last_sober_date, :streak, :goal,
                :sober_since_date, :weekly_alcohol_spend, :weekly_alcohol_hours,
                :morning_time, :evening_time, :last_morning_sent_date, :last_evening_sent_date,
                :onboarding_completed, :motivation, :triggers, :goals, :reasons
            )
        """, user_data)
    
    return row_to_user(dict(user_data))

def update_user(user_id, **fields):
    if not fields:
        return
    
    set_clause = ", ".join([f"{k} = ?" for k in fields.keys()])
    values = list(fields.values())
    values.append(user_id)
    
    # Конвертация специальных типов
    converted_values = []
    for v in fields.values():
        if isinstance(v, (datetime, date)):
            converted_values.append(v.isoformat())
        elif isinstance(v, (list, dict)):
            converted_values.append(json.dumps(v, ensure_ascii=False))
        else:
            converted_values.append(v)
    
    converted_values.append(user_id)
    
    with conn:
        conn.execute(f"UPDATE users SET {set_clause} WHERE user_id = ?", converted_values)

# ---------- КЛАВИАТУРЫ ----------
def get_main_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("Тяга сейчас"), KeyboardButton("Моя статистика")],
        [KeyboardButton("Мои причины бросить"), KeyboardButton("Мои цели")],
        [KeyboardButton("Дневник")],
        [KeyboardButton("Сорвался(ась)"), KeyboardButton("Настройки")]
    ], resize_keyboard=True)

def get_intro_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("В путь в трезвую жизнь")]
    ], resize_keyboard=True)

# ---------- КОМАНДЫ БОТА ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_or_create_user(update.effective_user.id)
    if user['onboarding_completed']:
        await update.message.reply_text(
            "С возвращением! Используй меню ниже.",
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text(
            "Привет! Я бот, который помогает работать с алкогольной тягой.\n\n"
            "⚠️ Я не врач и не заменяю лечение.\n"
            "Нажми «В путь в трезвую жизнь», чтобы настроить трекер.",
            reply_markup=get_intro_keyboard()
        )

async def start_journey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_or_create_user(update.effective_user.id)
    update_user(user['user_id'], waiting_for_sober_since=1)
    await update.message.reply_text("Начнём. С какой даты ты не пьёшь? Формат ДД.ММ.ГГГГ")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_or_create_user(update.effective_user.id)
    
    if not user['sober_since_date']:
        await update.message.reply_text("Сначала настрой трекер через «В путь в трезвую жизнь».")
        return
    
    days_sober = (date.today() - user['sober_since_date']).days
    money_saved = days_sober * (user['weekly_alcohol_spend'] or 0) / 7
    time_saved = days_sober * (user['weekly_alcohol_hours'] or 0) / 7
    
    stats_text = f"""
🎉 ТРЕЗВОСТЬ: {days_sober} ДНЕЙ

💰 Сэкономлено денег: {money_saved:.0f} руб
⏰ Сэкономлено времени: {time_saved:.1f} часов
📈 Улучшение здоровья: +{min(days_sober * 2, 100)}%

Ты делаешь огромные шаги! 💪
"""
    await update.message.reply_text(stats_text)

# ---------- ОБРАБОТЧИКИ СООБЩЕНИЙ ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_or_create_user(update.effective_user.id)
    text = update.message.text
    
    if text == "В путь в трезвую жизнь":
        await start_journey(update, context)
    elif text == "Моя статистика":
        await stats_command(update, context)
    elif text == "Тяга сейчас":
        await update.message.reply_text(
            "🆘 ПОМОЩЬ ПРИ ТЯГЕ\n\n"
            "1. Дыши глубоко - 4 секунды вдох, 4 задержка, 6 выдох\n"
            "2. Выпей воды - стакан холодной воды\n" 
            "3. Позвони другу - поговори 5 минут\n"
            "4. Сделай 10 приседаний - займи тело\n"
            "5. Вспомни причины - почему ты начал этот путь\n\n"
            "Тяга пройдет через 15-20 минут! Ты сильнее! 💪"
        )
    else:
        await update.message.reply_text("Используй кнопки меню 👇", reply_markup=get_main_keyboard())

# ---------- ВЕБ-СЕРВЕР ДЛЯ RENDER ----------
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "🤖 Бот трезвости работает! /start"

def run_web_server():
    web_app.run(host='0.0.0.0', port=WEB_PORT)

# ---------- ОСНОВНАЯ ФУНКЦИЯ ----------
def main():
    # Инициализация БД
    init_db()
    
    # Создаем приложение бота
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
    application.run_polling()

if __name__ == "__main__":
    main()