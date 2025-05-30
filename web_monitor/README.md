# Web Monitor

Веб-застосунок для відслідковування змін на веб-сайтах або їх конкретних елементах.

## Опис

Цей проект дозволяє користувачам додавати URL-адреси для моніторингу, вказувати CSS-селектори для конкретних елементів, встановлювати поріг зміни сторінки та часові інтервали перевірок. Система виявляє зміни, недоступність сайту або помилки та може надсилати сповіщення (запланована інтеграція з Telegram).

## Структура проекту

- `app.py`: Головний файл Flask-приложения.
- `monitor_engine.py`: Модуль з основною логікою моніторингу.
- `scheduler_tasks.py`: Модуль для визначення і управління задачами планувальника.
- `telegram_sender.py`: Модуль для відправки сповіщень в Telegram.
- `data_manager.py`: Модуль для управління даними (робота з JSON файлами).
- `data/`: Каталог для зберігання JSON файлів (`checks.json`, `history/`).
- `static/`: Каталог для статичних файлів фронтенду (CSS, JavaScript).
- `templates/`: Каталог для HTML-шаблонів.
- `logs/`: Каталог для файлів логів (`app.log`).

## Запуск

(Інструкції по запуску будуть додані пізніше)