
# Telegram Cost Calculator Bot (FastAPI + aiogram)

24/7 калькулятор стоимости работ для Telegram. Готов к деплою на Render (дефолтный домен).

## Быстрый старт на Render

1. Создай бота в Telegram через @BotFather -> получи BOT_TOKEN.
2. Залей эти файлы в репозиторий GitHub.
3. На https://render.com -> **New +** -> **Web Service** -> подключи репозиторий.
4. Настройки сервиса:
   - Runtime: **Python**
   - Build Command: *(пусто)*
   - Start Command: `uvicorn app:app --host 0.0.0.0 --port 10000`
   - Environment variables:
     - `BOT_TOKEN` = ваш токен из @BotFather
     - `WEBHOOK_SECRET` = любая строка (например `calc-987`)
     - `EXTERNAL_URL` = пока **не указывать** (добавим после первого деплоя)
5. Задеплой. Возьми публичный URL сервиса, например: `https://your-app.onrender.com`
6. Зайди в настройки сервиса -> Environment -> добавь переменную `EXTERNAL_URL` со значением этого URL.
7. Нажми **Deploy** / **Restart**. Теперь вебхук выставится автоматически.
8. Открой Telegram и напиши боту `/start` — калькулятор готов.

## Правка цен и городов

- Цены и коэффициенты в файле `pricing.json`. Можно править без изменения кода.
- Переменная окружения `PRICING_PATH` позволяет указать альтернативный путь к JSON.

## Локальный запуск (без Render)

```bash
pip install -r requirements.txt
export BOT_TOKEN=123:ABC
export WEBHOOK_SECRET=calc-987
# EXTERNAL_URL можно не указывать при локальном тесте вебхука
uvicorn app:app --host 0.0.0.0 --port 8000
```

Для теста вебхуков локально удобно использовать ngrok:
```bash
ngrok http 8000
export EXTERNAL_URL=https://<subdomain>.ngrok-free.app
# перезапусти uvicorn и бот начнет принимать апдейты
```

## Как это работает

- FastAPI принимает апдейты Telegram на `/webhook/<WEBHOOK_SECRET>`
- aiogram v3 обрабатывает FSM-диалоги для расчета стоимости
- Вебхук выставляется автоматически на старте, если задан `EXTERNAL_URL`

## Интеграция с Битрикс24 (опционально)

Добавьте пост-запрос на входящий вебхук Bitrix24 после расчета:
```python
import requests
BITRIX_WEBHOOK = "https://your.bitrix24.by/rest/1/abc123/"
def send_to_bitrix_lead(lead_id, fields):
    url = BITRIX_WEBHOOK + "crm.lead.update.json"
    requests.post(url, json={"id": lead_id, "fields": fields}, timeout=10)
```
