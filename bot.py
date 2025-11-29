import os
import logging
from threading import Thread
try:
    from flask import Flask
except ImportError:
    Flask = None

from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

# Конфигурация
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8336691136:AAGo_htB8Shysi6AW0p3ZpJvyGtJb8TJF3E')
WEB_PORT = int(os.environ.get('PORT', 10000))

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# ---------- КЛАВИАТУРЫ ----------
def get_main_keyboard():
    """
    Returns the main reply keyboard markup for the bot's primary actions.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Тяга сейчас"), KeyboardButton(text="Моя статистика")],
            [KeyboardButton(text="Сорвался(ась)"), KeyboardButton(text="Настройки")]
        ],
        resize_keyboard=True
    )

def get_intro_keyboard():
    """
    Returns the introductory reply keyboard markup for starting the journey.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="В путь в трезвую жизнь")]
        ],
        resize_keyboard=True
    )

def get_craving_scale_keyboard():
    """
    Returns an inline keyboard for rating craving intensity from 0 to 10.
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("0", callback_data="craving_scale_0"),
            InlineKeyboardButton("1", callback_data="craving_scale_1"),
            InlineKeyboardButton("2", callback_data="craving_scale_2"),
            InlineKeyboardButton("3", callback_data="craving_scale_3"),
            InlineKeyboardButton("4", callback_data="craving_scale_4"),
            InlineKeyboardButton("5", callback_data="craving_scale_5"),
        ],
        [
            InlineKeyboardButton("6", callback_data="craving_scale_6"),
            InlineKeyboardButton("7", callback_data="craving_scale_7"),
            InlineKeyboardButton("8", callback_data="craving_scale_8"),
            InlineKeyboardButton("9", callback_data="craving_scale_9"),
            InlineKeyboardButton("10", callback_data="craving_scale_10"),
        ],
    ])


def get_craving_methods_keyboard():
    """
    Returns an inline keyboard with different coping method options for cravings.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Дыхание", callback_data="craving_method_breath")],
        [InlineKeyboardButton("Стакан воды", callback_data="craving_method_water")],
        [InlineKeyboardButton("Движение/упражнение", callback_data="craving_method_move")],
        [InlineKeyboardButton("Позвонить другу", callback_data="craving_method_call")],
        [InlineKeyboardButton("Переключить внимание", callback_data="craving_method_focus")],
    ])

# ---------- КОМАНДЫ БОТА ----------
async def start(update, context):
    """
    Handles the /start command. Sends a welcome message and intro keyboard.
    """
    logger.info(f"User {update.effective_user.id} started the bot")
    await update.message.reply_text(
        "Привет! Я бот, который помогает работать с алкогольной тягой.\n\n"
        "⚠️ Я не врач и не заменяю лечение.\n"
        "Нажми «В путь в трезвую жизнь», чтобы начать.",
        reply_markup=get_intro_keyboard()
    )

async def start_journey(update, context):
    """
    Handles the start of the sobriety journey and shows the main keyboard.
    """
    logger.info(f"User {update.effective_user.id} started journey")
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
    """
    Sends the user's sobriety statistics.
    """
    logger.info(f"User {update.effective_user.id} requested stats")
    stats_text = """
🎉 ТРЕЗВОСТЬ: 1 ДЕНЬ

💰 Сэкономлено денег: 500 руб
⏰ Сэкономлено времени: 2 часов
📈 Улучшение здоровья: +2%

Ты делаешь огромные шаги! 💪
"""
    await update.message.reply_text(stats_text)

async def craving_handler(update, context):
    """
    Provides help and advice for handling alcohol cravings.
    """
    logger.info(f"User {update.effective_user.id} has craving")
    await update.message.reply_text(
        "🆘 ПОМОЩЬ ПРИ ТЯГЕ\n\n"
        "Оцени, пожалуйста, силу тяги по шкале от 0 до 10.\n"
        "0 — совсем не тянет, 10 — очень сильное желание выпить.\n\n"
        "Нажми на одну из кнопок ниже:",
        reply_markup=get_craving_scale_keyboard()
    )


async def craving_callback(update, context):
    """
    Unified callback handler for craving-related inline buttons.
    Handles:
    - craving_scale_X  (X = 0..10)  -> asks to choose a coping method
    - craving_method_* -> sends detailed description of the chosen method
    """
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    logger.info(f"Callback data received: {data}")

    # --- Scale selection: craving_scale_0..10 ---
    if data.startswith("craving_scale_"):
        try:
            level = int(data.split("_")[-1])
        except (ValueError, IndexError):
            logger.warning(f"Invalid craving scale data: {data}")
            return

        user_id = query.from_user.id if query.from_user else None
        logger.info(f"User {user_id} selected craving level {level}")

        if level <= 3:
            text = (
                f"Ты отметил(а) тягу на уровне {level}/10.\n\n"
                "Тяга сейчас слабая — это хороший знак. Всё равно важно позаботиться о себе.\n"
                "Выбери ниже способ, который хочешь попробовать:"
            )
        elif level <= 7:
            text = (
                f"Ты отметил(а) тягу на уровне {level}/10.\n\n"
                "Тяга уже ощутимая. Давай выберем одно из упражнений, чтобы её снизить.\n"
                "Выбери способ ниже:"
            )
        else:
            text = (
                f"Ты отметил(а) очень сильную тягу: {level}/10.\n\n"
                "Это тяжело, но это состояние пройдет. Сейчас важно сделать хотя бы один маленький шаг.\n"
                "Выбери способ, который готов(а) попробовать прямо сейчас:"
            )

        await query.message.reply_text(
            text,
            reply_markup=get_craving_methods_keyboard()
        )
        return

    # --- Methods selection: craving_method_* ---
    if data.startswith("craving_method_"):
        method_key = data.split("_", 2)[-1]  # "breath", "water", "move", "call", "focus"
        logger.info(f"User {query.from_user.id if query.from_user else 'unknown'} selected method {method_key}")

        if method_key == "breath":
            text = (
                "🧘 Упражнение «Дыхание 4–7–8»\n\n"
                "1. Вдохни через нос на 4 счёта.\n"
                "2. Задержи дыхание на 7 счётов.\n"
                "3. Медленно выдыхай через рот на 8 счётов.\n\n"
                "Сделай так 4 цикла. Это помогает снизить напряжение и сигнализирует мозгу, что опасности нет."
            )
        elif method_key == "water":
            text = (
                "💧 Стакан воды\n\n"
                "Налей стакан холодной воды и выпей его небольшими глотками.\n"
                "Сосредоточься на ощущениях: как вода проходит по горлу, какая она на вкус, какая температура.\n\n"
                "Это переключает внимание и помогает телу почувствовать себя лучше."
            )
        elif method_key == "move":
            text = (
                "🏃 Движение/упражнение\n\n"
                "Выбери любое простое движение: приседания, отжимания, быстрая ходьба по комнате, растяжка.\n"
                "Сделай 10–20 повторений или 3–5 минут движения.\n\n"
                "Тело сбрасывает напряжение, и тяга часто уменьшается."
            )
        elif method_key == "call":
            text = (
                "📞 Позвонить другу\n\n"
                "Позвони человеку, который может поддержать. Скажи честно, что тебе сейчас тяжело.\n"
                "Даже 5 минут разговора могут сильно снизить тягу.\n\n"
                "Если нет подходящего человека — можно написать сообщение самому себе или в дневник."
            )
        elif method_key == "focus":
            text = (
                "🎯 Переключить внимание\n\n"
                "Выбери занятие, которое может увлечь: сериал, игра, книга, музыка, уборка, душ.\n"
                "Поставь таймер на 15–20 минут и полностью уйди в это занятие.\n\n"
                "Обычно к концу этого времени волна тяги заметно снижается."
            )
        else:
            text = "Выбери один из доступных способов борьбы с тягой ниже."

        await query.message.reply_text(
            text,
            reply_markup=get_craving_methods_keyboard()
        )
        return

    # Fallback: unknown callback
    logger.warning(f"Unknown callback data received: {data}")

async def relapse_handler(update, context):
    """
    Handles user relapse events and offers encouragement to start again.
    """
    logger.info(f"User {update.effective_user.id} relapsed")
    await update.message.reply_text(
        "Не осуждаю тебя 🙏\n"
        "Это не конец, а опыт. Ты справишься.\n\n"
        "Нажми «В путь в трезвую жизнь», чтобы начать заново.",
        reply_markup=get_intro_keyboard()
    )

async def handle_message(update, context):
    """
    Handles all text messages from the user and routes to the appropriate handler.
    """
    user_id = update.effective_user.id
    text = update.message.text
    
    logger.info(f"User {user_id} sent: {text}")
    
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
if Flask is not None:
    web_app = Flask(__name__)

    @web_app.route('/')
    def home():
        return "🤖 Бот трезвости работает! Открой Telegram и напиши /start"

    @web_app.route('/health')
    def health():
        return "OK", 200

    def run_web_server():
        """
        Starts the Flask web server for health checks and Render deployment.
        """
        logger.info(f"Starting web server on port {WEB_PORT}")
        web_app.run(host='0.0.0.0', port=WEB_PORT, debug=False)
else:
    web_app = None

    def run_web_server():
        """
        Fallback web server stub when Flask is not installed.
        Does nothing, allowing the bot to run in polling mode only.
        """
        logger.warning("Flask is not installed; web server is disabled.")

# ---------- ОСНОВНАЯ ФУНКЦИЯ ----------
def main():
    """
    Main entry point for initializing and running the Telegram bot and web server.
    """
    logger.info("Starting bot initialization...")
    
    try:
        # Создаем приложение
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Добавляем обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_handler(CallbackQueryHandler(craving_callback))
        
        # Запускаем веб-сервер в отдельном потоке
        web_thread = Thread(target=run_web_server)
        web_thread.daemon = True
        web_thread.start()
        
        # Запускаем бота
        logger.info(f"🤖 Bot started успешно on port {WEB_PORT}")
        logger.info("🌐 Web server is running")
        # Явно разрешаем получать и обрабатывать callback_query (нажатия inline-кнопок)
        application.run_polling(allowed_updates=["message", "callback_query"])
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise

if __name__ == "__main__":
    main()