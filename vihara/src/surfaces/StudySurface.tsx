import { useState } from "react";

import { Icon } from "../components/Icon";
import {
  deletePasskey,
  isPasskeySupported,
  listPasskeys,
  registerPasskey,
  type PasskeyCredential,
} from "../api/authn";
import { fetchCompanyName } from "../api/identity";
import {
  fetchBalance,
  fetchMe,
  fetchPreferences,
  fetchSubscription,
  observeDensity,
  writePreference,
  type Me,
  type PreferenceValue,
} from "../api/study";
import { Bar, Empty, Failed, Lines, Scaffold, reasonOf, useResource } from "../lifecycle";
import "./study.css";

/**
 * The Study · depth 2 · S (D6 §15a) — the eighteenth surface, VP-03. Wired in
 * R-4 part W.
 *
 * **Not a place in the estate: the desk you sit at.** Reachable from the shell,
 * never from the territory — which is why it is the one depth-2 surface with no
 * district above it in the trail.
 *
 * The four R2 rules still hold and three of them survived wiring unchanged. The
 * fourth did not, and that is the interesting part of this diff.
 *
 * ## 1 · Passkeys, which had to actually work
 *
 * Enrolment is the prerequisite for **every T2 act in the product** — the tray,
 * the connector bind, the mastering flip, the strategy adoption. A tenant with
 * no passkey cannot complete a single ceremony, and this is the only surface
 * where one can be added. So this is the one panel where "it renders" was never
 * good enough: it runs the real WebAuthn registration ceremony against
 * `/ai/authn/webauthn/register/begin` and `/finish`, and the list re-reads from
 * the server afterwards rather than trusting what this screen thinks happened.
 *
 * **Adding is the ceremony; removing is one click.** The safe direction is never
 * made harder than the unsafe one (D3 §3.4) — which is also why `deletePasskey`
 * is a plain `DELETE` in `api/authn.ts` and routes through no certified layer.
 * A browser with no `PublicKeyCredential` gets the absence said in words rather
 * than a button that cannot work.
 *
 * ## 2 · The notification panel is one switch, not three
 *
 * `notify.*` was the right namespace and the panel drew three toggles in it.
 * Exactly **one** preference is read by anything on the platform:
 * `notify.whatsapp_mirror`, which `genui/whatsapp_mirror.py` consults before a
 * mirror send. `get_preferences` has one other caller in the entire backend and
 * it is the endpoint that serves this panel. So a toggle for push or for the
 * morning story would write a row to a store nothing reads and report it as
 * kept — the exact fraud part C names, one layer down. The two are drawn as
 * named absences instead, in the place their switches were.
 *
 * The one real switch is also **on by default and off only when stated**: the
 * mirror reads `value not in ("off", False)`, so an absent row means on. A
 * client that rendered an absent preference as an unchecked box would tell a
 * tenant they had turned something off that is running.
 *
 * ## 3 · Density is stated here, and nothing reads it yet
 *
 * The switch writes for real (`PUT /ai/learning/preferences`, which the backend
 * is explicit is *not* certified — "gating it would be the kind of ceremony that
 * teaches people to click through ceremonies") and records the observation on
 * the bus. Two things it no longer claims:
 *
 *  - **There is no learned value and no observation count.** `learn_preference`
 *    exists and nothing in the backend ever calls it with a density key;
 *    `observe_density` emits `learning.density_observed` and no job turns those
 *    into a preference. "learned: novice · 4 observations" was two invented
 *    figures. The store's own `learned` flag is shown when a row comes back
 *    carrying it, and nothing is shown when it does not.
 *  - **No surface in this app reads the stated value.** Every surface holds its
 *    own density in local state today. The panel says so, because a preference
 *    that is stored and ignored looks identical to one that is honoured.
 *
 * ## 4 · Money is credits, and nobody stamped a currency on it
 *
 * The wallet read is `GET /credits/balance`, and its body is buckets —
 * `daily_credits`, `wallet_balance`, `subscription_credits`,
 * `total_available` — not a rupee balance. The old panel printed
 * `₹{balanceINR}` and a runway derived from a weekly burn figure that exists
 * nowhere. Both are gone: the figure is credits, said in the endpoint's own
 * word, and the runway is absent rather than computed from an invented
 * denominator. A subscription fee is printed with the sentence saying no
 * currency was stated on it — the idiom `certified.payment` already ships and
 * `tests/tray_cost.test.tsx` pins.
 *
 * ## 5 · Dunning stays exactly as it was
 *
 * It is explanatory copy and it is correct: this is the one surface that must
 * explain why the estate has gone quiet, because everywhere else quiet reads as
 * calm — the product's own design working against the tenant at the worst
 * moment. The ladder is **always** visible rather than revealed once a rung is
 * reached. The one thing removed is the "you are here" marker, which was read
 * off the fixture; the tenant's standing is published on the estate projection
 * and not on any read this desk makes. See the report.
 */

/** The dunning ladder, in the order it is climbed. Copy, not data — and
 *  deliberately local: no endpoint describes what happens at each rung, and
 *  this is the one screen where a tenant is entitled to know in advance. */
const DUNNING: { label: string; what: string }[] = [
  {
    label: "We tell you",
    what: "A card in your tray and one message. Nothing changes about how the estate runs.",
  },
  {
    label: "Seven days of grace",
    what: "Everything keeps running. We stop starting anything new that costs money.",
  },
  {
    label: "The estate goes quiet",
    what: "Your colleagues stop acting and keep watching. Nothing is deleted, nothing is lost, and the record stays complete. You can still read everything.",
  },
  {
    label: "Suspended",
    what: "Access pauses. Your data is kept, and a full export stays available to you for ninety days.",
  },
];

/** The one preference anything on this platform reads. */
const MIRROR_KEY = "notify.whatsapp_mirror";

/** Where a stated density goes. Printed on the panel so the claim is checkable
 *  against the store rather than trusted. */
const DENSITY_KEY = "density.default";

/**
 * The two switches that are not drawn, and why. Their keys are valid in the
 * store's `notify` namespace and **nothing anywhere reads them**, so a toggle
 * would look kept and be forgotten (§7.4).
 */
const UNREAD_NOTIFY: { key: string; label: string; why: string }[] = [
  {
    key: "notify.push.device",
    label: "Push on this device",
    why: "Push delivery does not consult a preference. Nothing reads this key, so a switch here would record your choice and change nothing about what arrives.",
  },
  {
    key: "notify.morning.story",
    label: "The morning story",
    why: "The morning job composes and delivers on its own schedule and asks no preference first. Turning it off would be a setting you kept and we ignored.",
  },
];

type Density = "novice" | "operator";

interface Who {
  me: Me;
  company: string | null;
}

interface Billing {
  balance: Record<string, unknown>;
  subscription: Record<string, unknown>;
}

/** A number off a loosely-typed body. `null` where the field is absent — which
 *  is not zero, and on a wallet the difference is the whole point (§7.1). */
function numberAt(source: Record<string, unknown>, key: string): number | null {
  const value = source[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function textAt(source: Record<string, unknown>, key: string): string | null {
  const value = source[key];
  return typeof value === "string" && value !== "" ? value : null;
}

function objectAt(
  source: Record<string, unknown>,
  key: string,
): Record<string, unknown> | null {
  const value = source[key];
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/**
 * Three-digit grouping, by hand and locale-free.
 *
 * Deliberately not `toLocaleString`: it reformats a figure with whatever ICU
 * data the machine happens to carry, so the number changes shape between two
 * browsers. `TraySurface` makes the same call for the same reason.
 */
function grouped(value: number): string {
  const rounded = Math.round(value * 100) / 100;
  const [whole = "", fraction] = String(rounded).split(".");
  let out = "";
  for (let i = 0; i < whole.length; i += 1) {
    if (i > 0 && (whole.length - i) % 3 === 0) out += ",";
    out += whole[i]!;
  }
  return fraction === undefined ? out : `${out}.${fraction}`;
}

/** A wire timestamp trimmed to the day. */
function day(at: string | null): string | null {
  return at === null ? null : at.slice(0, 10);
}

export function StudySurface({ onEcho }: { onEcho: (msg: string) => void }) {
  const who = useResource<Who>(async () => {
    /* `fetchCompanyName` is fail-soft by contract — it returns `null` rather
       than throwing, so a tenant whose company row is unreadable still gets
       their own desk. */
    const [me, company] = await Promise.all([fetchMe(), fetchCompanyName()]);
    return { me, company };
  });

  if (who.phase === "pending") return <StudyScaffold />;

  return (
    <section className="sy">
      <header className="sy-head">
        <span className="t-eyebrow">THE STUDY</span>
        <h1 className="sy-title t-display">Your desk</h1>
        <p className="t-narrative sy-lead">
          Everything here is about you and this account — not about the estate.
          It is the one room your colleagues never enter.
        </p>
      </header>

      <div className="sy-grid">
        {/* ================================================================ you */}
        <section className="sy-panel m-plate">
          <h2 className="t-eyebrow">YOU</h2>
          {who.phase === "failed" ? (
            <Failed
              what="your account"
              reason={who.reason}
              onRetry={who.retry}
              alone={false}
            />
          ) : (
            <You who={who.value} />
          )}
        </section>

        <PasskeyPanel onEcho={onEcho} />
        <PreferencePanel onEcho={onEcho} />
        <WalletPanel onEcho={onEcho} />
      </div>
    </section>
  );
}

/* ========================================================================== */
/*  YOU                                                                       */
/* ========================================================================== */

function You({ who }: { who: Who }) {
  /* A pair renders only where the record carries it. `full_name` is nullable on
     the wire and "Name: —" would read as a field this screen failed to load
     rather than one nobody filled in. There is no "with us since": `/auth/me`
     carries no created date, so the row is absent rather than dated. */
  const rows: [string, string][] = [];
  if (who.me.full_name !== null && who.me.full_name !== "") {
    rows.push(["Name", who.me.full_name]);
  }
  rows.push(["Email", who.me.email]);
  if (who.company !== null) rows.push(["Company", who.company]);
  rows.push(["Role", who.me.role]);

  return (
    <dl className="sy-facts">
      {rows.map(([label, value]) => (
        <div className="sy-fact" key={label}>
          <dt className="t-eyebrow">{label}</dt>
          <dd className="sy-fact-val">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/* ========================================================================== */
/*  PASSKEYS — the prerequisite for every certified act                       */
/* ========================================================================== */

function PasskeyPanel({ onEcho }: { onEcho: (msg: string) => void }) {
  const keys = useResource<PasskeyCredential[]>(listPasskeys);
  const [busy, setBusy] = useState(false);
  const [broke, setBroke] = useState<string | null>(null);
  const supported = isPasskeySupported();

  const retry = keys.phase === "pending" ? undefined : keys.retry;

  async function add(): Promise<void> {
    setBroke(null);
    setBusy(true);
    try {
      await registerPasskey();
      onEcho("added a passkey");
      /* Re-read rather than push what this screen thinks was created. The
         server owns the credential row, its id and its label, and a list
         assembled here would eventually disagree with the one that matters. */
      retry?.();
    } catch (thrown) {
      setBroke(reasonOf(thrown));
    } finally {
      setBusy(false);
    }
  }

  async function remove(key: PasskeyCredential): Promise<void> {
    setBroke(null);
    setBusy(true);
    try {
      await deletePasskey(key.id);
      onEcho(`removed the passkey ${key.label ?? key.id.slice(0, 8)}`);
      retry?.();
    } catch (thrown) {
      setBroke(reasonOf(thrown));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="sy-panel m-plate">
      <div className="sy-panel-head">
        <h2 className="t-eyebrow">SECURITY · PASSKEYS</h2>
        {keys.phase === "ready" && (
          <span className="t-mono sy-count">
            {keys.value.length} on this account
          </span>
        )}
      </div>

      {keys.phase === "pending" && (
        <Scaffold label="Your passkeys">
          <Lines n={3} />
        </Scaffold>
      )}

      {keys.phase === "failed" && (
        <Failed
          what="your passkeys"
          reason={keys.reason}
          onRetry={keys.retry}
          alone={false}
        />
      )}

      {keys.phase === "ready" &&
        (keys.value.length === 0 ? (
          /* L2, and the most consequential empty state in the product: with no
             passkey a tenant cannot complete a single ceremony, so every
             certified act in the estate is closed to them. */
          <Empty
            icon="key"
            title="You have no passkey, so no certified act can be completed."
            body="Releasing money, binding a system, changing what a colleague may decide alone — each of those asks your device to prove it is you, and there is nothing here for it to prove with. Adding one takes a moment and needs no password."
          />
        ) : (
          <ul className="sy-keys">
            {keys.value.map((key) => (
              <li className="sy-key" key={key.id}>
                <span className="sy-key-icon" aria-hidden="true">
                  <Icon name="key" size={15} />
                </span>
                <span className="sy-key-text">
                  {/* An unlabelled credential prints its id rather than a
                      invented device name — the server allows a null label and
                      "Unknown device" would be this file's guess. */}
                  <span className="sy-key-label">
                    {key.label ?? key.id.slice(0, 8)}
                  </span>
                  <span className="t-mono sy-key-meta">
                    added {day(key.created_at)}
                    {key.last_used_at !== null && ` · last used ${day(key.last_used_at)}`}
                  </span>
                </span>
                {/* Deleting is plain — one click, no ceremony. The safe
                    direction is never harder than the unsafe one. */}
                <button
                  className="sy-key-remove"
                  aria-label={`Remove ${key.label ?? key.id.slice(0, 8)}`}
                  disabled={busy || keys.value.length === 1}
                  title={
                    keys.value.length === 1
                      ? "Removing your only passkey would leave no way to complete a certified act"
                      : undefined
                  }
                  onClick={() => void remove(key)}
                >
                  <Icon name="close" size={13} />
                </button>
              </li>
            ))}
          </ul>
        ))}

      {supported ? (
        <button
          className="m-btn"
          data-rank="certified"
          disabled={busy}
          onClick={() => void add()}
        >
          <Icon name="key" size={14} />
          Add a passkey
        </button>
      ) : (
        /* No control at all rather than one that cannot work. */
        <p className="sy-note t-mono">
          This browser has no passkey support, so one cannot be added from here.
          Any device with a fingerprint reader, a face unlock or a security key
          will do it; the passkey belongs to your account, not to that machine.
        </p>
      )}

      {broke !== null && (
        <p className="sy-note t-mono" role="status">
          That did not go through, and nothing changed. {broke}
        </p>
      )}

      <p className="sy-note t-mono">
        A passkey is the key to every certified act — releasing money, signing,
        changing what a colleague is allowed to do. Adding one asks your device
        to prove it is you. We never see a password, because there isn&apos;t
        one.
      </p>
    </section>
  );
}

/* ========================================================================== */
/*  DENSITY AND NOTIFICATIONS — one store, two panels                         */
/* ========================================================================== */

function PreferencePanel({ onEcho }: { onEcho: (msg: string) => void }) {
  const prefs = useResource<Record<string, PreferenceValue>>(() => fetchPreferences());
  /* What this session has written, over what the server last said. A re-read
     would blink the panel back through its skeleton on every toggle; an
     optimistic value that only ever holds a *successful* write cannot
     disagree with the store. */
  const [written, setWritten] = useState<Record<string, unknown>>({});
  const [busy, setBusy] = useState(false);
  const [broke, setBroke] = useState<string | null>(null);

  if (prefs.phase === "pending") {
    return (
      <section className="sy-panel m-plate">
        <h2 className="t-eyebrow">DENSITY</h2>
        <Scaffold label="Your preferences">
          <Lines n={4} />
        </Scaffold>
      </section>
    );
  }

  if (prefs.phase === "failed") {
    return (
      <section className="sy-panel m-plate">
        <h2 className="t-eyebrow">DENSITY</h2>
        <Failed
          what="your preferences"
          reason={prefs.reason}
          onRetry={prefs.retry}
          alone={false}
        />
      </section>
    );
  }

  const stored = prefs.value;
  const densityRow = stored[DENSITY_KEY];
  const rawDensity = DENSITY_KEY in written ? written[DENSITY_KEY] : densityRow?.value;
  const density: Density | null =
    rawDensity === "novice" || rawDensity === "operator" ? rawDensity : null;
  /* The store's own flag, shown only when a row carries it. Nothing on the
     platform sets a density on anybody's behalf today, so this is expected to
     be false — which is a fact rather than a blank. */
  const learned = densityRow?.learned === true && !(DENSITY_KEY in written);

  const mirrorRow = stored[MIRROR_KEY];
  const rawMirror = MIRROR_KEY in written ? written[MIRROR_KEY] : mirrorRow?.value;
  /* Absent means ON. The mirror reads `value not in ("off", False)`, so an
     unchecked box for a preference nobody ever stated would tell a tenant they
     had turned off something that is running. */
  const mirrorOn = rawMirror !== "off" && rawMirror !== false;

  async function write(key: string, value: unknown, echo: string): Promise<void> {
    setBroke(null);
    setBusy(true);
    try {
      await writePreference(key, value);
      setWritten((previous) => ({ ...previous, [key]: value }));
      onEcho(echo);
    } catch (thrown) {
      setBroke(reasonOf(thrown));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {/* ============================================================ density */}
      <section className="sy-panel m-plate">
        <div className="sy-panel-head">
          <h2 className="t-eyebrow">DENSITY</h2>
          <span className="t-mono sy-count">{DENSITY_KEY}</span>
        </div>

        <div className="sy-density" role="radiogroup" aria-label="Density">
          {(["novice", "operator"] as const).map((d) => (
            <button
              key={d}
              role="radio"
              aria-checked={density === d}
              className="sy-choice"
              data-selected={density === d || undefined}
              disabled={busy}
              onClick={() => {
                void write(DENSITY_KEY, d, `set density to ${d}`);
                /* An observation, not a setting — it goes on the bus as
                   `learning.density_observed`. Fire-and-forget for the same
                   reason an echo is: losing it loses training data, never
                   work. */
                void observeDensity("study", d);
              }}
            >
              <span className="sy-choice-name">{d}</span>
              <span className="sy-choice-note">
                {d === "novice"
                  ? "Fewer things at once, and prose where a number would do."
                  : "Everything on one sheet, and the trace one flip away."}
              </span>
            </button>
          ))}
        </div>

        <p className="sy-note t-mono">
          {density === null ? (
            <>
              You have not chosen one. Nothing has been inferred for you either
              — the platform records that you picked a density on a surface, and
              nothing yet turns those observations into a setting.
            </>
          ) : learned ? (
            <>
              This value was <strong>learned</strong> rather than stated.
              Choosing here replaces it and clears the learned flag.
            </>
          ) : (
            <>
              You chose <strong>{density}</strong>. Stating a preference clears
              any learned value — the store&apos;s own rule.
            </>
          )}
        </p>

        {/* The gap, rendered rather than drawn over. The write is real and the
            reading half does not exist yet. */}
        <p className="sy-note t-mono">
          <Icon name="alert" size={12} />
          No room in the estate reads this yet. Every surface holds its own
          density while you are on it, and none of them asks the store what you
          said here. Your choice is recorded and it is not yet honoured.
        </p>
      </section>

      {/* ====================================================== notifications */}
      <section className="sy-panel m-plate">
        <h2 className="t-eyebrow">NOTIFICATIONS</h2>

        <ul className="sy-toggles">
          <li className="sy-toggle">
            <button
              className="sy-switch"
              role="switch"
              aria-checked={mirrorOn}
              aria-label="WhatsApp as a last resort"
              disabled={busy}
              onClick={() =>
                void write(
                  MIRROR_KEY,
                  mirrorOn ? "off" : "on",
                  `turned the whatsapp mirror ${mirrorOn ? "off" : "on"}`,
                )
              }
            >
              <span className="sy-switch-knob" />
            </button>
            <span className="sy-toggle-text">
              <span className="sy-toggle-label">WhatsApp as a last resort</span>
              <span className="sy-toggle-note">
                Used only when something is waiting on you and the Line has not
                reached you. A mirror message carries a sentence and never a
                button — nothing can be approved from it.
              </span>
              <span className="t-mono sy-toggle-key">
                {MIRROR_KEY}
                {mirrorRow === undefined && " · never stated, and on by default"}
              </span>
            </span>
          </li>

          {/* Where two switches were. The keys are valid and nothing reads
              them, so a toggle would be a setting we kept and ignored. */}
          {UNREAD_NOTIFY.map((absent) => (
            <li className="sy-toggle" key={absent.key} data-absent>
              <span className="sy-toggle-mark" aria-hidden="true">
                <span className="m-lamp" />
              </span>
              <span className="sy-toggle-text">
                <span className="sy-toggle-label">{absent.label}</span>
                <span className="sy-toggle-note">{absent.why}</span>
                <span className="t-mono sy-toggle-key">{absent.key}</span>
              </span>
            </li>
          ))}
        </ul>

        {broke !== null && (
          <p className="sy-note t-mono" role="status">
            That did not go through, and nothing changed. {broke}
          </p>
        )}
      </section>
    </>
  );
}

/* ========================================================================== */
/*  BILLING AND WALLET — the panel that has to be kind                        */
/* ========================================================================== */

function WalletPanel({ onEcho }: { onEcho: (msg: string) => void }) {
  const billing = useResource<Billing>(async () => {
    const [balance, subscription] = await Promise.all([
      fetchBalance(),
      fetchSubscription(),
    ]);
    return {
      balance: balance as Record<string, unknown>,
      subscription: subscription as Record<string, unknown>,
    };
  });

  return (
    <section className="sy-panel sy-wallet m-plate">
      <div className="sy-panel-head">
        <h2 className="t-eyebrow">BILLING &amp; WALLET</h2>
        {billing.phase === "ready" && (
          <span className="m-chip sy-plan">
            {textAt(billing.value.subscription, "account_model")?.replace(/_/g, " ") ??
              "account"}
          </span>
        )}
      </div>

      {billing.phase === "pending" && (
        <Scaffold label="Your wallet">
          <Bar width="md" tall />
          <Lines n={3} />
        </Scaffold>
      )}

      {billing.phase === "failed" && (
        <Failed
          what="your wallet"
          reason={billing.reason}
          onRetry={billing.retry}
          alone={false}
        />
      )}

      {billing.phase === "ready" && <Wallet billing={billing.value} onEcho={onEcho} />}

      <hr className="m-rule-fade" />

      {/* The ladder, always visible. Not revealed once a rung is reached. */}
      <div className="sy-ladder">
        <div className="sy-ladder-head">
          <span className="t-eyebrow">IF CREDIT RUNS OUT</span>
          <span className="t-mono sy-ladder-note">
            shown always, so it is never a surprise
          </span>
        </div>
        <ol className="sy-rungs">
          {DUNNING.map((rung) => (
            <li className="sy-rung" key={rung.label}>
              <span className="sy-rung-mark" aria-hidden="true" />
              <span className="sy-rung-text">
                <span className="sy-rung-label">{rung.label}</span>
                <span className="sy-rung-what">{rung.what}</span>
              </span>
            </li>
          ))}
        </ol>
        <p className="sy-note t-mono">
          Nothing is ever deleted for non-payment, and the record stays complete
          at every rung. A full export is yours to take at any time, including
          after a suspension.
        </p>
        {/* No rung is marked. Which one you are on is a fact about the company
            and this desk does not read it — saying so is cheaper than marking
            the wrong rung, and far cheaper than marking "current" by default. */}
        <p className="sy-note t-mono">
          <Icon name="alert" size={12} />
          None of these is marked as yours. Your standing is published with the
          estate rather than here, and this screen will not guess which rung you
          are on from a balance.
        </p>
      </div>
    </section>
  );
}

function Wallet({
  billing,
  onEcho,
}: {
  billing: Billing;
  onEcho: (msg: string) => void;
}) {
  const total = numberAt(billing.balance, "total_available");
  const subscription = objectAt(billing.subscription, "subscription");

  /* Every bucket the endpoint sends, and only the ones it sends. A bucket that
     is absent renders as nothing — never as a zero balance, which is the one
     figure on this panel that would change what a person does next. */
  const buckets: [string, number, string | null][] = [];
  for (const [label, key, expiry] of [
    ["Daily", "daily_credits", "daily_expires_at"],
    ["Topped up", "wallet_balance", "wallet_expires_at"],
    ["Subscription", "subscription_credits", "sub_credits_expire_at"],
    ["Bonus", "subscription_bonus_credits", "sub_credits_expire_at"],
  ] as const) {
    const value = numberAt(billing.balance, key);
    if (value !== null) buckets.push([label, value, day(textAt(billing.balance, expiry))]);
  }

  return (
    <>
      <div className="sy-balance">
        {/* Credits, in the endpoint's own word. There is no rupee sign: the
            body carries buckets of credits and stamps no currency on any of
            them, and a bare figure in a rupee-shaped app is read as rupees
            whether or not anybody said so. */}
        {total !== null && (
          <span className="t-figure">
            {grouped(total)}
            <span className="sy-balance-unit">credits</span>
          </span>
        )}
        {subscription !== null && (
          <span className="sy-balance-side">
            <span
              className="m-lamp"
              data-positive={textAt(subscription, "status") === "active" || undefined}
            />
            <span className="t-mono">
              {textAt(subscription, "status") ?? "subscription"}
            </span>
          </span>
        )}
      </div>

      {buckets.length > 0 && (
        <dl className="sy-facts">
          {buckets.map(([label, value, expires]) => (
            <div className="sy-fact" key={label}>
              <dt className="t-eyebrow">{label}</dt>
              <dd className="sy-fact-val">
                {grouped(value)}
                {expires !== null && (
                  <span className="t-mono sy-count"> until {expires}</span>
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {subscription !== null && <Plan subscription={subscription} />}

      {/* There is no runway line. It was `balance / (weeklyBurn / 7)` and
          nothing anywhere reports a burn rate, so the denominator was invented
          and the answer read as a measurement (§7.1). */}
      <p className="sy-note t-mono">
        How long this lasts depends on what your colleagues do next, and nothing
        on the platform measures a burn rate yet — so there is no days-remaining
        figure here rather than one worked out from a number nobody recorded.
      </p>

      <div className="sy-panel-acts">
        {/* Topping up is a payment flow with a gateway on the other end of it,
            and it is not this surface's — the old buttons echoed and opened
            nothing. */}
        <button
          className="m-btn"
          data-rank="quiet"
          onClick={() => onEcho("read how topping up works")}
        >
          <Icon name="ledger" size={13} />
          How topping up works
        </button>
      </div>
    </>
  );
}

/**
 * The subscription line, assembled from whatever the row carries.
 *
 * Each clause is present only where its field is, so the line shortens rather
 * than growing dangling labels — a bare "Tier" with nothing after it reads as a
 * value this screen failed to load. The fee prints **with no currency and the
 * sentence saying none was stated**: the tier table holds a bare number, and a
 * figure in a rupee-shaped app is read as rupees whether or not anybody said so
 * (the idiom `certified.payment` ships and `tests/tray_cost.test.tsx` pins).
 */
function Plan({ subscription }: { subscription: Record<string, unknown> }) {
  const tier = textAt(subscription, "plan_tier") ?? numberAt(subscription, "plan_tier");
  const next = day(textAt(subscription, "next_billing_date"));
  const fee = numberAt(subscription, "monthly_fee");

  const clauses: string[] = [];
  if (tier !== null) clauses.push(`Tier ${tier}`);
  if (next !== null) clauses.push(`next billed ${next}`);
  if (fee !== null) clauses.push(`${grouped(fee)} a month`);
  if (clauses.length === 0) return null;

  return (
    <p className="sy-runway t-mono">
      {clauses.join(" · ")}
      {fee !== null && ". The platform states no currency on that figure."}
    </p>
  );
}

/* ========================================================================== */
/*  THE PENDING STATE                                                         */
/* ========================================================================== */

/**
 * The desk's own structure with the words not yet in it (D7 §3.1). No spinner:
 * this is one of the seventeen.
 *
 * The plates are drawn first and the bars go inside them — `vh-skeleton`'s
 * ground is a ~6/255 delta on the raw canvas, so a bar on the page background
 * draws nothing at all.
 */
function StudyScaffold() {
  return (
    <section className="sy">
      <Scaffold label="Your desk">
        <header className="sy-head">
          <Bar width="xs" />
          <Bar width="sm" tall />
        </header>
        <div className="sy-grid">
          {[0, 1, 2, 3].map((i) => (
            <section className="sy-panel m-plate" key={i}>
              <Bar width="xs" />
              <Lines n={4} />
            </section>
          ))}
        </div>
      </Scaffold>
    </section>
  );
}
