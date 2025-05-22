import logging
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import hashlib

# Настройка базового логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_content_hash(content_string):
    """Вычисляет MD5 хеш для строки."""
    if content_string is None:
        return None
    return hashlib.md5(content_string.encode('utf-8')).hexdigest()

def perform_check(check_data):
    """
    Выполняет проверку для указанного URL и селектора.
    check_data: словарь, содержащий как минимум:
        'id': id проверки
        'url': URL для проверки
        'selector': CSS селектор (опционально)
        'last_content_hash': хеш предыдущего контента (опционально)
        'name': имя проверки (для логирования)
    """
    check_id = check_data.get('id')
    url = check_data.get('url')
    selector = check_data.get('selector')
    previous_content_hash = check_data.get('last_content_hash')
    check_name = check_data.get('name', f"Check ID {check_id}") # Используем имя или ID для логов

    logging.info(f"Performing check for '{check_name}' (ID: {check_id}), URL: {url}, Selector: {selector}")

    current_status = "no_change"
    error_message = None
    new_content_text = None
    new_hash = None
    content_for_history = None # Пока не реализуем детальное сохранение контента

    try:
        response = requests.get(url, timeout=20) # Таймаут 20 секунд
        response.raise_for_status() # Вызовет исключение для HTTP ошибок 4xx/5xx

        page_content = response.text

        if selector:
            soup = BeautifulSoup(page_content, 'html.parser')
            selected_element = soup.select_one(selector)
            if selected_element:
                # Используем .prettify() чтобы сохранить структуру HTML элемента,
                # а не только текст. Это важно для отслеживания изменений в атрибутах и т.д.
                new_content_text = selected_element.prettify()
            else:
                current_status = "error"
                error_message = f"Selector '{selector}' not found on page."
                logging.warning(f"Selector not found for '{check_name}' (ID: {check_id}): {selector}")
        else:
            new_content_text = page_content
        
        if current_status not in ["error", "site_unavailable"]: # Только если нет ошибок на предыдущих этапах
            if new_content_text is not None:
                new_hash = get_content_hash(new_content_text)

                if previous_content_hash is None: # Первая проверка
                    current_status = "changed" # Считаем первой проверкой как "изменение" для сохранения хеша
                    logging.info(f"First check for '{check_name}' (ID: {check_id}). Storing initial hash.")
                elif new_hash != previous_content_hash:
                    current_status = "changed"
                    logging.info(f"Content changed for '{check_name}' (ID: {check_id}). Previous hash: {previous_content_hash}, New hash: {new_hash}")
                    # Здесь можно будет добавить логику для content_for_history
                else:
                    current_status = "no_change"
                    logging.info(f"No change detected for '{check_name}' (ID: {check_id}). Hash: {new_hash}")
            else: # Этого не должно произойти, если нет селектора или селектор найден
                current_status = "error"
                error_message = "Failed to extract content, but no specific error was raised."
                logging.error(f"Logic error: new_content_text is None for '{check_name}' (ID: {check_id}) without prior error.")


    except requests.exceptions.Timeout:
        current_status = "site_unavailable"
        error_message = "Request timed out."
        logging.warning(f"Timeout for '{check_name}' (ID: {check_id}), URL: {url}")
    except requests.exceptions.HTTPError as e:
        current_status = "site_unavailable"
        error_message = f"HTTP error: {e.response.status_code} {e.response.reason}."
        logging.warning(f"HTTP error for '{check_name}' (ID: {check_id}), URL: {url} - {error_message}")
    except requests.exceptions.RequestException as e:
        current_status = "site_unavailable"
        error_message = f"Failed to connect or other network error: {str(e)}."
        logging.warning(f"Network error for '{check_name}' (ID: {check_id}), URL: {url} - {error_message}")
    except Exception as e:
        current_status = "error"
        error_message = f"An unexpected error occurred during check: {str(e)}"
        logging.error(f"Unexpected error for '{check_name}' (ID: {check_id}): {e}", exc_info=True)

    # logging.info(f"Check completed for '{check_name}' (ID: {check_id}). Status: {current_status}")
    
    return {
        "status": current_status,
        "error_message": error_message,
        "new_content_hash": new_hash, # Возвращаем новый хеш, чтобы data_manager мог его сохранить
        "content_for_history": content_for_history, # Позже здесь будет фрагмент контента
        "checked_at": datetime.utcnow().isoformat() + 'Z'
    }

if __name__ == '__main__':
    # Пример вызова для тестирования
    # Для реального теста нужно создать check_data с last_content_hash
    
    # Тест 1: Сайт доступен, селектор существует (ожидаем 'changed' при первой проверке или 'no_change'/'changed')
    test_check_data_1 = {
        "id": "test-001",
        "name": "Example.com Title",
        "url": "http://example.com", # Используем http для простоты, если нет SSL проблем
        "selector": "h1",
        "last_content_hash": None # Первая проверка
    }
    logging.info(f"Manually testing perform_check for: {test_check_data_1.get('name')}")
    result1 = perform_check(test_check_data_1)
    logging.info(f"Test 1 result: {result1}\n")

    # Тест 2: Сайт доступен, селектор НЕ существует
    test_check_data_2 = {
        "id": "test-002",
        "name": "Example.com NonExistent",
        "url": "http://example.com",
        "selector": "#nonexistent-selector-abc123",
        "last_content_hash": None
    }
    logging.info(f"Manually testing perform_check for: {test_check_data_2.get('name')}")
    result2 = perform_check(test_check_data_2)
    logging.info(f"Test 2 result: {result2}\n")

    # Тест 3: Сайт недоступен (неверный URL)
    test_check_data_3 = {
        "id": "test-003",
        "name": "NonExistent Domain",
        "url": "http://thisdomainprobablydoesnotexist12345.com",
        "selector": None,
        "last_content_hash": None
    }
    logging.info(f"Manually testing perform_check for: {test_check_data_3.get('name')}")
    result3 = perform_check(test_check_data_3)
    logging.info(f"Test 3 result: {result3}\n")

    # Тест 4: Сайт доступен, без селектора (вся страница)
    test_check_data_4 = {
        "id": "test-004",
        "name": "Example.com Full Page",
        "url": "http://example.com",
        "selector": None,
        "last_content_hash": None # Первая проверка
    }
    logging.info(f"Manually testing perform_check for: {test_check_data_4.get('name')}")
    result4 = perform_check(test_check_data_4)
    logging.info(f"Test 4 result: {result4}\n")

    # Тест 5: Проверка с существующим хешем (ожидаем 'no_change', если контент тот же)
    # Сначала получим хеш из result4
    if result4.get("new_content_hash"):
        test_check_data_5 = {
            "id": "test-005",
            "name": "Example.com Full Page - Second Check",
            "url": "http://example.com",
            "selector": None,
            "last_content_hash": result4["new_content_hash"]
        }
        logging.info(f"Manually testing perform_check for: {test_check_data_5.get('name')}")
        result5 = perform_check(test_check_data_5)
        logging.info(f"Test 5 result: {result5}\n")

    # Тест 6: Проверка изменения контента (имитируем изменение хеша)
    if result4.get("new_content_hash"):
        test_check_data_6 = {
            "id": "test-006",
            "name": "Example.com Full Page - Changed Hash",
            "url": "http://example.com",
            "selector": None,
            "last_content_hash": "dummy_different_hash_value_12345" 
        }
        logging.info(f"Manually testing perform_check for: {test_check_data_6.get('name')}")
        result6 = perform_check(test_check_data_6)
        logging.info(f"Test 6 result: {result6}\n")