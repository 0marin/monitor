"""
Зручний скрипт для запуску Web Monitor з будь-якого місця.
"""
import os
import sys

print("🚀 Запуск Web Monitor...")

# Додаємо шлях до web_monitor в PYTHONPATH
current_dir = os.path.dirname(os.path.abspath(__file__))
web_monitor_dir = os.path.join(current_dir, 'web_monitor')

print(f"📁 Кореневий каталог: {current_dir}")
print(f"📁 Каталог web_monitor: {web_monitor_dir}")

# Перевіряємо, чи існує каталог web_monitor
if not os.path.exists(web_monitor_dir):
    print(f"❌ Каталог {web_monitor_dir} не існує!")
    print("💡 Переконайтесь, що ви знаходитесь в правильному каталозі проекту")
    input("Натисніть Enter для виходу...")
    sys.exit(1)

# Створюємо необхідні каталоги перед запуском
required_dirs = [
    os.path.join(web_monitor_dir, 'data'),
    os.path.join(web_monitor_dir, 'logs'), 
    os.path.join(web_monitor_dir, 'data', 'history')
]

for dir_path in required_dirs:
    if not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
        print(f"✅ Створено каталог: {dir_path}")

sys.path.insert(0, web_monitor_dir)

# Змінюємо робочий каталог на web_monitor
os.chdir(web_monitor_dir)

print(f"📁 Робочий каталог: {os.getcwd()}")
print(f"🐍 Python шлях: {sys.path[0]}")

# ВИПРАВЛЕНО: Імпортуємо і запускаємо застосунок правильно
try:
    print("⚙️  Завантажуємо модулі...")
    
    # Спочатку імпортуємо всі необхідні модулі
    import data_manager
    import scheduler_tasks
    import monitor_engine
    print("✅ Основні модулі завантажено")
    
    # Тепер імпортуємо Flask застосунок
    from app import app
    print("✅ Flask застосунок завантажено")
    
    print("🔗 Сервер буде доступний за адресою:")
    print("   📍 http://localhost:5000")
    print("   📍 http://127.0.0.1:5000")
    print("=" * 50)
    print("💡 Натисніть Ctrl+C щоб зупинити сервер")
    print("=" * 50)
    
    # ВИПРАВЛЕНО: Запускаємо Flask сервер напряму
    app.run(
        debug=True,
        host='0.0.0.0',
        port=5000,
        use_reloader=False
    )
    
except ImportError as e:
    print(f"❌ ПОМИЛКА ІМПОРТУ: {e}")
    import traceback
    traceback.print_exc()
    input("Натисніть Enter для виходу...")
except Exception as e:
    print(f"❌ Помилка запуску: {e}")
    import traceback
    traceback.print_exc()
    input("Натисніть Enter для виходу...")
