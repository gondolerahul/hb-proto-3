/**
 * `useCertifiedAct` — the hook every certified control routes through
 * (R-4 part C, C2 · C3 · C5).
 *
 * The legacy console's `useCertifiedAction`, rebuilt, with three properties
 * kept exactly because each closed a real hole:
 *
 * 1. **The act is a closure and is retried WHOLE, once.** Whatever follows
 *    success happens on the retry too, so there is no second success path to
 *    keep in step. Refused again after a completed ceremony → the ceremony
 *    closes with the server's reason; re-opening would loop against a server
 *    that has already made up its mind. This is the shipped policy and part C
 *    is explicit that it is not to be reinvented.
 * 2. **A refusal is never classified here.** The server said which ceremony is
 *    missing (`needs_step_up`, `needs_oob`, `locked`); this only carries the
 *    answer to it. An error that is not a `step_up_required` 403 is re-thrown
 *    to the caller untouched.
 * 3. **A 403 is an entry point, not an error** (C3). Nothing in this module
 *    reports a refusal as a failure — a refusal is the ceremony arriving.
 *
 * What is new, and what part C exists for:
 *
 * 4. **An act is named from a closed set** (`RunnableCertifiedType`). You
 *    cannot route an act this layer has never heard of, and the ceremony pair
 *    is excluded at the type level so a step-up cannot be scheduled as if it
 *    needed one.
 * 5. **An act whose gate does not exist does not run** (`acts.ts`, gate kind
 *    `absent`). §6's warning is that the two paths which *silently succeed*
 *    are more dangerous than the three that will 403, because a certified
 *    control that completes without a ceremony teaches the owner the ceremony
 *    is decorative. So `certified.consent` — which maps to no endpoint at all —
 *    performs nothing, echoes nothing, and returns a sentence saying so. A
 *    rendered gap, per DESIGN_CONTRACT §7.4.
 * 6. **The renderer is a parameter, never inferred** (C5). Every certified path
 *    echoes, and the echo carries `S` for the estate and `C` for the Line, so
 *    density learning cannot read a phone tap as an operator click. Inferring
 *    it from the DOM or from a module-level global is exactly how the two would
 *    eventually agree by accident.
 */
import { useCallback, useMemo, useRef, useState } from "react";

import { emitEcho } from "../../api/genui";
import { CERTIFIED_ACTS, type RunnableCertifiedType } from "./acts";
import type { CeremonyPrompt } from "./StepUpCeremony";
import { readStepUpRefusal } from "./refusal";

/** The two front doors. `W` never takes a certified act — the world is a view. */
export type EchoRenderer = "S" | "C";

export interface CertifiedActOptions {
  /** Which front door this act was taken from. Explicit — see 6 above. */
  renderer: EchoRenderer;
  /** The surface it was taken on; rides the echo's `action_ref`. */
  surface: string;
  /** The local echo ribbon (L10). */
  onEcho: (message: string) => void;
  /** Injectable for tests; the real one is fire-and-forget by contract. */
  emit?: typeof emitEcho;
}

export interface CertifiedRequest {
  /** Which of the eight runnable certified acts this is. */
  act: RunnableCertifiedType;
  /** The echo sentence: lowercase past tense, the user's own words. */
  echo: string;
  /** What the ceremony restates when the server's refusal names nothing. */
  summary: string;
  /** The object acted on, for the echo's `action_ref`. */
  subject?: string;
  /** The manifest component the control belongs to, when there is one. */
  componentId?: string;
}

/**
 * Why an act did not happen. The two kinds want different idioms on a surface:
 * a **gap** is the platform's, and is rendered quietly in `t-mono`; a
 * **refusal** is the server's answer to this attempt and belongs in an alert.
 * Collapsing them into one `error: string` is what makes a missing endpoint
 * look like a rejected act.
 */
export type CertifiedProblem =
  | { kind: "gap"; message: string; closedBy: string }
  | { kind: "refused"; message: string };

export interface CertifiedAct {
  /** Run `perform`, opening the ceremony if the server asks for one. */
  run: (request: CertifiedRequest, perform: () => Promise<void>) => Promise<void>;
  /** Non-null while a ceremony is owed. Render `StepUpCeremony` with it. */
  ceremony: (CeremonyPrompt & { act: RunnableCertifiedType }) | null;
  /** The ceremony completed — retry the pending act once. */
  onElevated: () => void;
  /** The ceremony was abandoned; the pending act is dropped. */
  onClose: () => void;
  /** True while an act (or its one retry) is in flight. */
  busy: boolean;
  problem: CertifiedProblem | null;
  clearProblem: () => void;
}

export function useCertifiedAct(options: CertifiedActOptions): CertifiedAct {
  const { renderer, surface, onEcho, emit = emitEcho } = options;

  const [ceremony, setCeremony] = useState<
    (CeremonyPrompt & { act: RunnableCertifiedType }) | null
  >(null);
  const [problem, setProblem] = useState<CertifiedProblem | null>(null);
  const [busy, setBusy] = useState(false);

  const pending = useRef<{
    request: CertifiedRequest;
    perform: () => Promise<void>;
  } | null>(null);

  const settle = useCallback(
    (request: CertifiedRequest) => {
      onEcho(request.echo);
      // Fire-and-forget by contract (D5 §6): an echo that fails to record
      // loses training data, never work.
      void emit({
        sentence: request.echo,
        action_ref: {
          kind: "certified_act",
          surface_id: surface,
          params: {
            act: request.act,
            renderer,
            ...(request.subject !== undefined ? { subject: request.subject } : {}),
          },
        },
        ...(request.componentId !== undefined
          ? { component_id: request.componentId }
          : {}),
      });
    },
    [emit, onEcho, renderer, surface],
  );

  const run = useCallback(
    async (request: CertifiedRequest, perform: () => Promise<void>) => {
      setProblem(null);
      const gate = CERTIFIED_ACTS[request.act].gate;

      if (gate.kind === "absent") {
        // Never perform, never echo. See 5 above — this is the whole point.
        setProblem({ kind: "gap", message: gate.why, closedBy: gate.closedBy });
        return;
      }

      setBusy(true);
      try {
        await perform();
        settle(request);
      } catch (raised) {
        const refusal = readStepUpRefusal(raised);
        // Not a step-up refusal: it belongs to the caller's error handling and
        // must not be swallowed by a security layer.
        if (refusal === null) throw raised;
        pending.current = { request, perform };
        setCeremony({
          act: request.act,
          refusal,
          summary: request.summary,
        });
      } finally {
        setBusy(false);
      }
    },
    [settle],
  );

  const onClose = useCallback(() => {
    setCeremony(null);
    pending.current = null;
  }, []);

  const onElevated = useCallback(() => {
    const held = pending.current;
    setCeremony(null);
    pending.current = null;
    if (held === null) return;
    setBusy(true);
    void held
      .perform()
      .then(() => settle(held.request))
      .catch((raised: unknown) => {
        // One retry, whole. A second refusal is the server's final answer —
        // re-opening the ceremony would loop against a decided server.
        const again = readStepUpRefusal(raised);
        setProblem({
          kind: "refused",
          message:
            again !== null ? again.reason : "That act could not be completed.",
        });
      })
      .finally(() => setBusy(false));
  }, [settle]);

  const clearProblem = useCallback(() => setProblem(null), []);

  return useMemo(
    () => ({ run, ceremony, onElevated, onClose, busy, problem, clearProblem }),
    [run, ceremony, onElevated, onClose, busy, problem, clearProblem],
  );
}
