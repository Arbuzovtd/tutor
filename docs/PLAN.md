# TutorBot — Implementation Plan & Status

**Снимок состояния:** 2026-05-12. **MVP закрыт.**

---

## Краткое резюме

**20 коммитов, 148 tests green, ~3000 строк кода.** Бот полностью реализован для MVP-сценария без Google Calendar. Полностью работающий flow:

```
ученик → business_message → debouncer (4с) → IntentParser (Polza/OpenAI)
   ├─> ack ученику в business chat
   └─> ping репетитору в личку с inline-кнопками [✅/❌]
            └─> tap → бот отвечает ученику от имени репетитора
                + audit_log: approved/rejected
```

---

## Phase Status

| # | Name | Status | Notes |
|---|---|---|---|
| 0 | Spike Telegram Business Mode | ✅ Done | aiogram 3.28 + business updates подтверждены живьём |
| 1 | Foundation (DB + skeleton + repos) | ✅ Done | 8 моделей, Alembic async, 100% покрытие |
| 2 | Bot core + FSM Onboarding + Auth gate | ✅ Done | `/start` FSM, `is_registered` gate, DB middleware |
| 3 | Calendar Protocol + Fernet | ✅ Done | InMemoryCalendar для тестов. OAuth/Google deferred post-MVP по решению пользователя. |
| 4 | AI Intent Parser | ✅ Done | Через **Polza** (OpenAI-compatible, base_url настраивается). prompt-injection envelope + max_tokens cap. |
| 5 | Reschedule Decision Engine | ✅ Done | 8 веток action, идемпотентность, handoff detection, debouncer |
| 6 | Personal Time `/block` | ✅ Done | `/block today 14-15 обед`, `/blocks`, `/unblock N` |
| 7 | Morning Summary 9:00 | ✅ Done | APScheduler cron + `/summary` manual + dedupe per day |
| 8 | Tutor-in-the-loop review | ✅ Done | Inline keyboards, cross-tenant auth check, audit |
| 10 | Deploy + Hardening | ✅ Done | Dockerfile + docker-compose, deploy.sh + backup.sh, docs/DEPLOY.md |

---

## Что есть у репетитора (команды)

| Команда | Что делает |
|---|---|
| `/start` | Онбординг FSM (4 шага: предметы → классы → часы → цена) |
| `/today` | Уроки + личные блоки на сегодня в твоём timezone |
| `/lessons` | Будущие уроки (до 50, сортировка по времени) |
| `/students` | Список учеников (наполняется автоматически из входящих) |
| `/summary` | Утренняя сводка вручную |
| `/block today 14:00-15:00 обед` | Добавить личный блок времени |
| `/blocks` | Все активные блоки |
| `/unblock 5` | Удалить блок по id |
| `/help` | Справка |
| `/cancel` | Прервать FSM |

## Автоматика

- **Каждое сообщение ученика** → парсер → ack в business chat + ping репетитору в личку с кнопками
- **9:00 локального времени** → APScheduler шлёт сводку дня в личку (dedup через audit_log)
- **Burst-typing** (несколько сообщений подряд) → debounce 4с / max 20с, склеиваются в один запрос к LLM
- **Tutor handoff:** если репетитор сам ответил в чате — бот молчит 60 минут

## Защита

- **Rate limit** per user / per business sender (30/мин и 10/мин соответственно)
- **OPENAI_MAX_TOKENS=300** — потолок стоимости на каждый LLM вызов
- **Prompt injection envelope** — `<student_message>` теги + sanitize
- **Cross-tenant auth check** на колбеках approve/reject + audit
- **Text length cap** — student message обрезается до 3500 символов перед persist
- **SQL injection — by design defended** через SQLAlchemy 2 expression language

---

## Архитектура (high-level)

```
┌──────────────────────────────────────────────────────────────┐
│                Telegram (Business Mode, май 2026)            │
│  Аккаунт репетитора ──┬── чаты с учениками                  │
│  (Premium)            │                                       │
└───────────────────────┼──────────────────────────────────────┘
                        │ business_message
                        ▼
              ┌──────────────────────┐
              │ aiogram 3.28 Bot     │ ◄── личный чат с репетитором (FSM, /команды)
              │ Dispatcher + Routers │
              │ + RateLimit + DB MW  │
              └────────┬─────────────┘
                       ▼
              ┌──────────────────────┐
              │ InboundDebouncer     │
              │ (4s quiet / 20s cap) │
              └──────────┬───────────┘
                         ▼
              ┌──────────────────────┐    ┌────────────────────┐
              │ handle_business_     │ ◄──┤ IntentParser       │
              │ message (engine)     │    │ (Polza JSON-mode)  │
              └────┬─────────┬───────┘    └────────────────────┘
                   │         │
        outbound  │         │  TutorNotification
                  │         │  (inline keyboard)
                  ▼         ▼
   ┌─────────────────┐  ┌─────────────────────┐
   │ Business chat   │  │ Личка репетитора    │
   │ ученика         │  │ ✅ Подтвердить       │
   │ (ack от бота)   │  │ ❌ Отказать          │
   └─────────────────┘  └──────────┬──────────┘
                                   │ callback_query
                                   ▼
                       ┌──────────────────────┐
                       │ review.py            │
                       │ auth check + reply   │
                       │ to student via BC    │
                       └──────────────────────┘
```

---

## Hosting

- **docker-compose.yml** + **Dockerfile** в репо
- **docs/DEPLOY.md** — варианты от Cloud.ru до Oracle Free Tier и Fly.io
- Cloud.ru блокирует api.telegram.org из РФ → нужен **не-РФ хостинг** или MTProto proxy
- Локально (`docker compose up -d`) работает без ограничений

---

## Открытые вопросы (post-MVP)

1. **Google Calendar OAuth** — нужны `GOOGLE_CLIENT_ID/SECRET` и публичный callback URL. Calendar Protocol + Fernet шифрование уже готовы.
2. **Hosting в РФ** — либо MTProto proxy через Cloud.ru, либо переход на не-РФ VPS.
3. **Subscription gate** — сейчас открытая регистрация через FSM. Перед публичным релизом нужен Stripe/YooMoney или invite-коды.
4. **Privacy policy / Terms** — debt.
5. **Webhook вместо polling** — после deploy на сервер с HTTPS endpoint.
