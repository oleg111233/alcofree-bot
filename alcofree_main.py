import asyncio
import logging
import os
import sqlite3
from datetime import datetime, date, timedelta
import json
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackContext


API_TOKEN = "8336691136:AAGo_htB8Shysi6AW0p3ZpJvyGtJb8TJF3E"  # ← вставь свой токен

logging.basicConfig(level=logging.INFO)

# ---------- БАЗА ДАННЫХ ----------

DB_PATH = "alcofree.db"
DUMP_PATH = "alcofree_db_dump.sql"  # текстовый дамп для разработки
ENABLE_TEXT_DUMP = os.getenv("ALCOFREE_TEXT_DUMP", "1") != "0"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row


def init_db():
    with conn:
        conn.execute(
            """
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
                waiting_for_craving_number INTEGER,
                waiting_for_sober_since INTEGER,
                waiting_for_weekly_spend INTEGER,
                waiting_for_weekly_hours INTEGER,
                waiting_for_morning_time INTEGER,
                waiting_for_evening_time INTEGER,
                onboarding_completed INTEGER DEFAULT 0,
                motivation TEXT,
                triggers TEXT,
                waiting_for_diary_entry INTEGER DEFAULT 0,
                waiting_for_goal_motivation INTEGER DEFAULT 0,
                waiting_for_triggers INTEGER DEFAULT 0,
                goals TEXT,
                reasons TEXT,
                waiting_for_goal_add INTEGER DEFAULT 0,
                waiting_for_reasons_add INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
            payload TEXT
            )
            """
        )
        # Добавляем колонку онбординга, если таблица уже существовала
        try:
            conn.execute(
                "ALTER TABLE users ADD COLUMN onboarding_completed INTEGER DEFAULT 0"
            )
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                raise
        # Дополнительные поля для дневника/мотивации/триггеров
        for alter_sql in [
            "ALTER TABLE users ADD COLUMN motivation TEXT",
            "ALTER TABLE users ADD COLUMN triggers TEXT",
            "ALTER TABLE users ADD COLUMN waiting_for_diary_entry INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN waiting_for_goal_motivation INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN waiting_for_triggers INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN goals TEXT",
            "ALTER TABLE users ADD COLUMN reasons TEXT",
            "ALTER TABLE users ADD COLUMN waiting_for_goal_add INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN waiting_for_reasons_add INTEGER DEFAULT 0",
        ]:
            try:
                conn.execute(alter_sql)
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise
    dump_db_to_text()


def create_default_user(user_id: int) -> dict:
    now = datetime.now()
    return {
        "user_id": user_id,
        "created_at": now,
        "last_sober_date": None,
        "streak": 0,
        "goal": "не задана",
        "sober_since_date": None,
        "weekly_alcohol_spend": None,
        "weekly_alcohol_hours": None,
        "morning_time": None,
        "evening_time": None,
        "last_morning_sent_date": None,
        "last_evening_sent_date": None,
        "waiting_for_craving_number": 0,
        "waiting_for_sober_since": 0,
        "waiting_for_weekly_spend": 0,
        "waiting_for_weekly_hours": 0,
        "waiting_for_morning_time": 0,
        "waiting_for_evening_time": 0,
        "onboarding_completed": 0,
        "motivation": "",
        "triggers": [],
        "waiting_for_diary_entry": 0,
        "waiting_for_goal_motivation": 0,
        "waiting_for_triggers": 0,
        "goals": [],
        "reasons": [],
        "waiting_for_goal_add": 0,
        "waiting_for_reasons_add": 0,
    }


def row_to_user(row: sqlite3.Row) -> dict:
    if row is None:
        return None
    d = dict(row)

    if d.get("created_at"):
        d["created_at"] = datetime.fromisoformat(d["created_at"])

    for field in [
        "last_sober_date",
        "sober_since_date",
        "last_morning_sent_date",
        "last_evening_sent_date",
    ]:
        if d.get(field):
            d[field] = date.fromisoformat(d[field])
        else:
            d[field] = None

    for flag in [
        "waiting_for_craving_number",
        "waiting_for_sober_since",
        "waiting_for_weekly_spend",
        "waiting_for_weekly_hours",
        "waiting_for_morning_time",
        "waiting_for_evening_time",
        "onboarding_completed",
        "waiting_for_diary_entry",
        "waiting_for_goal_motivation",
        "waiting_for_triggers",
        "waiting_for_goal_add",
        "waiting_for_reasons_add",
    ]:
        d[flag] = int(d.get(flag) or 0)

    # triggers хранится в json-строке
    if d.get("triggers"):
        try:
            d["triggers"] = json.loads(d["triggers"])
        except Exception:
            d["triggers"] = []
    else:
        d["triggers"] = []

    for col in ["goals", "reasons"]:
        if d.get(col):
            try:
                d[col] = json.loads(d[col])
            except Exception:
                d[col] = []
        else:
            d[col] = []

    return d


def insert_user(user: dict) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO users (
                user_id, created_at, last_sober_date, streak, goal,
                sober_since_date, weekly_alcohol_spend, weekly_alcohol_hours,
                morning_time, evening_time,
                last_morning_sent_date, last_evening_sent_date,
                waiting_for_craving_number, waiting_for_sober_since,
                waiting_for_weekly_spend, waiting_for_weekly_hours,
                waiting_for_morning_time, waiting_for_evening_time,
                onboarding_completed,
                motivation, triggers,
                waiting_for_diary_entry, waiting_for_goal_motivation, waiting_for_triggers,
                goals, reasons, waiting_for_goal_add, waiting_for_reasons_add
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["user_id"],
                user["created_at"].isoformat(),
                None,
                user["streak"],
                user["goal"],
                None,
                user["weekly_alcohol_spend"],
                user["weekly_alcohol_hours"],
                user["morning_time"],
                user["evening_time"],
                None,
                None,
                user["waiting_for_craving_number"],
                user["waiting_for_sober_since"],
                user["waiting_for_weekly_spend"],
                user["waiting_for_weekly_hours"],
                user["waiting_for_morning_time"],
                user["waiting_for_evening_time"],
                user["onboarding_completed"],
                user["motivation"],
                json.dumps(user["triggers"], ensure_ascii=False),
                user["waiting_for_diary_entry"],
                user["waiting_for_goal_motivation"],
                user["waiting_for_triggers"],
                json.dumps(user["goals"], ensure_ascii=False),
                json.dumps(user["reasons"], ensure_ascii=False),
                user["waiting_for_goal_add"],
                user["waiting_for_reasons_add"],
            ),
        )
    dump_db_to_text()


def update_user(user_id: int, **fields) -> None:
    if not fields:
        return

    columns = []
    values = []
    for k, v in fields.items():
        if isinstance(v, datetime):
            v = v.isoformat()
        elif isinstance(v, date):
            v = v.isoformat()
        elif isinstance(v, bool):
            v = int(v)
        elif k in {"triggers", "goals", "reasons"} and isinstance(v, (list, tuple)):
            v = json.dumps(list(v), ensure_ascii=False)

        columns.append(f"{k} = ?")
        values.append(v)

    values.append(user_id)

    sql = f"UPDATE users SET {', '.join(columns)} WHERE user_id = ?"
    with conn:
        conn.execute(sql, values)
    dump_db_to_text()


def get_or_create_user(user_id: int) -> dict:
    row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if row:
        return row_to_user(row)
    user = create_default_user(user_id)
    insert_user(user)
    return user


def get_all_users_with_reminders() -> list:
    rows = conn.execute(
        """SELECT * FROM users
           WHERE morning_time IS NOT NULL OR evening_time IS NOT NULL"""
    ).fetchall()
    return [row_to_user(r) for r in rows]


def dump_db_to_text():
    """Сохраняет текстовый дамп базы (для разработки)."""
    if not ENABLE_TEXT_DUMP:
        return
    try:
        with open(DUMP_PATH, "w", encoding="utf-8") as f:
            for line in conn.iterdump():
                f.write(f"{line}\n")
    except Exception as e:
        logging.warning("Не удалось сделать текстовый дамп БД: %s", e)


# --- Полный сброс статистики прогресса пользователя (серия, даты, история событий) ---
def reset_user_stats(user_id: int) -> None:
    """
    Полный сброс статистики прогресса для пользователя:
    - обнуляем серию;
    - убираем даты трезвости;
    - очищаем историю событий.
    Настройки трекера (weekly_*) и напоминаний сохраняем.
    """
    with conn:
        conn.execute(
            """
            UPDATE users
            SET last_sober_date = NULL,
                streak = 0,
                sober_since_date = NULL,
                last_morning_sent_date = NULL,
                last_evening_sent_date = NULL
            WHERE user_id = ?
            """,
            (user_id,),
        )
        conn.execute(
            "DELETE FROM events WHERE user_id = ?",
            (user_id,),
        )
    dump_db_to_text()


def reset_tracker_settings(user_id: int) -> None:
    """Сбрасываем настройки трекера и связанные флаги."""
    with conn:
        conn.execute(
            """
            UPDATE users
            SET sober_since_date = NULL,
                weekly_alcohol_spend = NULL,
                weekly_alcohol_hours = NULL,
                goal = 'не задана',
                waiting_for_craving_number = 0,
                waiting_for_sober_since = 0,
                waiting_for_weekly_spend = 0,
                waiting_for_weekly_hours = 0,
                onboarding_completed = 0,
                motivation = '',
                triggers = NULL,
                goals = NULL,
                reasons = NULL,
                waiting_for_goal_add = 0,
                waiting_for_reasons_add = 0,
                waiting_for_goal_motivation = 0,
                waiting_for_triggers = 0
            WHERE user_id = ?
            """,
            (user_id,),
        )
    dump_db_to_text()


def reset_reminders(user_id: int) -> None:
    """Сбрасываем настройки напоминаний и связанные метки отправки."""
    with conn:
        conn.execute(
            """
            UPDATE users
            SET morning_time = NULL,
                evening_time = NULL,
                last_morning_sent_date = NULL,
                last_evening_sent_date = NULL,
                waiting_for_morning_time = 0,
                waiting_for_evening_time = 0
            WHERE user_id = ?
            """,
            (user_id,),
        )
    dump_db_to_text()


def log_event(user_id: int, event_type: str, payload: Optional[dict] = None) -> None:
    now = datetime.now().isoformat()
    payload_json = json.dumps(payload, ensure_ascii=False) if payload else None
    with conn:
        conn.execute(
            """
            INSERT INTO events (user_id, created_at, event_type, payload)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, now, event_type, payload_json),
        )
    dump_db_to_text()


def reset_waiting_flags(user: dict):
    flags = {
        "waiting_for_craving_number": 0,
        "waiting_for_sober_since": 0,
        "waiting_for_weekly_spend": 0,
        "waiting_for_weekly_hours": 0,
        "waiting_for_morning_time": 0,
        "waiting_for_evening_time": 0,
        "waiting_for_diary_entry": 0,
        "waiting_for_goal_motivation": 0,
        "waiting_for_triggers": 0,
        "waiting_for_goal_add": 0,
        "waiting_for_reasons_add": 0,
    }
    update_user(user["user_id"], **flags)
    for k, v in flags.items():
        user[k] = v


# ---------- БОТ ----------

bot = Bot(token=API_TOKEN)
dp = Dispatcher()


def get_intro_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="В путь в трезвую жизнь")]],
        resize_keyboard=True,
    )


def get_settings_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Настроить трекер")],
            [KeyboardButton(text="Настроить напоминания")],
            [KeyboardButton(text="В главное меню")],
        ],
        resize_keyboard=True,
    )


def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Тяга сейчас"),
             KeyboardButton(text="Моя статистика")],

            [KeyboardButton(text="Мои причины бросить"),
             KeyboardButton(text="Мои цели")],

            [KeyboardButton(text="Дневник")],

            [KeyboardButton(text="Сорвался(ась)"),
             KeyboardButton(text="Настройки")],
        ],
        resize_keyboard=True,
    )


@dp.message(CommandStart())
async def cmd_start(message: Message):
    user = get_or_create_user(message.from_user.id)
    if user.get("onboarding_completed"):
        return await message.answer(
            "С возвращением! Используй меню ниже.",
            reply_markup=get_main_keyboard(),
        )

    text = (
        "Привет! Я бот, который помогает работать с алкогольной тягой.\n\n"
        "⚠️ Я не врач и не заменяю лечение.\n"
        "При тяжёлых симптомах — вызывай скорую.\n\n"
        "Нажми «В путь в трезвую жизнь», чтобы сразу настроить трекер и напоминания, "
        "после чего откроется главное меню."
    )
    await message.answer(text, reply_markup=get_intro_keyboard())


@dp.message(F.text == "В путь в трезвую жизнь")
async def start_journey(message: Message):
    user = get_or_create_user(message.from_user.id)
    reset_waiting_flags(user)
    update_user(
        user["user_id"],
        onboarding_completed=0,
        waiting_for_sober_since=1,
    )
    user["onboarding_completed"] = 0
    user["waiting_for_sober_since"] = 1
    await message.answer("Начнём. С какой даты ты не пьёшь? Формат ДД.ММ.ГГГГ")


# === Настройки ===

def build_settings_message(user: dict) -> str:
    parts = []

    if user.get("sober_since_date"):
        tracker = f"Трезвость с {user['sober_since_date'].strftime('%d.%m.%Y')}"
        if user.get("weekly_alcohol_spend") is not None:
            tracker += f", расход было: {user['weekly_alcohol_spend']} в неделю"
        if user.get("weekly_alcohol_hours") is not None:
            tracker += f", времени уходило: {user['weekly_alcohol_hours']} ч/нед"
        parts.append(f"Трекер: {tracker}")
    else:
        parts.append("Трекер: не настроен")

    if user.get("morning_time") or user.get("evening_time"):
        reminders = "Напоминания: "
        if user.get("morning_time"):
            reminders += f"утро {user['morning_time']} "
        if user.get("evening_time"):
            reminders += f"вечер {user['evening_time']}"
        parts.append(reminders.strip())
    else:
        parts.append("Напоминания: выключены")

    if user.get("goal") and user["goal"] != "не задана":
        parts.append(f"Цель: {user['goal']}")
    if user.get("motivation"):
        parts.append(f"Мотивация: {user['motivation']}")
    if user.get("triggers"):
        parts.append("Триггеры: " + ", ".join(user["triggers"]))
    if user.get("goals"):
        parts.append("Цели: " + ", ".join(user["goals"]))
    if user.get("reasons"):
        parts.append("Причины бросить: " + ", ".join(user["reasons"]))

    return "\n".join(parts)


@dp.message(F.text == "Настройки")
async def settings_menu(message: Message):
    user = get_or_create_user(message.from_user.id)
    if not user.get("onboarding_completed"):
        return await message.answer(
            "Сначала пройди начальную настройку — нажми «В путь в трезвую жизнь».",
            reply_markup=get_intro_keyboard(),
        )
    reset_waiting_flags(user)
    await message.answer(
        f"Текущие настройки:\n{build_settings_message(user)}",
        reply_markup=get_settings_keyboard(),
    )


@dp.message(F.text == "В главное меню")
async def back_to_main(message: Message):
    user = get_or_create_user(message.from_user.id)
    if not user.get("onboarding_completed"):
        return await message.answer(
            "Сначала завершим настройку: нажми «В путь в трезвую жизнь» и ответь на вопросы.",
            reply_markup=get_intro_keyboard(),
        )
    reset_waiting_flags(user)
    await message.answer("Возвращаю главное меню.", reply_markup=get_main_keyboard())


# === Дневник / Цель / Триггеры ===

@dp.message(F.text == "Дневник")
async def diary_start(message: Message):
    user = get_or_create_user(message.from_user.id)
    if not user.get("onboarding_completed"):
        return await message.answer(
            "Сначала настрой трекер и напоминания — нажми «В путь в трезвую жизнь».",
            reply_markup=get_intro_keyboard(),
        )
    reset_waiting_flags(user)
    rows = conn.execute(
        """
        SELECT created_at, payload FROM events
        WHERE user_id=? AND event_type='diary'
        ORDER BY created_at DESC LIMIT 10
        """,
        (user["user_id"],),
    ).fetchall()
    entries = []
    for r in rows:
        try:
            ts = datetime.fromisoformat(r["created_at"])
            payload = json.loads(r["payload"] or "{}")
            txt = payload.get("text", "")
            entries.append(f"{ts.strftime('%d.%m.%Y %H:%M')} — {txt}")
        except Exception:
            continue
    entries_text = "\n".join(entries) if entries else "Записей пока нет."
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Добавить запись")],
            [KeyboardButton(text="Удалить записи")],
            [KeyboardButton(text="В главное меню")],
        ],
        resize_keyboard=True,
    )
    await message.answer(f"Последние записи:\n{entries_text}\n\nВыбери действие.", reply_markup=kb)


@dp.message(F.text == "Добавить запись")
async def diary_add_entry(message: Message):
    user = get_or_create_user(message.from_user.id)
    if not user.get("onboarding_completed"):
        return await message.answer(
            "Сначала настрой трекер и напоминания — нажми «В путь в трезвую жизнь».",
            reply_markup=get_intro_keyboard(),
        )
    reset_waiting_flags(user)
    update_user(user["user_id"], waiting_for_diary_entry=1)
    user["waiting_for_diary_entry"] = 1
    await message.answer("Напиши запись в дневник. Чтобы отменить, отправь «отмена».")


@dp.message(F.text == "Удалить записи")
async def diary_delete_entries(message: Message):
    user = get_or_create_user(message.from_user.id)
    if not user.get("onboarding_completed"):
        return await message.answer(
            "Сначала настрой трекер и напоминания — нажми «В путь в трезвую жизнь».",
            reply_markup=get_intro_keyboard(),
        )
    reset_waiting_flags(user)
    with conn:
        conn.execute("DELETE FROM events WHERE user_id=? AND event_type='diary'", (user["user_id"],))
    dump_db_to_text()
    await message.answer("Все записи дневника удалены.", reply_markup=get_main_keyboard())


def format_list(items: list, empty_text: str) -> str:
    if not items:
        return empty_text
    return "\n".join(f"• {it}" for it in items)


@dp.message(F.text == "Мои цели")
async def goal_motivation(message: Message):
    user = get_or_create_user(message.from_user.id)
    if not user.get("onboarding_completed"):
        return await message.answer(
            "Сначала настрой трекер и напоминания — нажми «В путь в трезвую жизнь».",
            reply_markup=get_intro_keyboard(),
        )
    reset_waiting_flags(user)
    goals_text = format_list(user.get("goals"), "Цели пока не добавлены.")
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Добавить цель")],
            [KeyboardButton(text="Удалить цели")],
            [KeyboardButton(text="В главное меню")],
        ],
        resize_keyboard=True,
    )
    await message.answer(
        f"Твои цели:\n{goals_text}\n\nВыбери действие.",
        reply_markup=kb,
    )


@dp.message(F.text == "Добавить цель")
async def add_goal(message: Message):
    user = get_or_create_user(message.from_user.id)
    if not user.get("onboarding_completed"):
        return await message.answer(
            "Сначала настрой трекер и напоминания — нажми «В путь в трезвую жизнь».",
            reply_markup=get_intro_keyboard(),
        )
    reset_waiting_flags(user)
    update_user(user["user_id"], waiting_for_goal_add=1)
    user["waiting_for_goal_add"] = 1
    await message.answer("Напиши цель. Чтобы отменить, отправь «отмена».")


@dp.message(F.text == "Удалить цели")
async def delete_goals(message: Message):
    user = get_or_create_user(message.from_user.id)
    if not user.get("onboarding_completed"):
        return await message.answer(
            "Сначала настрой трекер и напоминания — нажми «В путь в трезвую жизнь».",
            reply_markup=get_intro_keyboard(),
        )
    update_user(user["user_id"], goals=[])
    user["goals"] = []
    await message.answer("Цели удалены.", reply_markup=get_main_keyboard())


@dp.message(F.text == "Триггеры")
async def triggers_handler(message: Message):
    user = get_or_create_user(message.from_user.id)
    if not user.get("onboarding_completed"):
        return await message.answer(
            "Сначала настрой трекер и напоминания — нажми «В путь в трезвую жизнь».",
            reply_markup=get_intro_keyboard(),
        )
    reset_waiting_flags(user)
    update_user(user["user_id"], waiting_for_triggers=1)
    user["waiting_for_triggers"] = 1
    current = ", ".join(user.get("triggers") or [])
    prefix = f"Сейчас: {current}\n\n" if current else ""
    await message.answer(
        f"{prefix}Пришли список триггеров через запятую (заменю список целиком).\n"
        "Чтобы отменить, отправь «отмена».",
    )


@dp.message(F.text == "Мои причины бросить")
async def reasons_menu(message: Message):
    user = get_or_create_user(message.from_user.id)
    if not user.get("onboarding_completed"):
        return await message.answer(
            "Сначала настрой трекер и напоминания — нажми «В путь в трезвую жизнь».",
            reply_markup=get_intro_keyboard(),
        )
    reset_waiting_flags(user)
    reasons_text = format_list(user.get("reasons"), "Причины пока не добавлены.")
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Добавить причину")],
            [KeyboardButton(text="Удалить причины")],
            [KeyboardButton(text="В главное меню")],
        ],
        resize_keyboard=True,
    )
    await message.answer(
        f"Твои причины бросить:\n{reasons_text}\n\nВыбери действие.",
        reply_markup=kb,
    )


@dp.message(F.text == "Добавить причину")
async def add_reason(message: Message):
    user = get_or_create_user(message.from_user.id)
    if not user.get("onboarding_completed"):
        return await message.answer(
            "Сначала настрой трекер и напоминания — нажми «В путь в трезвую жизнь».",
            reply_markup=get_intro_keyboard(),
        )
    reset_waiting_flags(user)
    update_user(user["user_id"], waiting_for_reasons_add=1)
    user["waiting_for_reasons_add"] = 1
    await message.answer("Напиши причину бросить. Чтобы отменить, отправь «отмена».")


@dp.message(F.text == "Удалить причины")
async def delete_reasons(message: Message):
    user = get_or_create_user(message.from_user.id)
    if not user.get("onboarding_completed"):
        return await message.answer(
            "Сначала настрой трекер и напоминания — нажми «В путь в трезвую жизнь».",
            reply_markup=get_intro_keyboard(),
        )
    update_user(user["user_id"], reasons=[])
    user["reasons"] = []
    await message.answer("Причины удалены.", reply_markup=get_main_keyboard())


# === Моя статистика ===

@dp.message(F.text == "Моя статистика")
async def stats_button(message: Message):
    user = get_or_create_user(message.from_user.id)
    if not user.get("onboarding_completed"):
        return await message.answer(
            "Сначала настроим трекер и напоминания — нажми «В путь в трезвую жизнь».",
            reply_markup=get_intro_keyboard(),
        )
    await message.answer(build_full_stats_message(user))


@dp.message(Command("stats"))
async def stats_command(message: Message):
    user = get_or_create_user(message.from_user.id)
    if not user.get("onboarding_completed"):
        return await message.answer(
            "Сначала настроим трекер и напоминания — нажми «В путь в трезвую жизнь».",
            reply_markup=get_intro_keyboard(),
        )
    await message.answer(build_full_stats_message(user))


# === Настройка трекера ===

@dp.message(F.text == "Настроить трекер")
async def setup_tracker(message: Message):
    user = get_or_create_user(message.from_user.id)
    reset_waiting_flags(user)
    update_user(user["user_id"], waiting_for_sober_since=1)
    user["waiting_for_sober_since"] = 1
    await message.answer("С какой даты ты не пьёшь? Формат ДД.ММ.ГГГГ")


@dp.message(F.text == "Настроить напоминания")
async def setup_reminders(message: Message):
    user = get_or_create_user(message.from_user.id)
    if not user.get("onboarding_completed"):
        return await message.answer(
            "Сначала пройдём базовую настройку трекера, нажми «В путь в трезвую жизнь».",
            reply_markup=get_intro_keyboard(),
        )
    reset_waiting_flags(user)
    update_user(user["user_id"], waiting_for_morning_time=1)
    user["waiting_for_morning_time"] = 1
    await message.answer(
        "Во сколько утром присылать сообщение? Формат ЧЧ:ММ.\n"
        "Если напоминания не нужны, напиши «выключить».",
    )


# === Отметка "я не пил" ===

@dp.message(F.text == "Я сегодня не пил(а)")
async def no_alcohol_today(message: Message):
    user = get_or_create_user(message.from_user.id)
    if not user.get("onboarding_completed"):
        return await message.answer(
            "Сперва настроим трекер и напоминания — нажми «В путь в трезвую жизнь».",
            reply_markup=get_intro_keyboard(),
        )
    today = date.today()

    if user["last_sober_date"] == today:
        await message.answer("Сегодня уже отмечено, что ты не пил 💚")
        return

    yesterday = today - timedelta(days=1)
    if user["last_sober_date"] == yesterday:
        streak = (user.get("streak") or 0) + 1
    else:
        streak = 1

    update_user(
        user["user_id"],
        last_sober_date=today,
        streak=streak,
    )
    log_event(user["user_id"], "sober_day", {"date": today.isoformat()})

    await message.answer(f"Отлично! Серия трезвых дней: {streak}")


@dp.message(F.text == "Сорвался(ась)")
async def relapse(message: Message):
    user = get_or_create_user(message.from_user.id)
    if not user.get("onboarding_completed"):
        return await message.answer(
            "Сначала пройди базовую настройку — нажми «В путь в трезвую жизнь».",
            reply_markup=get_intro_keyboard(),
        )
    stats_before = build_full_stats_message(user)
    prev = user.get("streak") or 0

    if stats_before:
        await message.answer(f"Твоя статистика перед сбросом:\n\n{stats_before}")
    else:
        await message.answer("Статистики пока мало — начни отмечать прогресс!")

    # Полный сброс: прогресс, трекер, напоминания
    reset_user_stats(user["user_id"])
    reset_tracker_settings(user["user_id"])
    reset_reminders(user["user_id"])
    user["onboarding_completed"] = 0
    update_user(
        user["user_id"],
        goals=[],
        reasons=[],
        triggers=[],
        motivation="",
    )
    user["goals"] = []
    user["reasons"] = []
    user["triggers"] = []
    user["motivation"] = ""

    await message.answer(
        f"Не осуждаю тебя 🙏\n"
        f"Предыдущая серия: {prev} дней.\n"
        f"Вся статистика, трекер и напоминания удалены.\n"
        f"Это не конец, а опыт. Ты справишься.\n\n"
        f"Нажми «В путь в трезвую жизнь», чтобы начать заново.",
        reply_markup=get_intro_keyboard(),
    )


# === Тяга ===

@dp.message(F.text == "Тяга сейчас")
async def craving_start(message: Message):
    user = get_or_create_user(message.from_user.id)
    if not user.get("onboarding_completed"):
        return await message.answer(
            "Сначала пройди настройку трекера и напоминаний — нажми «В путь в трезвую жизнь».",
            reply_markup=get_intro_keyboard(),
        )
    reset_waiting_flags(user)
    update_user(user["user_id"], waiting_for_craving_number=1)
    user["waiting_for_craving_number"] = 1

    await message.answer("Оцени тягу по шкале 0–10")


@dp.message()
async def catch_all(message: Message):
    user = get_or_create_user(message.from_user.id)

    text_raw = (message.text or "").strip()
    text_lower = text_raw.lower()
    cancel_words = {"отмена", "cancel", "стоп"}

    # 0. Дневник
    if user.get("waiting_for_diary_entry"):
        if text_lower in cancel_words:
            reset_waiting_flags(user)
            return await message.answer("Отменил запись.", reply_markup=get_main_keyboard())
        log_event(user["user_id"], "diary", {"text": text_raw})
        update_user(user["user_id"], waiting_for_diary_entry=0)
        user["waiting_for_diary_entry"] = 0
        return await message.answer("Сохранил запись в дневник.", reply_markup=get_main_keyboard())

    # 0.1 Цель и мотивация
    if user.get("waiting_for_goal_motivation"):
        if text_lower in cancel_words:
            reset_waiting_flags(user)
            return await message.answer("Настройка отменена.", reply_markup=get_main_keyboard())
        if "\n" in text_raw:
            goal, motivation = text_raw.split("\n", 1)
        else:
            goal, motivation = text_raw, text_raw
        update_user(
            user["user_id"],
            goal=goal.strip() or "не задана",
            motivation=motivation.strip(),
            waiting_for_goal_motivation=0,
        )
        user["waiting_for_goal_motivation"] = 0
        return await message.answer(
            "Цель и мотивация обновлены.",
            reply_markup=get_main_keyboard(),
        )

    # 0.1 Добавление цели
    if user.get("waiting_for_goal_add"):
        if text_lower in cancel_words:
            reset_waiting_flags(user)
            return await message.answer("Добавление цели отменено.", reply_markup=get_main_keyboard())
        goals = user.get("goals") or []
        goals.append(text_raw)
        update_user(
            user["user_id"],
            goals=goals,
            waiting_for_goal_add=0,
        )
        user["waiting_for_goal_add"] = 0
        user["goals"] = goals
        return await message.answer("Цель добавлена.", reply_markup=get_main_keyboard())

    # 0.2 Добавление причины
    if user.get("waiting_for_reasons_add"):
        if text_lower in cancel_words:
            reset_waiting_flags(user)
            return await message.answer("Добавление причины отменено.", reply_markup=get_main_keyboard())
        reasons = user.get("reasons") or []
        reasons.append(text_raw)
        update_user(
            user["user_id"],
            reasons=reasons,
            waiting_for_reasons_add=0,
        )
        user["waiting_for_reasons_add"] = 0
        user["reasons"] = reasons
        return await message.answer("Причина добавлена.", reply_markup=get_main_keyboard())

    # 0.2 Триггеры
    if user.get("waiting_for_triggers"):
        if text_lower in cancel_words:
            reset_waiting_flags(user)
            return await message.answer("Настройка триггеров отменена.", reply_markup=get_main_keyboard())
        triggers = [t.strip() for t in text_raw.split(",") if t.strip()]
        update_user(
            user["user_id"],
            triggers=triggers,
            waiting_for_triggers=0,
        )
        user["waiting_for_triggers"] = 0
        user["triggers"] = triggers
        return await message.answer("Триггеры обновлены.", reply_markup=get_main_keyboard())

    # 1. Ответ на тягу
    if user.get("waiting_for_craving_number"):
        try:
            level = int(message.text)
        except:
            return await message.answer("Напиши число 0–10")

        update_user(user["user_id"], waiting_for_craving_number=0)
        log_event(user["user_id"], "craving", {"level": level})

        if level <= 3:
            await message.answer("Тяга слабая. Попробуй переключиться: музыка, душ, прогулка.")
        elif level <= 7:
            await message.answer("Попробуй дыхание 4-7-8, это снимет напряжение.")
        else:
            await message.answer(
                "Очень сильная тяга. Выйди из комнаты/магазина. "
                "Позвони близкому. Сделай 10 глубоких вдохов."
            )
        return

    # 2. Настройка даты трезвости
    if user.get("waiting_for_sober_since"):
        try:
            sober_date = datetime.strptime(message.text, "%d.%m.%Y").date()
        except:
            return await message.answer("Формат: ДД.ММ.ГГГГ")

        update_user(
            user["user_id"],
            sober_since_date=sober_date,
            waiting_for_sober_since=0,
            waiting_for_weekly_spend=1,
        )
        return await message.answer("Сколько денег уходило на алкоголь в неделю?")

    # 3. Настройка weekly_spend
    if user.get("waiting_for_weekly_spend"):
        try:
            spend = float(message.text.replace(",", "."))
        except:
            return await message.answer("Напиши число, например: 3000")

        update_user(
            user["user_id"],
            weekly_alcohol_spend=spend,
            waiting_for_weekly_spend=0,
            waiting_for_weekly_hours=1,
        )
        return await message.answer("Сколько часов в неделю уходило на алкоголь?")

    # 4. Настройка weekly_hours
    if user.get("waiting_for_weekly_hours"):
        try:
            hours = float(message.text.replace(",", "."))
        except:
            return await message.answer("Напиши число, например: 5")

        update_user(
            user["user_id"],
            weekly_alcohol_hours=hours,
            waiting_for_weekly_hours=0,
        )
        user["waiting_for_weekly_hours"] = 0
        if not user.get("onboarding_completed"):
            update_user(user["user_id"], waiting_for_morning_time=1)
            user["waiting_for_morning_time"] = 1
            return await message.answer(
                "Теперь напиши время утреннего напоминания (ЧЧ:ММ) "
                "или «выключить», если напоминания не нужны."
            )
        return await message.answer("Трекер настроен! 👍", reply_markup=get_settings_keyboard())

    # 5. Настройка напоминаний — утро
    if user.get("waiting_for_morning_time"):
        onboarding = not bool(user.get("onboarding_completed"))
        text = (message.text or "").strip().lower()
        off_words = {"выключить", "отключить", "не надо", "нет"}
        if text in off_words:
            reset_reminders(user["user_id"])
            update_user(
                user["user_id"],
                waiting_for_morning_time=0,
                waiting_for_evening_time=0,
                onboarding_completed=1,
            )
            user["waiting_for_morning_time"] = 0
            user["waiting_for_evening_time"] = 0
            user["onboarding_completed"] = 1
            reply_markup = get_main_keyboard() if onboarding else get_settings_keyboard()
            return await message.answer(
                "Напоминания выключены.",
                reply_markup=reply_markup,
            )
        try:
            t = datetime.strptime(message.text, "%H:%M").time()
        except:
            return await message.answer("Формат времени ЧЧ:ММ или напиши «выключить».")

        update_user(
            user["user_id"],
            morning_time=t.strftime("%H:%M"),
            waiting_for_morning_time=0,
            waiting_for_evening_time=1,
        )
        user["morning_time"] = t.strftime("%H:%M")
        user["waiting_for_morning_time"] = 0
        user["waiting_for_evening_time"] = 1
        return await message.answer(
            "Теперь напиши время вечернего напоминания (ЧЧ:ММ) "
            "или «выключить», если напоминания не нужны.",
        )

    # 6. Настройка напоминаний — вечер
    if user.get("waiting_for_evening_time"):
        onboarding = not bool(user.get("onboarding_completed"))
        text = (message.text or "").strip().lower()
        off_words = {"выключить", "отключить", "не надо", "нет"}
        if text in off_words:
            reset_reminders(user["user_id"])
            update_user(
                user["user_id"],
                waiting_for_evening_time=0,
                onboarding_completed=1,
            )
            user["waiting_for_evening_time"] = 0
            user["onboarding_completed"] = 1
            reply_markup = get_main_keyboard() if onboarding else get_settings_keyboard()
            return await message.answer(
                "Напоминания выключены.",
                reply_markup=reply_markup,
            )
        try:
            t = datetime.strptime(message.text, "%H:%M").time()
        except:
            return await message.answer("Формат времени ЧЧ:ММ или напиши «выключить».")

        update_user(
            user["user_id"],
            evening_time=t.strftime("%H:%M"),
            waiting_for_evening_time=0,
            onboarding_completed=1,
        )
        user["evening_time"] = t.strftime("%H:%M")
        user["waiting_for_evening_time"] = 0
        user["onboarding_completed"] = 1
        reply_markup = get_main_keyboard() if onboarding else get_settings_keyboard()
        return await message.answer("Напоминания включены! ⚡", reply_markup=reply_markup)

    if not user.get("onboarding_completed"):
        return await message.answer(
            "Давай закончим настройку. Нажми «В путь в трезвую жизнь», чтобы пройти шаги.",
            reply_markup=get_intro_keyboard(),
        )

    await message.answer("Используй кнопки ниже 👇", reply_markup=get_main_keyboard())


# ---------- СТАТИСТИКА ----------

def plural_ru(n: int, one: str, few: str, many: str) -> str:
    n_abs = abs(n)
    n10 = n_abs % 10
    n100 = n_abs % 100
    if n10 == 1 and n100 != 11:
        return one
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return few
    return many


def build_achievement_text(days: int) -> str:
    """Формирует строку достижений по количеству дней трезвости."""
    if days <= 0:
        return ""
    years = days // 365
    rem = days % 365
    months = rem // 30
    rem = rem % 30
    weeks = rem // 7
    d = rem % 7

    parts = []
    if years:
        parts.append("🏆" * years)
    if months:
        parts.append("💎" * months)
    if weeks:
        parts.append("⭐" * weeks)
    if d:
        parts.append("➕" * d)

    if not parts:
        return ""

    return " ".join(parts)


def build_sober_stats_text(user: dict) -> str:
    sober_since = user.get("sober_since_date")
    if not sober_since:
        return ""

    days = (date.today() - sober_since).days + 1
    txt = f"Ты не пьёшь с {sober_since.strftime('%d.%m.%Y')} ({days} дней)."

    ach = build_achievement_text(days)
    if ach:
        txt += f"\n{ach}"

    if user.get("weekly_alcohol_spend"):
        saved = user["weekly_alcohol_spend"] / 7 * days
        txt += f"\nСэкономлено денег: {saved:.0f} у.е."

    if user.get("weekly_alcohol_hours"):
        saved_h = user["weekly_alcohol_hours"] / 7 * days
        txt += f"\nВернул(а) времени: {saved_h:.1f} часов"

    return txt


def build_full_stats_message(user: dict) -> str:
    parts = []

    s = build_sober_stats_text(user)
    if s:
        parts.append(s)

    if user.get("streak"):
        parts.append(f"Серия ежедневных отметок: {user['streak']} дней.")

    # Reminders
    if user.get("morning_time") or user.get("evening_time"):
        r = "Напоминания: "
        if user.get("morning_time"):
            r += f"утро {user['morning_time']} "
        if user.get("evening_time"):
            r += f"вечер {user['evening_time']}"
        parts.append(r)

    # EVENTS ANALYTICS
    rows = conn.execute(
        "SELECT event_type, COUNT(*) AS cnt FROM events WHERE user_id=? GROUP BY event_type",
        (user["user_id"],),
    ).fetchall()
    counts = {r["event_type"]: r["cnt"] for r in rows}

    if counts:
        ev = []
        if "sober_day" in counts:
            ev.append(f"Трезвых дней отмечено: {counts['sober_day']}")
        if "relapse" in counts:
            ev.append(f"Срывов: {counts['relapse']}")
        if "craving" in counts:
            ev.append(f"Эпизодов тяги: {counts['craving']}")
        if "diary" in counts:
            ev.append(f"Записей в дневнике: {counts['diary']}")
        parts.append("\n".join(ev))

    # last relapse
    row = conn.execute(
        """
        SELECT created_at FROM events
        WHERE user_id=? AND event_type='relapse'
        ORDER BY created_at DESC LIMIT 1
        """,
        (user["user_id"],),
    ).fetchone()

    if row:
        last = datetime.fromisoformat(row["created_at"]).date()
        days_ago = (date.today() - last).days
        parts.append(f"Последний срыв: {last.strftime('%d.%m.%Y')} ({days_ago} дней назад)")

    return "\n\n".join(parts) if parts else "Статистики пока мало — начни отмечать прогресс!"


# ---------- ПЛАНИРОВЩИК ----------

async def scheduler():
    while True:
        now = datetime.now()
        current = now.strftime("%H:%M")
        today = date.today()

        users = get_all_users_with_reminders()
        for u in users:
            # morning
            if u.get("morning_time") == current and u.get("last_morning_sent_date") != today:
                await bot.send_message(u["user_id"], "Доброе утро! 🟢\n" + build_sober_stats_text(u))
                update_user(u["user_id"], last_morning_sent_date=today)

            # evening
            if u.get("evening_time") == current and u.get("last_evening_sent_date") != today:
                await bot.send_message(u["user_id"], "Добрый вечер! 🌙\n" + build_sober_stats_text(u))
                update_user(u["user_id"], last_evening_sent_date=today)

        await asyncio.sleep(10)


# ---------- RUN ----------

async def main():
    init_db()
    asyncio.create_task(scheduler())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
