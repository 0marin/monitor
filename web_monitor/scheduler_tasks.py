import logging
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from . import data_manager
from . import monitor_engine
# from . import telegram_sender # Пока закомментировано, если не используется

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

    # Обновляем основную конфигурацию проверки
    check_config['last_checked_at'] = current_time_iso
    check_config['last_result'] = status
    if status != "error": # Обновляем хеш только если не было ошибки при проверке
        check_config['last_content_hash'] = new_hash
    check_config['last_error_message'] = error_msg
    
    # Рассчитываем следующее время запуска для информации (приблизительно)
    # Это поле больше не используется для управления планировщиком напрямую,
    # но может быть полезно для отображения.
    try:
        job = scheduler.get_job(check_id)
        if job and job.next_run_time:
            check_config['next_check_at'] = job.next_run_time.isoformat()
        else:
            # Если джоба нет или время следующего запуска неизвестно, можно оставить старое или None
            check_config['next_check_at'] = check_config.get('next_check_at') 
    except Exception as e:
        logging.warning(f"Scheduler: Could not get next_run_time for job {check_id}: {e}")
        check_config['next_check_at'] = check_config.get('next_check_at')


    data_manager.save_checks(all_checks)
    logging.info(f"Scheduler: Task for check_id: {check_id} ('{check_config.get('name', '')}') completed. Status: {status}. Next approximate run based on interval: {check_config.get('next_check_at', 'N/A')}")

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
        scheduler.shutdown(wait=False) # wait=False чтобы не блокировать, если задачи долгие
        # Даем немного времени на завершение, если необходимо
        # import time
        # time.sleep(1) 
        # Создаем новый экземпляр, чтобы избежать проблем с повторной инициализацией
        # globals()['scheduler'] = BackgroundScheduler(timezone="UTC")

    # Очищаем все существующие задачи, если shutdown не очистил (на всякий случай)
    # или если мы не создаем новый экземпляр
    # for job in scheduler.get_jobs():
    #     job.remove()
    # logging.info("Scheduler: All existing jobs removed.")
        
    # Пересоздаем планировщик для чистоты состояния
    # (более надежно, чем пытаться очистить существующий и перезапустить)
    globals()['scheduler'] = BackgroundScheduler(timezone="UTC")
    logging.info("Scheduler: Initializing...")
    
    for check_config in app_checks:
        if check_config.get("status") != "paused": # Не добавляем в планировщик неактивные или удаленные
            try:
                interval_minutes = int(check_config.get('interval', 5)) # По умолчанию 5 минут
                if interval_minutes <= 0:
                    logging.warning(f"Scheduler: Invalid interval {interval_minutes} for check '{check_config.get('name', check_config['id'])}'. Setting to 5 minutes.")
                    interval_minutes = 5
                
                scheduler.add_job(
                    func=scheduled_check_task,
                    trigger='interval',
                    minutes=interval_minutes,
                    id=check_config['id'],
                    name=f"Check: {check_config.get('name', check_config['id'])}",
                    replace_existing=True # Заменяет задачу, если она уже существует с таким id
                )
                logging.info(f"Scheduler: Added job for check_id: {check_config['id']} ('{check_config.get('name', '')}'), Interval: {interval_minutes} minutes.")
            except Exception as e:
                logging.error(f"Scheduler: Error adding job for check_id {check_config['id']}: {e}")
        else:
            logging.info(f"Scheduler: Check '{check_config.get('name', check_config['id'])}' is paused. Not scheduling.")


    if not scheduler.running:
        try:
            scheduler.start(paused=False) # paused=False чтобы задачи начали выполняться сразу
            logging.info("Scheduler: Started successfully.")
        except Exception as e:
            logging.error(f"Scheduler: Failed to start. {e}")
    else:
        logging.info("Scheduler: Already running (re-initialized or was running).")

def update_job(check_id, interval_minutes):
    """Обновляет интервал существующей задачи или добавляет новую, если ее нет."""
    try:
        if interval_minutes <= 0:
            logging.warning(f"Scheduler: Invalid interval {interval_minutes} for check_id {check_id}. Not updating.")
            return False
        
        job = scheduler.get_job(check_id)
        if job:
            scheduler.reschedule_job(check_id, trigger='interval', minutes=interval_minutes)
            logging.info(f"Scheduler: Rescheduled job for check_id: {check_id} to {interval_minutes} minutes.")
        else:
            # Если задачи нет, нужно загрузить конфигурацию и добавить ее
            # Это может произойти, если проверка была добавлена, когда планировщик не работал,
            # или была удалена из планировщика по какой-то причине.
            all_checks = data_manager.load_checks()
            check_config = next((c for c in all_checks if c['id'] == check_id), None)
            if check_config and check_config.get("status") != "paused":
                 scheduler.add_job(
                    func=scheduled_check_task,
                    trigger='interval',
                    minutes=interval_minutes,
                    id=check_config['id'],
                    name=f"Check: {check_config.get('name', check_config['id'])}",
                    replace_existing=True
                )
                 logging.info(f"Scheduler: Added new job for check_id: {check_id} with interval {interval_minutes} minutes (was not found).")
            elif check_config and check_config.get("status") == "paused":
                logging.info(f"Scheduler: Check {check_id} is paused. Not adding/rescheduling job.")
            else:
                logging.warning(f"Scheduler: Check {check_id} not found in config. Cannot add/reschedule job.")
                return False
        return True
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

# Также убедимся, что планировщик корректно останавливается при завершении приложения
import atexit
atexit.register(lambda: scheduler.shutdown(wait=False) if scheduler.running else None)

