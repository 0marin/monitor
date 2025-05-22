import logging
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import os # Добавлен импорт os для main блока

# Предполагается, что эти модули будут доступны
import data_manager
import monitor_engine

scheduler = BackgroundScheduler(daemon=True)

def scheduled_check_task(check_id):
    """
    Задача, выполняемая планировщиком для конкретной проверки.
    """
    logging.info(f"Scheduler: Running task for check_id: {check_id}")
    check_config = data_manager.get_check_by_id(check_id)

    if not check_config:
        logging.warning(f"Scheduler: Check with ID {check_id} not found. Removing job if exists.")
        if scheduler.get_job(check_id):
            scheduler.remove_job(check_id)
        return

    if check_config.get("status") != "active":
        logging.info(f"Scheduler: Check ID {check_id} ('{check_config.get('name', '')}') is not active. Skipping.")
        return

    # Выполняем проверку, передавая весь check_config
    result = monitor_engine.perform_check(check_config)

    # Обновляем данные проверки в checks.json
    check_config["last_checked_at"] = result["checked_at"]
    check_config["last_result"] = result["status"]
    check_config["last_error_message"] = result.get("error_message") # Используем .get для безопасности

    # Важно: обновляем хеш контента, если он был получен
    if result.get("new_content_hash") is not None: # Проверяем на None, т.к. хеш может быть пустой строкой (хотя наш get_content_hash не должен так делать)
        check_config["last_content_hash"] = result["new_content_hash"]
    
    # Обновляем время следующей проверки из данных задачи APScheduler
    job = scheduler.get_job(check_id)
    if job and job.next_run_time:
         check_config["next_check_at"] = job.next_run_time.isoformat()
    else:
        # Запасной вариант: если по какой-то причине job.next_run_time недоступен сразу
        interval_minutes = check_config.get("interval", 60)
        check_config["next_check_at"] = (datetime.utcnow() + timedelta(minutes=interval_minutes)).isoformat() + 'Z'
        logging.warning(f"Scheduler: Could not get next_run_time from job {check_id}. Calculated based on interval.")

    # Сохраняем обновленную конфигурацию проверки
    # Вместо перезаписи всего файла, лучше иметь функцию в data_manager для обновления одной проверки
    # Пока что оставим как есть, но это кандидат на рефакторинг в data_manager.py
    all_checks = data_manager.load_checks()
    updated = False
    for i, chk in enumerate(all_checks):
        if chk.get("id") == check_id:
            all_checks[i] = check_config
            updated = True
            break
    if updated:
        data_manager.save_checks(all_checks)
    else:
        logging.error(f"Scheduler: Failed to find check {check_id} in loaded checks to save updates.")
    
    logging.info(f"Scheduler: Task for check_id: {check_id} ('{check_config.get('name', '')}') completed. Status: {result['status']}. Next run: {check_config['next_check_at']}")
    
    # TODO: Отправка уведомления через telegram_sender, если были изменения или ошибки


def reschedule_check(check_config):
    """Добавляет или перепланирует задачу для проверки."""
    check_id = check_config.get("id")
    interval_minutes = check_config.get("interval", 60) 
    
    if not check_id:
        logging.error("Scheduler: Cannot schedule check without ID.")
        return

    job_exists = scheduler.get_job(check_id) is not None

    if job_exists:
        # Попытка изменить существующую задачу. 
        # APScheduler может не позволить изменить 'args' или 'func' существующей задачи напрямую через reschedule.
        # Проще удалить и добавить заново, если параметры, кроме интервала, могли измениться.
        # Но если меняется только интервал, reschedule_job достаточно.
        # Для простоты пока считаем, что reschedule_check вызывается, когда интервал мог измениться.
        try:
            scheduler.reschedule_job(check_id, trigger='interval', minutes=interval_minutes)
            logging.info(f"Scheduler: Rescheduled job for check_id: {check_id} ('{check_config.get('name', '')}') to run every {interval_minutes} minutes.")
        except Exception as e:
            logging.error(f"Scheduler: Error rescheduling job {check_id}: {e}. Removing and re-adding.")
            try:
                scheduler.remove_job(check_id)
                job_exists = False # Устанавливаем флаг, чтобы задача была добавлена ниже
            except Exception as e_rem:
                logging.error(f"Scheduler: Error removing job {check_id} for re-adding: {e_rem}")
                return # Не можем продолжить, если не удалось удалить
    
    if not job_exists: # Если задачи не было или она была удалена для пересоздания
        scheduler.add_job(
            scheduled_check_task,
            trigger='interval',
            minutes=interval_minutes,
            id=check_id,
            args=[check_id],
            next_run_time=datetime.now() + timedelta(seconds=10) # Запускаем первую проверку через 10 секунд
        )
        logging.info(f"Scheduler: Added new job for check_id: {check_id} ('{check_config.get('name', '')}') to run every {interval_minutes} minutes.")
    
    # Обновляем next_check_at в данных после добавления/перепланирования
    job = scheduler.get_job(check_id)
    if job and job.next_run_time:
        current_next_check_at = job.next_run_time.isoformat()
        if check_config.get("next_check_at") != current_next_check_at:
            check_config["next_check_at"] = current_next_check_at
            # Обновляем только если изменилось, чтобы избежать лишних записей в файл
            all_checks = data_manager.load_checks()
            updated_in_file = False
            for i, chk in enumerate(all_checks):
                if chk.get("id") == check_id:
                    all_checks[i]["next_check_at"] = check_config["next_check_at"]
                    updated_in_file = True
                    break
            if updated_in_file:
                data_manager.save_checks(all_checks)


def remove_scheduled_check(check_id):
    """Удаляет запланированную задачу."""
    if scheduler.get_job(check_id):
        try:
            scheduler.remove_job(check_id)
            logging.info(f"Scheduler: Removed job for check_id: {check_id}.")
        except Exception as e:
            logging.error(f"Scheduler: Error removing job {check_id}: {e}")


def load_and_schedule_all_active_checks():
    """Загружает все активные проверки и планирует их."""
    logging.info("Scheduler: Loading and scheduling all active checks...")
    all_checks = data_manager.load_checks()
    active_checks_count = 0
    for check_config in all_checks:
        if check_config.get("status") == "active":
            reschedule_check(check_config) # reschedule_check теперь обновляет next_check_at
            active_checks_count += 1
    logging.info(f"Scheduler: Processed {active_checks_count} active checks for scheduling.")


def start_scheduler():
    """Инициализирует и запускает планировщик."""
    if not scheduler.running:
        load_and_schedule_all_active_checks()
        scheduler.start()
        logging.info("Scheduler started.")
    else:
        logging.info("Scheduler is already running.")

def shutdown_scheduler():
    """Останавливает планировщик."""
    if scheduler.running:
        scheduler.shutdown()
        logging.info("Scheduler shut down.")

if __name__ == '__main__':
    # Пример для ручного тестирования планировщика
    # Убедимся, что каталог data существует
    if not os.path.exists(data_manager.DATA_DIR):
        os.makedirs(data_manager.DATA_DIR)
        
    if not os.path.exists(data_manager.CHECKS_FILE):
         data_manager.save_checks([])
    
    checks = data_manager.load_checks()
    test_check_id_manual = "test-scheduler-manual-001"
    test_check_found = any(c.get("id") == test_check_id_manual for c in checks)
    
    if not test_check_found:
        # Используем data_manager.add_check, который генерирует ID и другие поля
        data_manager.add_check({
            "name": "Test Scheduler Manual Check",
            "url": "http://example.com/scheduler-test-manual", # Используем http
            "interval": 1, 
            "status": "active"
        })
        # После add_check, ID будет сгенерирован, и он будет отличаться от test_check_id_manual
        # Для теста нам нужно знать ID, поэтому лучше найти его или использовать фиксированный,
        # но add_check не позволяет задать ID.
        # Для простоты теста, мы можем просто запустить load_and_schedule_all_active_checks.

    logging.info("Starting scheduler for manual test...")
    start_scheduler()
    
    try:
        while True:
            pass
    except (KeyboardInterrupt, SystemExit):
        logging.info("Shutting down scheduler from manual test...")
        shutdown_scheduler()