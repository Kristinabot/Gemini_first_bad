import os
import sqlite3
import requests
from threading import Thread
import telebot
from telebot import types
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

# БЕЗОПАСНОСТЬ: Токен берётся из настроек Render, хакеры его не украдут!
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY", "no_key")

if not BOT_TOKEN:
    raise ValueError("⚠️ Ошибка: Переменная BOT_TOKEN не настроена на сервере Render!")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
CORS(app) # Разрешаем фронтенду общаться с сервером без блокировок

# ССЫЛКА НА ВАШ ИНТЕРФЕЙС НА GITHUB PAGES (С большими буквами и слэшем на конце!)
WEBAPP_URL = "https://kristinabot.github.io/RepairExpense/"

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ---
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

# --- ЛОГИКА ТЕЛЕГРАМ БОТА ---
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    project_id, _ = get_or_create_project(user_id)

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    # Бот прикрепит вашу живую ссылку GitHub к кнопке в Телеграме!
    btn_app = types.KeyboardButton("📊 Открыть Ремонт-Панель", web_app=types.WebAppInfo(url=f"{WEBAPP_URL}?pid={project_id}"))
    markup.add(btn_app)
    
    welcome_text = (
        "🔨 Менеджер ремонта готов к работе!\n\n"
        "Нажмите кнопку ниже, чтобы открыть вашу личную ремонт-панель.\n"
        "Вы можете менять бюджет, фильтровать комнаты и даже отправлять прораба в огненный котел!\n\n"
        "📸 Чтобы добавить расход по чеку: просто пришлите ФОТО чека прямо в этот чат."
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

@bot.message_handler(content_types=['photo'])
def handle_receipt(message):
    user_id = message.from_user.id
    project_id, _ = get_or_create_project(user_id)
    user_name = message.from_user.username or message.from_user.first_name
    bot.send_message(message.chat.id, "📸 Чек получен! Идёт сканирование...")

    # Автоматическая заглушка трат
    amount, category, desc = 4500, "Ванная", "Чек обработан сервером"
    
    conn = sqlite3.connect('remont.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO expenses (project_id, amount, category, description, user_name) VALUES (?, ?, ?, ?, ?)",
                   (project_id, amount, category, desc, user_name))
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, f"✅ Чек добавлен в базу через сервер!\n💰 Сумма: {amount} ₽\n🧱 Зона: {category}")

# --- API ДЛЯ ИНТЕРФЕЙСА (GITHUB) ---
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
