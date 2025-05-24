import requests
import hashlib
from bs4 import BeautifulSoup
import logging

# Настройка логирования (если еще не настроено глобально)
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
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() # Вызовет исключение для плохих ответов (4xx, 5xx)
        
        soup = BeautifulSoup(response.content, 'html.parser')
        selected_element = soup.select_one(selector)

        if not selected_element:
            error_message = f"Element not found with selector: '{selector}'"
            logging.warning(f"{error_message} for '{name}' (ID: {check_id}) on URL {url}")
            return status, current_hash, extracted_text, error_message # current_hash and extracted_text are None

        extracted_text, current_hash = get_content_hash_from_element(selected_element)
        
        # ВИПРАВЛЕНО: Детальне логування для діагностики
        logging.info(f"Check for '{name}' (ID: {check_id}): Extracted text='{extracted_text}', Current hash='{current_hash}', Last hash='{last_hash}'")

        if last_hash is None: # Первая проверка для этого элемента
            status = "changed" # Считаем первой проверкой как изменение, чтобы сохранить начальное состояние
            logging.info(f"First check for '{name}' (ID: {check_id}). Storing initial hash: {current_hash}. Extracted: '{extracted_text}'")
        elif current_hash == last_hash:
            status = "no_change"
            logging.info(f"No change detected for '{name}' (ID: {check_id}). Hash unchanged: {current_hash}")
        else:
            status = "changed"
            logging.info(f"Change detected for '{name}' (ID: {check_id}). Old hash: {last_hash}, New hash: {current_hash}. New content: '{extracted_text}'")
        
        # error_message остается None, так как ошибок не было на этом этапе
        return status, current_hash, extracted_text, error_message

    except requests.exceptions.RequestException as e:
        error_message = f"Request error for '{name}' (ID: {check_id}): {str(e)}"
        logging.error(error_message)
        return status, None, None, error_message # status is 'error'
    except Exception as e:
        error_message = f"Unexpected error for '{name}' (ID: {check_id}): {str(e)}"
        logging.exception(error_message) # Используем logging.exception для вывода traceback
        return status, None, None, error_message # status is 'error'

