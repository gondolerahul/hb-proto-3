import { useCallback, useRef, useState } from 'react';
import { parseStepUpRefusal, type StepUpRefusal } from '@/services/authn.service';

/**
 * Run an action that the server may refuse until the human proves more (VG-05).
 *
 * Increment 3 built the ceremony and Increment 6 put the gate on the REST path,
 * but the console still turned a `step_up_required` refusal into a generic
 * failure — so five certified actions (approving a payout, binding a connector,
 * flipping a master, consenting to a provider, raising an autonomy band) simply
 * looked broken. This hook is the missing translation.
 *
 * Three properties are deliberate:
 *
 * 1. **The action is a closure, and it is retried whole.** Whatever the caller
 *    does after the call succeeds — updating local state, navigating — happens
 *    on the retry too, so there is no second success path to keep in step.
 * 2. **A refusal is never classified here.** The server said which ceremony is
 *    missing; this only carries the answer to {@link StepUpModal}.
 * 3. **One retry.** If the act is refused again after a completed ceremony the
 *    modal closes with the server's reason. Re-opening it would loop against a
 *    server that has already made up its mind.
 */
export interface CertifiedAction {
    /** Run `action`, opening the ceremony if the server asks for one. */
    run: (action: () => Promise<void>) => Promise<void>;
    /** Spread onto `<StepUpModal {...stepUp.modalProps} />`. */
    modalProps: {
        isOpen: boolean;
        needsOob: boolean;
        commandRef: string | undefined;
        commandSummary: string | undefined;
        onClose: () => void;
        onElevated: () => void;
    };
    /** Set when a retry was refused again; render it near the action. */
    error: string | null;
    clearError: () => void;
}

export const useCertifiedAction = (): CertifiedAction => {
    const [refusal, setRefusal] = useState<StepUpRefusal | null>(null);
    const [error, setError] = useState<string | null>(null);
    const pending = useRef<(() => Promise<void>) | null>(null);

    const run = useCallback(async (action: () => Promise<void>) => {
        setError(null);
        try {
            await action();
        } catch (err) {
            const refused = parseStepUpRefusal(err);
            // Not a step-up refusal: it belongs to the caller's error handling.
            if (!refused) throw err;
            pending.current = action;
            setRefusal(refused);
        }
    }, []);

    const close = useCallback(() => {
        setRefusal(null);
        pending.current = null;
    }, []);

    const onElevated = useCallback(() => {
        const action = pending.current;
        setRefusal(null);
        pending.current = null;
        if (!action) return;
        void action().catch((err) => {
            const refused = parseStepUpRefusal(err);
            setError(refused
                ? refused.reason
                : (err?.response?.data?.detail ?? 'That action could not be completed.'));
        });
    }, []);

    return {
        run,
        modalProps: {
            isOpen: refusal !== null,
            needsOob: refusal?.needs_oob ?? false,
            commandRef: refusal?.command_ref ?? undefined,
            commandSummary: refusal?.command_summary ?? undefined,
            onClose: close,
            onElevated,
        },
        error,
        clearError: () => setError(null),
    };
};
