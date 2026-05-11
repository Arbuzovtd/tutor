# Phase 5 Sequential TDD Loop — Runbook

**Pattern:** sequential, safe mode
**Branch:** master
**Stop conditions:** (a) all 3 cycles committed, OR (b) RED doesn't fire for the right reason, OR (c) GREEN breaks prior tests beyond 1 iteration.

## Cycles

### Cycle 2 — Student identification
- New: `app/db/repositories/student.py::StudentRepository.get_or_create_by_telegram_id`
- Update: `handle_business_message` looks up/creates Student, sets `ChatMessage.student_id`
- Tests (~4): creation, idempotent reuse, tenant isolation, ChatMessage linkage

### Cycle 3 — Handoff detection
- New: `ChatMessageRepository.last_outbound_at(connection_id) -> datetime | None`
- Update: if last_outbound by tutor within 60 min → silent (`tutor_handoff`)
- Tests (~3): no prior outbound = no silence, recent tutor outbound = silent, bot's own outbound doesn't count

### Cycle 4 — Intent routing (no calendar yet)
- New: parser injected as dependency; branching on `IntentKind`
- Updates: HandleResult.action gains `reschedule_pending` / `cancel_pending` / `unknown_query`
- Reply text: stub (e.g. `"Понял, уточняю расписание..."`); calendar action deferred to Cycle 5
- Tests (~5): reschedule path, cancel, question (no schedule keywords), unknown low-confidence, parser failure falls back to unknown

## Review gate
After each cycle commit: show diff summary + test counts → wait for `ok` before next cycle.

## Verification per cycle
```bash
uv run pytest --tb=short
```
Must end with all green and no new warnings beyond the known IntegrityError SAWarning.
