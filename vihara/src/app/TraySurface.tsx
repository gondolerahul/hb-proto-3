/**
 * The Tray (DRIVER D1, D6 §4) — the only interruption that exists, and the
 * single most consequential replacement in the product (HITLPanel → this).
 *
 * The four rules the surface must not break, each pinned by a test:
 *
 * 1. The certified block is byte-identical here and in any sheet — it
 *    renders through `implementationFor`, the SAME dispatch RenderManifest
 *    uses, never a local copy.
 * 2. The countdown is quiet. Never red, never pulsing, never an alarm.
 * 3. A path with no cost shows no cost line — no placeholder, no "—",
 *    no estimate.
 * 4. Certified components do not stream: the block renders whole from the
 *    composed tray; no manifest fetch is involved anywhere on this path.
 *
 * Every path echoes, including asking (L10). Approve/decline run through
 * `useCertifiedAct`, so a `step_up_required` refusal becomes the ceremony
 * rather than a broken button — VG-05's console lesson, kept.
 */
import { useCallback, useEffect, useState } from "react";

import { emitEcho } from "../api/genui";
import {
  fetchTrayList,
  respondToApproval,
  type Tray,
  type TrayDecision,
} from "../api/trays";
import {
  StepUpCeremony,
  type CeremonyDeps,
} from "../components/certified/StepUpCeremony";
import { useCertifiedAct } from "../components/certified/useCertifiedAct";
import { SlaCountdown } from "../components/primitive/SlaCountdown";
import { connectEstateStream } from "../estate/live";
import { subscribeEstateStream } from "../estate/sharedStream";
import { assessManifest } from "../manifest/refusals";
import type { WireComponent, WireScaffold } from "../manifest/schema";
import { implementationFor } from "../renderers/RenderManifest";
import { announce } from "./ribbon";

export interface TrayLoaders {
  trays: typeof fetchTrayList;
  respond: typeof respondToApproval;
  echo: typeof emitEcho;
  stream: typeof connectEstateStream;
  /** Injectable for tests; the real ceremony talks to `/ai/authn/*`. */
  ceremony?: CeremonyDeps;
}

const REAL: TrayLoaders = {
  trays: fetchTrayList,
  respond: respondToApproval,
  echo: emitEcho,
  stream: subscribeEstateStream,
};

type State =
  | { phase: "loading" }
  | { phase: "failed"; reason: string }
  | { phase: "ready"; trays: Tray[] };

function summaryOf(tray: Tray): string {
  const summary = tray.certified.props["summary"];
  return typeof summary === "string" && summary !== ""
    ? summary
    : tray.what_happened.sentence;
}

/**
 * The certified block, through the one shared dispatch (rule 1) — and
 * through the same refusal ladder the manifest path uses: the composer is
 * ours, but a certified block is checked, never trusted (D4 §2). Reject
 * renders a refusal, not a lookalike (L5).
 */
function CertifiedBlock({
  tray,
  density,
}: {
  tray: Tray;
  density: "novice" | "operator";
}): JSX.Element {
  const component: WireComponent = {
    id: `tray-${tray.tray_id}`,
    type: tray.certified.component,
    region: "certified",
    props: tray.certified.props,
  };
  const scaffold: WireScaffold = {
    part: "scaffold",
    manifest_version: 1,
    surface_id: "tray",
    renderer: "C",
    plane: "live",
    depth: 1,
    density,
    layout: { kind: "stack", regions: ["certified"] },
    components: [component],
    issued_at: "",
    ttl_seconds: 0,
  };
  const assessment = assessManifest(scaffold);
  const Impl = implementationFor(component.type);
  if (assessment.verdict === "reject" || Impl === undefined) {
    return (
      <p role="alert" data-part="uncertifiable">
        This decision cannot be shown certified here; it is waiting in the
        legacy console.
      </p>
    );
  }
  return <Impl component={component} density={density} />;
}

function TrayCard({
  tray,
  density,
  loaders,
  onSettled,
}: {
  tray: Tray;
  density: "novice" | "operator";
  loaders: TrayLoaders;
  onSettled: (trayId: string) => void;
}): JSX.Element {
  const act = useCertifiedAct();
  const [asked, setAsked] = useState(false);
  const [plainError, setPlainError] = useState<string | null>(null);

  const decide = useCallback(
    (decision: TrayDecision) => {
      const sentence = `${decision === "APPROVED" ? "approved" : "declined"}: ${summaryOf(tray)}`;
      setPlainError(null);
      act
        .run(async () => {
          await loaders.respond(tray.approval_id, decision);
          void loaders.echo({
            sentence,
            action_ref: {
              kind: "tray.respond",
              surface_id: "tray",
              params: { approval_id: tray.approval_id, decision },
            },
            manifest_hash: tray.certified.manifest_hash,
          });
          announce(sentence);
          onSettled(tray.tray_id);
        })
        // An ordinary failure (the hook only claims step-up refusals):
        // visible here, never a silently dead button.
        .catch(() => setPlainError("That could not be completed."));
    },
    [act, loaders, onSettled, tray],
  );

  return (
    <article className="vh-tray" data-part="tray" data-tray-id={tray.tray_id}>
      <header className="vh-tray-header">
        <span className="vh-eyebrow">
          {tray.prepared_by !== null
            ? `prepared by ${tray.prepared_by.name}`
            : "prepared by the platform"}
        </span>
        <SlaCountdown
          secondsLeft={tray.sla.seconds_left}
          onTimeout={tray.sla.on_timeout}
        />
      </header>

      <p className="vh-tray-happened">{tray.what_happened.sentence}</p>

      {tray.recommendation !== null && (
        <div className="vh-tray-recommendation" data-part="recommendation">
          <p>{tray.recommendation.sentence}</p>
          {tray.recommendation.why !== null && (
            <details open={density === "novice"}>
              <summary>why</summary>
              <p>{tray.recommendation.why}</p>
            </details>
          )}
        </div>
      )}

      <ul className="vh-tray-paths">
        {tray.paths.map((path) => (
          <li key={path.key} data-path={path.key}>
            <span>{path.consequence}</span>
            {/* Rule 3: a null cost is NO line — never a placeholder. */}
            {path.cost !== null && (
              <span className="vh-tray-cost" data-part="path-cost">
                {path.cost.currency !== null ? `${path.cost.currency} ` : ""}
                {path.cost.amount.toLocaleString()} · {path.cost.basis}
              </span>
            )}
          </li>
        ))}
      </ul>

      {act.refusal !== null ? (
        <StepUpCeremony
          refusal={act.refusal}
          onElevated={act.onElevated}
          onClose={act.onClose}
          deps={loaders.ceremony}
        />
      ) : (
        <div
          className="vh-tray-certified"
          onClick={(event) => {
            const button = (event.target as HTMLElement).closest("[data-action]");
            if (button === null) return;
            const action = button.getAttribute("data-action");
            if (action === "approve" || action === "confirm") decide("APPROVED");
            if (action === "decline" || action === "keep as is")
              decide("REJECTED");
          }}
        >
          <CertifiedBlock tray={tray} density={density} />
        </div>
      )}
      {act.error !== null && <p role="alert">{act.error}</p>}
      {plainError !== null && <p role="alert">{plainError}</p>}

      <button
        type="button"
        className="vh-quiet-link"
        data-part="talk-to-me"
        onClick={() => {
          void loaders.echo({
            sentence: `asked about: ${summaryOf(tray)}`,
            action_ref: {
              kind: "tray.ask",
              surface_id: "tray",
              params: { approval_id: tray.approval_id },
            },
            manifest_hash: tray.certified.manifest_hash,
          });
          setAsked(true);
        }}
      >
        talk to me about it
      </button>
      {asked && (
        <p className="vh-quiet" data-part="ask-honesty">
          She has seen the question. Her side of the conversation opens with
          the steward (G3).
        </p>
      )}
    </article>
  );
}

export function TraySurface({
  density = "novice",
  loaders = REAL,
  onCount,
}: {
  density?: "novice" | "operator";
  loaders?: TrayLoaders;
  onCount?: (count: number) => void;
}): JSX.Element {
  const [state, setState] = useState<State>({ phase: "loading" });

  const load = useCallback(async () => {
    try {
      const trays = await loaders.trays();
      setState({ phase: "ready", trays });
      onCount?.(trays.length);
    } catch {
      setState({
        phase: "failed",
        reason: "The trays could not be reached.",
      });
    }
  }, [loaders, onCount]);

  useEffect(() => {
    void load();
    let dispose: (() => void) | null = null;
    try {
      dispose = loaders.stream((event) => {
        // A delivered tray is not droppable (D5 §3) — refetch, don't merge:
        // the composed object on the wire event is a notification, and the
        // list read is the one source of truth for what is still pending.
        if (event.type === "tray.delivered" || event.type === "beacon.cleared") {
          void load();
        }
      });
    } catch {
      // No stream is a slower tray list, not a broken one.
    }
    return () => dispose?.();
  }, [load, loaders]);

  if (state.phase === "loading") {
    return <p className="vh-quiet">Fetching what needs you…</p>;
  }
  if (state.phase === "failed") {
    return (
      <p role="alert" data-part="trays-failed">
        {state.reason}
      </p>
    );
  }
  if (state.trays.length === 0) {
    return (
      <p className="vh-quiet" data-part="trays-empty">
        Nothing needs you.
      </p>
    );
  }

  return (
    <div className="vh-tray-stack" data-part="tray-stack">
      {state.trays.map((tray) => (
        <TrayCard
          key={tray.tray_id}
          tray={tray}
          density={density}
          loaders={loaders}
          onSettled={(trayId) => {
            setState((previous) => {
              if (previous.phase !== "ready") return previous;
              const trays = previous.trays.filter((t) => t.tray_id !== trayId);
              onCount?.(trays.length);
              return { ...previous, trays };
            });
          }}
        />
      ))}
    </div>
  );
}
