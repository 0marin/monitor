import json
import os
import uuid
from datetime import datetime

# Путь к файлу данных определяется относительно текущего файла data_manager.py
# Это делает его более предсказуемым, если data_manager.py будет импортирован из другого места.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
CHECKS_FILE = os.path.join(DATA_DIR, 'checks.json')

# Убедимся, что каталог data существует
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Убедимся, что файл checks.json существует и содержит валидный JSON (пустой список, если новый)
if not os.path.exists(CHECKS_FILE):
    with open(CHECKS_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f)
else:
    # Проверка на случай, если файл пуст или содержит невалидный JSON
    try:
        with open(CHECKS_FILE, 'r', encoding='utf-8') as f:
            if not f.read().strip(): # Если файл пустой
                with open(CHECKS_FILE, 'w', encoding='utf-8') as wf:
                    json.dump([], wf)
            else:
                # Попытка загрузить, чтобы убедиться, что это валидный JSON
                f.seek(0) # Возвращаемся в начало файла для чтения
                json.load(f)
    except json.JSONDecodeError:
        # Если файл содержит невалидный JSON, перезаписываем его пустым списком
        with open(CHECKS_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)


def load_checks():
    """Загружает все конфигурации проверок из файла checks.json."""
    try:
        with open(CHECKS_FILE, 'r', encoding='utf-8') as f:
            checks = json.load(f)
        return checks
    except FileNotFoundError:
        return []  # Если файл не найден, возвращаем пустой список
    except json.JSONDecodeError:
        # Если файл поврежден или не является валидным JSON, возвращаем пустой список
        # и, возможно, логируем ошибку
        print(f"Error: Could not decode JSON from {CHECKS_FILE}")
        return []

def save_checks(checks_data):
    """Сохраняет все конфигурации проверок в файл checks.json."""
    try:
        with open(CHECKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(checks_data, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Error: Could not write to {CHECKS_FILE}: {e}")


def add_check(new_check_data):
    """
    Добавляет новую конфигурацию проверки.
    new_check_data должен быть словарем с полями:
    'name' (str, опционально), 'url' (str, обязательно),
    'selector' (str, опционально), 'change_threshold' (float, опционально),
    'interval' (int, обязательно).
    """
    checks = load_checks()
    
    check_id = str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat() + 'Z' # Формат ISO 8601 UTC

    full_check_data = {
        "id": check_id,
        "name": new_check_data.get("name", ""),
        "url": new_check_data["url"],
        "selector": new_check_data.get("selector", None),
        "change_threshold": new_check_data.get("change_threshold", None),
        "interval": new_check_data["interval"], # в минутах
        "status": "active", # 'active', 'inactive', 'error'
        "created_at": created_at,
        "last_checked_at": None,
        "next_check_at": None, # Будет установлено планировщиком
        "last_result": None, # 'no_change', 'changed', 'site_unavailable', 'error'
        "last_error_message": None,
        "last_content_hash": None # Хеш последнего успешного контента
    }
    
    checks.append(full_check_data)
    save_checks(checks)
    return full_check_data


def get_check_by_id(check_id):
    """Возвращает конфигурацию проверки по её ID."""
    checks = load_checks()
    for check in checks:
        if check.get("id") == check_id:
            return check
    return None

# Другие функции для управления проверками (update_check, delete_check)
# будут добавлены позже.