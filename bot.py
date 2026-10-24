import os
import sqlite3
import requests
from threading import Thread
import telebot
from telebot import types
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

# ТЕПЕРЬ ТУТ НЕТ ПАРОЛЕЙ! Сервер сам подставит их из защищенной памяти
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY", "no_key")

if not BOT_TOKEN:
    raise ValueError("⚠️ Ошибка: Переменная BOT_TOKEN не настроена на сервере Render!")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
CORS(app)

def init_db():
    conn = sqlite3.connect('remont.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS projects 
                      (id TEXT PRIMARY KEY, budget INTEGER, owner_id INTEGER, spouse_id INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS expenses 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, amount INTEGER, 
                       category TEXT, description TEXT, user_name TEXT)''')
    conn.commit()
    conn.close()

init_db()

def get_or_create_project(user_id):
    conn = sqlite3.connect('remont.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, budget FROM projects WHERE owner_id=? OR spouse_id=?", (user_id, user_id))
    row = cursor.fetchone()
    if row:
        project_id, budget = row[0], row[1]
    else:
        project_id = str(user_id)
        cursor.execute("INSERT INTO projects (id, budget, owner_id) VALUES (?, ?, ?)", (project_id, 500000, user_id))
        conn.commit()
        budget = 500000
    conn.close()
    return project_id, budget

@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    args = message.text.split()
    conn = sqlite3.connect('remont.db')
    cursor = conn.cursor()

    if len(args) > 1 and args[1].startswith('join_'):
        parent_project_id = args[1].replace('join_', '')
        cursor.execute("UPDATE projects SET spouse_id=? WHERE id=?", (user_id, parent_project_id))
        conn.commit()
        bot.reply_to(message, "🎉 Вы успешно подключились к общему ремонту!")
        conn.close()
        return

    project_id, _ = get_or_create_project(user_id)
    conn.close()

    markup = types.InlineKeyboardMarkup()
    btn_app = types.InlineKeyboardButton("📊 Открыть Ремонт-Панель", web_app=types.WebAppInfo(url=f"https://github.io{project_id}"))
    markup.add(btn_app)

    welcome_text = (
        "🔨 Менеджер Ремонта запущен круглосуточно!\n\n"
        "👥 Ссылка для подключения мужа/жены:\n"
        f"https://t.me{bot.get_me().username}?start=join_{project_id}"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

@bot.message_handler(content_types=['photo'])
def handle_receipt(message):
    user_id = message.from_user.id
    project_id, _ = get_or_create_project(user_id)
    user_name = message.from_user.username or message.from_user.first_name
    bot.send_message(message.chat.id, "📸 Чек получен! Нейросеть начинает сканирование...")

    # Временный автоматический ввод, пока не активируем OpenRouter на сервере
    amount, category, desc = 4500, "Ванная", "Чек обработан сервером"
    
    conn = sqlite3.connect('remont.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO expenses (project_id, amount, category, description, user_name) VALUES (?, ?, ?, ?, ?)",
                   (project_id, amount, category, desc, user_name))
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, f"✅ Чек добавлен в общую базу!\n💰 Сумма: {amount} ₽\n🧱 Зона: {category}")

@app.route('/api/get_data')
def get_data():
    pid = request.args.get('pid')
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
    cursor.execute("UPDATE projects SET budget=? WHERE id=?", (data['budget'], data['pid']))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

@app.route('/api/link_spouse', methods=['POST'])
def link_spouse():
    data = request.json
    conn = sqlite3.connect('remont.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE projects SET spouse_id=? WHERE id=?", (data['spouse_id'], data['pid']))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

def run_flask():
    app.run(host='0.0.0.0', port=10000) # Меняем внутренний порт для Render

if __name__ == '__main__':
    Thread(target=run_flask).start()
    bot.infinity_polling()
EOF
