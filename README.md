# NGO Grants Outreach CRM

Початковий модуль v0.1: моніторинг закупівель Громадського Простору та ГУРТ, дедуплікація посилань, запис у CRM та перевірка підключення до Gmail. **Надсилання пошти вимкнено.** Оголошення реєструються для оцінки; тендерні контакти не використовуються для сторонніх пропозицій. 

## Розгортання
- GitHub Actions: тести під час push; workflow_dispatch для режимів check та monitor.
- У Settings → Secrets and variables → Actions → Secrets задати GOOGLE_AUTHORIZED_USER_JSON, CRM_ID, EXPECTED_GMAIL. Не публікувати їх або контакти в репозиторії.
- Для авторизації Google потрібен окремий OAuth client, увімкнені Sheets API та Gmail API, offline access і refresh token. Мінімальні scope: spreadsheets, gmail.readonly. Підключення ChatGPT не передається до GitHub. OAuth app в статусі Testing може видавати refresh token лише на сім днів.
- Спочатку вручну запустити workflow з mode=check; після успіху — mode=monitor в робочий час.
- Підключити cron-job.org тільки після живого тесту: POST https://api.github.com/repos/Prool-bot/ngo-grants-outreach/actions/workflows/outreach.yml/dispatches
- Timezone Europe/Istanbul, 0 9-17 * * 1-5. JSON body: {"ref":"main","inputs":{"mode":"monitor"}}.
- Headers: Authorization: Bearer <fine-grained PAT with Actions: write for this repository>, Accept: application/vnd.github+json, Content-Type: application/json. Токен зберігати тільки в захищених налаштуваннях планувальника.
- HTTP успіх — лише прийняття запуску. Перевірити результат Actions і запис у вкладці «Системний журнал».

## Межі версії
Моніторинг працює тільки Пн–Пт з 09:00 до 17:59 Europe/Istanbul. Не збирає адреси, не відправляє пошту. Аналіз архівів, ідентифікація організацій, окрема черга погоджених контактів, обробка відповідей та повернень ще не реалізовані. Перед будь-яким зверненням потрібна належна підтверджена підстава, перевірка відмов і виключень. 

## Локальні тести
`pip install -r requirements.txt`
`python -m unittest discover -s tests`
