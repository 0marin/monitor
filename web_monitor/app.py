from flask import Flask, request, jsonify, render_template, redirect, url_for # Ваши импорты Flask
import os # Ваш импорт os
import uuid # Был в предыдущей версии, вероятно, нужен
import logging # Ваш импорт logging
from datetime import datetime, timezone # Было в предыдущей версии, вероятно, нужно для created_at и т.д.

# --- ИЗМЕНИТЬ ЭТИ ИМПОРТЫ ---
from . import data_manager    # Импортируем наш модуль
from . import scheduler_tasks # Импортируем модуль планировщика
from . import monitor_engine  # Если он вам нужен напрямую в app.py
from .telegram_sender import send_telegram_message # Этот импорт, вероятно, уже правильный

# ... остальной код app.py (настройка логирования, app = Flask(__name__), и т.д.)


app = Flask(__name__, template_folder='templates', static_folder='static')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def format_datetime_filter(value, format='%d %B %Y %H:%M:%S %Z'):
    """Форматирует строку ISO datetime в читаемый вид."""
    if value is None:
        return ""
    try:
        # Предполагаем, что value - это строка ISO, заканчивающаяся на 'Z' или с offset
        dt_object = datetime.fromisoformat(value.replace('Z', '+00:00'))
        # Если хотим отображать в локальном времени сервера (не рекомендуется для консистентности)
        # dt_object = dt_object.astimezone(None) 
        # Для простоты оставим в UTC или как есть в строке
        return dt_object.strftime(format)
    except (ValueError, TypeError) as e:
        logging.warning(f"Could not format datetime string '{value}': {e}")
        return value # Возвращаем исходное значение, если не удалось отформатировать

app.jinja_env.filters['format_datetime'] = format_datetime_filter

# Конфигурация логирования (будет добавлена позже)

# --- HTML Страницы ---
@app.route('/')
def index_page():
    """Отображает главную страницу со списком проверок."""
    return render_template('index.html')

@app.route('/add')
def add_check_page():
    """Отображает страницу добавления новой проверки."""
    return render_template('add_check.html')

@app.route('/check/<check_id>')
def monitor_details_page(check_id):
    """Отображает страницу с детальной информацией о проверке."""
    # Логика получения данных о проверке по check_id будет здесь
    return render_template('monitor_details.html', check_id=check_id)

# --- API Эндпоинты ---

@app.route('/api/checks', methods=['POST'])
def api_add_check():
    """
    API эндпоинт для добавления новой проверки.
    Принимает JSON с данными проверки.
    """
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()

    # Валидация обязательных полей
    required_fields = ['url', 'interval']
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

    try:
        # Дополнительная валидация типов данных
        if not isinstance(data['url'], str) or not data['url'].startswith(('http://', 'https://')):
            return jsonify({"error": "Invalid URL format"}), 400
        if not isinstance(data['interval'], int) or data['interval'] < 1:
            return jsonify({"error": "Interval must be a positive integer (minutes)"}), 400
        
        # Опциональные поля и их валидация
        name = data.get('name')
        if name is not None and not isinstance(name, str):
            return jsonify({"error": "Name must be a string"}), 400
            
        selector = data.get('selector')
        if selector is not None and not isinstance(selector, str):
            return jsonify({"error": "Selector must be a string"}), 400

        change_threshold = data.get('change_threshold')
        if change_threshold is not None:
            if not isinstance(change_threshold, (int, float)) or not (0 <= change_threshold <= 100):
                return jsonify({"error": "Change threshold must be a number between 0 and 100"}), 400
        
        new_check_data = {
            "name": name,
            "url": data["url"],
            "selector": selector,
            "change_threshold": change_threshold,
            "interval": data["interval"]
        }
        
        created_check = data_manager.add_check(new_check_data)
        if created_check.get("status") == "active":
            scheduler_tasks.reschedule_check(created_check)
        return jsonify(created_check), 201
    except Exception as e:
        app.logger.error(f"Error adding check: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred while adding the check."}), 500


@app.route('/api/checks', methods=['GET'])
def api_get_checks():
    """API эндпоинт для получения списка всех проверок."""
    checks = data_manager.load_checks()
    return jsonify(checks), 200

@app.route('/api/checks/<check_id>', methods=['GET'])
def api_get_check_details(check_id):
    """API эндпоинт для получения детальной информации о проверке по ID."""
    check_details = data_manager.get_check_by_id(check_id)
    if check_details:
        return jsonify(check_details), 200
    else:
        return jsonify({"error": "Check not found"}), 404

@app.route('/api/system-status', methods=['GET'])
def api_get_system_status():
    """API эндпоинт для получения состояния системы (заглушка)."""
    # В будущем здесь будет реальная информация о системе
    active_jobs = scheduler_tasks.scheduler.get_jobs()
    status_info = {
        "scheduler_status": "Running" if scheduler_tasks.scheduler.running else "Stopped",
        "active_scheduled_jobs": len(active_jobs),
        "job_ids": [job.id for job in active_jobs],
        "last_global_error": None, # TODO: Implement global error tracking
        "app_version": "0.1.1"
    }
    return jsonify(status_info), 200

@app.route('/api/checks/<check_id>', methods=['PUT'])
def api_update_check(check_id):
    """API эндпоинт для обновления существующей проверки."""
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    data = request.get_json()
    existing_check = data_manager.get_check_by_id(check_id)
    if not existing_check:
        return jsonify({"error": "Check not found"}), 404

    # Обновляем только те поля, которые переданы
    for key, value in data.items():
        if key in existing_check and key != "id" and key != "created_at": # Не даем менять id и created_at
            # TODO: Добавить валидацию для каждого обновляемого поля
            if key == "interval" and (not isinstance(value, int) or value < 1):
                 return jsonify({"error": "Interval must be a positive integer (minutes)"}), 400
            existing_check[key] = value
    
    all_checks = data_manager.load_checks()
    for i, chk in enumerate(all_checks):
        if chk.get("id") == check_id:
            all_checks[i] = existing_check
            break
    data_manager.save_checks(all_checks)
    
    # Перепланируем или удаляем задачу в зависимости от статуса
    if existing_check.get("status") == "active":
        scheduler_tasks.reschedule_check(existing_check)
    else: # Если статус не 'active', удаляем задачу из планировщика
        scheduler_tasks.remove_scheduled_check(check_id)
        
    return jsonify(existing_check), 200

@app.route('/api/checks/<check_id>', methods=['DELETE'])
def api_delete_check(check_id):
    """API эндпоинт для удаления проверки."""
    existing_check = data_manager.get_check_by_id(check_id)
    if not existing_check:
        return jsonify({"error": "Check not found"}), 404
        
    all_checks = data_manager.load_checks()
    all_checks = [chk for chk in all_checks if chk.get("id") != check_id]
    data_manager.save_checks(all_checks)
    
    scheduler_tasks.remove_scheduled_check(check_id) # Удаляем из планировщика
    
    # TODO: Удалить историю проверки и логи, связанные с ней
    
    return jsonify({"message": f"Check {check_id} deleted successfully"}), 200


if __name__ == '__main__':
    # Убедимся, что каталог data и файл checks.json существуют при запуске
    # data_manager.py уже это делает при импорте (для HISTORY_DIR)
    # CHECKS_FILE директория создается в data_manager.save_checks()
    
    # Планировщик уже инициализирован и запущен на глобальном уровне модуля
    # функцией scheduler_tasks.init_scheduler(app_checks)
    
    # Запускаем Flask приложение
    try:
        # scheduler_tasks.start_scheduler() # <<< УДАЛИТЕ ИЛИ ЗАКОММЕНТИРУЙТЕ ЭТУ СТРОКУ
        app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
        # use_reloader=False важен, чтобы планировщик не запускался дважды в debug режиме
    except (KeyboardInterrupt, SystemExit):
        logging.info("Application shutting down...")
        # scheduler_tasks.shutdown_scheduler() # atexit уже должен это сделать
    finally:
        # Дополнительная проверка, если atexit не сработал или для явности
        if scheduler_tasks.scheduler and scheduler_tasks.scheduler.running:
             logging.info("Ensuring scheduler is shut down in finally block...")
             scheduler_tasks.shutdown_scheduler()
