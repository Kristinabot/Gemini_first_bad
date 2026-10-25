import os
import hmac
import hashlib
import json
from urllib.parse import parse_qsl
import psycopg2
from flask import Flask, jsonify, request
from flask_cors import CORS
import telebot

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

if not BOT_TOKEN or not DATABASE_URL:
    raise ValueError("⚠️ Ошибка: На Vercel не настроены BOT_TOKEN или DATABASE_URL!")

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
CORS(app)

def verify_telegram_data(init_data):
    try:
        vals = dict(parse_qsl(init_data))
        hash_value = vals.pop('hash', None)
        if not hash_value: return False
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        data_check_string = "\\n".join([f"{k}={v}" for k, v in sorted(vals.items())])
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        return calculated_hash == hash_value
    except Exception: return False

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
        # Создаем дефолтные комнаты для нового проекта
        default_rooms = ["Кухня 🍳", "Ванная 🛁", "Спальня 🛏️", "Аванс прорабу 💸"]
        for room in default_rooms:
            cursor.execute("INSERT INTO project_rooms (project_id, room_name) VALUES (%s, %s)", (project_id, room))
        conn.commit()
    cursor.close()
    conn.close()
    return project_id

# НАСТРОЙКА ТАБЛИЦ ПОД ДИНАМИЧЕСКИЕ КОМНАТЫ
def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, budget INTEGER DEFAULT 500000)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_projects (user_id BIGINT PRIMARY KEY, project_id TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS project_rooms 
                      (id SERIAL PRIMARY KEY, project_id TEXT, room_name TEXT, UNIQUE(project_id, room_name))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS expenses 
                      (id SERIAL PRIMARY KEY, project_id TEXT, amount INTEGER, category TEXT, description TEXT, user_name TEXT)''')
    conn.commit()
    cursor.close()
    conn.close()

init_db()

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return jsonify({"error": "Forbidden"}), 403

@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    args = message.text.split()
    
    if len(args) > 1 and args.startswith('join_'):
        parent_project_id = args[0].replace('join_', '')
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO user_projects (user_id, project_id) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET project_id=%s", 
                       (user_id, parent_project_id, parent_project_id))
        conn.commit()
        cursor.close()
        conn.close()
        bot.reply_to(message, "🎉 Вы успешно подключились к общему семейному бюджету ремонта!")
        return

    project_id = get_user_project(user_id)
    WEBAPP_URL = "https://github.io"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_app = types.KeyboardButton("📊 Открыть Ремонт-Панель", web_app=types.WebAppInfo(url=f"{WEBAPP_URL}?pid={project_id}"))
    markup.add(btn_app)
    bot.send_message(message.chat.id, f"🔨 Добро пожаловать!\n👥 Ссылка для супруга(и):\nhttps://t.me{bot.get_me().username}?start=join_{project_id}", reply_markup=markup)

@app.route('/api/get_data', methods=['POST'])
def get_data():
    data = request.json
    init_data = data.get('initData')
    if not init_data or not verify_telegram_data(init_data): return jsonify({"error": "Unauthorized"}), 401
    vals = dict(parse_qsl(init_data))
    user_id = json.loads(vals.get('user', '{}')).get('id')
    project_id = get_user_project(user_id)
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("SELECT budget FROM projects WHERE id=%s", (project_id,))
    budget = cursor.fetchone()[0]
    
    # Достаем список уникальных комнат этого проекта
    cursor.execute("SELECT room_name FROM project_rooms WHERE project_id=%s ORDER BY id ASC", (project_id,))
    rooms = [r[0] for r in cursor.fetchall()]
    
    cursor.execute("SELECT amount, category, description, user_name FROM expenses WHERE project_id=%s ORDER BY id DESC", (project_id,))
    expenses = [{"amount": r[0], "category": r[1], "description": r[2], "user_name": r[3]} for r in cursor.fetchall()]
    
    cursor.close()
    conn.close()
    return jsonify({"budget": budget, "expenses": expenses, "rooms": rooms, "pid": project_id})

@app.route('/api/add_room', methods=['POST'])
def add_room():
    data = request.json
    if not data.get('initData') or not verify_telegram_data(data['initData']): return jsonify({"error": "Unauthorized"}), 401
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO project_rooms (project_id, room_name) VALUES (%s, %s) ON CONFLICT DO NOTHING", (data['pid'], data['room_name']))
        conn.commit()
    except Exception as e: print(e)
    cursor.close()
    conn.close()
    return jsonify({"status": "ok"})

@app.route('/api/add_expense', methods=['POST'])
def add_expense():
    data = request.json
    if not data.get('initData') or not verify_telegram_data(data['initData']): return jsonify({"error": "Unauthorized"}), 401
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
    if not data.get('initData') or not verify_telegram_data(data['initData']): return jsonify({"error": "Unauthorized"}), 401
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO projects (id, budget) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET budget=%s", (data['pid'], data['budget'], data['budget']))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"status": "ok"})
