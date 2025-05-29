// Глобальні змінні
let isLoading = false;

// Функції для роботи з API
async function loadChecks() {
    console.log('🔄 Завантажуємо перевірки...');
    
    if (isLoading) {
        console.log('⏳ Вже завантажуємо, пропускаємо...');
        return;
    }
    
    isLoading = true;
    const container = document.getElementById('checksContainer');
    
    if (!container) {
        console.error('❌ Контейнер checksContainer не знайдено');
        isLoading = false;
        return;
    }
    
    container.innerHTML = '<div class="loading"></div> Завантаження перевірок...';
    
    try {
        // ВИПРАВЛЕНО: Правильний URL для API
        const response = await fetch('/api/checks');
        console.log('📡 Відповідь сервера:', response.status);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const checks = await response.json();
        console.log('📋 Отримано перевірок:', checks.length);
        
        showChecks(checks);
        
    } catch (error) {
        console.error('❌ Помилка:', error);
        container.innerHTML = `
            <div class="message error">
                <p>❌ Помилка завантаження: ${htmlEscape(error.message)}</p>
                <p><a href="/add" class="btn btn-add">➕ Додати першу перевірку</a></p>
            </div>
        `;
    } finally {
        isLoading = false;
    }
}

function showChecks(checks) {
    const container = document.getElementById('checksContainer');
    
    if (!checks || checks.length === 0) {
        container.innerHTML = `
            <div class="message">
                <p>🔍 Немає перевірок</p>
                <p><a href="/add" class="btn btn-add">➕ Додати першу перевірку</a></p>
            </div>
        `;
        return;
    }
    
    const html = checks.map(check => {
        // ДОДАНО: Отримуємо поточний контент
        const currentContent = getCurrentContent(check);
        const contentPreview = currentContent ? getContentPreview(currentContent, 100) : null;
        
        // Додаємо клас для статусу
        const statusClass = check.status === 'paused' ? 'status-paused' : 'status-active';
        
        return `
            <li>
                <a href="/check/${check.id}" class="monitor-item ${statusClass}">
                    <div class="monitor-header">
                        <div>
                            <div class="monitor-name">🔗 ${htmlEscape(check.name || 'Безіменна')}</div>
                            <div class="monitor-url">${htmlEscape(check.url)}</div>
                        </div>
                        <span class="monitor-status status-${getStatusClass(check.last_result)}">
                            ${getStatusText(check.last_result)}
                        </span>
                    </div>
                    <div class="monitor-details">
                        ${contentPreview ? `
                        <div class="monitor-content-preview">
                            <strong>📄 Поточний контент:</strong>
                            <span class="content-preview">${htmlEscape(contentPreview)}</span>
                        </div>
                        ` : ''}
                        <p><strong>⏰ Остання:</strong> ${formatTime(check.last_checked_at)}</p>
                        <p><strong>🔄 Інтервал:</strong> ${check.interval} хв.</p>
                    </div>
                </a>
            </li>
        `;
    }).join('');
    
    container.innerHTML = `<ul class="monitor-list">${html}</ul>`;
}

// ДОДАНО: Функція для отримання поточного контенту
function getCurrentContent(check) {
    // Спробуємо отримати контент з історії (якщо вона доступна) або з основних даних
    return check.current_content || check.last_extracted_value || null;
}

// ДОДАНО: Функція для створення превью контенту
function getContentPreview(content, maxLength = 100) {
    if (!content) return null;
    
    // Очищуємо зайві пробіли та переноси
    const cleaned = content.toString().trim().replace(/\s+/g, ' ');
    
    if (cleaned.length <= maxLength) {
        return cleaned;
    }
    
    return cleaned.substring(0, maxLength) + '...';
}

async function loadSystemStatus() {
    console.log('📊 Завантажуємо статус системи...');
    
    const statusContainer = document.getElementById('systemStatus');
    const statusContent = document.getElementById('statusContent');
    
    if (!statusContainer || !statusContent) {
        console.error('❌ Контейнери статусу не знайдено');
        return;
    }
    
    statusContainer.style.display = 'block';
    statusContent.innerHTML = '<span class="loading"></span> Завантаження...';
    
    try {
        const response = await fetch('/api/system-status');
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const status = await response.json();
        
        let overdueWarning = '';
        if (status.overdue_jobs_count > 0) {
            overdueWarning = `
                <div class="status-warning">
                    <strong>⚠️ УВАГА:</strong> ${status.overdue_jobs_count} прострочених завдань!
                    <ul>
                        ${status.overdue_jobs.map(job => `
                            <li>${job.name} (прострочено на ${Math.round(job.overdue_by_seconds)} сек.)</li>
                        `).join('')}
                    </ul>
                </div>
            `;
        }
        
        statusContent.innerHTML = `
            <div class="status-item">
                <strong>📡 Планувальник:</strong> 
                <span class="monitor-status status-${status.scheduler_status === 'Running' ? 'active' : 'inactive'}">
                    ${status.scheduler_status === 'Running' ? '🟢 Працює' : '🔴 Зупинено'}
                </span>
            </div>
            <div class="status-item"><strong>⚡ Завдань:</strong> ${status.active_scheduled_jobs}</div>
            <div class="status-item"><strong>⏰ UTC час:</strong> ${formatTime(status.current_time_utc)}</div>
            <div class="status-item"><strong>🏠 Локальний час:</strong> ${formatTime(status.current_time_local)}</div>
            <div class="status-item"><strong>🏷️ Версія:</strong> ${status.app_version}</div>
            ${overdueWarning}
        `;
        
    } catch (error) {
        console.error('❌ Помилка статусу:', error);
        statusContent.innerHTML = '<span class="message error">❌ Помилка завантаження</span>';
    }
}

async function loadSchedulerDiagnostics() {
    console.log('🔍 Завантажуємо діагностику планувальника...');
    
    try {
        const response = await fetch('/api/scheduler-diagnostics');
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const diagnostics = await response.json();
        
        console.log('📋 Діагностика планувальника:', diagnostics);
        
        let diagnosticsHtml = `
            <h4>🔍 Детальна діагностика планувальника</h4>
            <div class="diagnostics-info">
                <p><strong>Статус:</strong> ${diagnostics.status}</p>
                <p><strong>Кількість завдань:</strong> ${diagnostics.jobs_count}</p>
                <p><strong>Поточний час UTC:</strong> ${formatTime(diagnostics.current_time_utc)}</p>
                <p><strong>Поточний час локальний:</strong> ${formatTime(diagnostics.current_time_local)}</p>
            </div>
        `;
        
        if (diagnostics.jobs && diagnostics.jobs.length > 0) {
            diagnosticsHtml += '<h5>📋 Завдання:</h5><ul class="jobs-list">';
            diagnostics.jobs.forEach(job => {
                const overdueClass = job.is_overdue ? 'job-overdue' : '';
                diagnosticsHtml += `
                    <li class="job-item ${overdueClass}">
                        <strong>${job.id}</strong> (${job.name})<br>
                        Наступний запуск UTC: ${formatTime(job.next_run_utc)}<br>
                        Наступний запуск локальний: ${formatTime(job.next_run_local)}<br>
                        ${job.is_overdue ? '<span class="overdue-badge">⚠️ ПРОСТРОЧЕНО</span>' : ''}
                    </li>
                `;
            });
            diagnosticsHtml += '</ul>';
        }
        
        // Показуємо в модальному вікні або замінюємо контент
        const statusContent = document.getElementById('statusContent');
        statusContent.innerHTML = diagnosticsHtml;
        
    } catch (error) {
        console.error('❌ Помилка діагностики:', error);
        alert('❌ Помилка діагностики: ' + error.message);
    }
}

async function forceSchedulerCheck() {
    console.log('⚡ Примусова перевірка планувальника...');
    
    try {
        const response = await fetch('/api/scheduler-force-check', {
            method: 'POST'
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const result = await response.json();
        console.log('✅ Результат примусової перевірки:', result);
        
        alert('✅ Примусова перевірка завершена. Перевірте логи для деталей.');
        
        // Оновлюємо статус системи
        loadSystemStatus();
        
    } catch (error) {
        console.error('❌ Помилка примусової перевірки:', error);
        alert('❌ Помилка примусової перевірки: ' + error.message);
    }
}

// Функція для форми додавання перевірки
async function submitCheckForm(event) {
    event.preventDefault();
    
    const form = event.target;
    const submitButton = form.querySelector('button[type="submit"]');
    const originalText = submitButton.textContent;
    
    // Показуємо стан завантаження
    submitButton.textContent = '⏳ Створюємо...';
    submitButton.disabled = true;
    
    const formData = {
        name: document.getElementById('name').value.trim(),
        url: document.getElementById('url').value.trim(),
        selector: document.getElementById('selector').value.trim() || null,
        interval: parseInt(document.getElementById('interval').value),
        change_threshold: parseFloat(document.getElementById('change_threshold').value) || null
    };
    
    console.log('📝 Дані форми:', formData);
    
    // Клієнтська валідація
    if (!formData.url) {
        showMessage('URL є обов\'язковим полем', 'error');
        resetSubmitButton();
        return;
    }
    
    if (!formData.interval || formData.interval < 1) {
        showMessage('Інтервал має бути мінімум 1 хвилина', 'error');
        resetSubmitButton();
        return;
    }
    
    try {
        console.log('📡 Відправляємо запит на створення...');
        const response = await fetch('/api/checks', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(formData)
        });
        
        console.log('📨 Відповідь сервера:', response.status);
        
        if (!response.ok) {
            const errorResult = await response.json();
            throw new Error(errorResult.error || `HTTP ${response.status}`);
        }
        
        const result = await response.json();
        console.log('✅ Перевірка створена:', result);
        
        showMessage(`Перевірку "${result.name || 'Безіменну'}" успішно створено!`, 'success');
        
        // Перенаправляємо на головну сторінку через 2 секунди
        setTimeout(() => {
            console.log('🔄 Перенаправляємо на головну сторінку...');
            window.location.href = '/';
        }, 2000);
        
    } catch (error) {
        console.error('❌ Помилка створення перевірки:', error);
        showMessage(`Помилка при створенні перевірки: ${error.message}`, 'error');
        resetSubmitButton();
    }
    
    function resetSubmitButton() {
        submitButton.textContent = originalText;
        submitButton.disabled = false;
    }
}

// Функція для показу повідомлень
function showMessage(message, type = 'success') {
    const existingMessage = document.querySelector('.message');
    if (existingMessage) {
        existingMessage.remove();
    }
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    messageDiv.innerHTML = `
        <p>${type === 'success' ? '✅' : '❌'} ${htmlEscape(message)}</p>
    `;
    
    // Вставляємо повідомлення після заголовка
    const header = document.querySelector('header');
    if (header) {
        header.insertAdjacentElement('afterend', messageDiv);
    } else {
        document.body.insertBefore(messageDiv, document.body.firstChild);
    }
    
    // Автоматично видаляємо через 5 секунд
    setTimeout(() => {
        if (messageDiv.parentNode) {
            messageDiv.remove();
        }
    }, 5000);
}

// Допоміжні функції
function htmlEscape(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function getStatusClass(status) {
    switch (status) {
        case 'changed': return 'changed';
        case 'no_change': return 'no-change';
        case 'error': return 'error';
        default: return 'unknown';
    }
}

function getStatusText(status) {
    switch (status) {
        case 'changed': return '🔄 Зміни';
        case 'no_change': return '✅ Без змін';
        case 'error': return '❌ Помилка';
        default: return '❓ Невідомо';
    }
}

function formatTime(isoString) {
    if (!isoString) return 'Не перевірялось';
    
    try {
        const date = new Date(isoString);
        return date.toLocaleString('uk-UA', {
            day: '2-digit',
            month: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch {
        return isoString;
    }
}

// Ініціалізація
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Сторінка завантажена');
    
    // Перевіряємо, чи це головна сторінка
    if (document.getElementById('checksContainer')) {
        console.log('📋 Це головна сторінка, завантажуємо перевірки');
        loadChecks();
    }
    
    // Якщо це сторінка додавання, прив'язуємо обробник форми
    const addCheckForm = document.getElementById('addCheckForm');
    if (addCheckForm) {
        console.log('📝 Знайдено форму додавання, прив\'язуємо обробник...');
        addCheckForm.addEventListener('submit', submitCheckForm);
    }
});

// Експорт функцій для використання в HTML
window.loadChecks = loadChecks;
window.loadSystemStatus = loadSystemStatus;

console.log('✅ main.js завантажено успішно');