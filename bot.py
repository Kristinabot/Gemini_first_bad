import os
import hmac
import hashlib
import json
from urllib.parse import parse_qsl
from threading import Thread
import psycopg2
from flask import Flask, jsonify, request
from flask_cors import CORS
import telebot
from telebot import types

# 🛡️ БЕЗОПАСНОСТЬ: Все ключи скрыты в Environment хостинга
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL") # Ссылка на вашу будущую PostgreSQL

if not BOT_TOKEN or not DATABASE_URL:
    raise ValueError("⚠️ Ошибка: На хостинге не настроены переменные BOT_TOKEN или DATABASE_URL!")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
CORS(app) # Разрешаем фронтенду безопасный доступ

# --- ВАЛИДАЦИЯ TELEGRAM (Защита от хакеров и взлома) ---
def verify_telegram_data(init_data):
    try:
        vals = dict(parse_qsl(init_data))
        hash_value = vals.pop('hash', None)
        if not hash_value:
            return False
        
        # Создаем секретный ключ на основе токена бота
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        
        # Сортируем параметры и склеиваем в строку
        data_check_string = "\\n".join([f"{k}={v}" for k, v in sorted(vals.items())])
        
        # Вычисляем проверочный хэш
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        return calculated_hash == hash_value
    except Exception:
        return False

# --- ИНИЦИАЛИЗАЦИЯ PROFESSIONAL DATABASE (PostgreSQL) ---
def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    # Таблица проектов (бюджетов)
    cursor.execute('''CREATE TABLE IF NOT EXISTS projects 
                      (id TEXT PRIMARY KEY, budget INTEGER DEFAULT 500000)''')
    # Таблица связи пользователей с проектами (для совместного доступа)
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_projects 
                      (user_id BIGINT PRIMARY KEY, project_id TEXT)''')
    # Таблица расходов
    cursor.execute('''CREATE TABLE IF NOT EXISTS expenses 
                      (id SERIAL PRIMARY KEY, project_id TEXT, amount INTEGER, 
                       category TEXT, description TEXT, user_name TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    cursor.close()
    conn.close()

init_db()

def get_user_project(user_id):
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("SELECT project_id FROM user_projects WHERE user_id=%s", (user_id,))
    row = cursor.fetchone()
    
    if row:
        project_id = row[0]
    else:
        project_id = str(user_id)
        cursor.execute("INSERT INTO projects (id, budget) VALUES (%s, %s) ON CONFLICT DO NOTHING", (project_id, 500000))
        cursor.execute("INSERT INTO user_projects (user_id, project_id) VALUES (%s, %s)", (user_id, project_id))
        conn.commit()
    
    cursor.close()
    conn.close()
    return project_id

# --- ЛОГИКА ТЕЛЕГРАМ БОТА ---
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    args = message.text.split()
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    # Ссылка-приглашение для супруга/супруги
    if len(args) > 1 and args[1].startswith('join_'):
        parent_project_id = args[1].replace('join_', '')
        cursor.execute("INSERT INTO user_projects (user_id, project_id) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET project_id=%s", 
                       (user_id, parent_project_id, parent_project_id))
        conn.commit()
        bot.reply_to(message, "🎉 Вы успешно подключились к общему семейному бюджету ремонта!")
        cursor.close()
        conn.close()
        return

    project_id = get_user_project(user_id)
    cursor.close()
    conn.close()

    WEBAPP_URL = "https://github.io"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_app = types.KeyboardButton("📊 Открыть Ремонт-Панель", web_app=types.WebAppInfo(url=WEBAPP_URL))
    markup.add(btn_app)
    
    welcome_text = (
        f"🔨 Добро пожаловать в Ремонт Контроль PRO!\n\n"
        f"👥 Перешлите эту ссылку супругу(е) для совместного доступа:\n"
        f"https://t.me{bot.get_me().username}?start=join_{project_id}"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

# --- PRODUCTION API ДЛЯ ФРОНТЕНДА ---
@app.route('/api/get_data', methods=['POST'])
def get_data():
    data = request.json
    init_data = data.get('initData')
    
    # Жесткая проверка безопасности
    if not init_data or not verify_telegram_data(init_data):
        return jsonify({"error": "Unauthorized"}), 401
        
    # Извлекаем telegram user_id напрямую из зашифрованных данных Telegram
    vals = dict(parse_qsl(init_data))
    user_info = json.loads(vals.get('user', '{}'))
    user_id = user_info.get('id')
    
    project_id = get_user_project(user_id)
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    cursor.execute("SELECT budget FROM projects WHERE id=%s", (project_id,))
    budget = cursor.fetchone()[0]
    
    cursor.execute("SELECT amount, category, description, user_name FROM expenses WHERE project_id=%s ORDER BY id DESC", (project_id,))
    rows = cursor.fetchall()
    expenses = [{"amount": r[0], "category": r[1], "description": r[2], "user_name": r[3]} for r in rows]
    
    cursor.close()
    conn.close()
    return jsonify({"budget": budget, "expenses": expenses, "pid": project_id})

@app.route('/api/add_expense', methods=['POST'])
def add_expense():
    data = request.json
    init_data = data.get('initData')
    
    if not init_data or not verify_telegram_data(init_data):
        return jsonify({"error": "Unauthorized"}), 401
        
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO expenses (project_id, amount, category, description, user_name) VALUES (%s, %s, %s, %s, %s)",
                   (data['pid'], data['amount'], data['category'], data['description'], data['user_name']))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"status": "ok"})

@app.route('/api/set_budget', methods=['POST'])
def set_budget():
    data = request.json
    init_data = data.get('initData')
    
    if not init_data or not verify_telegram_data(init_data):
        return jsonify({"error": "Unauthorized"}), 401
        
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO projects (id, budget) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET budget=%s", 
                   (data['pid'], data['budget'], data['budget']))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"status": "ok"})

def run_flask():
    app.run(host='0.0.0.0', port=8000)

if __name__ == '__main__':
    Thread(target=run_flask).start()
    bot.infinity_polling()
