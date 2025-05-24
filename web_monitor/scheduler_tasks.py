import logging
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler

# ВИПРАВЛЕНО: Використовуємо абсолютні імпорти
import data_manager
import monitor_engine

scheduler = BackgroundScheduler(timezone="UTC") # Используем UTC для планировщика

def scheduled_check_task(check_id):
    """
    Задача, выполняемая по расписанию для одной проверки.
    """
    all_checks = data_manager.load_checks()
    check_config = next((c for c in all_checks if c['id'] == check_id), None)

    if not check_config:
        logging.error(f"Scheduler: Check with ID {check_id} not found for scheduled task.")
        return

    if check_config.get("status") == "paused":
        logging.info(f"Scheduler: Check '{check_config.get('name', check_id)}' is paused. Skipping.")
        return

    logging.info(f"Scheduler: Running task for check_id: {check_id} ('{check_config.get('name', '')}')")
    
    # Выполняем проверку
    status, new_hash, extracted_text, error_msg = monitor_engine.perform_check(
        check_id=check_config['id'],
        name=check_config.get('name', 'N/A'),
        url=check_config['url'],
        selector=check_config['selector'],
        last_hash=check_config.get('last_content_hash')
    )

    current_time_utc = datetime.now(timezone.utc)
    current_time_iso = current_time_utc.isoformat()

    # Формируем запись для истории
    history_entry = {
        "timestamp": current_time_iso,
        "status": status,
        "extracted_value": extracted_text,
        "content_hash": new_hash,
        "error_message": error_msg
    }

    # Сохраняем запись в историю
    data_manager.save_check_history_entry(check_id, history_entry)
    logging.info(f"Scheduler: History entry saved for check_id: {check_id}")

    # ВИПРАВЛЕНО: Завантажуємо найсвіжіші дані перевірки перед оновленням
    all_checks = data_manager.load_checks()
    check_config = next((c for c in all_checks if c['id'] == check_id), None)
    
    if not check_config:
        logging.error(f"Scheduler: Check with ID {check_id} not found after history save.")
        return

    # Обновляем основную конфигурацию проверки
    check_config['last_checked_at'] = current_time_iso
    check_config['last_result'] = status
    
    # ВИПРАВЛЕНО: Детальне логування оновлення хешу
    old_hash = check_config.get('last_content_hash')
    if status in ["changed", "no_change"]:
        check_config['last_content_hash'] = new_hash
        logging.info(f"Hash update for check {check_id}: '{old_hash}' -> '{new_hash}' (Status: {status})")
    else:
        logging.info(f"Hash NOT updated for check {check_id} due to error status: {status}")
    
    # Очищуємо повідомлення про помилку при успішній перевірці
    if status != "error":
        check_config['last_error_message'] = None
    else:
        check_config['last_error_message'] = error_msg
    
    # Рассчитываем следующее время запуска для информации
    try:
        job = scheduler.get_job(check_id)
        if job and job.next_run_time:
            # ВИПРАВЛЕНО: Правильне відображення наступного часу
            next_run_utc = job.next_run_time
            next_run_local = next_run_utc.astimezone()
            check_config['next_check_at'] = next_run_local.isoformat()
            logging.info(f"Next run for {check_id}: UTC={next_run_utc.isoformat()}, Local={next_run_local.isoformat()}")
        else:
            check_config['next_check_at'] = None
            logging.warning(f"Could not get next_run_time for job {check_id} - job may not exist")
    except Exception as e:
        logging.warning(f"Scheduler: Could not get next_run_time for job {check_id}: {e}")
        check_config['next_check_at'] = None

    # ВИПРАВЛЕНО: Зберігаємо оновлений список
    data_manager.save_checks(all_checks)
    
    # ДОДАНО: Перевіряємо, чи хеш справді збережено
    saved_checks = data_manager.load_checks()
    saved_check = next((c for c in saved_checks if c['id'] == check_id), None)
    if saved_check:
        logging.info(f"Verification after save - Check {check_id}: saved hash = '{saved_check.get('last_content_hash')}', expected = '{new_hash if status in ['changed', 'no_change'] else old_hash}'")
    
    logging.info(f"Scheduler: Task for check_id: {check_id} ('{check_config.get('name', '')}') completed. Status: {status}. Next run: {check_config.get('next_check_at', 'N/A')}")

    # Отправка уведомления, если статус 'changed' или 'error' (будет добавлено позже)
    # if status == "changed" or status == "error":
    #     message = f"Check '{check_config.get('name', check_id)}' status: {status}."
    #     if extracted_text and status == "changed":
    #         message += f"\nNew value: {extracted_text}"
    #     if error_msg:
    #         message += f"\nError: {error_msg}"
    #     # telegram_sender.send_telegram_message(message) # Раскомментировать, когда telegram_sender будет готов

def init_scheduler(app_checks):
    """
    Инициализирует и запускает планировщик с задачами из app_checks.
    Удаляет старые задачи перед добавлением новых.
    """
    if scheduler.running:
        logging.info("Scheduler is already running. Shutting down to re-initialize.")
        scheduler.shutdown(wait=False)
        
    # Пересоздаем планировщик для чистоти стано
    globals()['scheduler'] = BackgroundScheduler(timezone="UTC")
    logging.info("Scheduler: Initializing...")
    
    active_checks_count = 0
    for check_config in app_checks:
        # ВИПРАВЛЕНО: Перевіряємо статус "active" замість != "paused"
        if check_config.get("status") == "active":
            try:
                interval_minutes = int(check_config.get('interval', 5))
                if interval_minutes <= 0:
                    logging.warning(f"Scheduler: Invalid interval {interval_minutes} for check '{check_config.get('name', check_config['id'])}'. Setting to 5 minutes.")
                    interval_minutes = 5
                
                # ВИПРАВЛЕНО: Додаємо check_id як аргумент функції
                scheduler.add_job(
                    func=scheduled_check_task,
                    trigger='interval',
                    minutes=interval_minutes,
                    args=[check_config['id']],  # Передаємо check_id як аргумент
                    id=check_config['id'],
                    name=f"Check: {check_config.get('name', check_config['id'])}",
                    replace_existing=True
                )
                active_checks_count += 1
                logging.info(f"Scheduler: Added job for check_id: {check_config['id']} ('{check_config.get('name', '')}'), Interval: {interval_minutes} minutes.")
            except Exception as e:
                logging.error(f"Scheduler: Error adding job for check_id {check_config['id']}: {e}")
        else:
            logging.info(f"Scheduler: Check '{check_config.get('name', check_config['id'])}' has status '{check_config.get('status')}'. Not scheduling.")

    if not scheduler.running:
        try:
            scheduler.start(paused=False)
            logging.info(f"Scheduler: Started successfully with {active_checks_count} active checks.")
        except Exception as e:
            logging.error(f"Scheduler: Failed to start. {e}")
    else:
        logging.info(f"Scheduler: Already running (re-initialized with {active_checks_count} active checks).")

def update_job(check_id, interval_minutes):
    """Обновляет интервал существующей задачи или добавляет новую, если ее нет."""
    try:
        if interval_minutes <= 0:
            logging.warning(f"Scheduler: Invalid interval {interval_minutes} for check_id {check_id}. Not updating.")
            return False
        
        job = scheduler.get_job(check_id)
        if job:
            # Перепланувати існуючу задачу
            scheduler.reschedule_job(check_id, trigger='interval', minutes=interval_minutes)
            logging.info(f"Scheduler: Rescheduled job for check_id: {check_id} to {interval_minutes} minutes.")
            
        else:
            # Додати нову задачу, якщо її не існує
            all_checks = data_manager.load_checks()
            check_config = next((c for c in all_checks if c['id'] == check_id), None)
            if check_config and check_config.get("status") == "active":
                scheduler.add_job(
                    func=scheduled_check_task,
                    trigger='interval',
                    minutes=interval_minutes,
                    args=[check_config['id']],
                    id=check_config['id'],
                    name=f"Check: {check_config.get('name', check_config['id'])}",
                    replace_existing=True
                )
                logging.info(f"Scheduler: Added new job for check_id: {check_id} with interval {interval_minutes} minutes.")
                
            elif check_config and check_config.get("status") == "paused":
                logging.info(f"Scheduler: Check {check_id} is paused. Not adding job.")
                return False
            else:
                logging.warning(f"Scheduler: Check {check_id} not found in config. Cannot add job.")
                return False
        
        # ВИПРАВЛЕНО: Перевіряємо, чи завдання успішно створено/оновлено
        updated_job = scheduler.get_job(check_id)
        if updated_job and updated_job.next_run_time:
            logging.info(f"Job {check_id} successfully updated. Next run: {updated_job.next_run_time.isoformat()}")
            return True
        else:
            logging.error(f"Job {check_id} update failed - no next_run_time found")
            return False
            
    except Exception as e:
        logging.error(f"Scheduler: Error updating job for check_id {check_id}: {e}")
        return False

def remove_job(check_id):
    """Удаляет задачу из планировщика."""
    try:
        job = scheduler.get_job(check_id)
        if job:
            scheduler.remove_job(check_id)
            logging.info(f"Scheduler: Removed job for check_id: {check_id}.")
        else:
            logging.info(f"Scheduler: Job for check_id: {check_id} not found, no need to remove.")
        return True
    except Exception as e:
        logging.error(f"Scheduler: Error removing job for check_id {check_id}: {e}")
        return False

def pause_job(check_id):
    """Приостанавливает задачу в планировщике (если она существует)."""
    try:
        job = scheduler.get_job(check_id)
        if job:
            scheduler.pause_job(check_id)
            logging.info(f"Scheduler: Paused job for check_id: {check_id}.")
        else:
            logging.info(f"Scheduler: Job for check_id: {check_id} not found, cannot pause.")
        return True
    except Exception as e:
        logging.error(f"Scheduler: Error pausing job for check_id {check_id}: {e}")
        return False

def resume_job(check_id):
    """Возобновляет задачу в планировщике (если она существует)."""
    try:
        job = scheduler.get_job(check_id)
        if job:
            scheduler.resume_job(check_id)
            logging.info(f"Scheduler: Resumed job for check_id: {check_id}.")
        else:
            # Если задачи нет, но проверка активна, попробуем ее добавить
            all_checks = data_manager.load_checks()
            check_config = next((c for c in all_checks if c['id'] == check_id), None)
            if check_config and check_config.get("status") != "paused": # Должен быть 'active'
                interval_minutes = int(check_config.get('interval', 5))
                update_job(check_id, interval_minutes) # update_job добавит, если нет
                logging.info(f"Scheduler: Job for check_id: {check_id} was not found, attempted to add and resume.")
            else:
                logging.info(f"Scheduler: Job for check_id: {check_id} not found or check is not active, cannot resume.")
        return True
    except Exception as e:
        logging.error(f"Scheduler: Error resuming job for check_id {check_id}: {e}")
        return False

def get_scheduler_diagnostics():
    """
    Повертає діагностичну інформацію про планувальник.
    """
    if not scheduler.running:
        return {
            "status": "stopped",
            "jobs_count": 0,
            "jobs": []
        }
    
    jobs_info = []
    current_time = datetime.now(timezone.utc)
    
    for job in scheduler.get_jobs():
        job_info = {
            "id": job.id,
            "name": job.name,
            "next_run_utc": job.next_run_time.isoformat() if job.next_run_time else None,
            "next_run_local": job.next_run_time.astimezone().isoformat() if job.next_run_time else None,
            "is_overdue": job.next_run_time < current_time if job.next_run_time else False,
            "func": str(job.func),
            "trigger": str(job.trigger),
            "args": job.args
        }
        jobs_info.append(job_info)
    
    return {
        "status": "running",
        "current_time_utc": current_time.isoformat(),
        "current_time_local": current_time.astimezone().isoformat(),
        "jobs_count": len(jobs_info),
        "jobs": jobs_info
    }

def force_scheduler_check():
    """
    Примусово перевіряє та запускає прострочені завдання.
    """
    if not scheduler.running:
        logging.error("Scheduler is not running, cannot force check")
        return False
    
    try:
        current_time = datetime.now(timezone.utc)
        forced_jobs = 0
        
        for job in scheduler.get_jobs():
            if job.next_run_time and job.next_run_time < current_time:
                logging.warning(f"Found overdue job {job.id}: should have run at {job.next_run_time}, now is {current_time}")
                
                # Примусово запускаємо завдання
                try:
                    job.func(*job.args)
                    forced_jobs += 1
                    logging.info(f"Manually executed overdue job {job.id}")
                except Exception as e:
                    logging.error(f"Error executing overdue job {job.id}: {e}")
        
        if forced_jobs > 0:
            logging.info(f"Forced execution of {forced_jobs} overdue jobs")
        else:
            logging.info("No overdue jobs found")
        
        return True
        
    except Exception as e:
        logging.error(f"Error during forced scheduler check: {e}")
        return False

# Также убедимся, что планировщик корректно останавлиется при завершении приложения
import atexit
atexit.register(lambda: scheduler.shutdown(wait=False) if scheduler.running else None)

