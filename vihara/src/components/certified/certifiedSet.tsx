/**
 * The ten certified components (SUB T6, D3 §6.2) — derived from the tier
 * gate, not chosen (D3 §3.1). Rules they all keep:
 *
 * - **Deterministic.** Props in, identical DOM out — no generative text,
 *   no clock, no randomness. The goldens depend on it and L5 requires it.
 * - **Never lazy.** These ship in the shell bundle (D7 §3.3): a tray must
 *   not wait on a chunk.
 * - **The gold budget** (art bible §2.1/§11): prose renders in --fg; gold
 *   is the seal, the rule and the eyebrow — the ceremony's chrome, never
 *   its text.
 * - **The consent asymmetry** (D3 §3.4): granting consent is a ceremony;
 *   revoking is deliberately plain — a revoke that demands gravitas is a
 *   revoke people abandon halfway, and the safe direction must never be
 *   harder than the unsafe one.
 *
 * Actions (approve/decline/confirm) surface as data-action buttons; the
 * *wiring* to the gated endpoints is DRIVER/STEWARD work — a G0 certified
 * component renders the decision, it does not yet take it.
 */
import type { ReactNode } from "react";

import type { ComponentProps } from "../primitive/basics";

function prop(props: Record<string, unknown> | undefined, key: string): string {
  const value = (props ?? {})[key];
  if (value === null || value === undefined) return "";
  return String(value);
}

function CertifiedFrame({
  type,
  eyebrow,
  children,
  actions,
}: {
  type: string;
  eyebrow: string;
  children: ReactNode;
  actions?: readonly string[];
}): JSX.Element {
  return (
    <section className="vh-certified" data-part="certified" data-certified-type={type}>
      <header className="vh-certified-eyebrow">
        <span aria-hidden className="vh-certified-seal" />
        <span>{eyebrow}</span>
      </header>
      <div className="vh-certified-body">{children}</div>
      {actions !== undefined && actions.length > 0 && (
        <footer className="vh-certified-actions">
          {actions.map((action) => (
            <button key={action} type="button" data-action={action}>
              {action}
            </button>
          ))}
        </footer>
      )}
    </section>
  );
}

export function CertifiedApproval({ component }: ComponentProps): JSX.Element {
  const props = component.props;
  return (
    <CertifiedFrame
      type="certified.approval"
      eyebrow={`Approval · ${prop(props, "tier")}`}
      actions={["approve", "decline"]}
    >
      <p>{prop(props, "summary")}</p>
      <span className="vh-mono">{prop(props, "checkpoint_key")}</span>
    </CertifiedFrame>
  );
}

export function CertifiedPayment({ component }: ComponentProps): JSX.Element {
  const props = component.props;
  const currency = prop(props, "currency");
  return (
    <CertifiedFrame
      type="certified.payment"
      eyebrow={`Payment · ${prop(props, "tier")}`}
      actions={["approve", "decline"]}
    >
      <p>{prop(props, "summary")}</p>
      <output className="vh-figure">
        {currency !== "" ? `${currency} ` : ""}
        {prop(props, "amount")}
      </output>
      <span className="vh-mono">{prop(props, "checkpoint_key")}</span>
    </CertifiedFrame>
  );
}

export function CertifiedConsent({ component }: ComponentProps): JSX.Element {
  const props = component.props;
  const granting = prop(props, "direction") === "grant";
  if (!granting) {
    // The asymmetry, visible: no seal, no ceremony, one plain act.
    return (
      <div className="vh-consent-revoke" data-part="consent-revoke">
        <p>{prop(props, "summary")}</p>
        <button type="button" data-action="revoke">
          revoke
        </button>
      </div>
    );
  }
  return (
    <CertifiedFrame
      type="certified.consent"
      eyebrow="Consent"
      actions={["grant"]}
    >
      <p>{prop(props, "summary")}</p>
      <span className="vh-mono">
        {prop(props, "channel")} · {prop(props, "purpose")}
      </span>
    </CertifiedFrame>
  );
}

export function CertifiedAutonomyChange({
  component,
}: ComponentProps): JSX.Element {
  const props = component.props;
  return (
    <CertifiedFrame
      type="certified.autonomy-change"
      eyebrow="Autonomy"
      actions={["confirm", "keep as is"]}
    >
      <p>{prop(props, "summary")}</p>
      <span className="vh-mono">
        {prop(props, "entity_name")}: {prop(props, "from_band")} →{" "}
        {prop(props, "to_band")}
      </span>
    </CertifiedFrame>
  );
}

export function CertifiedConnectorBinding({
  component,
}: ComponentProps): JSX.Element {
  const props = component.props;
  return (
    <CertifiedFrame
      type="certified.connector-binding"
      eyebrow="Connector"
      actions={["bind"]}
    >
      <p>{prop(props, "summary")}</p>
      <span className="vh-mono">{prop(props, "connector_name")}</span>
    </CertifiedFrame>
  );
}

export function CertifiedMasteringDeclaration({
  component,
}: ComponentProps): JSX.Element {
  const props = component.props;
  return (
    <CertifiedFrame
      type="certified.mastering-declaration"
      eyebrow="Mastering"
      actions={["apply"]}
    >
      <p>{prop(props, "summary")}</p>
      <span className="vh-mono">
        {prop(props, "def_name")} ← {prop(props, "connector_key")} (
        {prop(props, "direction")})
      </span>
    </CertifiedFrame>
  );
}

export function CertifiedProviderOptIn({
  component,
}: ComponentProps): JSX.Element {
  const props = component.props;
  return (
    <CertifiedFrame
      type="certified.provider-opt-in"
      eyebrow="Model provider"
      actions={["opt in"]}
    >
      <p>{prop(props, "summary")}</p>
      <span className="vh-mono">
        {prop(props, "provider")} · disclosure {prop(props, "disclosure_version")}
      </span>
    </CertifiedFrame>
  );
}

export function CertifiedStrategyResolution({
  component,
}: ComponentProps): JSX.Element {
  const props = component.props;
  return (
    <CertifiedFrame
      type="certified.strategy-resolution"
      eyebrow="Resolution"
      actions={["adopt"]}
    >
      <h3>{prop(props, "title")}</h3>
      <p>{prop(props, "summary")}</p>
    </CertifiedFrame>
  );
}

export function CertifiedStepUp({ component }: ComponentProps): JSX.Element {
  const props = component.props;
  return (
    <CertifiedFrame
      type="certified.step-up"
      eyebrow={`Prove it is you · ${prop(props, "tier")}`}
      actions={["use passkey"]}
    >
      <p>{prop(props, "command_summary")}</p>
      <span className="vh-mono">{prop(props, "command_ref")}</span>
    </CertifiedFrame>
  );
}

export function CertifiedSecondChannelWait({
  component,
}: ComponentProps): JSX.Element {
  const props = component.props;
  return (
    <CertifiedFrame type="certified.second-channel-wait" eyebrow="Second channel">
      <p>{prop(props, "command_summary")}</p>
      <span className="vh-mono">
        waiting on {prop(props, "channel")} · {prop(props, "command_ref")}
      </span>
    </CertifiedFrame>
  );
}

export const CERTIFIED_IMPLEMENTATIONS = {
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
} as const;
