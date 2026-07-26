# Increment 1 / SCH — Appendix 03a: The HBS Spine (35-Object Seed Schema)

> **Status:** ✅ **Approved (Rahul, 2026-07-19)** — frozen as the seed fixture (`ai/tenant_schema/hbs_seed/`); field names, enums, refs, owners, and tags below are what the initializer loads. R1–R7 accepted as drafted. Future changes go through the §19.4 evolution rules, not edits here.
> **Amended 2026-07-26 (Increment 6 / STRAT):** **27 → 35 objects.** Eight Planning objects added — reviewed and approved on their own sheets ([increment-6/04a](../increment-6/04a_planning_object_sheets.md)), which is the authoritative record of *why* each field is named what it is. A ninth domain tag, `strategy`, joins the vocabulary. Nothing above changed; this is additive, and `seed_hbs_spine` picks the new defs up on an existing tenant's next provisioning touch.
> **Parent:** [03_sch_tenant_schema.md](./03_sch_tenant_schema.md) §1.2 · **Sources:** Blueprint §3.2 (the 27 objects) + §5 (P01–P19 process map) · technical doc §10.3 (modules), §19 (links/refs), §23.1 (ownership), §24.3 (domain tags)
> **Scope:** the **spine** — core fields per object, enough to run the Solo Pack's flows. Module field-depth (full chart of accounts, payroll inputs, leave/attendance, inventory movements, …) is Increment 4.

---

## 1. Conventions

**System fields (never declared per object).** The record service maintains on every record: `id`, `company_id`, `entity_def_id`, `version` (CAS), `def_version`, `updated_by_run_id`, `created_at`, `updated_at`, `deleted_at` (soft delete). Every def also implicitly carries `notes: text` and `tags: string[]`. The `sor`/`external_ref` blocks are reserved columns, unused until Increment 4.

**Field types (closed set).** `string` · `text` · `integer` · `decimal` · `boolean` · `date` · `datetime` · `enum(...)` · `money` · `email` · `phone` · `url` · `json` (escape hatch — used only for line-item lists in the spine) · `artifact` (id into the shipped artifacts store) · `ref(Target)` (materialized into `tenant_record_links`, §19.2).

**Money.** `money` = `{amount: decimal, currency: ISO-4217}`. Tenant default currency is a tenant setting (default `INR`); every money field stores its currency explicitly.

**Refs and link direction.** Each `ref` field declares its `rel_type` and direction. Notation in the tables below: `→ rel_type` means the link row is *this record → target*; `← rel_type` means *target → this record* (used where §19.1 fixes the direction, e.g. `Order → Invoice` is `billed_by`, so `Invoice.order` materializes `← billed_by`). `ref(any)` is a polymorphic ref (any def), always `→ attached_to` — legal only where noted (Ticket/Risk/Incident/Evidence/Signal per §19.1).

**Seed `rel_type` vocabulary (§19.1, unchanged):** `converted_to` · `belongs_to` · `attached_to` · `fulfilled_by` · `billed_by` · `paid_by` · `derived_from`.

**Enums are evolvable, not frozen.** Tenants extend enums through the §19.4 evolution rules (additive values, aliases); the values below are the platform seed.

**Owner processes.** `owner_process_id` stores the canonical process **code** (P01–P19) at seed time, resolved to the PROCESS entity id when Increment 2 seeds it (decision 2026-07-19). Codes whose process is **not** in Wave 0 (everything except P03/P06/P08/P10/P14/P19) are unresolvable until their increment — those objects are "platform-owned, HITL on write" until then.

**Memory domain tags (§24.3).** Seed vocabulary: `general` · `crm` · `marketing` · `operations` · `financial` · `hr` · `payroll` · `legal` · `trust` · **`strategy`** *(Inc-6 STRAT — deliberately not folded into `financial`, so board minutes stay out of a collections agent's retrieval; **no seeded agent is granted it**)*. A node ingested from an object carries its object's tag; agent viewports filter by the governance block's `memory_domains` allow-list.

---

## 2. Object Index

| # | Object | Blueprint domain | HBS module | Memory domain | Owner | Wave 0? |
|---|---|---|---|---|---|---|
| 1 | Signal | Market & Demand | Marketing & PR | `marketing` | P01 | platform-owned until Inc 2+ |
| 2 | Campaign | Market & Demand | Marketing & PR | `marketing` | P02 | platform-owned |
| 3 | Lead | Market & Demand | CRM | `crm` | P03 | ✅ |
| 4 | Account | Revenue | CRM | `crm` | P06 | ✅ |
| 5 | Contact | Revenue | CRM | `crm` | P06 | ✅ |
| 6 | Opportunity | Revenue | CRM | `crm` | P03 | ✅ |
| 7 | Quote | Revenue | CRM | `crm` | P03 | ✅ |
| 8 | Contract | Revenue | Legal | `legal` | P13 | platform-owned |
| 9 | Order | Delivery | ERP / Operations | `operations` | P05 | platform-owned |
| 10 | Project/Engagement | Delivery | ERP / Operations | `operations` | P05 | platform-owned |
| 11 | Deliverable | Delivery | ERP / Operations | `operations` | P05 | platform-owned |
| 12 | Ticket | Delivery | CRM | `crm` | P06 | ✅ |
| 13 | Invoice | Money | Accounting | `financial` | P08 | ✅ |
| 14 | Payment | Money | Accounting | `financial` | P08 | ✅ |
| 15 | Bill | Money | Accounting | `financial` | P09 | platform-owned |
| 16 | Ledger Entry | Money | Accounting | `financial` | P10 | ✅ |
| 17 | Budget | Money | Planning | `financial` | P11 | platform-owned |
| 28 | Objective | Strategy | Planning | `strategy` | P11 | platform-owned *(Inc 6)* |
| 29 | Target | Strategy | Planning | `strategy` | P11 | platform-owned *(Inc 6)* |
| 30 | Forecast | Strategy | Planning | `strategy` | P11 | platform-owned *(Inc 6)* |
| 31 | Minutes | Strategy | Planning | `strategy` | P11 | platform-owned *(Inc 6)* |
| 32 | Proposition | Strategy | Planning | `strategy` | P11 | platform-owned *(Inc 6)* |
| 33 | Resolution | Strategy | Planning | `strategy` | P11 | platform-owned *(Inc 6)* |
| 34 | Mandate | Strategy | Planning | `strategy` | P11 | platform-owned *(Inc 6)* |
| 35 | Review | Strategy | Planning | `strategy` | P11 | platform-owned *(Inc 6)* |
| 18 | Vendor | Supply | ERP / Operations | `operations` | P09 | platform-owned |
| 19 | Purchase Order | Supply | ERP / Operations | `operations` | P09 | platform-owned |
| 20 | Asset/Inventory Item | Supply | ERP / Operations | `operations` | P15 | platform-owned |
| 21 | Candidate | People | HRMS | `hr` | P12 | platform-owned |
| 22 | Employee | People | HRMS | `payroll` | P12 | platform-owned |
| 23 | Product/SKU | Product | ERP / Operations | `operations` | P16 | platform-owned |
| 24 | Risk | Trust | Legal | `trust` | P14 | ✅ |
| 25 | Incident | Trust | Legal | `trust` | P17 | platform-owned |
| 26 | Policy/Obligation | Trust | Legal | `legal` | P14 | ✅ |
| 27 | Evidence | Trust | Legal | `trust` | P14 | ✅ |

The lifecycle chain (`Signal → Lead → Opportunity → Quote → Contract → Order → Project → Invoice → Payment → Ledger Entry`, with Ticket/Risk/Incident attachable anywhere) is realized entirely by the ref fields below.

---

## 3. Field Definitions

### 3.1 Marketing & PR module

**Signal** — a sensed market/demand event worth acting on (distinct from the §18 signal-bus rows, which are triggers; a Signal *record* is durable business knowledge).

| Field | Type | Notes |
|---|---|---|
| title | string | required |
| source_type | enum(market_research, news, social, referral, web, event, conversation, other) | |
| summary | text | |
| strength | enum(weak, moderate, strong) | default `moderate` |
| status | enum(new, reviewed, actioned, dismissed) | default `new` |
| captured_at | datetime | |
| related_to | ref(any) | `→ attached_to`, optional |

**Campaign**

| Field | Type | Notes |
|---|---|---|
| name | string | required |
| channel | enum(email, whatsapp, voice, social, web, event, multi) | |
| objective | text | |
| status | enum(draft, active, paused, completed, archived) | default `draft` |
| start_date / end_date | date | |
| budget | money | |
| spend | money | rolled up |
| target_audience | text | |
| product | ref(Product/SKU) | `→ attached_to`, optional |

### 3.2 CRM module

**Lead**

| Field | Type | Notes |
|---|---|---|
| display_name | string | required — person or company |
| email | email | |
| phone | phone | |
| source | enum(campaign, referral, inbound_call, inbound_email, whatsapp, web, signal, manual) | |
| status | enum(new, contacted, qualified, disqualified, converted) | default `new` |
| qualification_notes | text | |
| score | integer | optional, 0–100 |
| campaign | ref(Campaign) | `→ derived_from`, optional |
| source_signal | ref(Signal) | `← converted_to` (Signal→Lead), optional |

**Account**

| Field | Type | Notes |
|---|---|---|
| name | string | required, unique per tenant |
| type | enum(prospect, customer, partner, former) | default `prospect` |
| industry | string | |
| website | url | |
| billing_address | text | |
| tax_id | string | GSTIN/VAT/EIN |
| email / phone | email / phone | primary account-level |
| status | enum(active, dormant, churned) | default `active` |

**Contact**

| Field | Type | Notes |
|---|---|---|
| first_name / last_name | string | first_name required |
| email | email | |
| phone | phone | |
| whatsapp | phone | optional, defaults to phone |
| role_title | string | |
| is_primary | boolean | default false |
| account | ref(Account) | `→ belongs_to`, required |

*Consent/DNC/unsubscribe state deliberately absent from the spine — register D6 (Increment 2) builds the consent registry as its own store; Contact will gain refs to it then.*

**Opportunity**

| Field | Type | Notes |
|---|---|---|
| name | string | required |
| stage | enum(discovery, proposal, negotiation, verbal, won, lost) | default `discovery` |
| amount | money | |
| probability | integer | 0–100 |
| expected_close | date | |
| loss_reason | string | required when `lost` |
| account | ref(Account) | `→ belongs_to`, required |
| lead | ref(Lead) | `← converted_to` (Lead→Opportunity), optional |
| primary_contact | ref(Contact) | `→ attached_to`, optional |

**Quote**

| Field | Type | Notes |
|---|---|---|
| quote_number | string | service-generated sequence per tenant |
| status | enum(draft, sent, accepted, rejected, expired) | default `draft` |
| valid_until | date | |
| line_items | json | `[{product_sku?, description, qty, unit_price, tax_rate, line_total}]` |
| subtotal / tax / total | money | |
| opportunity | ref(Opportunity) | `← converted_to`, required |
| account | ref(Account) | `→ belongs_to`, required |

**Ticket**

| Field | Type | Notes |
|---|---|---|
| subject | string | required |
| channel | enum(voice, email, whatsapp, web, internal) | |
| priority | enum(low, normal, high, urgent) | default `normal` |
| status | enum(open, in_progress, waiting_customer, resolved, closed) | default `open` |
| resolution | text | |
| opened_at / resolved_at | datetime | |
| csat | integer | optional, 1–5, from the shipped CSAT capture |
| account | ref(Account) | `→ belongs_to`, required |
| contact | ref(Contact) | `→ attached_to`, optional |
| related_to | ref(any) | `→ attached_to`, optional — the "dispute resolves in-loop" edge |

### 3.3 Legal module

**Contract**

| Field | Type | Notes |
|---|---|---|
| title | string | required |
| contract_type | enum(sales, purchase, service, employment, nda, other) | |
| status | enum(draft, in_review, signed, active, expired, terminated) | default `draft` |
| effective_date / end_date | date | |
| tcv | money | total contract value |
| signed_at | datetime | |
| document | artifact | the signed instrument |
| counterparty_account | ref(Account) | `→ belongs_to`, one of the two counterparty refs required |
| counterparty_vendor | ref(Vendor) | `→ belongs_to` |
| quote | ref(Quote) | `← converted_to`, optional |

**Risk**

| Field | Type | Notes |
|---|---|---|
| title | string | required |
| category | enum(financial, legal, operational, security, reputational, compliance) | |
| severity | enum(low, medium, high, critical) | |
| likelihood | enum(rare, possible, likely) | |
| status | enum(identified, assessed, mitigating, accepted, closed) | default `identified` |
| mitigation | text | |
| related_to | ref(any) | `→ attached_to`, optional |

**Incident**

| Field | Type | Notes |
|---|---|---|
| title | string | required |
| incident_type | enum(security, outage, data, fraud, pr, safety, other) | |
| severity | enum(sev1, sev2, sev3, sev4) | sev1 = worst |
| status | enum(declared, contained, resolved, postmortem, closed) | default `declared` |
| declared_at / resolved_at | datetime | declared_at required |
| summary | text | |
| related_to | ref(any) | `→ attached_to`, optional |
| risk | ref(Risk) | `→ attached_to`, optional |

**Policy/Obligation**

| Field | Type | Notes |
|---|---|---|
| title | string | required |
| policy_type | enum(internal_policy, regulatory_obligation, contractual_obligation) | |
| status | enum(draft, active, retired) | default `draft` |
| effective_date / review_date | date | |
| body | text | or `document: artifact` for uploaded policies |
| document | artifact | optional |
| source_contract | ref(Contract) | `→ derived_from`, optional — contractual obligations trace to their contract |

**Evidence**

| Field | Type | Notes |
|---|---|---|
| title | string | required |
| evidence_type | enum(document, screenshot, log, recording, attestation) | |
| captured_at | datetime | required |
| artifact | artifact | required — the evidence payload |
| content_hash | string | integrity hash stamped at capture |
| retention_until | date | per tenant retention policy |
| supports | ref(any) | `→ attached_to`, required — evidence always evidences *something* |

### 3.4 Accounting module

**Invoice**

| Field | Type | Notes |
|---|---|---|
| invoice_number | string | service-generated sequence per tenant |
| status | enum(draft, sent, partially_paid, paid, overdue, disputed, void) | default `draft` |
| issue_date / due_date | date | |
| line_items | json | same shape as Quote line items |
| subtotal / tax / total | money | |
| amount_paid | money | maintained by Payment application |
| account | ref(Account) | `→ belongs_to`, required |
| order | ref(Order) | `← billed_by` (Order→Invoice), optional |

**Payment**

| Field | Type | Notes |
|---|---|---|
| direction | enum(inbound, outbound) | inbound = receipt (AR), outbound = disbursement (AP) |
| method | enum(bank_transfer, upi, card, cheque, cash, gateway, other) | |
| amount | money | required |
| payment_date | date | required |
| reference | string | UTR / gateway id / cheque no |
| status | enum(pending, cleared, failed, refunded) | default `pending` |
| invoice | ref(Invoice) | `← paid_by` (Invoice→Payment), optional — inbound |
| bill | ref(Bill) | `← paid_by` (Bill→Payment), optional — outbound |

**Bill** (payable — the inbound mirror of Invoice)

| Field | Type | Notes |
|---|---|---|
| bill_number | string | vendor's number |
| status | enum(received, approved, scheduled, paid, disputed, void) | default `received` |
| bill_date / due_date | date | |
| total | money | |
| amount_paid | money | |
| vendor | ref(Vendor) | `→ belongs_to`, required |
| purchase_order | ref(Purchase Order) | `← billed_by` (PO→Bill), optional |

**Ledger Entry** (spine: single-line entries in named journals; full double-entry chart of accounts is Increment-4 depth)

| Field | Type | Notes |
|---|---|---|
| entry_date | date | required |
| account_code | string | seed CoA codes; full CoA in Inc 4 |
| description | string | |
| debit | money | exactly one of debit/credit non-zero |
| credit | money | |
| journal | enum(sales, purchases, bank, general) | |
| reconciled | boolean | default false |
| source | ref(any) | `→ derived_from`, optional — Payment/Invoice/Bill provenance |

### 3.5 ERP / Operations module

**Order**

| Field | Type | Notes |
|---|---|---|
| order_number | string | service-generated |
| status | enum(confirmed, in_progress, fulfilled, cancelled) | default `confirmed` |
| order_date | date | |
| line_items | json | |
| total | money | |
| account | ref(Account) | `→ belongs_to`, required |
| contract | ref(Contract) | `← converted_to`, optional |

**Project/Engagement**

| Field | Type | Notes |
|---|---|---|
| name | string | required |
| status | enum(planned, active, on_hold, completed, cancelled) | default `planned` |
| start_date / due_date | date | |
| completion_pct | integer | 0–100 |
| order | ref(Order) | `← fulfilled_by` (Order→Project), optional |
| account | ref(Account) | `→ belongs_to`, required |

**Deliverable**

| Field | Type | Notes |
|---|---|---|
| title | string | required |
| status | enum(pending, in_progress, review, delivered, accepted) | default `pending` |
| due_date | date | |
| delivered_at | datetime | |
| acceptance_notes | text | |
| project | ref(Project/Engagement) | `→ belongs_to`, required |

**Vendor**

| Field | Type | Notes |
|---|---|---|
| name | string | required, unique per tenant |
| category | string | |
| email / phone | email / phone | |
| tax_id | string | |
| bank_details | json | ⚠ sensitive — see review note R5 |
| status | enum(prospective, active, on_hold, terminated) | default `prospective` |

**Purchase Order**

| Field | Type | Notes |
|---|---|---|
| po_number | string | service-generated |
| status | enum(draft, sent, acknowledged, fulfilled, cancelled) | default `draft` |
| order_date / expected_date | date | |
| line_items | json | |
| total | money | |
| vendor | ref(Vendor) | `→ belongs_to`, required |

**Asset/Inventory Item**

| Field | Type | Notes |
|---|---|---|
| name | string | required |
| asset_type | enum(inventory, equipment, license, facility, digital) | |
| sku | string | optional |
| quantity | decimal | with `unit` |
| unit | string | e.g. pcs, hrs, kg |
| location | string | |
| unit_cost | money | |
| status | enum(in_stock, allocated, in_service, maintenance, retired, disposed) | |
| product | ref(Product/SKU) | `→ derived_from`, optional |
| vendor | ref(Vendor) | `→ attached_to`, optional |

**Product/SKU**

| Field | Type | Notes |
|---|---|---|
| name | string | required |
| sku | string | unique per tenant |
| description | text | |
| unit_price | money | list price |
| cost | money | COGS input (feeds the C6 gross-margin KPI, Inc 3) |
| unit | string | |
| status | enum(draft, active, discontinued) | default `draft` |

### 3.6 HRMS module

**Candidate**

| Field | Type | Notes |
|---|---|---|
| name | string | required |
| email / phone | email / phone | |
| role_applied | string | |
| stage | enum(applied, screening, interview, offer, hired, rejected, withdrawn) | default `applied` |
| resume | artifact | |
| source | string | |

*Automated screening/scoring fields deliberately absent — employment-AI automation is hard-gated on D4 (Increment 7); until then Candidate is a record humans drive.*

**Employee**

| Field | Type | Notes |
|---|---|---|
| name | string | required |
| email / phone | email / phone | |
| role_title | string | |
| employment_type | enum(full_time, part_time, contractor) | |
| start_date / end_date | date | end_date on exit |
| compensation | money | payroll-sensitive — the reason the whole object is tagged `payroll` |
| status | enum(active, on_leave, exited) | default `active` |
| reports_to | ref(Employee) | `→ belongs_to`, optional |

### 3.7 Planning module

**Budget**

| Field | Type | Notes |
|---|---|---|
| name | string | required |
| period_start / period_end | date | required |
| category | string | e.g. marketing, payroll, opex |
| planned | money | |
| actual | money | rolled up (Inc-4 depth automates the rollup) |
| status | enum(draft, active, closed) | default `draft` |

#### The strategy pipeline (Increment 6 / STRAT)

Notice → Strategize → Decide → Act → Close, as records. **The reviewed sheets with the reasoning behind every field name are [increment-6/04a](../increment-6/04a_planning_object_sheets.md); this is the summary.** All eight are module `Planning`, domain `strategy`, owner P11, and every ref uses the existing §19.1 vocabulary — STRAT extends it by nothing.

**Objective** — what the business is trying to achieve over a horizon.

| Field | Type | Notes |
|---|---|---|
| title | string | required |
| narrative | text | why this matters, in the owner's words |
| horizon | enum(quarter, year, multi_year) | |
| status | enum(draft, active, achieved, abandoned) | default `draft`. `abandoned` is deliberate — a quietly dropped objective is the most common real outcome |
| owner | ref(Employee) | `→ attached_to`, optional |

**Target** — a number, a direction and a date.

| Field | Type | Notes |
|---|---|---|
| name | string | required |
| kpi_key | string | a key from the C6 registry. **String, not enum** — the registry is the single source of truth and an enum copy would be the second store decision 3.2 forbids |
| direction | enum(increase, decrease, hold) | load-bearing: for a days-outstanding metric, improving means going *down* |
| target_value | decimal | |
| by_date | date | |
| status | enum(open, met, missed, withdrawn) | default `open` |
| objective | ref(Objective) | `→ belongs_to`, optional |

**Forecast** — a committed number the business plans against (distinct from TWIN's ephemeral run result).

| Field | Type | Notes |
|---|---|---|
| name | string | required |
| kpi_key | string | as Target |
| method | enum(manual, twin_forecast, external) | |
| value | decimal | |
| interval_low / interval_high | decimal | the honest band, not a point |
| for_period_start / for_period_end | date | |
| twin_run_id | string | optional. **String, not a ref** — `twin_runs` is control-plane and this record is tenant-plane |
| target | ref(Target) | `→ attached_to`, optional |

**Minutes** — what was said and noticed in a session.

| Field | Type | Notes |
|---|---|---|
| title | string | required |
| held_on | datetime | required |
| attendees | text | free text — a sole trader's "me" is a legitimate value, and a ref list would make it unrepresentable |
| body | text | |
| decisions_summary | text | what the room concluded, before any of it becomes a Resolution |
| objective | ref(Objective) | `→ attached_to`, optional |

**Proposition** — a candidate course of action, with its rationale and its cost.

| Field | Type | Notes |
|---|---|---|
| title | string | required |
| rationale | text | |
| expected_effect | text | |
| cost_estimate | money | |
| honesty_grade | enum(replay, forecast, unknown, untested) | default `untested`. **A non-`untested` grade is refused without a `twin_run_id`** — a grade must have a run behind it |
| twin_run_id | string | optional |
| status | enum(draft, tabled, adopted, rejected, withdrawn) | default `draft`. Adoption is legal **only from `tabled`** |
| minutes | ref(Minutes) | `→ derived_from`, optional |

**Resolution** — a decision the business formally adopted. **Adopting is a T2 certified human act.**

| Field | Type | Notes |
|---|---|---|
| title | string | required |
| decision | text | required |
| adopted_on | date | required |
| concerns_module | string | the HBS module it concerns |
| engraved_at | datetime | when it was pinned to the Seasons timeline |
| status | enum(active, superseded, revoked) | default `active`; `revoked` is terminal |
| adopted_by | ref(Employee) | `→ attached_to`, optional |
| proposition | ref(Proposition) | `← converted_to`, optional |

**Mandate** — what a Resolution actually obliges. Issues **only from an `active` Resolution**.

| Field | Type | Notes |
|---|---|---|
| title | string | required |
| owning_process | string | a process code — Processes are entities, not records, so there is nothing to ref at |
| review_due | date | **required** — the only required date in the eight, because the loop has to close |
| status | enum(issued, in_flight, reviewed, closed) | default `issued` |
| resolution | ref(Resolution) | `→ belongs_to`, **required** |
| target | ref(Target) | `→ attached_to`, optional |

**Review** — predicted versus realized, honestly.

| Field | Type | Notes |
|---|---|---|
| reviewed_on | date | |
| predicted_value | decimal | the Target's value, or the Forecast's where one is attached |
| realized_value | decimal | **nullable — None means not measurable, never zero** |
| measurable | boolean | default `false` |
| missing | text | what was absent, in words |
| verdict | enum(on_track, off_track, met, missed, not_measurable) | `not_measurable` is a first-class outcome |
| notes | text | |
| mandate | ref(Mandate) | `→ belongs_to`, **required** |

---

## 4. Link Vocabulary Recap

Every ref above materializes into exactly one `tenant_record_links` row:

| rel_type | Edges produced by the spine |
|---|---|
| `converted_to` | Signal→Lead · Lead→Opportunity · Opportunity→Quote · Quote→Contract · Contract→Order |
| `belongs_to` | Contact/Opportunity/Quote/Ticket/Invoice/Order/Project→Account · Bill/PO→Vendor · Deliverable→Project · Contract→counterparty · Employee→Employee (reports_to) |
| `attached_to` | Ticket/Risk/Incident/Signal/Evidence→any · Opportunity→Contact · Campaign→Product · Asset→Vendor |
| `fulfilled_by` | Order→Project |
| `billed_by` | Order→Invoice · PO→Bill |
| `paid_by` | Invoice→Payment · Bill→Payment |
| `derived_from` | Lead→Campaign · Ledger Entry→source · Asset→Product · Policy→Contract |

## 5. Review Notes — choices needing your eye (then this doc freezes as the fixture)

* **R1 — Account/Contact owner = P06.** Accounts are touched by P03/P04/P06/P07; I assigned ownership to **P06 Resolve-to-Retain** ("the relationship keeper") because it's in Wave 0 — P03 proposes account creation at conversion via `object.change_proposed`. The alternative (P07 Renew-&-Expand) is truer to the Blueprint's account-lifecycle framing but isn't seeded until later, which would leave the Solo Pack's most-touched object platform-owned/HITL-on-write. Confirm P06.
* **R2 — Payment owner = P08 for both directions.** One Payment object with a `direction` field, owned by Order-to-Cash. Outbound (AP) payments in Wave 0 will be rare and land as HITL-visible P08 writes; when P09 Source-to-Pay seeds (Inc 4), it *proposes* outbound payments to P08 rather than splitting Payment into two objects. Simple, one ledger of cash movements. Confirm.
* **R3 — Product/SKU module = ERP/Operations** (inventory/pricing ties) rather than Marketing. Its owner stays P16 Idea-to-Launch.
* **R4 — Employee tagged `payroll` wholesale.** Compensation lives on the record, so the entire object is behind the most restrictive tag; splitting a `payroll`-tagged compensation sub-record from an `hr`-tagged Employee is Inc-4 HRMS-depth work if finer access proves necessary. Candidate stays `hr`.
* **R5 — Vendor.bank_details as plain JSONB.** The tenant DB is per-tenant isolated, but bank details arguably deserve key-vault encryption like integration credentials. Options: (a) leave JSONB in the tenant DB (isolation is the control), (b) store in the control-plane key vault with a reference here. I lean (a) for the spine + a D2 revisit in Inc 4 (credential scoping increment). Your call.
* **R6 — Risk/Incident/Evidence homed in the Legal module** (§10.3 names seven modules; Trust objects fit Legal-compliance best). Purely organizational — tags (`trust`) and owners (P14/P17) are what enforcement uses.
* **R7 — Numbering sequences** (quote_number, invoice_number, order_number, po_number) are service-generated per tenant with a configurable prefix (e.g. `INV-2026-0001`). Format setting lands in tenant settings; confirm the pattern.
