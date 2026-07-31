import { useState } from "react";

import { Icon } from "../components/Icon";
import {
  StepUpCeremony,
  useCertifiedAct,
  type EchoRenderer,
  type RunnableCertifiedType,
} from "../components/certified";
import {
  Bar,
  Empty,
  Failed,
  Lines,
  Scaffold,
  reasonOf,
  useChoice,
  useResource,
} from "../lifecycle";
import {
  fetchTrayList,
  respondToApproval,
  type Tray,
  type TrayDecision,
  type TrayPath,
} from "../api/trays";
import "./tray.css";

/**
 * The Tray · any depth · C · **certified** (D6 §4). Wired in R-4 part W.
 *
 * D8 row 24 calls this the single most consequential replacement in the product
 * — it retires `HITLPanel`. The layout is unchanged from the owner-approved
 * build; what changed is where every field comes from, and what the surface
 * does when a field is not there.
 *
 * Spec §6.1's five-field order is preserved exactly, because it is the order a
 * person needs to decide and not a layout preference. What each field is now
 * bound to, and where the binding is honestly empty:
 *
 *   1  who raised it        `prepared_by` · `sla.seconds_left` · `sla.on_timeout`
 *   2  what is being asked  `certified.props.summary`
 *   3  why                  `what_happened.sentence`, and `recommendation` when written
 *   4  the facts            `checkpoint_key` · `approval_id` · `what_happened.object`
 *   5  the paths            `paths[]`, with `consequence` and `cost`
 *
 * **There is no "waited" figure any more, and its absence is the point.** The
 * card used to print "waited 34m". Nothing on the wire can produce that number
 * honestly. `GET /ai/approvals/pending` carries `requested_at`, but the column
 * is a naive `DateTime` defaulted to `datetime.utcnow` and is serialised with
 * no offset, so `Date.parse` reads it as *local* time and a tenant in IST would
 * be shown a figure 330 minutes wrong. Subtracting instead — budget minus
 * remainder — crosses two different SLA tables (`HITLCheckpointDef.sla_seconds`
 * keyed by checkpoint against `sla_for_category(snapshot["category"])`), which
 * makes the difference a number neither server computed. §7.1 says a binding
 * that cannot be answered renders nothing, so the card shows the one SLA figure
 * the server *did* compute — `sla.seconds_left` — and calls it what it is.
 *
 * **`paths[].cost` is an object now, and every part of it can be absent.** The
 * estimator ships (`genui/cost.py`) but returns `null` below a five-observation
 * floor, and the composer's `currency` is `null` in both of its branches — the
 * platform does not stamp a currency on an amount yet. So a null cost renders
 * as **no cost line at all** — never "₹0", never "—" — and a stated amount
 * renders with **no currency symbol** plus the sentence saying none was stated,
 * which is the idiom `certified.payment` already ships and `tests/certified`
 * pins. A bare figure in a rupee-shaped app is read as rupees whether or not
 * anyone said so. `tests/tray_cost.test.tsx` holds all of it.
 *
 * **This is `useCertifiedAct`'s first real consumer** (part C, C2/C3/C5). Every
 * path routes through it, so a `step_up_required` 403 from
 * `POST /ai/approvals/{id}/respond` — which a plain session *will* get, because
 * the gate is `enforce_tier(intent_for_approval(...))` in the handler body — is
 * the ceremony opening rather than an error. The act's kind is read off the
 * certified block the server struck (`certified.payment` or
 * `certified.approval`); a block naming anything else is not routed at all,
 * because `RunnableCertifiedType` is a closed set and guessing which gate an
 * unknown act needs is precisely what the closed set exists to prevent.
 *
 * `renderer` defaults to `"S"` for the estate and exists so the Line can pass
 * `"C"`: C5 wants the echo bus to tell a phone tap from an operator click, and
 * the hook takes the renderer as a parameter rather than sniffing for it.
 * `ThreadSurface` mounts this component and does not pass it yet — see the
 * report.
 */

/** A stable empty collection: a fresh `[]` per render would hand `useChoice` a
 *  new identity on every pass for no change in what is on screen. */
const NONE: readonly Tray[] = [];

/** The two certified blocks `genui/trays.py` can strike, and nothing else. */
const TRAY_ACTS: Record<string, RunnableCertifiedType> = {
  "certified.approval": "certified.approval",
  "certified.payment": "certified.payment",
};

const ACT_EYEBROW: Record<RunnableCertifiedType, string> = {
  "certified.approval": "APPROVAL",
  "certified.payment": "PAYMENT",
  "certified.autonomy-change": "AUTONOMY",
  "certified.connector-binding": "CONNECTOR",
  "certified.mastering-declaration": "MASTERING",
  "certified.provider-opt-in": "MODEL PROVIDER",
  "certified.strategy-resolution": "RESOLUTION",
  "certified.consent": "CONSENT",
};

/** Which of the closed set of acts this tray is, or `null` when the server
 *  struck a block this client cannot route. Never guessed. */
function actOf(tray: Tray): RunnableCertifiedType | null {
  return TRAY_ACTS[tray.certified.component.replace(/@\d+$/, "")] ?? null;
}

/** The two path keys the composer emits. An unrecognised key gets no button —
 *  responding `REJECTED` to a path nobody called "decline" would answer a
 *  question the person did not ask (§7.4). */
function decisionOf(path: TrayPath): TrayDecision | null {
  if (path.key === "approve") return "APPROVED";
  if (path.key === "decline") return "REJECTED";
  return null;
}

/** A prop off the certified block, with `""` read as absent — the registry
 *  types several of these as required strings, so a server with nothing to say
 *  sends an empty one, and a labelled row with nothing in it reads as a
 *  truncation bug rather than as the honest answer (§7.1). */
function propOf(props: Record<string, unknown>, key: string): string | null {
  const value = props[key];
  if (value === null || value === undefined) return null;
  const text = String(value);
  return text === "" ? null : text;
}

/**
 * Three-digit grouping, by hand and locale-free.
 *
 * Deliberately not `toLocaleString`: it reformats money with whatever ICU data
 * the machine happens to carry, so the figure the owner is about to release
 * changes shape between two browsers. `certifiedSet.tsx` makes the same call
 * for the same reason; it is not exported through the certified barrel and
 * `tests/certified.test.tsx` forbids reaching past that barrel, so this is a
 * second copy on purpose rather than an import that would break the boundary.
 * It groups and does nothing else — no rounding, no padding to two decimals,
 * no symbol.
 */
function grouped(value: number): string {
  const text = String(value);
  const negative = text.startsWith("-");
  const bare = negative ? text.slice(1) : text;
  const [whole, ...rest] = bare.split(".");
  if (whole === undefined || !/^\d+$/.test(whole)) return text;
  let out = "";
  for (let i = 0; i < whole.length; i += 1) {
    if (i > 0 && (whole.length - i) % 3 === 0) out += ",";
    out += whole[i]!;
  }
  return `${negative ? "-" : ""}${out}${rest.length > 0 ? `.${rest.join(".")}` : ""}`;
}

/** The server's own remainder, said in words. Floored, never rounded up: a
 *  card that says "1h left" with fifty-nine minutes gone is worse than one that
 *  says "0h". */
function remaining(seconds: number): string {
  if (seconds === 0) return "past its window";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m left`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h left`;
  return `${Math.floor(seconds / 86400)}d left`;
}

export function TraySurface({
  onEcho,
  renderer = "S",
}: {
  onEcho: (msg: string) => void;
  /** Which front door this Tray is standing in. The Line passes `"C"`. */
  renderer?: EchoRenderer;
}) {
  const trays = useResource(fetchTrayList);
  const [settled, setSettled] = useState<Record<string, string>>({});
  /* A failure that is *not* a step-up refusal. The hook re-throws those to the
     caller untouched and it is right to — a 409 "already responded" is the
     Tray's news to break, not a security layer's. */
  const [broke, setBroke] = useState<string | null>(null);

  const list = trays.phase === "ready" ? trays.value : NONE;

  /* L1. This was `useState<string>(TRAY[0]!.id)`, which threw before render on
     an empty tray — eleven lines above the copy that exists for exactly that
     case. The open card is derived from the collection now, so an empty
     response is a state this surface can reach rather than a crash. */
  const { chosenId: openId, choose } = useChoice(list, (t) => t.tray_id);

  const act = useCertifiedAct({ renderer, surface: "tray", onEcho });

  async function take(tray: Tray, path: TrayPath): Promise<void> {
    const kind = actOf(tray);
    const decision = decisionOf(path);
    if (kind === null || decision === null) return;

    const summary = propOf(tray.certified.props, "summary");
    const subject = tray.what_happened.object?.label ?? summary ?? tray.approval_id;

    setBroke(null);
    try {
      await act.run(
        {
          act: kind,
          echo: `${decision === "APPROVED" ? "approved" : "declined"} ${subject}`,
          summary: summary ?? tray.what_happened.sentence,
          subject: tray.approval_id,
          componentId: tray.certified.component,
        },
        async () => {
          await respondToApproval(tray.approval_id, decision);
          /* Reached only when the server took it. `run` retries `perform`
             WHOLE after a ceremony completes, so this rides the retry too and
             there is no second success path to keep in step. */
          setSettled((previous) => ({ ...previous, [tray.tray_id]: path.label }));
          const next = list.find(
            (other) =>
              other.tray_id !== tray.tray_id && settled[other.tray_id] === undefined,
          );
          if (next !== undefined) choose(next.tray_id);
        },
      );
    } catch (thrown) {
      setBroke(reasonOf(thrown));
    }
  }

  if (trays.phase === "pending") return <TrayScaffold />;

  if (trays.phase === "failed") {
    return (
      <section className="tr">
        <Failed what="the Tray" reason={trays.reason} onRetry={trays.retry} />
      </section>
    );
  }

  const waiting = list.filter((tray) => settled[tray.tray_id] === undefined);
  /* The soonest deadline the server itself computed. `Math.min()` of nothing is
     `Infinity`, and "soonest due in Infinitym" is a number nobody measured —
     which §7.1 forbids more strictly than it forbids a blank. */
  const deadlines = waiting
    .map((tray) => tray.sla.seconds_left)
    .filter((seconds): seconds is number => seconds !== null);
  const soonest = deadlines.length === 0 ? null : Math.min(...deadlines);

  return (
    <section className="tr">
      <header className="tr-head">
        <div>
          <span className="t-eyebrow">THE TRAY</span>
          <h1 className="tr-title t-display">
            {waiting.length === 0
              ? "Nothing needs you."
              : `${waiting.length} ${waiting.length === 1 ? "thing needs" : "things need"} you`}
          </h1>
        </div>
        {soonest !== null && (
          <div className="tr-head-meta">
            <span className="m-chip">
              <Icon name="clock" size={12} />
              soonest {remaining(soonest)}
            </span>
          </div>
        )}
      </header>

      {broke !== null && (
        <div className="m-plate tr-problem" role="status">
          <span className="m-lamp" data-negative aria-hidden="true" />
          <span className="tr-problem-text">
            That did not go through, and nothing was decided.
            <span className="tr-problem-reason t-mono">{broke}</span>
          </span>
        </div>
      )}

      {act.problem !== null && (
        <div className="m-plate tr-problem" role="status">
          <span className="m-lamp" data-negative aria-hidden="true" />
          <span className="tr-problem-text">
            {act.problem.message}
            {act.problem.kind === "gap" && (
              <span className="tr-problem-reason t-mono">
                Closed by {act.problem.closedBy}.
              </span>
            )}
          </span>
          <button className="m-btn" data-rank="quiet" onClick={act.clearProblem}>
            Dismiss
          </button>
        </div>
      )}

      {list.length === 0 ? (
        /* L2. The title above already says "Nothing needs you."; this says what
           that means, because the dangerous reading of an empty tray is that
           nothing is happening rather than that nothing has been escalated. */
        <Empty
          alone
          title="Your colleagues are working without needing you."
          body="Nothing has been escalated. Work is still running — a card arrives here only when a colleague reaches something it is not allowed to decide alone, and none of them has today."
        />
      ) : (
        <div className="tr-list vh-stagger">
          {list.map((tray, i) => (
            <TrayCardView
              key={tray.tray_id}
              tray={tray}
              index={i}
              open={openId === tray.tray_id && settled[tray.tray_id] === undefined}
              settledAs={settled[tray.tray_id]}
              busy={act.busy}
              onOpen={() => choose(tray.tray_id)}
              onTake={(path) => void take(tray, path)}
            />
          ))}
        </div>
      )}

      {act.ceremony !== null && (
        <StepUpCeremony
          prompt={act.ceremony}
          onElevated={act.onElevated}
          onClose={act.onClose}
        />
      )}
    </section>
  );
}

/**
 * The pending state: the Tray's own structure, standing, with the words not yet
 * in it (D7 §3.1 — layout first, data second, and no spinner on any of the
 * seventeen).
 *
 * The plates are drawn first and the bars go *inside* them. `vh-skeleton`'s
 * ground is a 6/255 delta on the raw canvas, so a bar on the page background is
 * invisible; on a plate it reads.
 */
function TrayScaffold() {
  return (
    <section className="tr">
      <Scaffold label="The Tray">
        <div className="tr-ghost">
          <header className="tr-head">
            <div className="tr-ghost-title">
              <Bar width="xs" />
              <Bar width="md" tall />
            </div>
          </header>

          <div className="tr-list">
            {[0, 1, 2].map((i) => (
              <article
                key={i}
                className="tr-card m-plate"
                data-open={i === 0 || undefined}
              >
                <div className="tr-ghost-head">
                  <Bar width="sm" />
                  <Bar width="xs" />
                </div>
                <div className="tr-ghost-ask">
                  <Bar width="lg" tall />
                </div>
                {i === 0 && (
                  <div className="tr-ghost-body">
                    <Lines n={3} />
                    <div className="m-well tr-facts" data-deep>
                      <Lines n={2} />
                    </div>
                  </div>
                )}
              </article>
            ))}
          </div>
        </div>
      </Scaffold>
    </section>
  );
}

function TrayCardView({
  tray,
  index,
  open,
  settledAs,
  busy,
  onOpen,
  onTake,
}: {
  tray: Tray;
  index: number;
  open: boolean;
  settledAs: string | undefined;
  busy: boolean;
  onOpen: () => void;
  onTake: (path: TrayPath) => void;
}) {
  const kind = actOf(tray);
  const props = tray.certified.props;
  const summary = propOf(props, "summary");
  const amount = props["amount"];
  const currency = propOf(props, "currency");

  /* Every tray carries a certified block, so "is this certified" no longer
     separates one card from another — every one of them is. The distinction
     that *does* carry information is the one the composer itself draws: an
     approval whose gate recorded an amount is a `certified.payment` and moves
     money. That is what earns the gold-tinted glass; a plain approval keeps
     the seal and the eyebrow on a plate, so the §2.1 budget stays a budget
     rather than becoming the page. */
  const moves = kind === "certified.payment";

  if (settledAs !== undefined) {
    return (
      <article className="tr-card tr-card-settled m-plate" style={{ ["--i" as string]: index }}>
        <span className="m-lamp" data-positive />
        <span className="tr-settled-text t-muted">
          {summary ?? tray.what_happened.sentence}
        </span>
        <span className="t-eyebrow">{settledAs.toUpperCase()}</span>
      </article>
    );
  }

  return (
    <article
      className={moves ? "tr-card m-glass" : "tr-card m-plate"}
      data-gold={moves || undefined}
      data-open={open || undefined}
      style={{ ["--i" as string]: index }}
    >
      {/* ------------------------------------- 1 · who raised it, and its clock */}
      <button className="tr-card-head" onClick={onOpen} aria-expanded={open}>
        <span className="tr-raiser">
          <span className="m-plinth tr-raiser-seal" aria-hidden="true">
            <span className="t-mono">
              {(tray.prepared_by?.name ?? "?").slice(0, 1)}
            </span>
          </span>
          <span className="tr-raiser-text">
            {/* §7.1 — the composer admits `prepared_by` can be null, so the name
                is not stood in for. The id line below still identifies the card. */}
            {tray.prepared_by !== null && (
              <span className="tr-raiser-name t-display">{tray.prepared_by.name}</span>
            )}
            <span className="t-mono tr-raiser-id">
              {tray.prepared_by?.entity_id ?? tray.approval_id}
            </span>
          </span>
        </span>

        <span className="tr-head-right">
          <span className="t-eyebrow" data-certified>
            <span className="m-medallion tr-seal" aria-hidden="true">
              <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.6" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20 6 9 17l-5-5" />
              </svg>
            </span>
            CERTIFIED
            {kind !== null && ` · ${ACT_EYEBROW[kind]}`}
            {` · ${tray.certified.tier}`}
          </span>
          {/* The one SLA figure the server computed for itself. */}
          {tray.sla.seconds_left !== null && (
            <span className="tr-waited t-mono">{remaining(tray.sla.seconds_left)}</span>
          )}
          <Icon name="chevron" size={14} className="tr-caret" />
        </span>
      </button>

      {/* ------------------------------------------------ 2 · what is asked */}
      {summary !== null && <h2 className="tr-ask t-display">{summary}</h2>}

      {open && (
        <div className="tr-body vh-enter-fade">
          {/* --------------------------------- 3 · why, in her own words */}
          <blockquote className="tr-because">
            <p className="t-narrative">{tray.what_happened.sentence}</p>
            {tray.prepared_by !== null && (
              <cite className="t-mono">— {tray.prepared_by.name}</cite>
            )}
          </blockquote>

          {/* Pragya's sentence, written once at first delivery and read back
              from `tray_recommendations`. Null is a real answer — the composer
              says "advice lost, never work" — so there is no line at all
              rather than an empty one. */}
          {tray.recommendation !== null && (
            <div className="tr-advice">
              <span className="t-eyebrow">PRAGYA RECOMMENDS</span>
              <p className="t-narrative">{tray.recommendation.sentence}</p>
              {tray.recommendation.why !== null && (
                <p className="tr-advice-why t-narrative">{tray.recommendation.why}</p>
              )}
            </div>
          )}

          {/* ----------------------------------- 4 · the facts it rests on */}
          <div className="m-well tr-facts" data-deep>
            <dl>
              {tray.checkpoint_key !== null && (
                <Fact label="CHECKPOINT" value={tray.checkpoint_key} />
              )}
              <Fact label="APPROVAL" value={tray.approval_id} />
              {tray.what_happened.object !== null && (
                <Fact
                  label={tray.what_happened.object.kind.toUpperCase()}
                  value={tray.what_happened.object.label}
                />
              )}
              {typeof amount === "number" && (
                <Fact label="AMOUNT" value={grouped(amount)} />
              )}
              {tray.sla.on_timeout !== null && (
                <Fact label="IF IT TIMES OUT" value={tray.sla.on_timeout} />
              )}
            </dl>
          </div>

          {/* A figure with no unit on it, said rather than assumed. The gate's
              snapshot records a bare amount and the platform does not stamp a
              currency on it, so a reader in a rupee-shaped app would supply one
              (§7.4 — render the gap, never draw over it). */}
          {typeof amount === "number" && currency === null && (
            <p className="tr-gap t-mono">The currency was not stated on this approval.</p>
          )}

          {/* ------------------------------------------------ 5 · the paths */}
          <div className="tr-paths">
            {tray.paths.map((path) => {
              const takeable = kind !== null && decisionOf(path) !== null;
              if (!takeable) return null;
              return (
                <button
                  key={path.key}
                  className="m-btn tr-path"
                  data-rank={path.key === "approve" ? "certified" : "quiet"}
                  disabled={busy}
                  onClick={() => onTake(path)}
                >
                  {path.key === "approve" && <Icon name="key" size={14} />}
                  <span>{path.label}</span>
                  {/* A null cost renders as nothing. Never "₹0", never a dash.
                      `cost.amount` of 0 is a real observation and does render —
                      the test is on the cost object, never on its truthiness. */}
                  {path.cost !== null && (
                    <span className="tr-path-cost t-mono">
                      {path.cost.currency !== null && `${path.cost.currency} `}
                      {grouped(path.cost.amount)}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* What each path does, in the composer's words, plus where a figure
              came from. Below the row rather than inside the buttons: a path is
              a decision and the consequence is why you would take it. */}
          <dl className="tr-consequences">
            {tray.paths.map((path) => (
              <div className="tr-consequence" key={path.key}>
                <dt className="t-eyebrow">{path.label.toUpperCase()}</dt>
                <dd>
                  <span className="tr-consequence-text">{path.consequence}</span>
                  {path.cost !== null && (
                    <span className="tr-gap t-mono">
                      {path.cost.basis}
                      {path.cost.currency === null &&
                        " · the platform stated no currency for it"}
                    </span>
                  )}
                  {kind !== null && decisionOf(path) === null && (
                    <span className="tr-gap t-mono">
                      No control is drawn for this path: the approval endpoint
                      answers approve and decline, and nothing else.
                    </span>
                  )}
                </dd>
              </div>
            ))}
          </dl>

          {/* Said once for the card, not once per path. §7.4 — the gap is
              rendered rather than drawn over, and it names the block the server
              actually struck so it is checkable rather than a shrug. */}
          {kind === null && (
            <p className="tr-gap t-mono">
              This estate cannot take any of these paths. The server struck a
              certified block of type {tray.certified.component}, and this client
              has no gate for it — routing it through a guessed one is exactly
              what the certified layer's closed set exists to prevent.
            </p>
          )}

          <p className="tr-cert-note t-mono">
            <Icon name="seal" size={12} />
            This act is certified at {tray.certified.tier}. Taking it asks you to
            prove it is you, and the estate refuses it until you have —{" "}
            {tray.certified.manifest_hash.slice(0, 19)}
          </p>
        </div>
      )}
    </article>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="tr-fact">
      <dt className="t-eyebrow">{label}</dt>
      <dd className="tr-fact-value t-mono">{value}</dd>
    </div>
  );
}
