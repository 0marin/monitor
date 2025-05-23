import requests
import logging
import os
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
# Убедитесь, что у вас есть файл .env в корне проекта (D:\AI\Monitor2\.env)
# и в нем определены TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def send_telegram_message(message): # Имя функции изменено на send_telegram_message
    """
    Отправляет уведомление в Telegram.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Telegram Bot Token или Chat ID не настроены в .env. Уведомление не отправлено.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'  # Или 'HTML', если предпочитаете
    }
    try:
        response = requests.post(url, data=payload, timeout=10) # Увеличил таймаут на всякий случай
        response.raise_for_status()  # Вызовет исключение для HTTP-ошибок (4xx, 5xx)
        logging.info(f"Telegram notification sent successfully: {message[:50]}...")
    except requests.exceptions.Timeout:
        logging.error(f"Failed to send Telegram notification: Timeout after 10 seconds.")
    except requests.exceptions.HTTPError as http_err:
        logging.error(f"Failed to send Telegram notification: HTTP error occurred: {http_err} - {response.text}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to send Telegram notification: {e}")
    except Exception as e: # Ловим другие возможные ошибки
        logging.error(f"An unexpected error occurred while sending Telegram notification: {e}")

if __name__ == '__main__':
    # Пример использования (для тестирования этого модуля отдельно)
    # Убедитесь, что логирование настроено, если запускаете этот файл напрямую
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, 
                            format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        logging.info("Attempting to send a test Telegram message...")
        send_telegram_message("Тестовое уведомление из `telegram_sender.py`! \nМожно использовать *Markdown*.")
        send_telegram_message("Это второе тестовое сообщение для проверки.")
    else:
        logging.warning("Не могу запустить тест telegram_sender.py: TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не установлены в .env файле.")
        logging.info("Пожалуйста, создайте файл .env в корне проекта (D:\\AI\\Monitor2\\.env) и добавьте в него:")
        logging.info("TELEGRAM_BOT_TOKEN='ВАШ_БОТ_ТОКЕН'")
        logging.info("TELEGRAM_CHAT_ID='ВАШ_ЧАТ_ID'")

