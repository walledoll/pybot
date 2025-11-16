import telebot
from telebot import types
import sqlite3
import requests
import time
import sys
import hashlib
import os
import uuid
import json
from datetime import datetime, timedelta

# Устанавливаем кодировку для Windows
try:
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass


# Проверка подключения к интернету
def check_internet():
    try:
        requests.get('https://api.telegram.org', timeout=10)
        return True
    except:
        return False


print("Проверяем интернет соединение...")
if not check_internet():
    print("НЕТ ИНТЕРНЕТА! Проверьте подключение")
    sys.exit(1)

print("Интернет работает")

# Инициализация бота
bot = telebot.TeleBot('8518996408:AAEuKz0Dvoif0Rw71Do67Fs7zOyq5jsbluM')


# Проверка токена бота
def check_bot_token():
    try:
        bot_info = bot.get_me()
        print(f"Бот @{bot_info.username} подключен!")
        return True
    except Exception as e:
        print(f"Ошибка токена бота: {e}")
        return False


print("Проверяем токен бота...")
if not check_bot_token():
    print("Неверный токен бота!")
    sys.exit(1)


# КЛАСС ДЛЯ РАБОТЫ С OPENAI API
class OpenAIAnalyzer:
    def __init__(self):
        self.api_key = "sk-kQdRlPAG1zDhaYRxHOrydjdc9BYoarFr"
        self.base_url = "https://openai.api.proxyapi.ru/v1"
        self.model = "gpt-3.5-turbo"

    def get_user_history(self, user_id):
        """Получить историю снов пользователя"""
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
        """Анализ сна с учетом истории"""

        # Получаем историю пользователя
        history = self.get_user_history(user_id)

        # Формируем контекст с историей
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

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 500,
            "temperature": 0.7
        }

        try:
            print("Отправляем запрос к OpenAI API...")
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                analysis = result['choices'][0]['message']['content']
                print("Анализ от OpenAI получен!")
                return analysis
            else:
                print(f"Ошибка API: {response.status_code}")
                return None

        except Exception as e:
            print(f"Ошибка анализа: {e}")
            return None


# КЛАСС ДЛЯ БАЗОВОГО АНАЛИЗА
class BasicAnalyzer:
    def generate_dream_analysis(self, dream_text, emotion, user_info):
        """Базовый анализ без OpenAI"""

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


# КЛАСС ДЛЯ РАБОТЫ С РОБОКАССОЙ
class RobokassaPayment:
    def __init__(self):
        self.merchant_login = "dreamanalyzer_bot"
        self.password1 = "test_password_1"
        self.password2 = "test_password_2"
        self.test_mode = True
        self.base_url = "https://auth.robokassa.ru/Merchant/Index.aspx"

    def generate_payment_url(self, amount, inv_id, description, user_id):
        """Генерируем URL для оплаты в Робокассе"""

        # Формируем подпись
        signature_string = f"{self.merchant_login}:{amount}:{inv_id}:{self.password1}"
        signature = hashlib.md5(signature_string.encode('utf-8')).hexdigest()

        # Формируем параметры
        params = {
            'MerchantLogin': self.merchant_login,
            'OutSum': amount,
            'InvId': inv_id,
            'Description': description,
            'SignatureValue': signature,
            'IsTest': 1 if self.test_mode else 0
        }

        # Формируем URL
        url_params = "&".join([f"{k}={v}" for k, v in params.items()])
        payment_url = f"{self.base_url}?{url_params}"

        return payment_url

    def check_payment_status(self, inv_id):
        """Проверяем статус платежа (упрощенная версия для тестов)"""
        # В тестовом режиме просто возвращаем успешный статус
        if self.test_mode:
            return "paid"

        # В реальном режиме здесь будет запрос к API Робокассы
        # Для тестов всегда считаем, что платеж прошел
        return "paid"


# Проверяем доступность OpenAI API
def check_openai_available():
    try:
        analyzer = OpenAIAnalyzer()
        test_response = analyzer.generate_dream_analysis(
            "Тестовый сон", "Нейтрально", {"name": "Тест"}, 123456
        )
        if test_response and "Ошибка" not in test_response:
            print("OpenAI API доступен!")
            return True
        else:
            print("OpenAI API недоступен")
            return False
    except Exception as e:
        print(f"OpenAI API недоступен: {e}")
        return False


print("Проверяем подключение к OpenAI API...")
api_available = check_openai_available()

# Создаем экземпляр анализатора
if api_available:
    dream_analyzer = OpenAIAnalyzer()
    print("AI-анализ активирован!")
else:
    dream_analyzer = BasicAnalyzer()
    print("Используется базовый анализ")

# Инициализация Робокассы
robokassa = RobokassaPayment()

# Глобальные переменные
user_data = {}
payment_sessions = {}


# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('dreams.db', check_same_thread=False)
    cursor = conn.cursor()

    # Таблица пользователей
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

    # Добавляем поле premium_expiry если его нет
    try:
        cursor.execute("SELECT premium_expiry FROM users LIMIT 1")
    except sqlite3.OperationalError:
        print("Добавляем поле premium_expiry в таблицу users...")
        cursor.execute('ALTER TABLE users ADD COLUMN premium_expiry TIMESTAMP')

    # Таблица снов
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

    # Таблица платежей
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
    conn = sqlite3.connect('dreams.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, name, birthdate, phone, save_history)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, name, birthdate, phone, save_history))
    conn.commit()
    conn.close()


def save_dream(user_id, dream_text, emotion, analysis=None):
    conn = sqlite3.connect('dreams.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO dreams (user_id, dream_text, emotion, analysis)
        VALUES (?, ?, ?, ?)
    ''', (user_id, dream_text, emotion, analysis))
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = sqlite3.connect('dreams.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user


def is_premium_user(user_id):
    """Проверяем, есть ли у пользователя активная премиум подписка"""
    conn = sqlite3.connect('dreams.db', check_same_thread=False)
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
    """Активируем премиум подписку"""
    conn = sqlite3.connect('dreams.db', check_same_thread=False)
    cursor = conn.cursor()

    expiry_date = datetime.now() + timedelta(days=duration_days)

    cursor.execute('''
        UPDATE users 
        SET premium_expiry = ? 
        WHERE user_id = ?
    ''', (expiry_date.strftime('%Y-%m-%d %H:%M:%S'), user_id))

    conn.commit()
    conn.close()


# Функция для просмотра базы данных
def view_database():
    conn = sqlite3.connect('dreams.db')
    cursor = conn.cursor()

    print("=" * 50)
    print("ПОЛЬЗОВАТЕЛИ:")
    print("=" * 50)
    cursor.execute('SELECT * FROM users')
    users = cursor.fetchall()
    for user in users:
        # Безопасный вывод - проверяем длину кортежа
        user_info = f"ID: {user[0]}, Имя: {user[1]}, Дата рождения: {user[2]}, Телефон: {user[3]}"
        if len(user) > 6:  # Если есть поле premium_expiry
            user_info += f", Премиум до: {user[6]}"
        print(user_info)

    print("\n" + "=" * 50)
    print("СНЫ:")
    print("=" * 50)
    cursor.execute(
        'SELECT d.dream_id, u.name, d.emotion, d.analysis_date, substr(d.dream_text, 1, 50) as short_dream FROM dreams d LEFT JOIN users u ON d.user_id = u.user_id ORDER BY d.analysis_date DESC')
    dreams = cursor.fetchall()
    for dream in dreams:
        print(f"ID: {dream[0]}, Пользователь: {dream[1]}, Эмоция: {dream[2]}, Дата: {dream[3]}")
        print(f"Сон: {dream[4]}...")
        print("-" * 30)

    conn.close()


# Инициализируем БД
init_db()


# Обработчики команд
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    print(f"Получена команда /start от {message.chat.id}")

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

Расскажите мне свой сон, и я помогу его проанализировать!
"""

    # Создаем клавиатуру
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton('📊 Анализ сна')
    btn2 = types.KeyboardButton('📚 История')
    btn3 = types.KeyboardButton('📊 Статистика')
    btn4 = types.KeyboardButton('💎 Премиум')
    btn5 = types.KeyboardButton('ℹ️ Помощь')
    markup.add(btn1, btn2, btn3)
    markup.add(btn4, btn5)

    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)


@bot.message_handler(commands=['premium'])
@bot.message_handler(func=lambda message: message.text == '💎 Премиум')
def show_premium_plans(message):
    user_id = message.chat.id

    if is_premium_user(user_id):
        conn = sqlite3.connect('dreams.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('SELECT premium_expiry FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()

        expiry_date = result[0] if result else "неизвестно"

        bot.send_message(
            message.chat.id,
            f"💎 **У вас уже есть премиум доступ!**\n\n"
            f"Премиум действует до: {expiry_date}\n\n"
            "Вы можете пользоваться всеми премиум функциями:\n"
            "• ✅ Неограниченное количество анализов\n"
            "• ✅ Расширенный AI-анализ\n"
            "• ✅ Сохранение истории снов\n\n"
            "Спасибо за доверие! 🌟"
        )
        return

    markup = types.InlineKeyboardMarkup()
    btn_pay_month = types.InlineKeyboardButton('💳 1 месяц - 100 руб.', callback_data='premium_1month')
    btn_pay_3month = types.InlineKeyboardButton('💳 3 месяца - 250 руб.', callback_data='premium_3month')
    markup.add(btn_pay_month)
    markup.add(btn_pay_3month)

    bot.send_message(
        message.chat.id,
        "💎 **ПРЕМИУМ ДОСТУП**\n\n"
        "Премиум функции:\n"
        "• ✅ Неограниченное количество анализов\n"
        "• ✅ Расширенный AI-анализ\n"
        "• ✅ Сохранение истории снов\n\n"
        "Выберите тариф:",
        reply_markup=markup,
        parse_mode='Markdown'
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('premium_'))
def handle_premium_selection(call):
    user_id = call.message.chat.id

    if call.data == 'premium_1month':
        amount = 100.00
        description = "Премиум подписка на 1 месяц"
        duration_days = 30
    else:  # premium_3month
        amount = 250.00
        description = "Премиум подписка на 3 месяца"
        duration_days = 90

    # Генерируем уникальный ID для платежа
    inv_id = str(uuid.uuid4().int)[:10]

    # Создаем платеж в Робокассе
    payment_url = robokassa.generate_payment_url(amount, inv_id, description, user_id)

    if payment_url:
        # Сохраняем информацию о сессии
        payment_sessions[inv_id] = {
            'user_id': user_id,
            'amount': amount,
            'duration_days': duration_days
        }

        markup = types.InlineKeyboardMarkup()
        btn_pay = types.InlineKeyboardButton('💳 Перейти к оплате', url=payment_url)
        btn_check = types.InlineKeyboardButton('🔄 Проверить оплату', callback_data=f'check_payment_{inv_id}')
        markup.add(btn_pay)
        markup.add(btn_check)

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"💎 **Оплата премиум доступа**\n\n"
                 f"Сумма: {amount} руб.\n"
                 f"Период: {duration_days} дней\n"
                 f"ID платежа: {inv_id}\n\n"
                 f"Нажмите кнопку ниже для оплаты:",
            reply_markup=markup,
            parse_mode='Markdown'
        )
    else:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="❌ **Ошибка при создании платежа**\n\n"
                 "Пожалуйста, попробуйте позже или свяжитесь с поддержкой: @aleexaandraa",
            parse_mode='Markdown'
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith('check_payment_'))
def handle_check_payment(call):
    inv_id = call.data.replace('check_payment_', '')
    status = robokassa.check_payment_status(inv_id)

    if status == "paid":
        # Платеж успешен
        if inv_id in payment_sessions:
            session_data = payment_sessions[inv_id]
            user_id = session_data['user_id']
            duration_days = session_data['duration_days']

            # Активируем премиум
            activate_premium(user_id, duration_days)

            # Удаляем сессию
            del payment_sessions[inv_id]

            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="✅ **Оплата успешно завершена!**\n\n"
                     "Премиум доступ активирован! Теперь вам доступны все функции:\n"
                     "• ✅ Неограниченное количество анализов\n"
                     "• ✅ Расширенный AI-анализ\n"
                     "• ✅ Сохранение истории снов\n\n"
                     "Спасибо за покупку! 🌟",
                parse_mode='Markdown'
            )
        else:
            bot.answer_callback_query(call.id, "❌ Сессия платежа не найдена")
    else:
        bot.answer_callback_query(call.id, "⏳ Платеж еще не подтвержден...")


@bot.message_handler(commands=['analyze'])
@bot.message_handler(func=lambda message: message.text == '📊 Анализ сна')
def start_analysis(message):
    user_id = message.chat.id

    # Проверяем лимиты для бесплатных пользователей
    if not is_premium_user(user_id):
        conn = sqlite3.connect('dreams.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM dreams 
            WHERE user_id = ? AND date(analysis_date) = date('now')
        ''', (user_id,))
        today_analyses = cursor.fetchone()[0]
        conn.close()

        if today_analyses >= 3:  # Лимит 3 анализа в день
            bot.send_message(
                message.chat.id,
                "❌ **Достигнут дневной лимит анализов!**\n\n"
                "Бесплатные пользователи могут анализировать до 3 снов в день.\n"
                "Для неограниченного количества анализов оформите /premium",
                parse_mode='Markdown'
            )
            return

    bot.send_message(
        message.chat.id,
        "Расскажите, что вам приснилось? Постарайтесь вспомнить как можно больше деталей."
    )
    bot.register_next_step_handler(message, analyze_dream)


@bot.message_handler(commands=['history'])
@bot.message_handler(func=lambda message: message.text == '📚 История')
def show_history(message):
    user_id = message.chat.id

    conn = sqlite3.connect('dreams.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT emotion, dream_text, analysis, analysis_date 
        FROM dreams 
        WHERE user_id = ? 
        ORDER BY analysis_date DESC 
        LIMIT 5
    ''', (user_id,))

    dreams = cursor.fetchall()
    conn.close()

    if not dreams:
        bot.send_message(message.chat.id,
                         "📭 У вас пока нет сохраненных снов.\n\nИспользуйте /analyze чтобы проанализировать первый сон!")
        return

    response = "📚 **Ваша история снов:**\n\n"

    for i, (emotion, dream_text, analysis, date) in enumerate(dreams, 1):
        response += f"**{i}. {emotion}** ({date[:10]})\n"
        response += f"💭 *Сон:* {dream_text[:80]}...\n"
        response += f"🔍 *Анализ:* {analysis[:120]}...\n\n"

    response += "---\nВсего снов: {}".format(len(dreams))

    bot.send_message(message.chat.id, response, parse_mode='Markdown')


@bot.message_handler(commands=['stats'])
@bot.message_handler(func=lambda message: message.text == '📊 Статистика')
def show_stats(message):
    user_id = message.chat.id

    conn = sqlite3.connect('dreams.db', check_same_thread=False)
    cursor = conn.cursor()

    # Статистика по эмоциям
    cursor.execute('''
        SELECT emotion, COUNT(*) as count 
        FROM dreams 
        WHERE user_id = ? 
        GROUP BY emotion 
        ORDER BY count DESC
    ''', (user_id,))

    emotion_stats = cursor.fetchall()

    # Общее количество снов
    cursor.execute('SELECT COUNT(*) FROM dreams WHERE user_id = ?', (user_id,))
    total_dreams = cursor.fetchone()[0]

    # Первый сон
    cursor.execute('SELECT analysis_date FROM dreams WHERE user_id = ? ORDER BY analysis_date ASC LIMIT 1', (user_id,))
    first_dream = cursor.fetchone()

    conn.close()

    if total_dreams == 0:
        bot.send_message(message.chat.id,
                         "📭 У вас пока нет сохраненных снов.\n\nИспользуйте /analyze чтобы проанализировать первый сон!")
        return

    response = f"📊 **Ваша статистика снов:**\n\n"
    response += f"📈 Всего проанализировано снов: **{total_dreams}**\n"

    if first_dream:
        response += f"📅 Первый анализ: {first_dream[0][:10]}\n"

    response += "\n**📋 Распределение по эмоциям:**\n"

    for emotion, count in emotion_stats:
        percentage = (count / total_dreams) * 100
        response += f"• {emotion}: {count} ({percentage:.1f}%)\n"

    # Анализ преобладающих эмоций
    if emotion_stats:
        main_emotion, main_count = emotion_stats[0]
        response += f"\n🎯 **Основная эмоция:** {main_emotion}\n"
        response += f"Эта эмоция встречается в {main_count} из {total_dreams} снов"

    bot.send_message(message.chat.id, response, parse_mode='Markdown')


@bot.message_handler(commands=['reg'])
def start_registration(message):
    print(f"Начата регистрация для {message.chat.id}")
    bot.send_message(message.chat.id, "Давайте зарегистрируемся! Как вас зовут?")
    bot.register_next_step_handler(message, get_name)


def get_name(message):
    user_id = message.chat.id
    user_data[user_id] = {'name': message.text}
    print(f"Имя пользователя {user_id}: {message.text}")

    bot.send_message(message.chat.id, 'Укажите дату рождения в формате ДД.ММ.ГГГГ (например, 14.11.2000)')
    bot.register_next_step_handler(message, get_birthdate)


def get_birthdate(message):
    user_id = message.chat.id
    user_data[user_id]['birthdate'] = message.text
    print(f"Дата рождения пользователя {user_id}: {message.text}")

    bot.send_message(message.chat.id, 'Введите ваш номер телефона:')
    bot.register_next_step_handler(message, get_phone)


def get_phone(message):
    user_id = message.chat.id
    user_data[user_id]['phone'] = message.text
    print(f"Телефон пользователя {user_id}: {message.text}")

    user = user_data[user_id]
    keyboard = types.InlineKeyboardMarkup()
    key_yes = types.InlineKeyboardButton(text='Да', callback_data='confirm_yes')
    key_no = types.InlineKeyboardButton(text='Нет', callback_data='confirm_no')
    keyboard.add(key_yes, key_no)

    question = f"Проверьте данные:\nИмя: {user['name']}\nДата рождения: {user['birthdate']}\nТелефон: {user['phone']}\n\nВсё верно?"
    bot.send_message(message.chat.id, text=question, reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_'))
def callback_handler(call):
    if call.data == 'confirm_yes':
        user_id = call.message.chat.id
        if user_id in user_data:
            save_user(
                user_id=user_id,
                name=user_data[user_id]['name'],
                birthdate=user_data[user_id]['birthdate'],
                phone=user_data[user_id]['phone'],
                save_history=True
            )
            print(f"Пользователь {user_id} зарегистрирован")

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="✅ Отлично! Регистрация завершена! Теперь расскажите, что вам приснилось? Постарайтесь вспомнить как можно больше деталей."
        )
        bot.register_next_step_handler(call.message, analyze_dream)

    elif call.data == 'confirm_no':
        user_id = call.message.chat.id
        if user_id in user_data:
            del user_data[user_id]
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Давайте начнем регистрацию заново. Как вас зовут?"
        )
        bot.register_next_step_handler(call.message, get_name)


def analyze_dream(message):
    dream_description = message.text
    user_id = message.chat.id
    print(f"Пользователь {user_id} отправил сон: {dream_description[:50]}...")

    if user_id in user_data:
        user_data[user_id]['dream'] = dream_description
    else:
        user_data[user_id] = {'dream': dream_description}

    if api_available:
        bot.send_message(message.chat.id, "🤖 Анализирую ваш сон с помощью нейросети... Это займет 10-30 секунд.")
    else:
        bot.send_message(message.chat.id, "📝 Анализирую ваш сон...")

    keyboard = types.InlineKeyboardMarkup()
    btn_fear = types.InlineKeyboardButton('Страх/Тревога', callback_data='emotion_fear')
    btn_joy = types.InlineKeyboardButton('Радость/Счастье', callback_data='emotion_joy')
    btn_anger = types.InlineKeyboardButton('Гнев/Раздражение', callback_data='emotion_anger')
    btn_confusion = types.InlineKeyboardButton('Смущение/Растерянность', callback_data='emotion_confusion')
    btn_neutral = types.InlineKeyboardButton('Нейтрально', callback_data='emotion_neutral')
    keyboard.row(btn_fear, btn_joy)
    keyboard.row(btn_anger, btn_confusion)
    keyboard.row(btn_neutral)

    bot.send_message(
        message.chat.id,
        "Какую основную эмоцию вы чувствовали во сне?",
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('emotion_'))
def handle_emotion_choice(call):
    emotion_map = {
        'emotion_fear': 'Страх/Тревога',
        'emotion_joy': 'Радость/Счастье',
        'emotion_anger': 'Гнев/Раздражение',
        'emotion_confusion': 'Смущение/Растерянность',
        'emotion_neutral': 'Нейтрально'
    }

    emotion = emotion_map.get(call.data, 'Неизвестная эмоция')
    user_id = call.message.chat.id

    print(f"Пользователь {user_id} выбрал эмоцию: {emotion}")

    if user_id in user_data:
        user_data[user_id]['emotion'] = emotion

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"🎭 Вы выбрали: {emotion}\n\n🔄 Продолжаю анализ..."
    )

    # АНАЛИЗ СНА
    if user_id in user_data and 'dream' in user_data[user_id]:
        dream_text = user_data[user_id]['dream']

        # Добавляем индикатор процесса
        processing_msg = bot.send_message(user_id, "🔍 Анализирую сон...")

        if api_available:
            analysis = dream_analyzer.generate_dream_analysis(
                dream_text=dream_text,
                emotion=emotion,
                user_info=user_data.get(user_id, {}),
                user_id=user_id
            )
        else:
            analysis = BasicAnalyzer().generate_dream_analysis(
                dream_text, emotion, user_data.get(user_id, {})
            )

        # Если AI не сработал, используем базовый анализ
        if not analysis:
            analysis = BasicAnalyzer().generate_dream_analysis(dream_text, emotion, user_data.get(user_id, {}))

        # Удаляем сообщение о процессе
        try:
            bot.delete_message(user_id, processing_msg.message_id)
        except:
            pass

        save_dream(
            user_id=user_id,
            dream_text=dream_text,
            emotion=emotion,
            analysis=analysis
        )

        # Отправляем анализ пользователю
        bot.send_message(
            user_id,
            f"**📖 Анализ вашего сна:**\n\n{analysis}\n\n"
            f"*🎭 Эмоция: {emotion}*\n"
            f"*💾 Сон сохранен в истории*",
            parse_mode='Markdown'
        )

    # Предлагаем сохранить историю (только для незарегистрированных)
    if user_id in user_data and 'name' not in user_data[user_id]:
        keyboard = types.InlineKeyboardMarkup()
        btn_reg = types.InlineKeyboardButton('📝 Зарегистрироваться', callback_data='offer_registration')
        keyboard.add(btn_reg)

        bot.send_message(
            call.message.chat.id,
            "📚 Для сохранения полной истории снов и персонализированного анализа пройдите регистрацию!",
            reply_markup=keyboard
        )


@bot.callback_query_handler(func=lambda call: call.data == 'offer_registration')
def handle_offer_registration(call):
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="📝 Давайте зарегистрируемся для полного доступа к функциям!"
    )
    start_registration(call.message)


@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.text.lower() in ['привет', 'здравствуйте', 'здравствуй']:
        send_welcome(message)
    elif message.text == 'ℹ️ Помощь':
        bot.send_message(
            message.chat.id,
            "📖 **Помощь по боту:**\n\n"
            "/start - начать работу\n"
            "/analyze - анализ сна\n"
            "/history - история снов\n"
            "/stats - статистика\n"
            "/reg - регистрация\n"
            "/premium - премиум доступ\n"
            "/help - эта справка\n\n"
            "Просто напишите /analyze и расскажите свой сон!\n"
            "Если остались вопросы, напиши в поддержку - @aleexaandraa",
            parse_mode='Markdown'
        )
    else:
        bot.send_message(
            message.chat.id,
            "🤖 Я специализируюсь на анализе снов!\n\n"
            "Напишите /analyze чтобы рассказать свой сон\n"
            "Или /help для списка команд."
        )


# ЗАПУСК БОТА
if __name__ == '__main__':
    print("=" * 50)
    print("ЗАПУСК БОТА ДЛЯ АНАЛИЗА СНОВ")
    print("=" * 50)

    if api_available:
        print("Режим: AI-анализ с OpenAI API")
    else:
        print("Режим: Базовый анализ")

    # Показываем содержимое базы данных при запуске
    print("\nСОДЕРЖИМОЕ БАЗЫ ДАННЫХ:")
    view_database()

    try:
        print("\nЗапускаем опрос сервера Telegram...")
        bot.polling(
            none_stop=True,
            interval=3,
            timeout=30
        )

    except Exception as e:
        print(f"Ошибка: {e}")
        print("Перезапуск через 5 секунд...")
        time.sleep(5)