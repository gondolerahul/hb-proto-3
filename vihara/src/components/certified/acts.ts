/**
 * The certified act table — R-4 part C (06_r4_wiring.md §6).
 *
 * There are ten certified components and there is one row here per component,
 * because the set is *derived from the tier gate, not chosen* (D3 §3.1). What
 * each row adds to the registry entry is the thing the registry cannot say:
 * **what the server actually does when the act is taken today.**
 *
 * That distinction is the whole of part C. Six surfaces currently draw a
 * `data-rank="certified"` control, print "it will ask for your passkey", and
 * mutate local state. Three of those paths will 403 the moment they are wired.
 * Two will not — and §6 is explicit that *the two that silently succeed are the
 * dangerous ones*, because a certified control that completes without a
 * ceremony teaches the owner that the ceremony is decorative. Once they have
 * learnt that, the ceremony that does fire is an obstacle rather than a moment.
 *
 * So a gate is one of three things, and the difference is behavioural:
 *
 * - **`server`** — a named handler-body `enforce_tier`/`enforce_kind` call. The
 *   act runs optimistically; a `step_up_required` 403 is the ceremony's entry
 *   point (C3), not an error.
 * - **`absent`** — the endpoint does not exist. The act **does not run and does
 *   not echo**: there is nothing to write to, and pretending otherwise is the
 *   exact fraud §6 names. DESIGN_CONTRACT §7.4 — render the gap, never draw a
 *   working feature over a known absence.
 * - **`ceremony`** — the component *is* the ceremony. Not runnable; excluded
 *   from `RunnableCertifiedType` so `useCertifiedAct` cannot be handed one.
 *
 * `enforcedBy` names the backend line, so every `server` claim here is
 * checkable by opening one file rather than by trusting this comment.
 *
 * **Hiring is deliberately absent from this table.** The Talent Office draws
 * hire-from-template as a certified act with a passkey note; it is not one.
 * `talent.hireFromTemplate` forces `autonomy_level: "A1"` and `POST
 * /ai/entities` carries no `enforce_*` at all — only a *raise* is gated
 * (`certified.autonomy-change` below). That is the second silent success, and
 * the fix is that no act kind exists for it: a later round wiring the Talent
 * Office finds nothing to pass and has to confront the claim.
 */

export type Gate =
  | {
      kind: "server";
      /** `METHOD /path` exactly as the backend router declares it. */
      call: string;
      /** Where the gate is, so the claim can be verified in one open. */
      enforcedBy: string;
    }
  | {
      kind: "absent";
      /** What a person is told. A sentence, not a code — they did nothing wrong. */
      why: string;
      /** The work that closes it, for the report and the Undercroft. */
      closedBy: string;
    }
  | { kind: "ceremony" };

export interface CertifiedActEntry {
  /** The verb on the control, lowercase — the echo and the button share it. */
  verb: string;
  gate: Gate;
}

export const CERTIFIED_ACTS = {
  "certified.approval": {
    verb: "respond",
    gate: {
      kind: "server",
      call: "POST /ai/approvals/{approval_id}/respond",
      enforcedBy: "enforce_tier(intent_for_approval(...)) — ai/router.py respond_to_approval",
    },
  },
  "certified.payment": {
    verb: "respond",
    gate: {
      kind: "server",
      call: "POST /ai/approvals/{approval_id}/respond",
      enforcedBy: "enforce_tier(intent_for_approval(...)) — ai/router.py respond_to_approval",
    },
  },
  /* Only a *raise* is gated, and the gate reads the stored band before the
     incoming one — so this act's 403 depends on the payload, not the path. */
  "certified.autonomy-change": {
    verb: "confirm",
    gate: {
      kind: "server",
      call: "PUT /ai/entities/{entity_id}",
      enforcedBy: "raises_autonomy(...) then enforce_tier(AUTONOMY_RAISE) — ai/router.py update_entity",
    },
  },
  "certified.connector-binding": {
    verb: "bind",
    gate: {
      kind: "server",
      call: "POST /ai/connectors/{connector_id}/bind",
      enforcedBy: "enforce_kind(CONNECTOR_BINDING) — ai/connectors/router.py bind",
    },
  },
  "certified.mastering-declaration": {
    verb: "apply",
    gate: {
      kind: "server",
      call: "POST /ai/connectors/master/{def_name}/apply",
      enforcedBy: "enforce_kind(CONNECTOR_BINDING) — ai/connectors/router.py apply_master_migration",
    },
  },
  "certified.provider-opt-in": {
    verb: "opt in",
    gate: {
      kind: "server",
      call: "POST /ai/intelligence/providers/{provider}/opt-in",
      enforcedBy: "enforce_kind(BINDING_CHANGE) — ai/intelligence/api.py opt_in_provider",
    },
  },
  "certified.strategy-resolution": {
    verb: "adopt",
    gate: {
      kind: "server",
      call: "POST /ai/strategy/adopt",
      enforcedBy: "enforce_kind(STRATEGY_RESOLUTION) — ai/strategy/api.py adopt",
    },
  },
  /* The first of §6's two silent successes. The registry's own `gate` string
     for this type is a *policy* ("asymmetric: ceremony on grant only"), not an
     endpoint — and there is no write endpoint to point at.

     Part E's E1 landed while this round was in flight, and it is worth being
     exact about what it closed: `src/ai/trust/router.py` ships `GET
     /ai/consent` and nothing else, deliberately — its own docstring says a
     grant belongs to "the flows that have the counterparty's word for it …
     never a panel that merely lists them", and names the certified `consent@1`
     act as one of those flows. That act still has nowhere to POST. So the read
     is closed and the grant is not, and this row stays `absent` until a write
     exists. Granting through this layer therefore writes nothing, and says so. */
  "certified.consent": {
    verb: "grant",
    gate: {
      kind: "absent",
      why:
        "Nothing was granted. This estate cannot record consent yet — there is " +
        "no consent endpoint behind this control, so a grant here would look " +
        "kept and be forgotten.",
      closedBy:
        "R-4 part E — E1 shipped GET /ai/consent (read only); the grant needs a write",
    },
  },
  /* Revoking is not in this table on purpose (D3 §3.4): the safe direction must
     never be harder than the unsafe one, so a revoke is a plain control that
     routes through nothing here. `CertifiedConsent` renders it without a seal. */
  "certified.step-up": { verb: "prove", gate: { kind: "ceremony" } },
  "certified.second-channel-wait": { verb: "confirm", gate: { kind: "ceremony" } },
} as const satisfies Record<string, CertifiedActEntry>;

export type CertifiedType = keyof typeof CERTIFIED_ACTS;

/** The two components that *are* the ceremony rather than acts it guards. */
export type CeremonyType = "certified.step-up" | "certified.second-channel-wait";

/**
 * What `useCertifiedAct.run` will accept. Excluding the ceremony pair at the
 * type level is the cheapest of part C's several guards, and the only one that
 * costs nothing at runtime: a step-up cannot be scheduled as if it were an act
 * that needs a step-up.
 */
export type RunnableCertifiedType = Exclude<CertifiedType, CeremonyType>;

export const CERTIFIED_TYPES = Object.keys(CERTIFIED_ACTS) as CertifiedType[];

export function gateFor(type: CertifiedType): Gate {
  return CERTIFIED_ACTS[type].gate;
}
