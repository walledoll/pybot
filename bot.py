import os
import sys
import sqlite3
import requests
import hashlib
import uuid
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import telebot
from telebot import types

# ========== Настройки ==========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
API_KEY = os.getenv("API_KEY")  # например: https://your-bot.onrender.com

if not TELEGRAM_TOKEN or not WEBHOOK_URL:
    print("Ошибка: не заданы TELEGRAM_TOKEN или WEBHOOK_URL", file=sys.stderr)
    sys.exit(1)

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
app = Flask(__name__)

# ========== Глобальные переменные ==========
user_data = {}
payment_sessions = {}

# ========== Классы анализа и оплаты ==========

class OpenAIAnalyzer:
    def __init__(self):
        self.api_key = API_KEY
        self.base_url = "https://openai.api.proxyapi.ru/v1"
        self.model = "gpt-3.5-turbo"

    def get_user_history(self, user_id):
        conn = sqlite3.connect('dreams.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT emotion, dream_text, analysis, analysis_date 
            FROM dreams 
            WHERE user_id = ? 
            ORDER BY analysis_date DESC 
            LIMIT 3
        ''', (user_id,))
        history = cursor.fetchall()
        conn.close()
        return history

    def generate_dream_analysis(self, dream_text, emotion, user_info, user_id):
        history = self.get_user_history(user_id)
        history_context = ""
        if history:
            history_context = "\n\nПРЕДЫДУЩИЕ СНЫ ПОЛЬЗОВАТЕЛЯ:\n"
            for i, (prev_emotion, prev_dream, prev_analysis, date) in enumerate(history, 1):
                history_context += f"{i}. Эмоция: {prev_emotion}, Сон: {prev_dream[:100]}...\n"

        prompt = f"""
Ты опытный психолог и специалист по анализу снов. 
Проанализируй этот сон и дай интерпретацию с учетом истории пользователя.
Тон: Загадочный, но не мистический; спокойный и доверительный, эмпатичный.
Эмоция: Любопытство + безопасность
Целевая аудитория: 20-35 лет, интересуются психологией, саморазвитием

Использовать разговорный, но грамотный русский язык. Короткие абзацы, эмодзи для передачи тона, но без избытка. 

В первом сообщении добавь  текст: "Помните: я — инструмент для рефлексии, а не для медицинской или психологической диагностики.
ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ:
- Имя: {user_info.get('name', 'Не указано')}
- Эмоция во сне: {emotion}
{history_context}

ТЕКСТ СНА:
{dream_text}

УЧТИ В АНАЛИЗЕ:
1. Повторяющиеся темы из предыдущих снов
2. Эмоциональные паттерны
3. Развитие сюжетных линий

Дай глубокий анализ на русском языке (3-4 предложения) с учетом контекста.
"""

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
            "temperature": 0.7
        }

        try:
            response = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=data, timeout=30)
            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            else:
                return None
        except Exception as e:
            print(f"Ошибка OpenAI: {e}", file=sys.stderr)
            return None


class BasicAnalyzer:
    def generate_dream_analysis(self, dream_text, emotion, user_info):
        emotion_analysis = {
            'Страх/Тревога': 'Ваш сон отражает внутренние страхи и тревоги. Это может быть связано с неопределенностью в реальной жизни.',
            'Радость/Счастье': 'Позитивные эмоции во сне часто указывают на внутреннюю гармонию и удовлетворенность жизнью.',
            'Гнев/Раздражение': 'Эмоции гнева могут свидетельствовать о накопившемся напряжении или неразрешенных конфликтах.',
            'Смущение/Растерянность': 'Чувство растерянности связано с неопределенностью в принятии важных решений.',
            'Нейтрально': 'Нейтральные эмоции указывают на процесс обработки информации без сильных эмоциональных реакций.'
        }
        analysis = f"""
**Анализ вашего сна:**

**Основные наблюдения:**
{emotion_analysis.get(emotion, 'Сон отражает ваше текущее эмоциональное состояние.')}

**Детали сна:**
- Основная эмоция: {emotion}
- Длина описания: {len(dream_text)} символов

**Рекомендации:**
- Записывайте сны регулярно
- Обратите внимание на повторяющиеся образы
- Свяжите эмоции сна с событиями последних дней
"""
        return analysis


class RobokassaPayment:
    def __init__(self):
        self.merchant_login = "dreamanalyzer_bot"
        self.password1 = "test_password_1"
        self.password2 = "test_password_2"
        self.test_mode = True
        self.base_url = "https://auth.robokassa.ru/Merchant/Index.aspx"

    def generate_payment_url(self, amount, inv_id, description, user_id):
        signature_string = f"{self.merchant_login}:{amount}:{inv_id}:{self.password1}"
        signature = hashlib.md5(signature_string.encode('utf-8')).hexdigest()
        params = {
            'MerchantLogin': self.merchant_login,
            'OutSum': amount,
            'InvId': inv_id,
            'Description': description,
            'SignatureValue': signature,
            'IsTest': 1 if self.test_mode else 0
        }
        url_params = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{self.base_url}?{url_params}"

    def check_payment_status(self, inv_id):
        return "paid"  # упрощено для теста


# ========== Инициализация БД ==========
def init_db():
    conn = sqlite3.connect('dreams.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            birthdate TEXT,
            phone TEXT,
            save_history BOOLEAN,
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            premium_expiry TIMESTAMP
        )
    ''')

    try:
        cursor.execute("SELECT premium_expiry FROM users LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute('ALTER TABLE users ADD COLUMN premium_expiry TIMESTAMP')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dreams (
            dream_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            dream_text TEXT,
            emotion TEXT,
            analysis TEXT,
            analysis_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            payment_id TEXT PRIMARY KEY,
            user_id INTEGER,
            amount REAL,
            status TEXT,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()


def save_user(user_id, name, birthdate, phone, save_history):
    conn = sqlite3.connect('dreams.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, name, birthdate, phone, save_history)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, name, birthdate, phone, save_history))
    conn.commit()
    conn.close()


def save_dream(user_id, dream_text, emotion, analysis=None):
    conn = sqlite3.connect('dreams.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO dreams (user_id, dream_text, emotion, analysis)
        VALUES (?, ?, ?, ?)
    ''', (user_id, dream_text, emotion, analysis))
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = sqlite3.connect('dreams.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user


def is_premium_user(user_id):
    conn = sqlite3.connect('dreams.db')
    cursor = conn.cursor()
    cursor.execute('SELECT premium_expiry FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result and result[0]:
        try:
            expiry_date = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S')
            return expiry_date > datetime.now()
        except ValueError:
            return False
    return False


def activate_premium(user_id, duration_days=30):
    conn = sqlite3.connect('dreams.db')
    cursor = conn.cursor()
    expiry_date = datetime.now() + timedelta(days=duration_days)
    cursor.execute('''
        UPDATE users 
        SET premium_expiry = ? 
        WHERE user_id = ?
    ''', (expiry_date.strftime('%Y-%m-%d %H:%M:%S'), user_id))
    conn.commit()
    conn.close()


# ========== Инициализация ==========
init_db()
api_available = False
try:
    test_analyzer = OpenAIAnalyzer()
    test_resp = test_analyzer.generate_dream_analysis("test", "Нейтрально", {"name": "test"}, 1)
    api_available = test_resp is not None
except:
    pass

dream_analyzer = OpenAIAnalyzer() if api_available else BasicAnalyzer()
robokassa = RobokassaPayment()


# ========== Telegram обработчики ==========
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = "Привет! Я бот для анализа снов с искусственным интеллектом! 🌙\n\n"
    if api_available:
        welcome_text += "🤖 Режим: AI-анализ активирован\n"
    else:
        welcome_text += "📝 Режим: Базовый анализ\n"
    welcome_text += """
Используй команды:
/reg - регистрация
/analyze - анализ сна
/history - история снов
/stats - статистика
/premium - премиум доступ
/help - помощь
"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('📊 Анализ сна', '📚 История', '📊 Статистика')
    markup.add('💎 Премиум', 'ℹ️ Помощь')
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)


@bot.message_handler(commands=['premium'])
@bot.message_handler(func=lambda m: m.text == '💎 Премиум')
def show_premium_plans(message):
    user_id = message.chat.id
    if is_premium_user(user_id):
        bot.send_message(message.chat.id, "💎 У вас уже есть премиум доступ!")
        return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('💳 1 месяц - 100 руб.', callback_data='premium_1month'))
    markup.add(types.InlineKeyboardButton('💳 3 месяца - 250 руб.', callback_data='premium_3month'))
    bot.send_message(message.chat.id, "💎 **ПРЕМИУМ ДОСТУП**\n\nВыберите тариф:", reply_markup=markup, parse_mode='Markdown')


@bot.callback_query_handler(func=lambda call: call.data.startswith('premium_'))
def handle_premium_selection(call):
    user_id = call.message.chat.id
    if call.data == 'premium_1month':
        amount, duration = 100.00, 30
    else:
        amount, duration = 250.00, 90
    inv_id = str(uuid.uuid4().int)[:10]
    payment_url = robokassa.generate_payment_url(amount, inv_id, f"Премиум на {duration} дней", user_id)
    payment_sessions[inv_id] = {'user_id': user_id, 'amount': amount, 'duration_days': duration}
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('💳 Перейти к оплате', url=payment_url))
    markup.add(types.InlineKeyboardButton('🔄 Проверить оплату', callback_data=f'check_payment_{inv_id}'))
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"💎 Оплата премиум доступа\nСумма: {amount} руб.\nПериод: {duration} дней\nID: {inv_id}",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('check_payment_'))
def handle_check_payment(call):
    inv_id = call.data.replace('check_payment_', '')
    status = robokassa.check_payment_status(inv_id)
    if status == "paid" and inv_id in payment_sessions:
        session = payment_sessions[inv_id]
        activate_premium(session['user_id'], session['duration_days'])
        del payment_sessions[inv_id]
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="✅ Оплата успешна! Премиум активирован!"
        )
    else:
        bot.answer_callback_query(call.id, "⏳ Платеж не подтверждён...")


@bot.message_handler(commands=['analyze'])
@bot.message_handler(func=lambda m: m.text == '📊 Анализ сна')
def start_analysis(message):
    user_id = message.chat.id
    if not is_premium_user(user_id):
        conn = sqlite3.connect('dreams.db')
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM dreams WHERE user_id = ? AND date(analysis_date) = date("now")', (user_id,))
        count = cursor.fetchone()[0]
        conn.close()
        if count >= 3:
            bot.send_message(message.chat.id, "❌ Достигнут лимит 3 анализов в день. Оформите /premium")
            return
    bot.send_message(message.chat.id, "Расскажите, что вам приснилось?")
    bot.register_next_step_handler(message, analyze_dream)


def analyze_dream(message):
    user_id = message.chat.id
    user_data[user_id] = {'dream': message.text}
    keyboard = types.InlineKeyboardMarkup()
    emotions = ['Страх/Тревога', 'Радость/Счастье', 'Гнев/Раздражение', 'Смущение/Растерянность', 'Нейтрально']
    for e in emotions:
        keyboard.add(types.InlineKeyboardButton(e, callback_data=f'emotion_{e}'))
    bot.send_message(message.chat.id, "Какую эмоцию вы чувствовали?", reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data.startswith('emotion_'))
def handle_emotion_choice(call):
    emotion = call.data.replace('emotion_', '')
    user_id = call.message.chat.id
    user_data[user_id]['emotion'] = emotion
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"Анализирую сон...")
    dream_text = user_data[user_id]['dream']
    if api_available:
        analysis = dream_analyzer.generate_dream_analysis(dream_text, emotion, user_data.get(user_id, {}), user_id)
    else:
        analysis = BasicAnalyzer().generate_dream_analysis(dream_text, emotion, user_data.get(user_id, {}))
    if not analysis:
        analysis = BasicAnalyzer().generate_dream_analysis(dream_text, emotion, user_data.get(user_id, {}))
    save_dream(user_id, dream_text, emotion, analysis)
    bot.send_message(
        user_id,
        f"**📖 Анализ вашего сна:**\n\n{analysis}\n\n*Эмоция: {emotion}*",
        parse_mode='Markdown'
    )


# Остальные обработчики (/reg, /history, /stats и т.д.) — добавьте по аналогии

# ========== Flask-роуты ==========
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return jsonify({'ok': True})
    return jsonify({'error': 'Invalid content-type'}), 400


@app.route('/setwebhook', methods=['GET'])
def set_webhook():
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
    return "Webhook установлен!"


@app.route('/health', methods=['GET'])
def health():
    return "OK", 200


# ========== Запуск ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)