// Main JavaScript file for Web Monitor frontend logic

document.addEventListener('DOMContentLoaded', function() {
    console.log('Web Monitor frontend script loaded.');

    const checkForm = document.getElementById('checkForm');
    const monitorList = document.getElementById('monitorList');
    const systemStatusDiv = document.getElementById('systemStatus');

    // --- Логика для страницы добавления/редактирования проверки ---
    if (checkForm) {
        checkForm.addEventListener('submit', async function(event) {
            event.preventDefault();
            console.log('Add check form submitted');

            const formData = new FormData(checkForm);
            const data = {
                name: formData.get('name') || null, // Отправляем null если пусто, чтобы соответствовать ожиданиям API
                url: formData.get('url'),
                selector: formData.get('selector') || null,
                change_threshold: formData.get('change_threshold') ? parseFloat(formData.get('change_threshold')) : null,
                interval: parseInt(formData.get('interval'), 10)
            };

            // Простая клиентская валидация
            if (!data.url || !data.interval) {
                alert('Будь ласка, заповніть обов\'язкові поля: URL та Інтервал.');
                return;
            }
            if (data.interval < 1) {
                alert('Інтервал перевірки повинен бути не менше 1 хвилини.');
                return;
            }
            if (data.change_threshold !== null && (data.change_threshold < 0 || data.change_threshold > 100)) {
                alert('Поріг зміни повинен бути від 0 до 100.');
                return;
            }


            try {
                const response = await fetch('/api/checks', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(data),
                });

                if (response.ok) {
                    const result = await response.json();
                    console.log('Check added successfully:', result);
                    alert('Перевірку успішно додано!');
                    window.location.href = '/'; // Перенаправление на главную страницу
                } else {
                    const errorResult = await response.json();
                    console.error('Error adding check:', errorResult);
                    alert(`Помилка додавання перевірки: ${errorResult.error || response.statusText}`);
                }
            } catch (error) {
                console.error('Network error or other issue:', error);
                alert('Не вдалося зв\'язатися з сервером. Перевірте консоль для деталей.');
            }
        });
    }

    // --- Логика для главной страницы (Dashboard) ---
    if (monitorList) {
        // Функция для загрузки и отображения списка проверок
        async function loadAndDisplayChecks() {
            try {
                const response = await fetch('/api/checks');
                if (!response.ok) {
                    monitorList.innerHTML = '<li class="monitor-item-error">Не вдалося завантажити список перевірок.</li>';
                    console.error('Failed to load checks:', response.statusText);
                    return;
                }
                const checks = await response.json();
                
                if (checks.length === 0) {
                    monitorList.innerHTML = '<li class="monitor-item-empty">Список перевірок порожній. Додайте нову перевірку.</li>';
                    return;
                }

                monitorList.innerHTML = ''; // Очищаем текущий список
                checks.forEach(check => {
                    const listItem = document.createElement('li');
                    listItem.className = 'monitor-item'; // Предполагается, что такой класс есть в CSS
                    listItem.innerHTML = `
                        <a href="/check/${check.id}" class="monitor-item-link">
                            <div class="monitor-header">
                                <span class="monitor-name">${check.name || 'Без назви'}</span>
                                <span class="monitor-status status-${check.last_result || 'unknown'}">${check.last_result || 'Невідомо'}</span>
                            </div>
                            <div class="monitor-details">
                                <p>URL: <a href="${check.url}" target="_blank" onclick="event.stopPropagation();">${check.url.length > 50 ? check.url.substring(0, 50) + '...' : check.url}</a></p>
                                <p>Остання перевірка: ${check.last_checked_at ? new Date(check.last_checked_at).toLocaleString() : 'Ще не перевірялось'}</p>
                                <p>Наступна перевірка: ${check.next_check_at ? new Date(check.next_check_at).toLocaleString() : 'Не заплановано'}</p>
                            </div>
                        </a>
                    `;
                    monitorList.appendChild(listItem);
                });

            } catch (error) {
                monitorList.innerHTML = '<li class="monitor-item-error">Помилка завантаження списку перевірок.</li>';
                console.error('Error loading checks:', error);
            }
        }
        
        // Загружаем проверки при загрузке страницы
        loadAndDisplayChecks();

        // TODO: Добавить обработчики для кнопок "Оновити всі перевірки" и "Пауза застосунку"
    }

    // --- Логика для отображения состояния системы ---
    if (systemStatusDiv) {
        async function loadSystemStatus() {
            try {
                const response = await fetch('/api/system-status');
                 if (!response.ok) {
                    systemStatusDiv.textContent = 'Не вдалося завантажити стан системи.';
                    console.error('Failed to load system status:', response.statusText);
                    return;
                }
                const status = await response.json();
                systemStatusDiv.innerHTML = `
                    <p>Статус планувальника: ${status.scheduler_status || 'N/A'}</p>
                    <p>Активних завдань: ${status.active_tasks !== undefined ? status.active_tasks : 'N/A'}</p>
                    <p>Остання глобальна помилка: ${status.last_global_error || 'Немає'}</p>
                    <p>Версія застосунку: ${status.app_version || 'N/A'}</p>
                `;
            } catch (error) {
                systemStatusDiv.textContent = 'Помилка завантаження стану системи.';
                console.error('Error loading system status:', error);
            }
        }
        // Загружаем состояние системы при загрузке страницы
        loadSystemStatus();
    }

    // --- Логика для страницы деталей проверки (monitor_details.html) ---
    const monitorDetailsContainer = document.getElementById('monitorDetailsContainer');
    if (monitorDetailsContainer) {
        async function loadMonitorDetails() {
            const pathParts = window.location.pathname.split('/');
            const checkId = pathParts[pathParts.length - 1];

            if (!checkId) {
                monitorDetailsContainer.innerHTML = '<p class="error">Не вдалося визначити ID перевірки.</p>';
                return;
            }

            try {
                const response = await fetch(`/api/checks/${checkId}`);
                if (!response.ok) {
                    const errorResult = await response.json();
                    monitorDetailsContainer.innerHTML = `<p class="error">Не вдалося завантажити деталі перевірки: ${errorResult.error || response.statusText}</p>`;
                    return;
                }
                const check = await response.json();

                document.getElementById('monitorNameTitle').textContent = check.name || 'Без назви';
                document.getElementById('monitorName').textContent = check.name || 'N/A';
                
                const monitorUrlLink = document.getElementById('monitorUrl');
                monitorUrlLink.href = check.url;
                monitorUrlLink.textContent = check.url;
                
                document.getElementById('monitorSelector').textContent = check.selector || 'Вся сторінка';
                document.getElementById('monitorThreshold').textContent = check.change_threshold !== null ? `${check.change_threshold}%` : 'N/A (використовується селектор або не задано)';
                document.getElementById('monitorInterval').textContent = check.interval;
                document.getElementById('monitorStatus').textContent = check.status; // TODO: Сделать более дружелюбным
                document.getElementById('lastCheckTime').textContent = check.last_checked_at ? new Date(check.last_checked_at).toLocaleString() : 'Ще не перевірялось';
                document.getElementById('nextCheckTime').textContent = check.next_check_at ? new Date(check.next_check_at).toLocaleString() : 'Не заплановано';
                document.getElementById('lastCheckResult').textContent = check.last_result || 'Немає даних'; // TODO: Сделать более дружелюбным

                // TODO: Загрузка и отображение истории последних 20 проверок
                const historyList = document.getElementById('checkHistoryList');
                historyList.innerHTML = '<li>Історія перевірок буде реалізована пізніше.</li>';

                // TODO: Добавить обработчики для кнопок "Позачергова перевірка", "Активувати/Деактивувати", "Редагувати", "Видалити"

            } catch (error) {
                console.error('Error loading monitor details:', error);
                monitorDetailsContainer.innerHTML = '<p class="error">Помилка завантаження деталей перевірки. Дивіться консоль.</p>';
            }
        }
        loadMonitorDetails();
    }
});