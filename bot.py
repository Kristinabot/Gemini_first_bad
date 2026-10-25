import os
import sqlite3
from threading import Thread
import telebot
from telebot import types
from flask import Flask, jsonify, request
from flask_cors import CORS

BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY", "no_key")

if not BOT_TOKEN:
    raise ValueError("⚠️ Ошибка: Переменная BOT_TOKEN не настроена на сервере Render!")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ЖЕЛЕЗОБЕТОННАЯ РАЗБЛОКИРОВКА КНОПОК ДЛЯ ТЕЛЕФОНА (CORS)
CORS(app, resources={r"/api/*": {"origins": "*"}})

def init_db():
    conn = sqlite3.connect('remont.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS projects 
                      (id TEXT PRIMARY KEY, budget INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS expenses 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, amount INTEGER, 
                       category TEXT, description TEXT, user_name TEXT)''')
    conn.commit()
    conn.close()

init_db()

def get_or_create_project(user_id):
    conn = sqlite3.connect('remont.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, budget FROM projects WHERE id=?", (str(user_id),))
    row = cursor.fetchone()
    if row:
        project_id, budget = row[0], row[1]
    else:
        project_id = str(user_id)
        cursor.execute("INSERT INTO projects (id, budget) VALUES (?, ?)", (project_id, 500000))
        conn.commit()
        budget = 500000
    conn.close()
    return project_id, budget

@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    project_id, _ = get_or_create_project(user_id)
    
    # Ссылка на ваш Фронтенд на GitHub
    WEBAPP_URL = "https://github.io"

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_app = types.KeyboardButton("📊 Открыть Ремонт-Панель", web_app=types.WebAppInfo(url=f"{WEBAPP_URL}?pid={project_id}"))
    markup.add(btn_app)
    
    welcome_text = "🔨 Менеджер ремонта готов! Нажмите кнопку ниже, чтобы открыть панель управления:"
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

# ДОБАВЛЯЕМ СПЕЦИАЛЬНЫЙ СИСТЕМНЫЙ ПРОПУСК ДЛЯ БРАУЗЕРА ТЕЛЕФОНА
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

@app.route('/api/get_data')
def get_data():
    pid = request.args.get('pid', 'demo')
    conn = sqlite3.connect('remont.db')
    cursor = conn.cursor()
    cursor.execute("SELECT budget FROM projects WHERE id=?", (pid,))
    proj = cursor.fetchone()
    budget = proj[0] if proj else 500000
    cursor.execute("SELECT amount, category, description, user_name FROM expenses WHERE project_id=? ORDER BY id DESC", (pid,))
    rows = cursor.fetchall()
    expenses = [{"amount": r[0], "category": r[1], "description": r[2], "user_name": r[3]} for r in rows]
    conn.close()
    return jsonify({"budget": budget, "expenses": expenses})

@app.route('/api/add_expense', methods=['POST'])
def add_expense():
    data = request.json
    conn = sqlite3.connect('remont.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO expenses (project_id, amount, category, description, user_name) VALUES (?, ?, ?, ?, ?)",
                   (data['pid'], data['amount'], data['category'], data['description'], data['user_name']))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

@app.route('/api/set_budget', methods=['POST'])
def set_budget():
    data = request.json
    conn = sqlite3.connect('remont.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO projects (id, budget) VALUES (?, ?)", (data['pid'], data['budget']))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

def run_flask():
    app.run(host='0.0.0.0', port=10000)

if __name__ == '__main__':
    Thread(target=run_flask).start()
    bot.infinity_polling()
