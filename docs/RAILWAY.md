# Deploy на Railway (через GitHub)

Бот работает на **long-polling** (исходящий трафик), поэтому публичный домен Railway не обязателен — но он включается бесплатно и используется для `/healthz`.

---

## 1. Залить код на GitHub

```bash
# на локали, в корне репо
git remote add origin git@github.com:<your-user>/tutor_automation.git
git branch -M main          # Railway по дефолту слушает main; ветка master тоже работает
git push -u origin main
```

Если SSH ещё не настроен — создайте репо на github.com (приватный), он покажет точные команды push.

## 2. Создать проект на Railway

1. **railway.app → New Project → Deploy from GitHub repo** → выбрать `tutor_automation`.
2. Railway увидит `Dockerfile` и `railway.json`, начнёт первый билд. Можно сразу его отменить — нам ещё нужна БД и переменные.
3. В проекте: **+ New → Database → Add PostgreSQL**.

## 3. Подключить Postgres к сервису бота

В сервисе **bot** → **Variables → + New Variable → Add Reference** → выбрать `Postgres → DATABASE_URL`.

Railway отдаст URL вида `postgresql://...`. `scripts/entrypoint.sh` сам перепишет его в `postgresql+asyncpg://...` перед стартом uvicorn — править вручную не нужно.

## 4. Задать переменные окружения

В **bot → Variables** добавить:

| Variable | Required | Value |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | из @BotFather |
| `OPENAI_API_KEY` | no | без него бот молчит на сообщения учеников |
| `OPENAI_BASE_URL` | no | `https://api.polza.ai/v1` для Polza |
| `OPENAI_MODEL` | no | по умолчанию `gpt-4o-mini` |
| `OPENAI_MAX_TOKENS` | no | по умолчанию `300` |
| `LOG_LEVEL` | no | `INFO` |
| `ENVIRONMENT` | no | `prod` |
| `SENTRY_DSN` | no | если используется Sentry |
| `DATABASE_URL` | yes | **Reference** на Postgres-сервис (см. шаг 3) |

`PORT` Railway инжектит сам — не задавайте вручную.

## 5. Healthcheck и redeploy

В **bot → Settings**:
- **Healthcheck Path:** `/healthz` (уже прописан в `railway.json`).
- **Public Networking → Generate Domain** (опционально — для ручной проверки `/healthz` снаружи; для работы бота не требуется).

Жмём **Deploy**. На старте `entrypoint.sh` сам прогонит `alembic upgrade head`, потом поднимет uvicorn на `$PORT`.

## 6. Проверка

```
Logs → искать:
  [entrypoint] normalized DATABASE_URL postgresql:// → postgresql+asyncpg://
  [entrypoint] running alembic upgrade head…
  INFO ... Starting bot @<username>; allowed_updates=[...]
```

Если домен сгенерирован: `curl https://<your-app>.up.railway.app/healthz` → `{"status":"ok"}`.

## 7. Обновления

`git push` в `main` → Railway автоматически билдит и катит новый деплой. Миграции применяются на каждом старте.

---

## Что отличается от VPS-деплоя

| | VPS (docker-compose) | Railway |
|---|---|---|
| БД | контейнер `db` в compose | managed Postgres add-on |
| Порт | фикс `8000` | `$PORT` инжектится |
| `DATABASE_URL` | сам формируем в compose | reference из Postgres-сервиса, нормализуется в entrypoint |
| Бэкапы | `scripts/backup.sh` по cron | Railway → Postgres → Backups (включить вручную) |
| Healthcheck | `docker-compose` healthcheck | `railway.json → healthcheckPath` |

`docker-compose.yml` и `scripts/deploy.sh` остаются в репо для self-hosted сценария — Railway их игнорирует.

## Troubleshooting

- **`alembic` падает с `Driver not found`** — `DATABASE_URL` не нормализовался. Убедитесь что переменная — это Reference на Postgres, а не вписанная руками строка без `postgresql+asyncpg://`.
- **Бот не отвечает на business_message** — Telegram должен явно знать про `business_*` updates. У нас они уже в `ALLOWED_UPDATES` (см. `app/bot/dispatcher.py`). Проверьте `Settings → My Account → Chat Automation` в приложении репетитора и что у него Telegram Premium.
- **Healthcheck падает** — посмотрите логи: возможно крашится Alembic на миграциях (например при первой раскатке поверх непустой БД).
- **Дорого/много логов** — поднимите `LOG_LEVEL=WARNING` и Railway → Settings → **Sleep on inactivity** (если тарифный план поддерживает).
