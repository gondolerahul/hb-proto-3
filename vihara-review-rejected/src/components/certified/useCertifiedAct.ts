/**
 * Run an action the server may refuse until the human proves more — the
 * legacy console's `useCertifiedAction`, rebuilt for Vihara (DRIVER D1).
 *
 * The three properties are kept exactly, because each closed a real hole:
 *
 * 1. **The action is a closure and is retried whole** — whatever follows
 *    success happens on the retry too; there is no second success path to
 *    keep in step.
 * 2. **A refusal is never classified here.** The server said which
 *    ceremony is missing; this only carries the answer to the ceremony.
 * 3. **One retry.** Refused again after a completed ceremony → the
 *    ceremony closes with the server's reason. Re-opening would loop
 *    against a server that has already made up its mind.
 */
import { useCallback, useRef, useState } from "react";

import { parseStepUpRefusal, type StepUpRefusal } from "../../api/authn";

export interface CertifiedAct {
  /** Run `action`, opening the ceremony if the server asks for one. */
  run: (action: () => Promise<void>) => Promise<void>;
  /** Non-null while a ceremony is owed; render `StepUpCeremony` with it. */
  refusal: StepUpRefusal | null;
  /** The ceremony completed — retry the pending action once. */
  onElevated: () => void;
  /** The ceremony was abandoned. */
  onClose: () => void;
  /** Set when the retry was refused again; render it near the action. */
  error: string | null;
  clearError: () => void;
}

export function useCertifiedAct(): CertifiedAct {
  const [refusal, setRefusal] = useState<StepUpRefusal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef<(() => Promise<void>) | null>(null);

  const run = useCallback(async (action: () => Promise<void>) => {
    setError(null);
    try {
      await action();
    } catch (raised) {
      const refused = parseStepUpRefusal(raised);
      // Not a step-up refusal: it belongs to the caller's error handling.
      if (refused === null) throw raised;
      pending.current = action;
      setRefusal(refused);
    }
  }, []);

  const onClose = useCallback(() => {
    setRefusal(null);
    pending.current = null;
  }, []);

  const onElevated = useCallback(() => {
    const action = pending.current;
    setRefusal(null);
    pending.current = null;
    if (action === null) return;
    void action().catch((raised: unknown) => {
      const refused = parseStepUpRefusal(raised);
      setError(
        refused !== null
          ? refused.reason
          : "That action could not be completed.",
      );
    });
  }, []);

  return {
    run,
    refusal,
    onElevated,
    onClose,
    error,
    clearError: () => setError(null),
  };
}
