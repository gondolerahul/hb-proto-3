import type { ReactNode } from "react";

import { Icon } from "../Icon";
import { resolve } from "../../manifest/registry";
import type { WireComponent } from "../../manifest/schema";
import type { CertifiedType } from "./acts";
import "./certified.css";

/**
 * The ten certified components (D3 §6.2) — restored for R-4 part C, C4.
 *
 * Four rules govern all of them, and three of the four are why this file looks
 * more constrained than a surface:
 *
 * 1. **Context is not an input.** These take `{ component }` and nothing else —
 *    no `renderer`, no `density`. The property L5 needs is that a certified
 *    block is identical wherever it appears, and the strongest form of that is
 *    not "the S and C outputs happen to be equal" but "there is no parameter
 *    they could differ on". `tests/certified.test.tsx` states it both ways.
 * 2. **Deterministic.** Props in, identical DOM out. No clock, no randomness,
 *    and — the one that bites — **no locale formatting**: `toLocaleString` on
 *    a payment would reformat money with the machine's ICU data, which makes a
 *    golden environment-sensitive and, far worse, silently regroups a figure
 *    the owner is about to release. `groupDigits` below is pure.
 * 3. **Never invent a number** (DESIGN_CONTRACT §7.1). An absent prop renders
 *    *nothing*. `certified.payment` carries this furthest: `currency` is
 *    nullable in the registry, and a null one prints no symbol and says the
 *    currency was not stated, because a bare 84,200 beside a rupee-shaped app
 *    is read as rupees whether or not anyone said so.
 * 4. **The gold budget** (art bible §2.1). Prose is `--fg`; gold is the struck
 *    seal, the eyebrow and the one primary action. A certified block is the
 *    sanctioned use of gold, which is exactly why it must not be *made of* it.
 *
 * The a11y role and the accessible name are read off the registry entry rather
 * than chosen here (D3 §3.1 again): the same JSON that validates the component
 * says what it announces itself as, so the two cannot drift.
 *
 * Actions surface as `data-action` buttons and are wired from *outside* the
 * block — click delegation on the container. That keeps the display a pure
 * function of props, which is what makes the goldens worth having.
 */

export interface CertifiedProps {
  component: WireComponent;
}

/**
 * A prop, or null — and an empty string is null.
 *
 * The registry types several of these as required strings, so a server with
 * nothing to say sends `""` rather than omitting the key. Rendering that as a
 * labelled row with an empty value is the §7.1 failure in its quietest form: a
 * fact block that says "Command:" and then nothing looks like a truncation
 * bug, where rendering neither says the honest thing.
 */
function prop(component: WireComponent, key: string): string | null {
  const value = (component.props ?? {})[key];
  if (value === null || value === undefined) return null;
  const text = String(value);
  return text === "" ? null : text;
}

/**
 * Three-digit grouping, by hand. See rule 2 above — this exists so a figure on
 * a payment card cannot change shape between two machines.
 *
 * It groups and does nothing else: no rounding, no padding to two decimals, no
 * currency symbol. `842000.5` renders as `842,000.5` rather than `842,000.50`,
 * because the second is a digit the wire did not send and this is the one card
 * in the product where a client that quietly disagrees with the ledger is a
 * defect rather than a nicety.
 */
export function groupDigits(value: string): string {
  const negative = value.startsWith("-");
  const bare = negative ? value.slice(1) : value;
  const [whole, ...rest] = bare.split(".");
  if (whole === undefined || !/^\d+$/.test(whole)) return value;
  let out = "";
  for (let i = 0; i < whole.length; i += 1) {
    if (i > 0 && (whole.length - i) % 3 === 0) out += ",";
    out += whole[i]!;
  }
  const fraction = rest.length > 0 ? `.${rest.join(".")}` : "";
  return `${negative ? "-" : ""}${out}${fraction}`;
}

/** The two components that are the ceremony rather than an act inside it. */
const CEREMONY_TYPES = new Set<string>([
  "certified.step-up",
  "certified.second-channel-wait",
]);

interface CertifiedAction {
  label: string;
  /** `certified` is the gold one. Exactly one per block, or none. */
  rank: "certified" | "quiet";
}

function a11yFor(
  type: CertifiedType,
  component: WireComponent,
): { role?: string; label?: string } {
  // The ceremony pair declares `role: "dialog"`, but the dialog is the modal
  // that HOSTS them (`StepUpCeremony`) — announcing a second one nested inside
  // the first would put a screen reader in two dialogs at once.
  if (CEREMONY_TYPES.has(type)) return {};
  const resolution = resolve(type);
  if (resolution.kind !== "ok") return {};
  const { role, label_from } = resolution.entry.a11y;
  const key = label_from === null ? null : label_from.replace(/^props\./, "");
  const label = key === null ? null : prop(component, key);
  if (label === null) return {};
  return { role, label };
}

/**
 * The shared frame: seal, eyebrow, hairline, body, actions.
 *
 * `m-plate` and not `m-glass`, deliberately. The Tray draws its certified card
 * in gold-tinted glass because it sits in a list of cards; a certified block
 * that may also appear alone inside the ceremony must be the most *solid*
 * object on screen at the moment money moves. Glass would let the estate show
 * through the one surface that has to own the decision.
 */
function CertifiedFrame({
  type,
  eyebrow,
  component,
  children,
  actions,
}: {
  type: CertifiedType;
  eyebrow: string;
  component: WireComponent;
  children: ReactNode;
  actions?: readonly CertifiedAction[];
}) {
  const { role, label } = a11yFor(type, component);
  return (
    <section
      className="ce m-plate"
      data-part="certified"
      data-certified-type={type}
      role={role}
      aria-label={label}
    >
      <header className="ce-head">
        <span className="m-medallion ce-seal" aria-hidden="true">
          <Icon name="check" size={9} />
        </span>
        <span className="t-eyebrow" data-certified>
          {eyebrow}
        </span>
        {/* Never colour alone: the gold seal is the fast read, this is the
            correct one, and it is the only place the word appears in full. */}
        <span className="vh-sr-only">Certified act</span>
      </header>

      <hr className="m-rule-fade ce-rule" />

      <div className="ce-body">{children}</div>

      {actions !== undefined && actions.length > 0 && (
        <footer className="ce-acts">
          {actions.map((action) => (
            <button
              key={action.label}
              type="button"
              className="m-btn ce-act"
              data-rank={action.rank}
              data-action={action.label}
            >
              {action.rank === "certified" && <Icon name="key" size={14} />}
              {action.label}
            </button>
          ))}
        </footer>
      )}
    </section>
  );
}

/** The fact block. `m-well` because this is where data lives (RD-5). */
function Facts({ rows }: { rows: readonly [string, string | null][] }) {
  const present = rows.filter((row): row is [string, string] => row[1] !== null);
  if (present.length === 0) return null;
  return (
    <div className="m-well ce-facts" data-deep>
      <dl>
        {present.map(([key, value]) => (
          <div className="ce-fact" key={key}>
            <dt className="t-eyebrow">{key}</dt>
            <dd className="ce-fact-v t-mono">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Prose({ text }: { text: string | null }) {
  if (text === null) return null;
  return <p className="ce-prose t-narrative">{text}</p>;
}

// ── 1 · approval ─────────────────────────────────────────────────────────────

export function CertifiedApproval({ component }: CertifiedProps) {
  const tier = prop(component, "tier");
  return (
    <CertifiedFrame
      type="certified.approval"
      component={component}
      eyebrow={tier === null ? "APPROVAL" : `APPROVAL · ${tier}`}
      actions={[
        { label: "approve", rank: "certified" },
        { label: "decline", rank: "quiet" },
      ]}
    >
      <Prose text={prop(component, "summary")} />
      <Facts
        rows={[
          ["Checkpoint", prop(component, "checkpoint_key")],
          ["Approval", prop(component, "approval_id")],
        ]}
      />
    </CertifiedFrame>
  );
}

// ── 2 · payment ──────────────────────────────────────────────────────────────

export function CertifiedPayment({ component }: CertifiedProps) {
  const tier = prop(component, "tier");
  const amount = prop(component, "amount");
  const currency = prop(component, "currency");
  return (
    <CertifiedFrame
      type="certified.payment"
      component={component}
      eyebrow={tier === null ? "PAYMENT" : `PAYMENT · ${tier}`}
      actions={[
        { label: "approve", rank: "certified" },
        { label: "decline", rank: "quiet" },
      ]}
    >
      <Prose text={prop(component, "summary")} />

      {amount !== null && (
        <p className="ce-amount">
          {/* Gold text is sanctioned here and nowhere else on this block: the
              figure is both "certified" and "needs you", which is the whole of
              the §2.1 budget in one number. */}
          {currency !== null && <span className="ce-amount-cur">{currency}</span>}
          <output className="ce-amount-fig t-figure m-gold-text">
            {groupDigits(amount)}
          </output>
        </p>
      )}

      {amount !== null && currency === null && (
        // §7.1 forbids inventing the number; §7.4 requires rendering the gap.
        // A bare figure in a rupee-shaped app is read as rupees by default, so
        // the absence has to be said rather than left to be assumed.
        <p className="ce-gap t-mono">
          The currency was not stated on this approval.
        </p>
      )}

      <Facts
        rows={[
          ["Checkpoint", prop(component, "checkpoint_key")],
          ["Approval", prop(component, "approval_id")],
        ]}
      />
    </CertifiedFrame>
  );
}

// ── 3 · consent ──────────────────────────────────────────────────────────────

/**
 * The consent asymmetry, made structural (D3 §3.4). Granting is a ceremony;
 * revoking is one plain control with no seal, no gold and no gate — a revoke
 * that demands gravitas is a revoke people abandon halfway, and the safe
 * direction must never be harder than the unsafe one.
 */
export function CertifiedConsent({ component }: CertifiedProps) {
  if (prop(component, "direction") !== "grant") {
    return (
      <div className="ce-revoke m-plate" data-part="consent-revoke">
        <Prose text={prop(component, "summary")} />
        <button type="button" className="m-btn" data-rank="quiet" data-action="revoke">
          revoke
        </button>
      </div>
    );
  }
  return (
    <CertifiedFrame
      type="certified.consent"
      component={component}
      eyebrow="CONSENT"
      actions={[{ label: "grant", rank: "certified" }]}
    >
      <Prose text={prop(component, "summary")} />
      <Facts
        rows={[
          ["Channel", prop(component, "channel")],
          ["Purpose", prop(component, "purpose")],
        ]}
      />
    </CertifiedFrame>
  );
}

// ── 4 · autonomy change ──────────────────────────────────────────────────────

export function CertifiedAutonomyChange({ component }: CertifiedProps) {
  const name = prop(component, "entity_name");
  const from = prop(component, "from_band");
  const to = prop(component, "to_band");
  return (
    <CertifiedFrame
      type="certified.autonomy-change"
      component={component}
      eyebrow="AUTONOMY"
      actions={[
        { label: "confirm", rank: "certified" },
        { label: "keep as is", rank: "quiet" },
      ]}
    >
      <Prose text={prop(component, "summary")} />
      {name !== null && <h3 className="ce-title t-display">{name}</h3>}
      {from !== null && to !== null && (
        <p className="ce-band">
          <span className="m-chip ce-band-from">{from}</span>
          <Icon name="forward" size={13} className="ce-band-arrow" />
          <span className="m-chip ce-band-to" data-selected>
            {to}
          </span>
          <span className="vh-sr-only">
            autonomy band {from} raised to {to}
          </span>
        </p>
      )}
      <Facts rows={[["Colleague", prop(component, "entity_id")]]} />
    </CertifiedFrame>
  );
}

// ── 5 · connector binding ────────────────────────────────────────────────────

export function CertifiedConnectorBinding({ component }: CertifiedProps) {
  const name = prop(component, "connector_name");
  return (
    <CertifiedFrame
      type="certified.connector-binding"
      component={component}
      eyebrow="CONNECTOR"
      actions={[{ label: "bind", rank: "certified" }]}
    >
      {name !== null && <h3 className="ce-title t-display">{name}</h3>}
      <Prose text={prop(component, "summary")} />
      <Facts rows={[["Connector", prop(component, "connector_key")]]} />
    </CertifiedFrame>
  );
}

// ── 6 · mastering declaration ────────────────────────────────────────────────

export function CertifiedMasteringDeclaration({ component }: CertifiedProps) {
  const def = prop(component, "def_name");
  return (
    <CertifiedFrame
      type="certified.mastering-declaration"
      component={component}
      eyebrow="MASTERING"
      actions={[{ label: "apply", rank: "certified" }]}
    >
      {def !== null && <h3 className="ce-title t-display">{def}</h3>}
      <Prose text={prop(component, "summary")} />
      <Facts
        rows={[
          ["Connector", prop(component, "connector_key")],
          ["Direction", prop(component, "direction")],
        ]}
      />
    </CertifiedFrame>
  );
}

// ── 7 · provider opt-in ──────────────────────────────────────────────────────

export function CertifiedProviderOptIn({ component }: CertifiedProps) {
  const provider = prop(component, "provider");
  return (
    <CertifiedFrame
      type="certified.provider-opt-in"
      component={component}
      eyebrow="MODEL PROVIDER"
      actions={[{ label: "opt in", rank: "certified" }]}
    >
      {provider !== null && <h3 className="ce-title t-display">{provider}</h3>}
      <Prose text={prop(component, "summary")} />
      <Facts rows={[["Disclosure", prop(component, "disclosure_version")]]} />
    </CertifiedFrame>
  );
}

// ── 8 · strategy resolution ──────────────────────────────────────────────────

export function CertifiedStrategyResolution({ component }: CertifiedProps) {
  const title = prop(component, "title");
  return (
    <CertifiedFrame
      type="certified.strategy-resolution"
      component={component}
      eyebrow="RESOLUTION"
      actions={[{ label: "adopt", rank: "certified" }]}
    >
      {title !== null && <h3 className="ce-title t-display">{title}</h3>}
      <Prose text={prop(component, "summary")} />
      <Facts rows={[["Proposition", prop(component, "resolution_id")]]} />
    </CertifiedFrame>
  );
}

// ── 9 · step-up ──────────────────────────────────────────────────────────────

/**
 * The statement the ceremony asks you to confirm. Its one action is delegated
 * — `StepUpCeremony` listens for `data-action="use passkey"` on its own
 * container — so this stays a pure function of props while the ceremony around
 * it holds all the state a WebAuthn call needs.
 */
export function CertifiedStepUp({ component }: CertifiedProps) {
  const tier = prop(component, "tier");
  return (
    <CertifiedFrame
      type="certified.step-up"
      component={component}
      eyebrow={tier === null ? "PROVE IT IS YOU" : `PROVE IT IS YOU · ${tier}`}
      actions={[{ label: "use passkey", rank: "certified" }]}
    >
      <Prose text={prop(component, "command_summary")} />
      <Facts rows={[["Command", prop(component, "command_ref")]]} />
    </CertifiedFrame>
  );
}

// ── 10 · second-channel wait ─────────────────────────────────────────────────

/**
 * The T3 leg's statement. No action: the nonce arrives on a *second* registered
 * channel and is typed back into the ceremony, and drawing a control here would
 * imply this block could send it.
 */
export function CertifiedSecondChannelWait({ component }: CertifiedProps) {
  return (
    <CertifiedFrame
      type="certified.second-channel-wait"
      component={component}
      eyebrow="SECOND CHANNEL"
    >
      <Prose text={prop(component, "command_summary")} />
      <Facts
        rows={[
          ["Waiting on", prop(component, "channel")],
          ["Command", prop(component, "command_ref")],
        ]}
      />
    </CertifiedFrame>
  );
}

/**
 * The set. It is TEN, it matches `CERTIFIED_ACTS` key for key, and
 * `tests/certified.test.tsx` fails if an eleventh appears in either — the
 * registry, the act table and the implementations are three views of one list
 * and a component that exists in only two of them is a component nobody gated.
 */
export const CERTIFIED_IMPLEMENTATIONS: Record<
  CertifiedType,
  (props: CertifiedProps) => JSX.Element
> = {
  "certified.approval": CertifiedApproval,
  "certified.payment": CertifiedPayment,
  "certified.consent": CertifiedConsent,
  "certified.autonomy-change": CertifiedAutonomyChange,
  "certified.connector-binding": CertifiedConnectorBinding,
  "certified.mastering-declaration": CertifiedMasteringDeclaration,
  "certified.provider-opt-in": CertifiedProviderOptIn,
  "certified.strategy-resolution": CertifiedStrategyResolution,
  "certified.step-up": CertifiedStepUp,
  "certified.second-channel-wait": CertifiedSecondChannelWait,
};
