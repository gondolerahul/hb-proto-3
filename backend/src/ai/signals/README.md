# ai.signals — Signal Bus & Trigger Registry (Increment 1 / SIG)

**Design authority:** `docs/product-road-map/increment-1/01_sig_signal_bus.md`
(restating technical doc §18). Postgres is the bus: signals are transactional
rows (outbox pattern) claimed with `FOR UPDATE SKIP LOCKED`; Arq delivers.

## Module map

| Module | Role |
|---|---|
| `models.py` | `Signal` + `TriggerRegistration` ORM, status/urgency/trust/source vocabularies, Inc-1 type taxonomy |
| `service.py` | `emit_signal` (outbox insert in the caller's transaction, `ON CONFLICT DO NOTHING` dedupe), `enqueue_dispatch` (post-commit), `emit_completion_for_run` (§18.5 hook) |
| `triggers.py` | Owner resolution: pattern match (exact / `prefix.*` / `*`), priority DESC then entity-id tiebreak |
| `dispatcher.py` | `dispatch_signal` Arq job; claim → resolve → spawn run → CONSUMED, atomically. Failure path: backoff (60s·2^n via `park_review_at`) → DEAD + `incident.governance` |
| `sweeper.py` | 60s cron: re-dispatch due PENDING (covers crash-between-commit-and-enqueue — the "no dropped signals" guarantee), review PARKED (15 min timer; ESCALATED after 3 unresolved reviews) |
| `email_poll.py` | First channel producer: IMAP poll → `email.inbound`, `dedupe_key` = Message-ID. Subscription-gated per company |
| `api.py` | `/api/v1/ai/signals` — signals list/detail/replay/coverage + trigger-registry CRUD (API-only in Inc 1) |

## Producing a signal (the outbox contract)

```python
from src.ai.signals.service import emit_signal, enqueue_dispatch

signal_id = await emit_signal(          # inside YOUR open transaction
    db, company_id=company_id,
    source="connector", type="lead.inbound",
    trust="counterparty", payload={...},
    dedupe_key=external_event_id,       # producer idempotency
)
await db.commit()                       # signal commits WITH your business write
if signal_id:                           # None = duplicate (deduped)
    await enqueue_dispatch(redis, signal_id)   # best-effort; sweeper covers failure
```

Never enqueue before commit; never emit outside the business transaction.

## Delivery semantics (§18.4)

* **At-least-once delivery, exactly-once consumption** — PENDING→CONSUMED is
  an atomic claimed transition; a re-delivered signal cannot spawn a second run.
* **Dedupe** — partial unique `(company_id, dedupe_key)`.
* **Ordering** — best-effort FIFO per company; `urgency="critical"` claims
  ahead of the queue. No global ordering guarantee: object state is truth,
  signals are triggers.
* **Replay** — immutable rows; replay clones with `replayed_from`.
* **Completion** — run finalization emits `<type>.completed`
  (`agent_loop._emit_signal_completion`); unsubscribed completions
  self-consume as audit records rather than parking.
* **Escalation** — ESCALATED signals are surfaced via `GET /ai/signals?status=ESCALATED`
  (+ `signals.signal.escalated` telemetry). The approvals-panel card follows with
  the Inc-2 admin UI: `human_approvals.run_id` is NOT NULL and a parked signal
  has no run, so Inc 1 deliberately does not force a schema change there.

## The coverage audit (§18.5)

Arc-VI's signal-coverage KPI is one query (also `GET /ai/signals/coverage`):

```sql
SELECT status, COUNT(*) FROM signals
WHERE company_id = :company_id
GROUP BY status;
-- coverage % = rows not in (PARKED, ESCALATED, DEAD) / total
```

## Operational notes

* The dispatcher spawns runs through the same `ExecutionRun` +
  `run_execution_recursive` path as every other entry point — no second
  engine. If the run enqueue fails after the consume commit, the run row
  stays visible in PENDING; the consumed signal records `consumed_by_run_id`.
* `park_review_at` is dual-purpose by design: retry not-before on PENDING,
  review timer on PARKED. `attempts` likewise: dispatch attempts vs. review count.
* Email polling only touches companies with an enabled trigger matching
  `email.inbound` — sensing without a subscriber would only manufacture
  escalation noise. Mail stays UNSEEN-tracked in the inbox regardless.
