# Deploy TutorBot

The bot is packaged as a single Docker Compose stack: `bot` (FastAPI + aiogram polling) + `db` (Postgres 16). It does **not** need an HTTPS endpoint or domain — Telegram polling works outbound only.

---

## Free hosting options

| Provider | Free tier | Setup difficulty | Notes |
|---|---|---|---|
| **Cloud.ru Evolution** | 1 vCPU, 1 GB RAM, 30 GB SSD — **always free** | Easy | RU юрисдикция, регистрация по паспорту. Compose уже затюнен под 1 GB. |
| **Oracle Cloud Free Tier** | 2 ARM VMs, 24 GB RAM total, 200 GB disk — always free | Medium | Лучше всех по ресурсам. Нужна **не-РФ** карта для верификации. |
| **Yandex Cloud trial** | ₽4000 грант на 60 дней | Easy | После — ~₽600/мес. |
| **Hetzner CX22** | €4.5/mo | Easy | Не бесплатно, но самый дешёвый EU VPS. |

The defaults in `docker-compose.yml` are tuned for 1 GB RAM (Cloud.ru baseline). On larger VMs you can drop the `mem_limit:` lines and raise Postgres' `shared_buffers`.

---

## Cloud.ru Evolution (recommended free path)

### Регистрация

1. Зайти на **cloud.ru** → «Войти/Регистрация» → создать аккаунт по СберID или e-mail/телефону.
2. Подтвердить личность (паспорт РФ) — это нужно для всех клиентов, даже free tier.
3. Привязать рублёвую карту: бесплатные ресурсы списываний не дают, но карта обязательна для активации Free Tier.
4. В консоли: **Evolution Free Tier** → активировать. Выдадут квоту: 1 vCPU + 1 GB RAM + 30 GB SSD навсегда.

### Создание VM

В разделе **Evolution → Виртуальные машины**:

```
Образ:        Ubuntu 22.04 LTS
Конфигурация: 1 vCPU / 1 GB / 30 GB SSD  (Free Tier)
Сеть:         Public IPv4 (один на free)
SSH-ключ:     загрузить свой публичный ключ (~/.ssh/id_ed25519.pub)
Firewall:     открыть только 22/tcp (SSH). Бот работает на polling — входящих портов не нужно.
```

После создания получишь публичный IP. SSH:

```bash
ssh ubuntu@<vm-ip>
```

### Дальше → блок "One-time VPS setup" ниже одинаков для Cloud.ru и любых других провайдеров.

---

## One-time VPS setup

1. **Create the VM** (Ubuntu 22.04 LTS is the simplest target).
2. **Open ports**: only `22` for SSH. The bot uses outbound polling — no inbound ports needed.
3. **Install Docker + Compose plugin**:
   ```bash
   curl -fsSL https://get.docker.com | sh
   sudo usermod -aG docker $USER
   newgrp docker
   ```
4. **Get the code onto the VM** — pick one:

   **A) Прямой SCP с локальной машины (быстрый старт, без GitHub):**
   ```bash
   # На локальной машине, в корне репо:
   sudo mkdir -p /opt && sudo chown $USER /opt   # на VM, не локально
   # Запусти на локали:
   tar --exclude='.venv' --exclude='__pycache__' --exclude='.pytest_cache' \
       --exclude='.coverage' --exclude='.git' --exclude='backups' \
       -czf /tmp/tutorbot.tar.gz -C /home/ser/my_projects/tutor_automation .
   scp /tmp/tutorbot.tar.gz ubuntu@<vm-ip>:/opt/
   ssh ubuntu@<vm-ip> 'mkdir -p /opt/tutorbot && tar -xzf /opt/tutorbot.tar.gz -C /opt/tutorbot'
   ```

   **B) Через GitHub** (удобно для обновлений):
   ```bash
   # Создай приватный репо на github.com, потом:
   git remote add origin git@github.com:<user>/tutor_automation.git
   git push -u origin master
   # На VM:
   sudo mkdir -p /opt && sudo chown $USER /opt
   cd /opt && git clone git@github.com:<user>/tutor_automation.git tutorbot
   cd tutorbot
   ```
5. **Configure environment**:
   ```bash
   cp .env.example .env
   nano .env   # fill in TELEGRAM_BOT_TOKEN, POSTGRES_PASSWORD, optional OPENAI_*
   ```
   Generate a strong DB password:
   ```bash
   echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)" >> .env
   ```

---

## Deploy

From the repo root on the VPS:

```bash
bash scripts/deploy.sh
```

This builds the bot image, brings up `db` + `bot`, runs Alembic migrations on startup via the entrypoint, and waits for the `/healthz` probe.

Manual equivalent:

```bash
docker compose up -d --build
docker compose logs -f bot
```

---

## Update to a new version

```bash
cd /opt/tutorbot
git pull
bash scripts/deploy.sh
```

The entrypoint re-runs `alembic upgrade head` on every start, so migrations are applied automatically. Old containers are replaced; Postgres data persists in the `postgres_data` volume.

---

## Daily backups

Add to crontab on the VPS:

```bash
crontab -e
```

```cron
0 3 * * * cd /opt/tutorbot && bash scripts/backup.sh >> /var/log/tutorbot-backup.log 2>&1
```

This dumps `tutorbot` DB every night at 03:00 UTC into `./backups/`, keeping the last 14 days.

---

## Restore from backup

```bash
gunzip < backups/tutorbot_<timestamp>.sql.gz | docker compose exec -T db psql -U tutorbot tutorbot
```

---

## Operational commands

```bash
docker compose ps                # service status
docker compose logs -f bot       # tail bot logs
docker compose logs --tail=200 db
docker compose restart bot       # restart only the bot
docker compose down              # stop everything (Postgres data is preserved)
docker compose down -v           # ⚠️  also wipes the DB volume
docker compose exec db psql -U tutorbot tutorbot   # open psql against the DB
```

---

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | — | From @BotFather |
| `POSTGRES_PASSWORD` | yes | — | Long random string |
| `POSTGRES_USER` | no | `tutorbot` | DB user name |
| `POSTGRES_DB` | no | `tutorbot` | DB name |
| `OPENAI_API_KEY` | no | — | If unset, bot stays silent on student messages |
| `OPENAI_BASE_URL` | no | OpenAI's default | Set to `https://api.polza.ai/v1` for Polza |
| `OPENAI_MODEL` | no | `gpt-4o-mini` | Cheapest model that handles Russian intent well |
| `OPENAI_MAX_TOKENS` | no | `300` | Hard cap on response size; controls cost |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR` |
| `ENVIRONMENT` | no | `prod` | Free-form label, currently informational |
| `SENTRY_DSN` | no | — | Reserved for future error reporting |

---

## Security notes

- The `bot` service binds `127.0.0.1:8000` only — `/healthz` is **not** reachable from the public internet.
- `db` has no host port mapping — only `bot` can reach it via the Docker network.
- The container runs as a non-root `tutorbot` user.
- Telegram bot token, OpenAI key, and Postgres password are in `.env` — make sure it's `chmod 600` and excluded from git (already in `.gitignore`).
- The bot drops bursty traffic via in-memory rate limit (30 events/min per user, 10/min per student per business connection).
- LLM responses are capped at `OPENAI_MAX_TOKENS` (default 300) to bound per-call cost.

---

## Health checks

- `GET /healthz` → `{"status":"ok"}` (liveness, no DB)
- `GET /readyz` → `{"status":"ready"}` (touches the DB, returns 500 if DB is down)

Docker Compose's healthcheck uses `/healthz` and will restart the bot if it fails for ≥3 intervals.
