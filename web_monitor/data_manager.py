import json
import os
import logging
import uuid
from datetime import datetime, timezone

CHECKS_FILE = 'data/checks.json'  # ВИПРАВЛЕНО: видалив 'web_monitor/' префікс
HISTORY_DIR = 'data/history'       # ВИПРАВЛЕНО: видалив 'web_monitor/' префікс
MAX_HISTORY_ENTRIES = 20

def load_checks():
    """Загружает конфигурации проверок из файла checks.json."""
    if not os.path.exists(CHECKS_FILE):
        logging.info(f"Checks file {CHECKS_FILE} not found. Returning empty list.")
        return []
    try:
        with open(CHECKS_FILE, 'r', encoding='utf-8') as f:
            checks = json.load(f)
        return checks
    except (IOError, json.JSONDecodeError) as e:
        logging.error(f"Error loading checks from {CHECKS_FILE}: {e}")
        return []

def save_checks(checks):
    """Сохраняет конфигурации проверок в файл checks.json."""
    try:
        os.makedirs(os.path.dirname(CHECKS_FILE), exist_ok=True)
        with open(CHECKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(checks, f, indent=4, ensure_ascii=False, default=str) 
        logging.info(f"Checks saved to {CHECKS_FILE}")
    except IOError as e:
        logging.error(f"Error saving checks to {CHECKS_FILE}: {e}")

def get_check_by_id(check_id):
    """Загружает все проверки и возвращает одну по ее ID, или None если не найдена."""
    all_checks = load_checks()
    for check in all_checks:
        if check['id'] == check_id:
            return check
    logging.warning(f"Check with ID {check_id} not found in load_checks().") # Добавим лог
    return None

def get_history_filepath(check_id):
    """Возвращает путь к файлу истории для данного check_id."""
    return os.path.join(HISTORY_DIR, f"{check_id}.json")

def load_check_history(check_id):
    """Загружает историю проверок для указанного check_id."""
    filepath = get_history_filepath(check_id)
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            history = json.load(f)
        return history
    except (IOError, json.JSONDecodeError) as e:
        logging.error(f"Error loading history for check_id {check_id} from {filepath}: {e}")
        return []

def save_check_history_entry(check_id, history_entry):
    """
    Добавляет новую запись в историю проверок для указанного check_id.
    Ограничивает количество записей до MAX_HISTORY_ENTRIES.
    """
    os.makedirs(HISTORY_DIR, exist_ok=True)
    
    filepath = get_history_filepath(check_id)
    history = load_check_history(check_id) 

    history.append(history_entry)
    logging.debug(f"History for {check_id} before trim: {len(history)} entries")

    if len(history) > MAX_HISTORY_ENTRIES:
        history = history[-MAX_HISTORY_ENTRIES:] 
    
    logging.debug(f"History for {check_id} after trim (before save): {len(history)} entries")

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=4, ensure_ascii=False, default=str)
            f.flush()  # <<< ДОБАВЛЕНО
            os.fsync(f.fileno()) # <<< ДОБАВЛЕНО
        logging.debug(f"Saved history entry for check_id {check_id} to {filepath}. Actual saved length: {len(history)}")
    except IOError as e:
        logging.error(f"Error saving history for check_id {check_id} to {filepath}: {e}")
    except Exception as e: # Ловим другие возможные ошибки от fsync
        logging.error(f"Unexpected error during saving/flushing history for {check_id}: {e}")

def add_check(check_data):
    """
    Додає нову перевірку до списку та зберігає у файл checks.json.
    Генерує унікальний ID та додає системні поля.
    """
    # Генеруємо унікальний ID
    check_id = str(uuid.uuid4())
    current_time = datetime.now(timezone.utc).isoformat()
    
    # Створюємо повну конфігурацію перевірки
    new_check = {
        "id": check_id,
        "name": check_data.get("name"),
        "url": check_data["url"],
        "selector": check_data.get("selector"),
        "change_threshold": check_data.get("change_threshold"),
        "interval": check_data["interval"],
        "status": "active",  # За замовчуванням нові перевірки активні
        "created_at": current_time,
        "last_checked_at": None,
        "last_result": None,
        "last_content_hash": None,
        "next_check_at": None,
        "last_error_message": None
    }
    
    # Завантажуємо існуючі перевірки
    all_checks = load_checks()
    
    # Додаємо нову перевірку
    all_checks.append(new_check)
    
    # Зберігаємо оновлений список
    save_checks(all_checks)
    
    logging.info(f"Нову перевірку створено: ID={check_id}, Name='{new_check['name']}', URL={new_check['url']}")
    
    return new_check

def delete_check_history(check_id):
    """
    Видаляє файл історії для вказаного check_id.
    Повертає True, якщо файл було видалено або його не існувало.
    """
    filepath = get_history_filepath(check_id)
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            logging.info(f"Deleted history file for check_id {check_id}: {filepath}")
            return True
        except OSError as e:
            logging.error(f"Error deleting history file for check_id {check_id} at {filepath}: {e}")
            return False
    else:
        logging.info(f"History file for check_id {check_id} does not exist: {filepath}")
        return True  # Вважаємо успіхом, якщо файлу не було

def sync_check_with_latest_history(check_id):
    """
    Синхронізує основні дані перевірки з найсвіжішим записом в історії.
    Використовується для виправлення розбіжностей.
    """
    history = load_check_history(check_id)
    if not history:
        logging.info(f"No history found for check {check_id}, nothing to sync")
        return False
    
    # Сортуємо історію за часом (найновіші спочатку)
    history.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    latest_entry = history[0]
    
    # Завантажуємо всі перевірки
    all_checks = load_checks()
    check_config = None
    
    for i, check in enumerate(all_checks):
        if check['id'] == check_id:
            check_config = check
            break
    
    if not check_config:
        logging.error(f"Check with ID {check_id} not found for sync")
        return False
    
    # Оновлюємо основні дані з історії
    old_time = check_config.get('last_checked_at')
    old_result = check_config.get('last_result')
    
    check_config['last_checked_at'] = latest_entry.get('timestamp')
    check_config['last_result'] = latest_entry.get('status')
    
    if latest_entry.get('content_hash'):
        check_config['last_content_hash'] = latest_entry.get('content_hash')
    
    if latest_entry.get('error_message'):
        check_config['last_error_message'] = latest_entry.get('error_message')
    else:
        check_config['last_error_message'] = None
    
    # Зберігаємо оновлені дані
    save_checks(all_checks)
    
    logging.info(f"Synced check {check_id}: time '{old_time}' -> '{latest_entry.get('timestamp')}', result '{old_result}' -> '{latest_entry.get('status')}'")
    return True

def debug_check_data(check_id):
    """
    Діагностична функція для перевірки даних конкретної перевірки.
    """
    logging.info(f"=== DEBUG CHECK DATA for {check_id} ===")
    
    # Завантажуємо основні дані
    check_config = get_check_by_id(check_id)
    if check_config:
        logging.info(f"Main config:")
        logging.info(f"  last_checked_at: {check_config.get('last_checked_at')}")
        logging.info(f"  last_result: {check_config.get('last_result')}")
        logging.info(f"  last_content_hash: {check_config.get('last_content_hash')}")
    else:
        logging.info(f"Check config not found!")
        return
    
    # Завантажуємо історію
    history = load_check_history(check_id)
    logging.info(f"History entries: {len(history)}")
    
    if history:
        # Показуємо останні 3 записи
        sorted_history = sorted(history, key=lambda x: x.get('timestamp', ''), reverse=True)
        for i, entry in enumerate(sorted_history[:3]):
            logging.info(f"  [{i}] {entry.get('timestamp')} | {entry.get('status')} | hash: {entry.get('content_hash')} | text: '{entry.get('extracted_value', '')[:50]}'")
    
    logging.info("=== END DEBUG ===")

def clean_duplicate_history_entries(check_id):
    """
    Видаляє дублікати з історії перевірок на основі timestamp та content_hash.
    """
    history = load_check_history(check_id)
    if len(history) <= 1:
        return
    
    # Створюємо множину для відстеження унікальних комбінацій
    seen = set()
    cleaned_history = []
    
    for entry in history:
        timestamp = entry.get('timestamp')
        content_hash = entry.get('content_hash')
        key = (timestamp, content_hash)
        
        if key not in seen:
            seen.add(key)
            cleaned_history.append(entry)
        else:
            logging.info(f"Removing duplicate entry: {timestamp} with hash {content_hash}")
    
    if len(cleaned_history) != len(history):
        logging.info(f"Cleaned history for {check_id}: {len(history)} -> {len(cleaned_history)} entries")
        
        # Зберігаємо очищену історію
        filepath = get_history_filepath(check_id)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(cleaned_history, f, indent=4, ensure_ascii=False, default=str)
                f.flush()
                os.fsync(f.fileno())
            logging.info(f"Saved cleaned history for {check_id}")
        except IOError as e:
            logging.error(f"Error saving cleaned history for {check_id}: {e}")

def get_current_content(check_id):
    """
    Повертає поточний контент для вказаної перевірки з останнього запису історії.
    """
    history = load_check_history(check_id)
    if not history:
        return None
    
    # Сортуємо за часом (найновіші спочатку)
    history.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    latest_entry = history[0]
    
    return {
        'content': latest_entry.get('extracted_value'),
        'timestamp': latest_entry.get('timestamp'),
        'status': latest_entry.get('status'),
        'hash': latest_entry.get('content_hash')
    }

def get_check_with_current_content(check_id):
    """
    Повертає дані перевірки разом з поточним контентом.
    """
    check = get_check_by_id(check_id)
    if not check:
        return None
    
    current_content = get_current_content(check_id)
    if current_content:
        check['current_content'] = current_content['content']
        check['current_timestamp'] = current_content['timestamp']
        check['current_status'] = current_content['status']
    
    return check

if __name__ == '__main__':
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.DEBUG, 
                            format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
    
    test_check_id = "example-check-id-for-test-123"
    history_file_path = get_history_filepath(test_check_id)
    if os.path.exists(history_file_path):
        try:
            os.remove(history_file_path)
            logging.info(f"Removed old history file: {history_file_path}")
        except OSError as e:
            logging.error(f"Error removing old history file {history_file_path}: {e}")

    logging.info(f"Testing history functions for check_id: {test_check_id} with MAX_HISTORY_ENTRIES = {MAX_HISTORY_ENTRIES}")
    for i in range(MAX_HISTORY_ENTRIES + 5): # Add 25 entries if MAX_HISTORY_ENTRIES is 20
        entry_timestamp = datetime.now().isoformat() 
        entry = {
            "timestamp": entry_timestamp,
            "status": "no_change" if i % 2 == 0 else "changed",
            "extracted_value": f"Test Value {i+1}",
            "content_hash": f"testhash_{i+1}",
            "error_message": None
        }
        save_check_history_entry(test_check_id, entry)

    # Небольшая пауза перед финальной загрузкой, на всякий случай
    import time
    time.sleep(0.1) 

    loaded_history = load_check_history(test_check_id)
    logging.info(f"Loaded history for {test_check_id} contains {len(loaded_history)} entries (expected {MAX_HISTORY_ENTRIES}).")
    
    if loaded_history:
        logging.info(f"First entry in loaded history (oldest of the last {MAX_HISTORY_ENTRIES}):")
        logging.info(json.dumps(loaded_history[0], indent=2))
        logging.info("Last entry in loaded history (newest):")
        logging.info(json.dumps(loaded_history[-1], indent=2))
    
    assert len(loaded_history) == MAX_HISTORY_ENTRIES, \
        f"History length mismatch: expected {MAX_HISTORY_ENTRIES}, got {len(loaded_history)}"
    
    expected_first_value_index = (MAX_HISTORY_ENTRIES + 5) - MAX_HISTORY_ENTRIES
    if loaded_history:
         assert loaded_history[0]["extracted_value"] == f"Test Value {expected_first_value_index + 1}", \
             f"Expected first value to be 'Test Value {expected_first_value_index + 1}', but got '{loaded_history[0]['extracted_value']}'"

    logging.info("Test for data_manager.py (history part) completed successfully.")

    # Тестирование checks.json (остальная часть теста)
    original_checks_file_const = CHECKS_FILE 
    sample_checks_path = os.path.join(os.path.dirname(CHECKS_FILE), 'sample_checks_for_test.json')
    
    original_checks_content = None
    if os.path.exists(original_checks_file_const):
        try:
            with open(original_checks_file_const, 'r', encoding='utf-8') as f_orig:
                original_checks_content = f_orig.read()
            logging.info(f"Backed up content of {original_checks_file_const}")
        except Exception as e:
            logging.error(f"Could not back up {original_checks_file_const}: {e}")

    CHECKS_FILE = sample_checks_path 

    sample_checks_data = [
        {"id": "check1", "name": "Test Check 1", "url": "http://example.com", "selector": "h1"},
        {"id": "check2", "name": "Test Check 2", "url": "http://example.org", "selector": "title"}
    ]
    save_checks(sample_checks_data)
    loaded_s_checks = load_checks() 
    logging.info(f"Loaded sample checks from {CHECKS_FILE}: {loaded_s_checks}")
    assert len(loaded_s_checks) == 2, f"Expected 2 sample checks, got {len(loaded_s_checks)}"
    
    if os.path.exists(sample_checks_path):
        try:
            os.remove(sample_checks_path) 
            logging.info(f"Removed sample checks file: {sample_checks_path}")
        except OSError as e:
            logging.error(f"Error removing sample checks file {sample_checks_path}: {e}")
    
    CHECKS_FILE = original_checks_file_const 
    if original_checks_content is not None:
        try:
            os.makedirs(os.path.dirname(CHECKS_FILE), exist_ok=True)
            with open(CHECKS_FILE, 'w', encoding='utf-8') as f_orig_write:
                f_orig_write.write(original_checks_content)
            logging.info(f"Restored original checks file: {CHECKS_FILE}")
        except Exception as e:
            logging.error(f"Could not restore {CHECKS_FILE}: {e}")
            
    logging.info("All tests for data_manager.py passed.")

