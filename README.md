# NGO Grants Outreach CRM

Початковий модуль v0.1: моніторинг закупівель Громадського Простору, ГУРТ, Prozorro та TED, дедуплікація посилань, запис у CRM та перевірка підключення до Gmail. **Зовнішнє надсилання пошти вимкнено.** Оголошення реєструються для оцінки; тендерні контакти не використовуються для сторонніх пропозицій. 

## Розгортання
- GitHub Actions: тести під час push; workflow_dispatch для режимів check, monitor, smtp-check, smtp-self-test, sources-check.
- У Settings → Secrets and variables → Actions → Secrets задати GOOGLE_AUTHORIZED_USER_JSON, CRM_ID, EXPECTED_GMAIL. Не публікувати їх або контакти в репозиторії.
- Для авторизації Google потрібен окремий OAuth client, увімкнені Sheets API та Gmail API, offline access і refresh token. Мінімальні scope: spreadsheets, gmail.readonly. Підключення ChatGPT не передається до GitHub. OAuth app в статусі Testing може видавати refresh token лише на сім днів.
- Спочатку вручну запустити workflow з mode=check; після успіху — mode=monitor в робочий час.
- Підключити cron-job.org тільки після живого тесту: POST https://api.github.com/repos/Prool-bot/ngo-grants-outreach/actions/workflows/outreach.yml/dispatches
- Timezone Europe/Istanbul, 0 9-17 * * 1-5. JSON body: {"ref":"main","inputs":{"mode":"monitor"}}.
- Headers: Authorization: Bearer <fine-grained PAT with Actions: write for this repository>, Accept: application/vnd.github+json, Content-Type: application/json. Токен зберігати тільки в захищених налаштуваннях планувальника.
- HTTP успіх — лише прийняття запуску. Перевірити результат Actions і запис у вкладці «Системний журнал».

## Перевірка наявної SMTP-авторизації
У старому ngo-grants-bot використовуються EMAIL_ADDRESS та EMAIL_APP_PASSWORD. Ці ж назви секретів підтримує новий модуль. Секрети старого репозиторію не доступні новому автоматично. Задайте EMAIL_ADDRESS, EMAIL_APP_PASSWORD та EXPECTED_GMAIL у новому репозиторії через Settings → Secrets and variables → Actions. Не розкривайте пароль у чаті, логах або коді.
Режим smtp-check перевіряє відповідність акаунта та авторизацію SMTP без надсилання. Режим smtp-self-test надсилає один технічний лист лише на власну адресу. Для роботи з CRM, Drive та читання Gmail API потрібна окрема OAuth-авторизація.

## Межі версії
Моніторинг працює тільки Пн–Пт з 09:00 до 17:59 Europe/Istanbul. Не збирає адреси та не здійснює зовнішніх розсилок; можливий окремий тестовий лист лише власнику. Аналіз архівів, ідентифікація організацій, окрема черга погоджених контактів, обробка відповідей та повернень ще не реалізовані. Перед будь-яким зверненням потрібна належна підтверджена підстава, перевірка відмов і виключень. 

## Локальні тести
`pip install -r requirements.txt`
`python -m unittest discover -s tests`

## Джерела без витрат на пошукові API (v0.2)
- Громадський Простір та ГУРТ: читання дозволених публічних сторінок.
- Prozorro: офіційна публічна стрічка закупівель, обмежена вибірка останніх змін і профільні CPV.
- TED: офіційний Search API, без ключа; вибірка за CPV за останні 7 днів.
- Режим sources-check тестує доступність двох API, без запису в CRM, без надсилання. Логи містять лише кількість та статус.
- Публічний запис закупівлі не є згодою на рекламу. Код не збирає адреси. Не використовує Tavily, Exa, Gemini чи інші спільні квоти. Джерела обмежені і не є повним вебпошуком.
- Пошукові ліміти, помилки API та порожні вибірки відображаються окремо; 0 релевантних закупівель може бути нормальним результатом.
