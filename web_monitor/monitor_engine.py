import requests
import hashlib
from bs4 import BeautifulSoup
import logging

# Настройка логування (якщо ще не налаштовано глобально)
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_content_hash_from_element(element):
    """
    Извлекает текстовое содержимое элемента, нормализует его и возвращает текст и MD5 хеш.
    """
    if not element:
        # Эта ветка не должна вызываться, если perform_check уже проверил selected_element
        return None, None 

    text_content = element.get_text(separator=' ', strip=True)
    
    # Раскомментируйте для отладки, чтобы увидеть извлеченный текст
    # logging.debug(f"Extracted text for hashing: '{text_content}'") 
    
    # Хешируем текстовое содержимое, даже если оно пустое
    content_hash = hashlib.md5(text_content.encode('utf-8')).hexdigest()
    return text_content, content_hash

def perform_check(check_id, name, url, selector, last_hash):
    """
    Выполняет проверку веб-страницы.
    Возвращает кортеж: (status, new_hash, extracted_text, error_message)
    status: 'changed', 'no_change', 'error'
    new_hash: MD5 хеш текущего контента или None в случае ошибки
    extracted_text: извлеченный текст или None в случае ошибки
    error_message: сообщение об ошибке или None
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 WebMonitorBot/1.0'
    }
    
    status = "error" # Default status
    current_hash = None
    extracted_text = None
    error_message = None

    try:
        logging.info(f"Performing check for '{name}' (ID: {check_id}), URL: {url}, Selector: {selector}")
        
        # ВИПРАВЛЕНО: Збільшуємо timeout та додаємо більше параметрів
        response = requests.get(
            url, 
            headers=headers, 
            timeout=(10, 30),  # (connection timeout, read timeout) 
            allow_redirects=True,
            verify=True  # Перевіряємо SSL сертифікати
        )
        response.raise_for_status() # Вызовет исключение для плохих ответов (4xx, 5xx)
        
        soup = BeautifulSoup(response.content, 'html.parser')
        selected_element = soup.select_one(selector)

        if not selected_element:
            error_message = f"Element not found with selector: '{selector}'"
            logging.warning(f"{error_message} for '{name}' (ID: {check_id}) on URL {url}")
            return status, current_hash, extracted_text, error_message

        extracted_text, current_hash = get_content_hash_from_element(selected_element)
        
        # ВИПРАВЛЕНО: Детальне логування для діагностики
        logging.info(f"Check for '{name}' (ID: {check_id}:")
        logging.info(f"  Extracted text: '{extracted_text}'")
        logging.info(f"  Current hash: '{current_hash}'")
        logging.info(f"  Last hash: '{last_hash}'")
        logging.info(f"  Hash comparison: current==last -> {current_hash == last_hash}")

        if last_hash is None: # Перша перевірка для цього елемента
            status = "changed" # Считаем первой проверкой как изменение
            logging.info(f"First check for '{name}' (ID: {check_id}). Status: {status}. Hash: {current_hash}")
        elif current_hash == last_hash:
            status = "no_change"
            logging.info(f"No change detected for '{name}' (ID: {check_id}). Status: {status}. Hash unchanged: {current_hash}")
        else:
            status = "changed"
            logging.info(f"Change detected for '{name}' (ID: {check_id}). Status: {status}. Old hash: {last_hash}, New hash: {current_hash}")
        
        # ДОДАНО: Додаткова перевірка для діагностики
        if status == "changed" and last_hash is not None and extracted_text:
            logging.info(f"CHANGE ANALYSIS for '{name}' (ID: {check_id}:")
            logging.info(f"  Text length: {len(extracted_text)} chars")
            logging.info(f"  Text content: '{extracted_text[:100]}{'...' if len(extracted_text) > 100 else ''}'")
            
        # error_message остается None, так как ошибок не было на этом этапе
        return status, current_hash, extracted_text, error_message

    # ВИПРАВЛЕНО: Детальна обробка різних типів помилок мережі
    except requests.exceptions.Timeout as e:
        if "Read timed out" in str(e):
            error_message = f"Сервер '{url}' не відповідає (timeout через {30}с). Можливо сайт перевантажений або недоступний."
        elif "Connection timeout" in str(e):
            error_message = f"Не вдалося підключитися до '{url}' (connection timeout через {10}с). Перевірте доступність сайту."
        else:
            error_message = f"Timeout при підключенні до '{url}': {str(e)}"
        logging.warning(f"TIMEOUT ERROR for '{name}' (ID: {check_id}): {error_message}")
        return status, None, None, error_message
        
    except requests.exceptions.ConnectionError as e:
        error_message = f"Помилка з'єднання з '{url}': сервер недоступний або проблеми з мережею"
        logging.error(f"CONNECTION ERROR for '{name}' (ID: {check_id}): {error_message} | Details: {str(e)}")
        return status, None, None, error_message
        
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response else "Unknown"
        if status_code == 404:
            error_message = f"Сторінка не знайдена (404): '{url}'"
        elif status_code == 403:
            error_message = f"Доступ заборонено (403): '{url}' - можливо потрібна авторизація"
        elif status_code == 500:
            error_message = f"Помилка сервера (500): '{url}' - внутрішня помилка сайту"
        elif status_code == 503:
            error_message = f"Сервіс недоступний (503): '{url}' - сайт тимчасово недоступний"
        else:
            error_message = f"HTTP помилка {status_code}: '{url}'"
        logging.error(f"HTTP ERROR for '{name}' (ID: {check_id}): {error_message}")
        return status, None, None, error_message
        
    except requests.exceptions.SSLError as e:
        error_message = f"Помилка SSL сертифікату для '{url}': сертифікат недійсний або застарілий"
        logging.error(f"SSL ERROR for '{name}' (ID: {check_id}): {error_message} | Details: {str(e)}")
        return status, None, None, error_message
        
    except requests.exceptions.TooManyRedirects as e:
        error_message = f"Забагато перенаправлень для '{url}': можливо циклічні редиректи"
        logging.error(f"REDIRECT ERROR for '{name}' (ID: {check_id}): {error_message}")
        return status, None, None, error_message
        
    except requests.exceptions.RequestException as e:
        error_message = f"Загальна помилка запиту до '{url}': {str(e)}"
        logging.error(f"REQUEST ERROR for '{name}' (ID: {check_id}): {error_message}")
        return status, None, None, error_message
        
    except Exception as e:
        error_message = f"Неочікувана помилка для '{url}': {str(e)}"
        logging.exception(f"UNEXPECTED ERROR for '{name}' (ID: {check_id}): {error_message}")
        return status, None, None, error_message

