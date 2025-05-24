from flask import Flask, request, jsonify, render_template, redirect, url_for # Ваши импорты Flask
import os # Ваш импорт os
import uuid # Был в предыдущей версии, вероятно, нужен
import logging # Ваш импорт logging
from datetime import datetime, timezone # Было в предыдущей версии, вероятно, нужно для created_at и т.д.

# --- ИЗМЕНИТЬ ЭТИ ИМПОРТЫ ---
# ВИПРАВЛЕНО: Замінюємо відносні імпорти на абсолютні для прямого запуску
try:
    # Спробуємо відносні імпорти (для запуску як модуль)
    from . import data_manager
    from . import scheduler_tasks
    from . import monitor_engine
    from .telegram_sender import send_telegram_message
except ImportError:
    # Якщо не вдалося, використовуємо абсолютні імпорти (для прямого запуску)
    import data_manager
    import scheduler_tasks
    import monitor_engine
    from telegram_sender import send_telegram_message

# ... остальной код app.py (настройка логирования, app = Flask(__name__), і т.д.)


app = Flask(__name__, template_folder='templates', static_folder='static')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def format_datetime_filter(value, format='%d %B %Y %H:%M:%S %Z'):
    """Форматирует строку ISO datetime в читаемый вид."""
    if value is None or value == "":
        return ""
    try:
        # Предполагаем, что value - это строка ISO
        if isinstance(value, str):
            # Обрабатываем разные форматы ISO datetime
            if value.endswith('Z'):
                dt_object = datetime.fromisoformat(value.replace('Z', '+00:00'))
            elif '+' in value[-6:] or value.endswith('00:00'):
                dt_object = datetime.fromisoformat(value)
            else:
                # Если нет информации о timezone, предполагаем UTC
                dt_object = datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
        else:
            dt_object = value
        
        # Якщо формат містить UTC, відображаємо в UTC
        if 'UTC' in format:
            # Переконуємося, що час в UTC
            if dt_object.tzinfo is None:
                dt_object = dt_object.replace(tzinfo=timezone.utc)
            else:
                dt_object = dt_object.astimezone(timezone.utc)
            # Замінюємо %Z на UTC для відображення
            format = format.replace('%Z', 'UTC')
        
        return dt_object.strftime(format)
    except (ValueError, TypeError) as e:
        logging.warning(f"Could not format datetime string '{value}': {e}")
        return str(value) # Возвращаем строковое представление, если не удалось отформатировать

app.jinja_env.filters['format_datetime'] = format_datetime_filter

# Конфигурация логирования (будет добавлена позже)

# --- HTML Страницы ---
@app.route('/')
def index_page():
    """Отображает главную страницу со списком проверок."""
    try:
        checks = data_manager.load_checks()
        return render_template('index.html', checks=checks)
    except Exception as e:
        app.logger.error(f"Error loading checks for index page: {e}", exc_info=True)
        return render_template('index.html', checks=[], error="Failed to load checks")

@app.route('/add')
def add_check_page():
    """Отображает страницу добавления новой проверки."""
    return render_template('add_check.html')

@app.route('/check/<check_id>')
def monitor_details_page(check_id):
    """Отображает страницу с детальной информацией о проверке."""
    try:
        check_details = data_manager.get_check_by_id(check_id)
        if not check_details:
            return render_template('error.html', 
                                 error_message=f"Check with ID {check_id} not found"), 404
        
        # Получаем историю проверок для данной проверки (ВИПРАВЛЕНО НАЗВУ ФУНКЦІЇ)
        check_history = data_manager.load_check_history(check_id)
        
        # Сортируем историю по времени (новые сначала) для удобства отображения
        check_history.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        return render_template('monitor_details.html', 
                             check=check_details, 
                             history=check_history,
                             check_id=check_id)
    except Exception as e:
        app.logger.error(f"Error loading check details for {check_id}: {e}", exc_info=True)
        return render_template('error.html', 
                             error_message="An error occurred while loading check details"), 500

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
        
        # ВИПРАВЛЕНО: Додаємо нову перевірку до планувальника
        if created_check.get("status") == "active":
            try:
                # ВИПРАВЛЕНО: Додаємо check_id як аргумент функції
                scheduler_tasks.scheduler.add_job(
                    func=scheduler_tasks.scheduled_check_task,
                    trigger='interval',
                    minutes=created_check['interval'],
                    args=[created_check['id']],  # Передаємо check_id як аргумент
                    id=created_check['id'],
                    name=f"Check: {created_check.get('name', created_check['id'])}",
                    replace_existing=True
                )
                logging.info(f"Додано завдання до планувальника для перевірки: {created_check['id']}")
            except Exception as e:
                logging.error(f"Помилка додавання завдання до планувальника: {e}")
        
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
        scheduler_tasks.update_job(check_id, existing_check['interval'])
    else: # Если статус не 'active', удаляем задачу из планировщика
        scheduler_tasks.remove_job(check_id)
        
    return jsonify(existing_check), 200

@app.route('/api/checks/<check_id>', methods=['DELETE'])
def api_delete_check(check_id):
    """API эндпоинт для удаления проверки."""
    existing_check = data_manager.get_check_by_id(check_id)
    if not existing_check:
        return jsonify({"error": "Check not found"}), 404
    
    check_name = existing_check.get('name', check_id)
    
    try:
        # 1. Видаляємо завдання з планувальника
        scheduler_tasks.remove_job(check_id)
        
        # 2. Видаляємо запис з checks.json
        all_checks = data_manager.load_checks()
        all_checks = [chk for chk in all_checks if chk.get("id") != check_id]
        data_manager.save_checks(all_checks)
        
        # 3. ВИПРАВЛЕНО: Видаляємо файл історії
        data_manager.delete_check_history(check_id)
        
        # 4. Логуємо успішне видалення
        logging.info(f"Check '{check_name}' (ID: {check_id}) completely deleted with all associated data")
        
        return jsonify({
            "message": f"Check {check_id} deleted successfully", 
            "deleted_check_name": check_name
        }), 200
        
    except Exception as e:
        logging.error(f"Error during complete deletion of check {check_id}: {e}", exc_info=True)
        return jsonify({"error": "An error occurred while deleting the check"}), 500

@app.errorhandler(404)
def not_found_error(error):
    """Обробник для 404 помилок."""
    logging.warning(f"404 error for request: {request.url}")
    return render_template('error.html', 
                         error_message="Сторінка не знайдена"), 404

if __name__ == '__main__':
    # Ініціалізуємо та запускаємо планувальник
    try:
        print("=== ДІАГНОСТИКА ЗАПУСКУ ===")
        # Завантажуємо існуючі перевірки для ініціалізації планувальника
        existing_checks = data_manager.load_checks()
        active_checks = [check for check in existing_checks if check.get("status") == "active"]
        
        print(f"Знайдено перевірок: {len(existing_checks)}")
        print(f"Активних перевірок: {len(active_checks)}")
        
        for check in active_checks:
            logging.info(f"  - Активна перевірка: {check.get('name', 'Без назви')} (ID: {check['id']}, Інтервал: {check.get('interval', 'N/A')} хв.)")
        # Ініціалізуємо планувальник з існуючими перевірками
        scheduler_tasks.init_scheduler(existing_checks)
        
        # Запускаємо Flask додаток
        app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
    except (KeyboardInterrupt, SystemExit):
        logging.info("Application shutting down...")
    finally:
        # Зупиняємо планувальник при завершенні
        if hasattr(scheduler_tasks, 'scheduler') and scheduler_tasks.scheduler and scheduler_tasks.scheduler.running:
            logging.info("Ensuring scheduler is shut down in finally block...")
            try:
                scheduler_tasks.scheduler.shutdown(wait=False)
            except Exception as e:
                logging.error(f"Error shutting down scheduler: {e}")
