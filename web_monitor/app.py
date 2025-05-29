from flask import Flask, request, jsonify, render_template, redirect, url_for
import os
import uuid
import logging
import sys
from datetime import datetime, timezone

# ВИПРАВЛЕНО: Спрощуємо імпорти - використовуємо абсолютні імпорти
import data_manager
import scheduler_tasks
import monitor_engine

# Telegram sender поки не обов'язковий
try:
    from telegram_sender import send_telegram_message
except ImportError:
    def send_telegram_message(message):
        logging.warning("Telegram sender not available")

# Налаштування логування
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/app.log', encoding='utf-8')  # ВИПРАВЛЕНО: прибрав 'web_monitor/'
    ]
)

print("🚀 Starting Web Monitor application...")
logging.info("Starting Web Monitor application")

app = Flask(__name__, template_folder='templates', static_folder='static')

def format_datetime_filter(value, format='%d %B %Y %H:%M:%S'):
    """Форматирует строку ISO datetime в читаемый вид в локальном времени системы."""
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
        
        # ВИПРАВЛЕНО: Конвертуємо в локальний час системи
        if dt_object.tzinfo is not None:
            # Конвертуємо з UTC в локальний час
            dt_object = dt_object.astimezone()
        else:
            # Якщо немає timezone info, вважаємо що це вже локальний час
            pass
        
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
        
        # Получаем историю проверок
        check_history = data_manager.load_check_history(check_id)
        
        # ВИПРАВЛЕНО: Перевіряємо синхронізацію даних з історією
        if check_history:
            # Сортуємо історію за часом (нові спочатку)
            check_history.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            latest_history = check_history[0]
            
            # Перевіряємо, чи основні дані застарілі
            check_time = check_details.get('last_checked_at')
            history_time = latest_history.get('timestamp')
            
            if history_time and (not check_time or history_time > check_time):
                logging.info(f"Data mismatch detected for check {check_id}. Syncing with latest history.")
                data_manager.sync_check_with_latest_history(check_id)
                # Перезавантажуємо дані після синхронізації
                check_details = data_manager.get_check_by_id(check_id)
        
        return render_template('monitor_details.html', 
                             check=check_details, 
                             history=check_history,
                             check_id=check_id)
    except Exception as e:
        app.logger.error(f"Error loading check details for {check_id}: {e}", exc_info=True)
        return render_template('error.html', 
                             error_message="An error occurred while loading check details"), 500

@app.route('/check/<check_id>/edit')
def edit_check_page(check_id):
    """Відображає сторінку редагування перевірки."""
    try:
        check_details = data_manager.get_check_by_id(check_id)
        if not check_details:
            return render_template('error.html', 
                                 error_message=f"Check with ID {check_id} not found"), 404
        
        return render_template('edit_check.html', check=check_details)
    except Exception as e:
        app.logger.error(f"Error loading edit page for {check_id}: {e}", exc_info=True)
        return render_template('error.html', 
                             error_message="An error occurred while loading edit page"), 500

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
    """API эндпоінт для получения списка всех проверок."""
    checks = data_manager.load_checks()
    
    # ДОДАНО: Додаємо поточний контент до кожної перевірки
    for check in checks:
        check_id = check.get('id')
        if check_id:
            # Завантажуємо останній запис з історії
            history = data_manager.load_check_history(check_id)
            if history:
                # Сортуємо за часом (найновіші спочатку)
                history.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
                latest_entry = history[0]
                
                # Додаємо поточний контент
                check['current_content'] = latest_entry.get('extracted_value')
                check['current_timestamp'] = latest_entry.get('timestamp')
    
    return jsonify(checks), 200

@app.route('/api/checks/<check_id>', methods=['GET'])
def api_get_check_details(check_id):
    """API эндпоінт для получения детальной информации о проверке по ID."""
    check_details = data_manager.get_check_by_id(check_id)
    if check_details:
        return jsonify(check_details), 200
    else:
        return jsonify({"error": "Check not found"}), 404

@app.route('/api/system-status', methods=['GET'])
def api_get_system_status():
    """API эндпоінт для получения состояния системы."""
    try:
        active_jobs = scheduler_tasks.scheduler.get_jobs()
        
        # ДОДАНО: Перевіряємо прострочені завдання
        current_time = datetime.now(timezone.utc)
        overdue_jobs = []
        
        for job in active_jobs:
            if job.next_run_time and job.next_run_time < current_time:
                overdue_jobs.append({
                    "id": job.id,
                    "name": job.name,
                    "overdue_by_seconds": (current_time - job.next_run_time).total_seconds()
                })
        
        status_info = {
            "scheduler_status": "Running" if scheduler_tasks.scheduler.running else "Stopped",
            "active_scheduled_jobs": len(active_jobs),
            "overdue_jobs_count": len(overdue_jobs),
            "overdue_jobs": overdue_jobs,
            "current_time_utc": current_time.isoformat(),
            "current_time_local": current_time.astimezone().isoformat(),
            "job_ids": [job.id for job in active_jobs],
            "last_global_error": None,
            "app_version": "0.1.2"
        }
        return jsonify(status_info), 200
    except Exception as e:
        app.logger.error(f"Error getting system status: {e}", exc_info=True)
        return jsonify({"error": "Failed to get system status"}), 500

@app.route('/api/checks/<check_id>', methods=['PUT'])
def api_update_check(check_id):
    """API эндпоінт для обновления существующей проверки."""
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
    """API эндпоінт для удаления проверки."""
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

@app.route('/api/checks/<check_id>/debug', methods=['GET'])
def api_debug_check(check_id):
    """API ендпоінт для діагностики проблем з перевіркою."""
    try:
        # Перевіряємо, чи існує перевірка
        check_details = data_manager.get_check_by_id(check_id)
        if not check_details:
            return jsonify({"error": f"Check with ID {check_id} not found"}), 404
        
        logging.info(f"Starting debug for check {check_id}")
        
        # Виконуємо діагностику з детальною обробкою помилок
        try:
            data_manager.debug_check_data(check_id)
            logging.info(f"Debug data completed for {check_id}")
        except Exception as e:
            logging.error(f"Error during debug_check_data for {check_id}: {e}")
        
        try:
            data_manager.clean_duplicate_history_entries(check_id)
            logging.info(f"Clean duplicates completed for {check_id}")
        except Exception as e:
            logging.error(f"Error during clean_duplicate_history_entries for {check_id}: {e}")
        
        try:
            sync_result = data_manager.sync_check_with_latest_history(check_id)
            logging.info(f"Sync with history completed for {check_id}: {sync_result}")
        except Exception as e:
            logging.error(f"Error during sync_check_with_latest_history for {check_id}: {e}")
        
        return jsonify({
            "message": "Debug completed successfully", 
            "check_id": check_id,
            "details": "Check application logs for detailed debug information"
        }), 200
        
    except Exception as e:
        app.logger.error(f"Critical error during debug for {check_id}: {e}", exc_info=True)
        return jsonify({
            "error": f"Debug failed for check {check_id}",
            "details": str(e)
        }), 500

@app.route('/api/checks/<check_id>/manual-check', methods=['POST'])
def api_manual_check(check_id):
    """API ендпоінт для позачергової перевірки."""
    try:
        check_details = data_manager.get_check_by_id(check_id)
        if not check_details:
            return jsonify({"error": "Check not found"}), 404
        
        logging.info(f"Manual check triggered for {check_id} by user")
        
        # Виконуємо перевірку
        status, new_hash, extracted_text, error_msg = monitor_engine.perform_check(
            check_id=check_details['id'],
            name=check_details.get('name', 'Manual Check'),
            url=check_details['url'],
            selector=check_details['selector'],
            last_hash=check_details.get('last_content_hash')
        )
        
        # Оновлюємо дані перевірки
        current_time_utc = datetime.now(timezone.utc)
        current_time_iso = current_time_utc.isoformat()
        
        # Зберігаємо в історію
        history_entry = {
            "timestamp": current_time_iso,
            "status": status,
            "extracted_value": extracted_text,
            "content_hash": new_hash,
            "error_message": error_msg
        }
        data_manager.save_check_history_entry(check_id, history_entry)
        
        # Оновлюємо основні дані
        all_checks = data_manager.load_checks()
        for check in all_checks:
            if check['id'] == check_id:
                check['last_checked_at'] = current_time_iso
                check['last_result'] = status
                if status in ["changed", "no_change"]:
                    check['last_content_hash'] = new_hash
                if status != "error":
                    check['last_error_message'] = None
                else:
                    check['last_error_message'] = error_msg
                
                # ВИПРАВЛЕНО: ОБОВ'ЯЗКОВО оновлюємо наступний час перевірки
                if check.get('status') == 'active':
                    try:
                        job = scheduler_tasks.scheduler.get_job(check_id)
                        if job and job.next_run_time:
                            next_run_local = job.next_run_time.astimezone()
                            old_time = check.get('next_check_at')
                            new_time = next_run_local.isoformat()
                            check['next_check_at'] = new_time
                            logging.info(f"🔄 Manual check - updated next_check_at: {old_time} -> {new_time}")
                        else:
                            # ДОДАНО: Якщо завдання не знайдено, створюємо його
                            logging.warning(f"No job found for active check {check_id} during manual check. Creating job...")
                            interval_minutes = check.get('interval', 5)
                            if scheduler_tasks.update_job(check_id, interval_minutes):
                                # Спробуємо отримати час ще раз
                                import time
                                time.sleep(0.1)
                                job = scheduler_tasks.scheduler.get_job(check_id)
                                if job and job.next_run_time:
                                    next_run_local = job.next_run_time.astimezone()
                                    check['next_check_at'] = next_run_local.isoformat()
                                    logging.info(f"✅ Created missing job and set next_check_at: {check['next_check_at']}")
                                else:
                                    logging.error(f"❌ Failed to get next_check_at even after creating job for {check_id}")
                                    check['next_check_at'] = None
                            else:
                                logging.error(f"❌ Failed to create missing job for {check_id}")
                                check['next_check_at'] = None
                    except Exception as e:
                        logging.warning(f"Could not get next_run_time for job {check_id}: {e}")
                        check['next_check_at'] = None
                else:
                    # Для неактивних перевірок очищуємо час
                    check['next_check_at'] = None
                break
        
        data_manager.save_checks(all_checks)
        
        # ДОДАНО: Повертаємо оновлену інформацію про планувальник
        scheduler_job = scheduler_tasks.scheduler.get_job(check_id)
        
        return jsonify({
            "status": status,
            "extracted_text": extracted_text,
            "error_message": error_msg,
            "timestamp": current_time_iso,
            "next_check_at": all_checks[next(i for i, c in enumerate(all_checks) if c['id'] == check_id)].get('next_check_at'),
            "scheduler_job_exists": scheduler_job is not None,
            "scheduler_next_run": scheduler_job.next_run_time.astimezone().isoformat() if scheduler_job and scheduler_job.next_run_time else None
        }), 200
        
    except Exception as e:
        app.logger.error(f"Error during manual check for {check_id}: {e}", exc_info=True)
        return jsonify({"error": "Manual check failed"}), 500

@app.route('/api/checks/<check_id>/toggle-status', methods=['POST'])
def api_toggle_check_status(check_id):
    """API ендпоінт для деактивації/активації перевірки."""
    try:
        check_details = data_manager.get_check_by_id(check_id)
        if not check_details:
            return jsonify({"error": "Check not found"}), 404
        
        current_status = check_details.get('status', 'active')
        new_status = 'paused' if current_status == 'active' else 'active'
        
        logging.info(f"Toggling check {check_id} from {current_status} to {new_status}")
        
        # Оновлюємо статус в базі даних
        all_checks = data_manager.load_checks()
        check_result = None
        target_check = None
        
        for check in all_checks:
            if check['id'] == check_id:
                check['status'] = new_status
                target_check = check
                # ВИПРАВЛЕНО: Очищуємо старий час наступної перевірки при деактивації
                if new_status == 'paused':
                    check['next_check_at'] = None
                break
        
        if not target_check:
            return jsonify({"error": "Check not found in data"}), 404
        
        # ВИПРАВЛЕНО: Зберігаємо дані ПЕРЕД роботою з планувальником
        data_manager.save_checks(all_checks)
        
        # Управляємо планувальником
        if new_status == 'active':
            # Активуємо - додаємо/поновлюємо завдання
            interval_minutes = check_details.get('interval', 5)
            
            # ВИПРАВЛЕНО: Спочатку видаляємо старе завдання, якщо є
            try:
                scheduler_tasks.remove_job(check_id)
                logging.info(f"Removed old job for {check_id} before activation")
            except Exception as e:
                logging.info(f"No old job to remove for {check_id}: {e}")
            
            # Додаємо нове завдання
            success = scheduler_tasks.update_job(check_id, interval_minutes)
            
            if success:
                # ВИПРАВЛЕНО: Чекаємо та форсуємо оновлення next_check_at
                import time
                time.sleep(0.2)  # Збільшуємо паузу для стабілізації
                
                # ДОДАНО: Повторюємо спроби отримання часу
                for attempt in range(3):
                    try:
                        job = scheduler_tasks.scheduler.get_job(check_id)
                        if job and job.next_run_time:
                            next_run_local = job.next_run_time.astimezone()
                            target_check['next_check_at'] = next_run_local.isoformat()
                            logging.info(f"✅ Attempt {attempt+1}: Set next_check_at for activated job {check_id}: {target_check['next_check_at']}")
                            break
                        else:
                            logging.warning(f"❌ Attempt {attempt+1}: Could not get next_run_time for activated job {check_id}")
                            if attempt < 2:
                                time.sleep(0.1 * (attempt + 1))  # Прогресивна затримка
                    except Exception as e:
                        logging.warning(f"❌ Attempt {attempt+1}: Error getting next_run_time for activated job {check_id}: {e}")
                        if attempt < 2:
                            time.sleep(0.1 * (attempt + 1))
                
                if not target_check.get('next_check_at'):
                    logging.error(f"❌ Failed to set next_check_at after 3 attempts for {check_id}")
            else:
                logging.error(f"❌ Failed to create job for {check_id}")
                target_check['next_check_at'] = None
            
            # Виконуємо одразу перевірку при активації
            try:
                status, new_hash, extracted_text, error_msg = monitor_engine.perform_check(
                    check_id=check_details['id'],
                    name=check_details.get('name', 'Activation Check'),
                    url=check_details['url'],
                    selector=check_details['selector'],
                    last_hash=check_details.get('last_content_hash')
                )
                
                # Зберігаємо результат
                current_time_utc = datetime.now(timezone.utc)
                current_time_iso = current_time_utc.isoformat()
                
                history_entry = {
                    "timestamp": current_time_iso,
                    "status": status,
                    "extracted_value": extracted_text,
                    "content_hash": new_hash,
                    "error_message": error_msg
                }
                data_manager.save_check_history_entry(check_id, history_entry)
                
                # Оновлюємо основні дані після перевірки
                target_check['last_checked_at'] = current_time_iso
                target_check['last_result'] = status
                if status in ["changed", "no_change"]:
                    target_check['last_content_hash'] = new_hash
                if status != "error":
                    target_check['last_error_message'] = None
                else:
                    target_check['last_error_message'] = error_msg
                
                check_result = {
                    "status": status,
                    "extracted_text": extracted_text,
                    "error_message": error_msg
                }
                
                # ДОДАНО: Перевіряємо час після виконання перевірки
                try:
                    job = scheduler_tasks.scheduler.get_job(check_id)
                    if job and job.next_run_time:
                        next_run_local = job.next_run_time.astimezone()
                        target_check['next_check_at'] = next_run_local.isoformat()
                        logging.info(f"🔄 Updated next_check_at after activation check: {target_check['next_check_at']}")
                except Exception as e:
                    logging.warning(f"Could not update next_check_at after activation check: {e}")
                
            except Exception as e:
                logging.error(f"Error during activation check for {check_id}: {e}")
                check_result = {
                    "status": "error",
                    "error_message": str(e)
                }
        else:
            # Деактивуємо - видаляємо завдання
            scheduler_tasks.remove_job(check_id)
        
        # ВИПРАВЛЕНО: Зберігаємо оновлені дані після всіх операцій
        data_manager.save_checks(all_checks)
        
        # ДОДАНО: Повертаємо свіжі дані перевірки
        updated_check = data_manager.get_check_by_id(check_id)
        
        return jsonify({
            "old_status": current_status,
            "new_status": new_status,
            "check_result": check_result if new_status == 'active' else None,
            "updated_check": updated_check,
            "next_check_at": updated_check.get('next_check_at'),
            "scheduler_job_exists": scheduler_tasks.scheduler.get_job(check_id) is not None
        }), 200
        
    except Exception as e:
        app.logger.error(f"Error toggling status for {check_id}: {e}", exc_info=True)
        return jsonify({"error": "Failed to toggle status"}), 500

@app.route('/api/force-check-all', methods=['POST'])
def api_force_check_all():
    """API ендпоінт для примусової перевірки всіх активних моніторів."""
    try:
        logging.info("Force check all triggered by user")
        
        # Використовуємо функцію з scheduler_tasks
        executed_count = scheduler_tasks.execute_all_active_checks()
        
        return jsonify({
            "message": f"Примусово виконано {executed_count} активних перевірок",
            "executed_count": executed_count,
            "success": True
        }), 200
        
    except Exception as e:
        app.logger.error(f"Error during force check all: {e}", exc_info=True)
        return jsonify({"error": f"Примусова перевірка не вдалася: {str(e)}"}), 500

@app.route('/api/scheduler-diagnostics', methods=['GET'])
def api_scheduler_diagnostics():
    """API ендпоінт для діагностики планувальника."""
    try:
        # Використовуємо функцію з scheduler_tasks
        diagnostics = scheduler_tasks.get_scheduler_diagnostics()
        
        return jsonify(diagnostics), 200
    except Exception as e:
        app.logger.error(f"Error during scheduler diagnostics: {e}", exc_info=True)
        return jsonify({"error": "Diagnostics failed"}), 500

@app.route('/api/test-selector', methods=['POST'])
def api_test_selector():
    """API ендпоінт для тестування селектора на реальному сайті."""
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    data = request.get_json()
    url = data.get('url')
    selector = data.get('selector')
    
    if not url:
        return jsonify({"error": "URL is required"}), 400
    
    if not selector:
        return jsonify({"error": "Selector is required"}), 400
    
    try:
        # Тестуємо селектор
        status, hash_value, extracted_text, error_msg = monitor_engine.perform_check(
            check_id="test", 
            name="Test Selector", 
            url=url, 
            selector=selector, 
            last_hash=None
        )
        
        return jsonify({
            "status": status,
            "extracted_text": extracted_text,
            "content_hash": hash_value,
            "error_message": error_msg,
            "text_length": len(extracted_text) if extracted_text else 0,
            "success": status != "error"
        }), 200
        
    except Exception as e:
        app.logger.error(f"Error testing selector: {e}", exc_info=True)
        return jsonify({"error": f"Test failed: {str(e)}"}), 500

@app.route('/api/force-update-times', methods=['POST'])
def api_force_update_times():
    """API ендпоінт для примусового оновлення часів наступних перевірок."""
    try:
        updated_count = scheduler_tasks.force_update_next_check_times()
        
        return jsonify({
            "message": f"Примусово оновлено {updated_count} часів наступних перевірок",
            "updated_count": updated_count,
            "success": True
        }), 200
        
    except Exception as e:
        app.logger.error(f"Error during force update times: {e}", exc_info=True)
        return jsonify({"error": f"Помилка оновлення часів: {str(e)}"}), 500

@app.route('/api/app-sleep-toggle', methods=['POST'])
def api_app_sleep_toggle():
    """API ендпоінт для переведення застосунку в режим сну та виходу з нього."""
    try:
        # Отримуємо поточний стан системи
        is_sleeping = scheduler_tasks.is_app_sleeping()
        
        if is_sleeping:
            # Виводимо з режиму сну - відновлюємо всі активні перевірки
            logging.info("Waking up application - resuming all active checks")
            
            # Відновлюємо планувальник
            success = scheduler_tasks.wake_up_app()
            
            if success:
                return jsonify({
                    "action": "wake_up",
                    "old_state": "sleeping",
                    "new_state": "active",
                    "message": "Застосунок виведено з режиму сну. Всі активні перевірки відновлено.",
                    "success": True
                }), 200
            else:
                return jsonify({
                    "error": "Помилка виведення з режиму сну",
                    "success": False
                }), 500
        else:
            # Переводимо в режим сну - зупиняємо всі перевірки
            logging.info("Putting application to sleep - pausing all active checks")
            
            # Зупиняємо планувальник
            success = scheduler_tasks.put_app_to_sleep()
            
            if success:
                return jsonify({
                    "action": "sleep",
                    "old_state": "active", 
                    "new_state": "sleeping",
                    "message": "Застосунок переведено в режим сну. Всі перевірки призупинено.",
                    "success": True
                }), 200
            else:
                return jsonify({
                    "error": "Помилка переведення в режим сну",
                    "success": False
                }), 500
                
    except Exception as e:
        app.logger.error(f"Error during app sleep toggle: {e}", exc_info=True)
        return jsonify({
            "error": f"Помилка управління режимом сну: {str(e)}",
            "success": False
        }), 500

@app.route('/api/app-status', methods=['GET'])
def api_app_status():
    """API ендпоінт для отримання статусу застосунку (сон/активний)."""
    try:
        is_sleeping = scheduler_tasks.is_app_sleeping()
        active_jobs = scheduler_tasks.scheduler.get_jobs() if scheduler_tasks.scheduler.running else []
        
        # ВИПРАВЛЕНО: Підраховуємо активні перевірки з файлу даних
        all_checks = data_manager.load_checks()
        active_checks_count = len([check for check in all_checks if check.get('status') == 'active'])
        
        return jsonify({
            "is_sleeping": is_sleeping,
            "scheduler_running": scheduler_tasks.scheduler.running if hasattr(scheduler_tasks, 'scheduler') else False,
            "active_jobs_count": len(active_jobs),
            "active_checks": active_checks_count,  # ДОДАНО: правильний підрахунок
            "total_checks": len(all_checks),      # ДОДАНО: загальна кількість
            "status": "sleeping" if is_sleeping else "active"
        }), 200
        
    except Exception as e:
        app.logger.error(f"Error getting app status: {e}", exc_info=True)
        return jsonify({"error": "Failed to get app status"}), 500

# --- Запуск програми ---
if __name__ == '__main__':
    print("=== ДІАГНОСТИКА ЗАПУСКУ ===")
    
    try:
        # Перевіряємо наявність необхідних каталогів
        required_dirs = ['data', 'logs', 'data/history']
        for dir_name in required_dirs:
            dir_path = dir_name
            if not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
                print(f"✅ Створено каталог: {dir_path}")
            else:
                print(f"✅ Каталог існує: {dir_path}")
        
        # Завантажуємо існуючі перевірки
        print("📂 Завантажуємо перевірки...")
        existing_checks = data_manager.load_checks()
        active_checks = [check for check in existing_checks if check.get("status") == "active"]
        
        print(f"📊 Знайдено перевірок: {len(existing_checks)}")
        print(f"📊 Активних перевірок: {len(active_checks)}")
        
        for check in active_checks:
            print(f"  ✓ {check.get('name', 'Без назви')} (ID: {check['id'][:8]}..., Інтервал: {check.get('interval', 'N/A')} хв.)")
        
        # Ініціалізуємо планувальник
        print("⚙️  Ініціалізуємо планувальник...")
        scheduler_tasks.init_scheduler(existing_checks)
        print("✅ Планувальник ініціалізовано")
        
        # ДОДАНО: Оновлюємо часи наступних перевірок
        print("🕒 Оновлюємо часи наступних перевірок...")
        update_next_check_times()
        print("✅ Часи наступних перевірок оновлено")
        
        # ДОДАНО: Виконуємо початкові перевірки всіх активних моніторів
        print("🔍 Виконуємо початкові перевірки...")
        perform_initial_checks()
        print("✅ Початкові перевірки завершено")
        
        # ВИПРАВЛЕНО: Запускаємо Flask сервер тільки якщо запущено безпосередньо
        print("🌐 Запускаємо Flask сервер...")
        print("🔗 Сервер буде доступний за адресою:")
        print("   📍 Локально: http://localhost:5000")
        print("   📍 В мережі: http://127.0.0.1:5000")
        print("   📍 Для доступу з інших пристроїв: http://[ваша_IP]:5000")
        print("=" * 50)
        
        app.run(
            debug=True, 
            host='0.0.0.0',
            port=5000,
            use_reloader=False
        )
        
    except ImportError as e:
        print(f"❌ ПОМИЛКА ІМПОРТУ: {e}")
        print("💡 Перевірте, чи знаходитесь ви в правильному каталозі:")
        print("   cd d:\\AI\\Monitor2\\web_monitor")
        print("   python app.py")
        sys.exit(1)
        
    except Exception as e:
        print(f"❌ КРИТИЧНА ПОМИЛКА: {e}")
        logging.error(f"Critical startup error: {e}", exc_info=True)
        sys.exit(1)
        
    except (KeyboardInterrupt, SystemExit):
        print("\n🛑 Зупинка застосунку...")
        logging.info("Application shutting down...")
        
    finally:
        # Зупиняємо планувальник
        if hasattr(scheduler_tasks, 'scheduler') and scheduler_tasks.scheduler and scheduler_tasks.scheduler.running:
            print("🔄 Зупиняємо планувальник...")
            try:
                scheduler_tasks.scheduler.shutdown(wait=False)
                print("✅ Планувальник зупинено")
            except Exception as e:
                print(f"⚠️  Помилка зупинки планувальника: {e}")

# ДОДАНО: Створюємо Flask застосунок для імпорту
else:
    # Якщо app.py імпортується, а не запускається напряму
    # Все одно ініціалізуємо планувальник
    try:
        # Створюємо каталоги
        required_dirs = ['data', 'logs', 'data/history']
        for dir_name in required_dirs:
            if not os.path.exists(dir_name):
                os.makedirs(dir_name, exist_ok=True)
        
        # Завантажуємо перевірки та ініціалізуємо планувальник
        existing_checks = data_manager.load_checks()
        scheduler_tasks.init_scheduler(existing_checks)
        print("✅ Планувальник ініціалізовано при імпорті")
        
        # ДОДАНО: Оновлюємо часи і при імпорті
        update_next_check_times()
        print("✅ Часи наступних перевірок оновлено при імпорті")
        
        # ДОДАНО: Виконуємо початкові перевірки і при імпорті
        perform_initial_checks()
        print("✅ Початкові перевірки виконано при імпорті")
        
    except Exception as e:
        print(f"⚠️  Помилка ініціалізації при імпорті: {e}")

@app.route('/static-test')
def static_test():
    """Тестовий роут для перевірки статичних файлів."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>CSS Test</title>
        <link rel="stylesheet" href="/static/css/style.css">
    </head>
    <body>
        <div class="container">
            <h1>CSS Test</h1>
            <button class="btn btn-primary">Test Button</button>
            <p>Якщо кнопка має синій фон, CSS працює правильно.</p>
        </div>
    </body>
    </html>
    """
