import os
import telebot
import sqlite3
import threading  # <-- ОДИН раз!
import atexit
from datetime import datetime
import time
import schedule
from flask import Flask
# УБРАТЬ: from threading import Thread  # уже есть import threading

# Создаем простой веб-сервер
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

# Запускаем Flask в отдельном потоке
def run_flask():
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8432420548:AAGX_EqsarA7q_Jx4iNL2zV8j3c_JWd_POU"
CHANNEL_ID = "-1003227241488"  # Твой канал
ADMIN_ID = 644037215  # Твой ID
TILDA_LINK = "https://pleinairclub.tilda.ws/"  # Ссылка на Tilda

# ТВОИ РЕКВИЗИТЫ ДЛЯ ОПЛАТЫ
SBER_PHONE = "+79043323607"  # Твой номер телефона Сбер
SBER_CARD = "2202208262152375"  # Твоя карта Сбер (если есть)
YOUR_NAME = "Илья Козлов"  # Твое имя для перевода
# ===============================

bot = telebot.TeleBot(BOT_TOKEN)

print("🎨 Пленэрный Клуб Бот запущен!")

# Создаем локальное хранилище для каждого потока
thread_local = threading.local()

def get_db_connection():
    """Создает соединение с БД для текущего потока"""
    if not hasattr(thread_local, "conn"):
        thread_local.conn = sqlite3.connect('club.db', check_same_thread=False)
        thread_local.cursor = thread_local.conn.cursor()
        
        # Создаем таблицы с правильной структурой
        create_tables()
    
    return thread_local.conn, thread_local.cursor

def create_tables():
    """Создает таблицы с правильной структурой"""
    cursor = thread_local.cursor
    
    # Проверяем, существует ли таблица users
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    table_exists = cursor.fetchone()
    
    if not table_exists:
        # Создаем таблицу с нуля
        print("🔄 Создаем таблицу users с нуля...")
        cursor.execute('''
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                tariff TEXT,
                amount INTEGER,
                clicked_link INTEGER DEFAULT 0,
                paid INTEGER DEFAULT 0,
                purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                screenshot_date TIMESTAMP
            )
        ''')
        thread_local.conn.commit()
        print("✅ Таблица users создана")
    else:
        # Проверяем структуру существующей таблицы
        print("🔍 Проверяем структуру таблицы users...")
        cursor.execute("PRAGMA table_info(users)")
        columns = {column[1]: column for column in cursor.fetchall()}
        
        # Список всех необходимых колонок
        required_columns = {
            'user_id': 'INTEGER PRIMARY KEY',
            'tariff': 'TEXT',
            'amount': 'INTEGER',
            'clicked_link': 'INTEGER DEFAULT 0',
            'paid': 'INTEGER DEFAULT 0',
            'purchase_date': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
            'screenshot_date': 'TIMESTAMP'
        }
        
        # Добавляем недостающие колонок
        for column_name, column_type in required_columns.items():
            if column_name not in columns:
                print(f"⚠️ Добавляем колонку '{column_name}'...")
                try:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")
                    thread_local.conn.commit()
                    print(f"✅ Колонка '{column_name}' добавлена")
                except Exception as e:
                    print(f"❌ Ошибка при добавлении колонки '{column_name}': {e}")

    # ========== НОВАЯ ТАБЛИЦА ДЛЯ СООБЩЕНИЙ В КАНАЛЕ ==========
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS channel_messages (
            message_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            first_name TEXT,
            username TEXT,
            text TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            tariff TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)
    
    thread_local.conn.commit()
    print("✅ Таблица channel_messages создана/проверена")

# ========== НОВОЕ ПРИВЕТСТВИЕ ==========

@bot.message_handler(commands=['check'])
def check_admin(message):
    bot.send_message(message.chat.id, f"✅ Команда работает! Ваш ID: {message.from_user.id}")


# ========== ДИАГНОСТИКА =========
  
@bot.message_handler(commands=['stats'])
def show_stats(message):
    try:
        print(f"🔍 Команда /stats получена от {message.from_user.id}")
        
        if message.from_user.id != ADMIN_ID:
            print(f"❌ Отказ: {message.from_user.id} != {ADMIN_ID}")
            return
        
        conn, cursor = get_db_connection()  # <-- ДОБАВЬТЕ ОТСТУП!
        
        # Всего пользователей
        cursor.execute("SELECT COUNT(*) FROM users")
        total = cursor.fetchone()[0] or 0
        
        # Получили урок (нажали кнопку)
        cursor.execute("SELECT COUNT(*) FROM users WHERE clicked_link = 1")
        clicked = cursor.fetchone()[0] or 0
        
        # Выбрали тариф
        cursor.execute("SELECT COUNT(*) FROM users WHERE tariff IS NOT NULL")
        with_tariff = cursor.fetchone()[0] or 0
        
        # Оплатили
        cursor.execute("SELECT COUNT(*) FROM users WHERE paid = 1")
        paid = cursor.fetchone()[0] or 0
        
        # Читатели
        cursor.execute("SELECT COUNT(*) FROM users WHERE tariff = 'читатель' AND paid = 1")
        readers = cursor.fetchone()[0] or 0
        
        # Участники
        cursor.execute("SELECT COUNT(*) FROM users WHERE tariff = 'участник' AND paid = 1")
        members = cursor.fetchone()[0] or 0
        
        # Общий доход
        cursor.execute("SELECT SUM(amount) FROM users WHERE paid = 1")
        total_income = cursor.fetchone()[0] or 0
        
        # Скриншоты за 7 дней
        cursor.execute("""
            SELECT COUNT(*) FROM users 
            WHERE paid = 1 
            AND screenshot_date >= datetime('now', '-7 days')
        """)
        screenshots_7days = cursor.fetchone()[0] or 0
        
        # Формируем статистику
        stats = (
            "📊 *СТАТИСТИКА БОТА:*\n\n"
            f"👥 Всего пользователей: {total}\n"
            f"👀 Получили урок: {clicked}\n"
            f"🎯 Выбрали тариф: {with_tariff}\n"
            f"💰 Оплатили (в клубе): {paid}\n"
            f"📖 Читатели: {readers}\n"
            f"💎 Участники: {members}\n"
            f"💵 Общий доход: {total_income}₽\n"
            f"📸 Скриншоты (7 дней): {screenshots_7days}\n\n"
        )
        
        # Конверсии
        if total > 0:
            conv_to_tariff = (with_tariff / clicked * 100) if clicked > 0 else 0
            conv_to_paid = (paid / with_tariff * 100) if with_tariff > 0 else 0
            
            stats += "📈 *Конверсия:*\n"
            stats += f"• В тариф: {conv_to_tariff:.1f}%\n"
            stats += f"• В оплату: {conv_to_paid:.1f}%"
        
        # Отправляем
        bot.send_message(message.chat.id, stats, parse_mode='Markdown')
        
    except Exception as e:
        print(f"❌ Ошибка в /stats: {e}")
        bot.send_message(
            message.chat.id,
            f"❌ Ошибка при получении статистики:\n`{str(e)[:100]}`",
            parse_mode='Markdown'
        )
        


@bot.message_handler(commands=['start'])
def start(message):
    # Первое приветственное сообщение
    bot.send_message(
        message.chat.id,
        "Приветствую Вас. Оставайтесь на волне созерцания и пленэра!"
    )
    
    # Второе сообщение с описанием и кнопками
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    
    # Кнопка "Узнать больше" (ссылка на Tilda)
    btn_more = telebot.types.InlineKeyboardButton(
        text="Узнать больше",
        url=TILDA_LINK
    )
    
    # Кнопка "Хочу в клуб!" (переход к выбору тарифа)
    btn_club = telebot.types.InlineKeyboardButton(
        text="Хочу в клуб!",
        callback_data="join_club"
    )
    
    markup.add(btn_more, btn_club)
    
    bot.send_message(
        message.chat.id,
        "Здесь можно купить подписку и получить доступ в \"Пленэрный Клуб\"!\n\n"
        "Это закрытый телеграм-канал, где все участники могут делиться своим творчеством и получать от меня обратную связь. "
        "Также на канале будет много эксклюзивных видео-уроков и другие полезные материалы, которые я обычно выкладываю на платной основе.\n\n"
        "Здесь Вы получите мою профессиональную поддержку и сможете более уверенно шагать по пути искусства!",
        reply_markup=markup,
        parse_mode=None
    )

# ========== ПРЕДЛОЖЕНИЕ КЛУБА ==========

@bot.callback_query_handler(func=lambda call: call.data == "join_club")
def show_club_offer(call):
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    
    btn_reader = telebot.types.InlineKeyboardButton(
        text="🔥 ЧИТАТЕЛЬ — 100₽/месяц",
        callback_data="tariff_reader"
    )
    btn_member = telebot.types.InlineKeyboardButton(
        text="💎 УЧАСТНИК — 500₽/месяц", 
        callback_data="tariff_member"
    )
    
    markup.add(btn_reader, btn_member)
    
    bot.send_message(
        call.from_user.id,
        "🎯 ВЫБЕРИТЕ ТАРИФ ДОСТУПА К ПЛЕНЭРНОМУ КЛУБУ:\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔥 ЧИТАТЕЛЬ — 100₽\n"
        "• Просмотр всех материалов канала\n"
        "• Доступ к архиву постов\n"
        "• Без возможности комментировать\n\n"
        "💎 УЧАСТНИК — 500₽\n"  
        "• Всё из тарифа Читатель\n"
        "• Возможность комментировать посты\n"
        "• Участие в обсуждениях\n"
        "• Обратная связь от автора\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "👇 ВЫБЕРИТЕ ТАРИФ И НАЖМИТЕ КНОПКУ",
        reply_markup=markup,
        parse_mode=None
    )

# ========== ВЫБОР ТАРИФА ==========

@bot.callback_query_handler(func=lambda call: call.data in ["tariff_reader", "tariff_member"])
def handle_tariff_selection(call):
    conn, cursor = get_db_connection()
    user_id = call.from_user.id
    
    if call.data == "tariff_reader":
        tariff = "читатель"
        amount = 100
    else:
        tariff = "участник" 
        amount = 500
    
    try:
        # Проверяем, есть ли пользователь в базе
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user_exists = cursor.fetchone()
        
        if user_exists:
            cursor.execute("UPDATE users SET tariff = ?, amount = ? WHERE user_id = ?",
                          (tariff, amount, user_id))
        else:
            cursor.execute("INSERT INTO users (user_id, tariff, amount, clicked_link) VALUES (?, ?, ?, 1)",
                          (user_id, tariff, amount))
        
        conn.commit()
        
        bot.answer_callback_query(call.id, f"Вы выбрали {tariff}")
        
        # САМЫЙ ПРОСТОЙ ТЕКСТ БЕЗ ВСЯКОЙ РАЗМЕТКИ
        message_text = f"""Вы выбрали тариф: {tariff.upper()}

Сумма к оплате: {amount} рублей

ПРОСТОЙ СПОСОБ ОПЛАТЫ:

1. Переведите {amount} рублей на номер:
{SBER_PHONE}"""
        
        if SBER_CARD:
            message_text += f"""

Или на карту: {SBER_CARD}"""
        
        message_text += f"""

2. Отправьте скриншот перевода в этот чат

Доступ к каналу откроется автоматически!

Если возникнут проблемы, напишите мне @artistilja"""
        
        # БЕЗ РАЗМЕТКИ
        bot.send_message(user_id, message_text, parse_mode=None)
        
        # Уведомление админу тоже БЕЗ разметки
        bot.send_message(
            ADMIN_ID,
            f"НОВЫЙ ВЫБОР ТАРИФА\n\n"
            f"Пользователь: {call.from_user.first_name}\n"
            f"Username: @{call.from_user.username or 'без username'}\n"
            f"ID: {user_id}\n\n"
            f"Тариф: {tariff.upper()}\n"
            f"Сумма: {amount}₽\n\n"
            f"Ожидает оплаты (скриншот)",
            parse_mode=None
        )
        
    except Exception as e:
        print(f"Ошибка: {e}")
        bot.answer_callback_query(call.id, "Ошибка, попробуйте еще раз")
        
        bot.send_message(
            ADMIN_ID,
            f"Ошибка при выборе тарифа:\n"
            f"Пользователь: {user_id}\n"
            f"Ошибка: {str(e)}",
            parse_mode=None
        )

# ========== АВТОМАТИЧЕСКАЯ ОБРАБОТКА СКРИНШОТОВ ==========

@bot.message_handler(content_types=['photo'])
def handle_screenshot(message):
    """Автоматическая обработка скриншотов оплаты"""
    user_id = message.from_user.id
    
    # Проверяем, что пользователь выбирал тариф
    conn, cursor = get_db_connection()
    cursor.execute("SELECT tariff, amount, paid FROM users WHERE user_id = ?", (user_id,))
    user_data = cursor.fetchone()
    
    if not user_data:
        # Пользователь еще не выбирал тариф
        bot.send_message(
            user_id,
            "❌ Сначала выберите тариф \n\n"
            "Пожалуйста, вернитесь к сообщению с выбором тарифа и начните оплату оттуда.",
            parse_mode=None
        )
        return
    
    tariff, amount, already_paid = user_data
    
    if already_paid:
        # Уже оплатил
        bot.send_message(
            user_id,
            "✅ Вы уже в клубе!\n\n"
            "Ваш доступ к Пленэрному Клубу уже активен.\n"
            "Если возникли проблемы с доступом, напишите мне @artistilja",
            parse_mode=None
        )
        return
    
    # Обновляем статус оплаты и дату скриншота
    screenshot_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE users SET paid = 1, screenshot_date = ? WHERE user_id = ?", 
                  (screenshot_time, user_id))
    conn.commit()
    
    # Создаем ссылку-приглашение
    try:
        invite_link = bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
            creates_join_request=False
        )
        
        # Отправляем пользователю ссылку на канал
        bot.send_message(
            user_id,
            f"🎉 СКРИНШОТ ПОЛУЧЕН! ДОБРО ПОЖАЛОВАТЬ В КЛУБ!\n\n"
            f"✅ Ваш тариф: {tariff.upper()}\n"
            f"💰 Сумма: {amount}₽\n\n"
            f"Ссылка для перехода: {invite_link.invite_link}\n\n"
            "Если возникнут проблемы с доступом, напишите мне @artistilja\n\n"
            "🎨 Увидимся внутри!",
            parse_mode=None,
            disable_web_page_preview=True
        )
        
        # Уведомляем админа (вас) об автоматической выдаче
        bot.send_message(
            ADMIN_ID,
            f"🔄 АВТОМАТИЧЕСКАЯ ВЫДАЧА ДОСТУПА\n\n"
            f"👤 Пользователь: {message.from_user.first_name}\n"
            f"📛 @{message.from_user.username or 'без username'}\n"
            f"🆔 ID: {user_id}\n\n"
            f"💎 Тариф: {tariff}\n"
            f"💵 Сумма: {amount}₽\n\n"
            f"✅ Доступ выдан автоматически по скриншоту\n"
            f"⏰ Время: {screenshot_time}\n\n"
            f"📸 Скриншот ниже (переслан):",
            parse_mode=None
        )
        
        # Пересылаем скриншот админу
        bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
        
    except Exception as e:
        # Если ошибка при создании ссылки
        error_msg = str(e)
        
        bot.send_message(
            user_id,
            "⏳ Скриншот получен!\n\n"
            "Идет обработка...\n"
            "Если доступ не откроется через минуту, напишите мне @artistilja",
            parse_mode=None
        )
        
        # Уведомляем админа об ошибке
        bot.send_message(
            ADMIN_ID,
            f"❌ ОШИБКА АВТОМАТИЧЕСКОЙ ВЫДАЧИ\n\n"
            f"👤 {user_id}\n"
            f"📛 @{message.from_user.username or 'нет'}\n"
            f"💎 Тариф: {tariff}\n\n"
            f"⚠️ Ошибка: {error_msg[:200]}\n\n"
            f"Добавьте пользователя вручную командой:\n"
            f"/add {user_id}\n\n"
            f"📸 Скриншот:",
            parse_mode=None
        )
        
        # Пересылаем скриншот даже при ошибке
        bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)

# ========== ОТСЛЕЖИВАНИЕ СООБЩЕНИЙ В КАНАЛЕ ==========

@bot.message_handler(content_types=['text'])
def handle_channel_messages(message):
    """Сохраняет сообщения из канала"""
    # Проверяем, что сообщение из нужного канала
    if str(message.chat.id) == CHANNEL_ID:
        user_id = message.from_user.id if message.from_user else None
        
        if not user_id:  # Если нет информации о пользователе
            return
            
        first_name = message.from_user.first_name if message.from_user else "Аноним"
        username = message.from_user.username if message.from_user and message.from_user.username else None
        
        conn, cursor = get_db_connection()
        
        # Получаем тариф пользователя из базы
        cursor.execute("SELECT tariff FROM users WHERE user_id = ?", (user_id,))
        user_data = cursor.fetchone()
        tariff = user_data[0] if user_data else "неизвестен"
        
        # Сохраняем сообщение
        cursor.execute("""
            INSERT OR REPLACE INTO channel_messages 
            (message_id, user_id, first_name, username, text, date, tariff)
            VALUES (?, ?, ?, ?, ?, datetime('now'), ?)
        """, (message.message_id, user_id, first_name, username, message.text, tariff))
        
        conn.commit()
        
        # Для отладки (можно убрать потом)
        print(f"💬 Сообщение сохранено: {first_name} ({tariff}): {message.text[:50]}...")

# ========== КОМАНДЫ ДЛЯ ОТЧЕТОВ ==========

@bot.message_handler(commands=['report'])
def send_report(message):
    """Отправляет отчет о сообщениях за последние 24 часа"""
    if message.from_user.id != ADMIN_ID:
        return
    
    bot.send_message(ADMIN_ID, "⏳ Формирую отчет за последние 24 часа...")
    
    conn, cursor = get_db_connection()
    
    # Получаем сообщения за последние 24 часа
    cursor.execute("""
        SELECT DISTINCT user_id, first_name, username, tariff
        FROM channel_messages 
        WHERE date >= datetime('now', '-24 hours')
        ORDER BY tariff DESC, first_name
    """)
    
    active_users = cursor.fetchall()
    
    if not active_users:
        bot.send_message(ADMIN_ID, "📭 За последние 24 часа сообщений не было.")
        return
    
    # Формируем отчет
    report = "📊 *ОТЧЕТ ОБ АКТИВНОСТИ В КАНАЛЕ*\n"
    report += f"*Период:* последние 24 часа\n"
    report += f"*Активных пользователей:* {len(active_users)}\n\n"
    
    for user_id, first_name, username, tariff in active_users:
        # Получаем все сообщения этого пользователя за период
        cursor.execute("""
            SELECT message_id, text, date 
            FROM channel_messages 
            WHERE user_id = ? AND date >= datetime('now', '-24 hours')
            ORDER BY date DESC
        """, (user_id,))
        
        messages = cursor.fetchall()
        
        # Добавляем пользователя в отчет
        user_link = f"@{username}" if username else f"ID: {user_id}"
        report += f"👤 *{first_name}* ({user_link})\n"
        report += f"   🏷️ Тариф: {tariff.upper() if tariff else 'неизвестен'}\n"
        report += f"   💬 Сообщений: {len(messages)}\n"
        
        # Добавляем ссылки на сообщения (первые 3)
        for msg_id, msg_text, msg_date in messages[:3]:
            # Создаем ссылку на сообщение
            # Формат: https://t.me/c/CHAT_ID/MESSAGE_ID
            chat_id_for_link = str(CHANNEL_ID).replace("-100", "")
            message_link = f"https://t.me/c/{chat_id_for_link}/{msg_id}"
            
            # Обрезаем текст сообщения
            short_text = (msg_text[:50] + "...") if len(msg_text) > 50 else msg_text
            if not short_text.strip():
                short_text = "(медиа-сообщение)"
            
            report += f"   🔗 [{short_text}]({message_link})\n"
        
        report += "\n"
    
    # Добавляем статистику по тарифам
    cursor.execute("""
        SELECT tariff, COUNT(DISTINCT user_id) 
        FROM channel_messages 
        WHERE date >= datetime('now', '-24 hours')
        GROUP BY tariff
    """)
    
    tariff_stats = cursor.fetchall()
    
    report += "\n📈 *СТАТИСТИКА ПО ТАРИФАМ:*\n"
    for tariff, count in tariff_stats:
        report += f"   • {tariff.upper() if tariff else 'БЕЗ ТАРИФА'}: {count} чел.\n"
    
    # Общее количество сообщений
    cursor.execute("SELECT COUNT(*) FROM channel_messages WHERE date >= datetime('now', '-24 hours')")
    total_messages = cursor.fetchone()[0]
    report += f"\n📝 *Всего сообщений:* {total_messages}"
    
    # Отправляем отчет
    try:
        if len(report) > 4000:
            # Разбиваем на части
            parts = [report[i:i+4000] for i in range(0, len(report), 4000)]
            for part in parts:
                bot.send_message(ADMIN_ID, part, parse_mode='Markdown', disable_web_page_preview=True)
        else:
            bot.send_message(ADMIN_ID, report, parse_mode='Markdown', disable_web_page_preview=True)
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ Ошибка при отправке отчета: {str(e)[:100]}")

@bot.message_handler(commands=['report7'])
def send_weekly_report(message):
    """Отчет за 7 дней"""
    if message.from_user.id != ADMIN_ID:
        return
    
    bot.send_message(ADMIN_ID, "⏳ Формирую отчет за последние 7 дней...")
    
    conn, cursor = get_db_connection()
    
    # Получаем сообщения за последние 7 дней
    cursor.execute("""
        SELECT DISTINCT user_id, first_name, username, tariff
        FROM channel_messages 
        WHERE date >= datetime('now', '-7 days')
        ORDER BY tariff DESC, first_name
    """)
    
    active_users = cursor.fetchall()
    
    if not active_users:
        bot.send_message(ADMIN_ID, "📭 За последние 7 дней сообщений не было.")
        return
    
    # Формируем отчет
    report = "📊 *ОТЧЕТ ОБ АКТИВНОСТИ В КАНАЛЕ*\n"
    report += f"*Период:* последние 7 дней\n"
    report += f"*Активных пользователей:* {len(active_users)}\n\n"
    
    for user_id, first_name, username, tariff in active_users:
        # Получаем все сообщения этого пользователя за период
        cursor.execute("""
            SELECT COUNT(*) 
            FROM channel_messages 
            WHERE user_id = ? AND date >= datetime('now', '-7 days')
        """, (user_id,))
        
        message_count = cursor.fetchone()[0]
        
        # Получаем последние 2 сообщения для примера
        cursor.execute("""
            SELECT message_id, text, date 
            FROM channel_messages 
            WHERE user_id = ? AND date >= datetime('now', '-7 days')
            ORDER BY date DESC
            LIMIT 2
        """, (user_id,))
        
        recent_messages = cursor.fetchall()
        
        # Добавляем пользователя в отчет
        user_link = f"@{username}" if username else f"ID: {user_id}"
        report += f"👤 *{first_name}* ({user_link})\n"
        report += f"   🏷️ Тариф: {tariff.upper() if tariff else 'неизвестен'}\n"
        report += f"   💬 Сообщений за неделю: {message_count}\n"
        
        # Добавляем ссылки на последние сообщения
        for msg_id, msg_text, msg_date in recent_messages:
            # Создаем ссылку на сообщение
            chat_id_for_link = str(CHANNEL_ID).replace("-100", "")
            message_link = f"https://t.me/c/{chat_id_for_link}/{msg_id}"
            
            # Обрезаем текст сообщения
            short_text = (msg_text[:40] + "...") if len(msg_text) > 40 else msg_text
            if not short_text.strip():
                short_text = "(медиа)"
            
            report += f"   🔗 [{short_text}]({message_link})\n"
        
        report += "\n"
    
    # Статистика по тарифам
    cursor.execute("""
        SELECT tariff, COUNT(DISTINCT user_id) 
        FROM channel_messages 
        WHERE date >= datetime('now', '-7 days')
        GROUP BY tariff
    """)
    
    tariff_stats = cursor.fetchall()
    
    report += "\n📈 *СТАТИСТИКА ПО ТАРИФАМ:*\n"
    for tariff, count in tariff_stats:
        report += f"   • {tariff.upper() if tariff else 'БЕЗ ТАРИФА'}: {count} чел.\n"
    
    # Общее количество сообщений
    cursor.execute("SELECT COUNT(*) FROM channel_messages WHERE date >= datetime('now', '-7 days')")
    total_messages = cursor.fetchone()[0]
    report += f"\n📝 *Всего сообщений за неделю:* {total_messages}"
    
    # Отправляем отчет
    try:
        if len(report) > 4000:
            parts = [report[i:i+4000] for i in range(0, len(report), 4000)]
            for part in parts:
                bot.send_message(ADMIN_ID, part, parse_mode='Markdown', disable_web_page_preview=True)
        else:
            bot.send_message(ADMIN_ID, report, parse_mode='Markdown', disable_web_page_preview=True)
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ Ошибка при отправке отчета: {str(e)[:100]}")

@bot.message_handler(commands=['activity'])
def activity_menu(message):
    """Меню отчетов об активности"""
    if message.from_user.id != ADMIN_ID:
        return
    
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    
    btn_today = telebot.types.InlineKeyboardButton(
        "📊 Сегодня", 
        callback_data="report_today"
    )
    btn_week = telebot.types.InlineKeyboardButton(
        "📈 Неделя", 
        callback_data="report_week"
    )
    btn_top = telebot.types.InlineKeyboardButton(
        "🏆 Топ активных", 
        callback_data="report_top"
    )
    btn_stats = telebot.types.InlineKeyboardButton(
        "📈 Общая статистика", 
        callback_data="report_stats"
    )
    
    markup.add(btn_today, btn_week, btn_top, btn_stats)
    
    bot.send_message(
        ADMIN_ID,
        "📊 *МЕНЮ ОТЧЕТОВ ПО АКТИВНОСТИ*\n\n"
        "Выберите тип отчета:",
        reply_markup=markup,
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("report_"))
def handle_report_buttons(call):
    """Обработка кнопок отчетов"""
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Только для админа")
        return
    
    if call.data == "report_today":
        bot.answer_callback_query(call.id, "Формирую отчет за сегодня...")
        send_report(call.message)
    elif call.data == "report_week":
        bot.answer_callback_query(call.id, "Формирую отчет за неделю...")
        send_weekly_report(call.message)
    elif call.data == "report_top":
        bot.answer_callback_query(call.id, "Формирую топ активных...")
        send_top_users(call.message)
    elif call.data == "report_stats":
        bot.answer_callback_query(call.id, "Формирую статистику...")
        send_general_stats(call.message)

def send_top_users(message):
    """Топ самых активных пользователей"""
    conn, cursor = get_db_connection()
    
    cursor.execute("""
        SELECT user_id, first_name, username, tariff, COUNT(*) as msg_count
        FROM channel_messages 
        WHERE date >= datetime('now', '-30 days')
        GROUP BY user_id
        ORDER BY msg_count DESC
        LIMIT 10
    """)
    
    top_users = cursor.fetchall()
    
    if not top_users:
        bot.send_message(ADMIN_ID, "📭 За последний месяц сообщений не было.")
        return
    
    report = "🏆 *ТОП АКТИВНЫХ ПОЛЬЗОВАТЕЛЕЙ*\n"
    report += f"*Период:* последние 30 дней\n\n"
    
    for i, (user_id, first_name, username, tariff, msg_count) in enumerate(top_users, 1):
        user_link = f"@{username}" if username else f"ID: {user_id}"
        report += f"{i}. *{first_name}* ({user_link})\n"
        report += f"   🏷️ Тариф: {tariff.upper() if tariff else 'неизвестен'}\n"
        report += f"   💬 Сообщений: {msg_count}\n\n"
    
    bot.send_message(ADMIN_ID, report, parse_mode='Markdown')

def send_general_stats(message):
    """Общая статистика активности"""
    conn, cursor = get_db_connection()
    
    report = "📈 *ОБЩАЯ СТАТИСТИКА АКТИВНОСТИ*\n\n"
    
    # За сегодня
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM channel_messages WHERE date >= datetime('now', '-24 hours')")
    today_active = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM channel_messages WHERE date >= datetime('now', '-24 hours')")
    today_messages = cursor.fetchone()[0]
    
    # За неделю
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM channel_messages WHERE date >= datetime('now', '-7 days')")
    week_active = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM channel_messages WHERE date >= datetime('now', '-7 days')")
    week_messages = cursor.fetchone()[0]
    
    # За месяц
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM channel_messages WHERE date >= datetime('now', '-30 days')")
    month_active = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM channel_messages WHERE date >= datetime('now', '-30 days')")
    month_messages = cursor.fetchone()[0]
    
    # Всего
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM channel_messages")
    total_active = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM channel_messages")
    total_messages = cursor.fetchone()[0]
    
    report += f"*📅 СЕГОДНЯ:*\n"
    report += f"   👤 Активных: {today_active}\n"
    report += f"   💬 Сообщений: {today_messages}\n\n"
    
    report += f"*📅 НЕДЕЛЯ:*\n"
    report += f"   👤 Активных: {week_active}\n"
    report += f"   💬 Сообщений: {week_messages}\n\n"
    
    report += f"*📅 МЕСЯЦ:*\n"
    report += f"   👤 Активных: {month_active}\n"
    report += f"   💬 Сообщений: {month_messages}\n\n"
    
    report += f"*📅 ВСЕГО:*\n"
    report += f"   👤 Уникальных: {total_active}\n"
    report += f"   💬 Сообщений: {total_messages}"
    
    bot.send_message(ADMIN_ID, report, parse_mode='Markdown')

# ========== АДМИН КОМАНДЫ ==========

@bot.message_handler(commands=['list'])
def list_users(message):
    """Список всех пользователей"""
    if message.from_user.id == ADMIN_ID:
        conn, cursor = get_db_connection()
        
        try:
            cursor.execute("SELECT user_id, tariff, amount, paid, screenshot_date FROM users ORDER BY purchase_date DESC")
            users = cursor.fetchall()
            
            if users:
                response = "📋 *Пользователи в базе:*\n\n"
                for user_id, tariff, amount, paid, screenshot_date in users:
                    status = "✅ ОПЛАЧЕНО" if paid else "⏳ ОЖИДАЕТ"
                    tariff_text = f" • {tariff} ({amount}₽)" if tariff else " • нет тарифа"
                    screenshot_text = f"\n   📸 {screenshot_date}" if screenshot_date else ""
                    response += f"• {user_id}: {status}{tariff_text}{screenshot_text}\n"
            else:
                response = "📭 База пуста"
                
            bot.send_message(ADMIN_ID, response, parse_mode='Markdown')
            
        except Exception as e:
            bot.send_message(ADMIN_ID, f"❌ Ошибка: {e}")
            

# ========== ТЕСТОВАЯ КОМАНДА ==========
@bot.message_handler(commands=['test'])
def test_command(message):
    try:
        print(f"✅ Тестовая команда от {message.from_user.id}")
        bot.send_message(message.chat.id, "✅ Тест работает!")
    except Exception as e:
        print(f"❌ Ошибка в /test: {e}")
        
# ========== КОМАНДА ДЛЯ РУЧНОГО ДОБАВЛЕНИЯ ==========

@bot.message_handler(commands=['add'])
def manual_add_to_channel(message):
    """Ручное добавление пользователя в канал: /add user_id"""
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        # Получаем ID пользователя из команды
        user_id = int(message.text.split()[1])
        
        # Создаем ссылку-приглашение
        invite_link = bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
            creates_join_request=False
        )
        
        # Отправляем пользователю
        bot.send_message(
            user_id,
            f"🎉 *ВАС ДОБАВИЛИ В ПЛЕНЭРНЫЙ КЛУБ!*\n\n"
            f"👉 [ПЕРЕЙТИ В КЛУБ]({invite_link.invite_link})\n\n"
            "*Ссылка действует 24 часа.*\n"
            "Если ссылка не работает, напишите @artistilja",
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        # Обновляем статус в базе
        conn, cursor = get_db_connection()
        cursor.execute("UPDATE users SET paid = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        
        # Получаем информацию о пользователе
        cursor.execute("SELECT tariff, amount FROM users WHERE user_id = ?", (user_id,))
        user_data = cursor.fetchone()
        tariff_info = f"Тариф: {user_data[0] if user_data else 'неизвестен'}" if user_data else ""
        
        bot.send_message(
            ADMIN_ID, 
            f"✅ Пользователь {user_id} добавлен в канал!\n{tariff_info}"
        )
        
    except (IndexError, ValueError):
        bot.send_message(ADMIN_ID, "Используйте: /add USER_ID")
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ Ошибка: {e}")

# ========== ЗАКРЫТИЕ СОЕДИНЕНИЙ ==========

def close_all_connections():
    if hasattr(thread_local, "conn"):
        thread_local.conn.close()

atexit.register(close_all_connections)

# ========== ЗАПУСК БОТА ==========

if __name__ == "__main__":
    # Проверяем, работаем ли мы на Render (через переменную окружения)
    is_render = os.getenv('RENDER', False)
    
    if is_render:
        # На Render: запускаем Flask в фоне
        print("🚀 Запускаем на Render (с Flask)")
        flask_thread = threading.Thread(target=run_flask)
        flask_thread.daemon = True
        flask_thread.start()
    else:
        # Локально (Pydroid 3): НЕ запускаем Flask
        print("📱 Запускаем локально (без Flask)")
    
    # Создаем начальное соединение в главном потоке
    get_db_connection()
    print(f"🤖 Бот @{bot.get_me().username} запущен")
    print(f"👑 Админ: {ADMIN_ID}")
    print(f"🌐 Ссылка на Tilda: {TILDA_LINK}")
    print(f"📱 Реквизиты: {SBER_PHONE}")
    print("=" * 50)
    print("📱 ОСНОВНАЯ ЛОГИКА БОТА:")
    print("1. /start → Приветствие с двумя сообщениями")
    print("2. Две кнопки: 'Узнать больше' и 'Хочу в клуб!'")
    print("3. Выбор тарифа (Читатель 100₽ / Участник 500₽)")
    print("4. Оплата по реквизитам + скриншот")
    print("5. Автоматическая выдача доступа в канал")
    print("=" * 50)
    
    # ПРОСТОЙ ЗАПУСК
    try:
        print("✅ Бот готов к работе...")
        bot.polling(none_stop=True)
    except KeyboardInterrupt:
        print("\n⏹️ Остановка бота...")
        close_all_connections()