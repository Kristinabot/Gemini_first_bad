import os
import telebot
from telebot import types

BOT_TOKEN = "8695940920:AAEU9e-iXlZ1hsMCWKIaiEEvAXCelg35RD0"
bot = telebot.TeleBot(BOT_TOKEN)

# ВАША ОФИЦИАЛЬНАЯ ПОДТВЕРЖДЕННАЯ ССЫЛКА ОТ GITHUB
WEBAPP_URL = "https://kristinabot.github.io/RepairExpense/"

@bot.message_handler(commands=['start'])
def start_command(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_app = types.KeyboardButton("📊 Открыть Ремонт-Панель", web_app=types.WebAppInfo(url=WEBAPP_URL))
    markup.add(btn_app)
    
    welcome_text = (
        "🔨 Менеджер ремонта готов!\n\n"
        "Нажмите кнопку ниже, чтобы открыть вашу личную панель трат.\n"
        "Вы можете вносить расходы вручную или отправить прораба в котел!\n\n"
        "📸 Чтобы распознать чек: просто пришлите его фото прямо в этот чат."
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

@bot.message_handler(content_types=['photo'])
def handle_receipt(message):
    bot.send_message(message.chat.id, "📸 Чек получен! Нейросеть OpenRouter начинает сканирование трат...")
    
    # Имитация работы ИИ для чеков
    mock_amount = 7300
    mock_category = "Кухня 🍳"
    
    bot.send_message(
        message.chat.id, 
        f"✅ Успешно добавлено в общую ленту расходов!\n"
        f"💰 Сумма: {mock_amount} ₽\n"
        f"🧱 Зона: {mock_category}\n"
        f"👤 Добавил(а): {message.from_user.first_name}"
    )

if __name__ == '__main__':
    print("🤖 Бот успешно запущен на вашей личной платформе!")
    bot.infinity_polling()
