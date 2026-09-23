# Публикация Smart Contractor

Сначала загрузите **содержимое папки проекта** в корень GitHub-репозитория. В корне должны находиться `main.py`, `Dockerfile`, `render.yaml`, `requirements.txt`. Не загружайте ZIP вместо исходников. Сохраните вложенные папки `static/`, `tests/`, `tools/` и скрытую `.github/`.

## Render: простой путь из GitHub

1. В Render создайте **Web Service** и подключите GitHub-репозиторий.
2. Если репозиторий содержит проект в корне, оставьте Root Directory пустым.
3. Для ручного запуска выберите Python 3 и задайте:

| Поле | Значение |
|---|---|
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/healthz` |
| Python version | `3.12.10` через переменную `PYTHON_VERSION` |

4. В разделе переменных добавьте `OPENAI_API_KEY` и `OPENAI_MODEL=gpt-4o-mini`.
5. Запустите деплой и дождитесь успешного health check. Откройте выданный адрес сайта.

Альтернатива — создать **Blueprint** из репозитория: все основные настройки уже в `render.yaml`; он запросит `OPENAI_API_KEY`. Без ключа можно запустить резервный режим через обычный Web Service. Включённый в Blueprint бесплатный план может иметь ограничения и холодный запуск; выбирайте план по условиям своей площадки.

Если выбран Docker runtime, Render использует `Dockerfile`. Не указывайте отдельную команду запуска: она уже находится в образе и учитывает `PORT`.

## Railway: через Dockerfile

Создайте сервис из GitHub-репозитория. В корне лежит `Dockerfile`, поэтому доступен Docker build. Добавьте `OPENAI_API_KEY`, задайте health check `/healthz` в настройках сервиса и создайте публичный домен. Приложение использует переменную `PORT` платформы. Отдельный legacy-файл `railway.json` не требуется.

## Свой Linux-сервер: Docker Compose

Требования: установленный Docker с Compose v2, доступ к портам 80/443.

```bash
git clone https://github.com/YOUR_USERNAME/smart-contractor.git
cd smart-contractor
cp .env.example .env
```

Откройте `.env` редактором на сервере, заполните `OPENAI_API_KEY`. Для HTTPS добавьте строку `DOMAIN=events.example.com`. DNS A/AAAA-записи должны указывать на сервер. Затем:

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 app
```

С доменом Caddy получает сертификат и обслуживает `https://events.example.com`. Без `DOMAIN` сайт доступен по `http://IP-СЕРВЕРА` на порту 80. Если эти порты уже заняты существующим сайтом, используйте свой reverse proxy и вариант ниже.

## Один контейнер за существующим reverse proxy

```bash
docker build -t smart-contractor .
docker run -d --name smart-contractor --restart unless-stopped \
  --env-file .env -e PORT=8000 -p 127.0.0.1:8000:8000 smart-contractor
```

Направьте reverse proxy на `http://127.0.0.1:8000`. Для правильного лимита по IP настройте `FORWARDED_ALLOW_IPS` на адрес доверенного proxy. В готовом Compose значение `*` применяется только к приложению, чей порт не опубликован наружу: запросы идут через Caddy по внутренней сети Docker.

## Проверка после публикации

1. `/healthz` возвращает `status: ok`, `profiles: 66`.
2. Главная страница показывает Smart Contractor и заполненные списки формы.
3. «Ведущие осенью» возвращает 3 карточки; «Редкая категория» — 2; «Нет совпадений» — объяснённую пустую выдачу.
4. Переключатель слепого теста скрывает имена и сохраняет порядок карточек.
5. При рабочем OpenAI-ключе успешные карточки API возвращают `explanation_source: openai`. Иначе сервис показывает резервные объяснения и соответствующую подпись.

API-ключ хранится в `.env` на своём сервере или в секретных переменных хостинга. `.env` исключён из Git и Docker build context; он не должен попадать в браузер, коммиты или изображения контейнера.

## Обновление на своём сервере

```bash
git pull
docker compose up -d --build
```

Остановка: `docker compose down`. Тома Caddy сохраняют сертификаты; не удаляйте их при обычном обновлении.

Источники: [FastAPI на Render](https://render.com/docs/deploy-fastapi), [Dockerfiles в Railway](https://docs.railway.com/builds/dockerfiles), [автоматический HTTPS Caddy](https://caddyserver.com/docs/automatic-https).
