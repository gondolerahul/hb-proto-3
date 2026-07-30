/**
 * The T2 ceremony surface (DRIVER D1). The certified block inside it is
 * the pinned `certified.step-up` component, byte-identical to its golden —
 * the wiring lives AROUND the block (click delegation on `data-action`),
 * never inside it, so the display stays deterministic and golden-tested.
 *
 * A failed factor is reported, not retried silently — the server counts
 * it toward the lockout and the human deserves to see the count coming.
 * T3 (`needs_oob`) drives the out-of-band leg end to end (STEWARD S7):
 * issue → the nonce rides a SECOND channel → the human types it back.
 */
import { useState } from "react";

import {
  confirmOob,
  isPasskeySupported,
  issueOob,
  stepUpWithPasskey,
  stepUpWithTotp,
  type StepUpRefusal,
} from "../../api/authn";
import type { WireComponent } from "../../manifest/schema";
import { CertifiedSecondChannelWait, CertifiedStepUp } from "./certifiedSet";

export interface CeremonyDeps {
  passkey: typeof stepUpWithPasskey;
  totp: typeof stepUpWithTotp;
  oobIssue?: typeof issueOob;
  oobConfirm?: typeof confirmOob;
}

const REAL: CeremonyDeps = {
  passkey: stepUpWithPasskey,
  totp: stepUpWithTotp,
  oobIssue: issueOob,
  oobConfirm: confirmOob,
};

function stepUpComponent(refusal: StepUpRefusal): WireComponent {
  return {
    id: "step-up",
    type: "certified.step-up@1",
    props: {
      tier: refusal.tier,
      command_ref: refusal.command_ref ?? "",
      command_summary: refusal.command_summary ?? refusal.why,
    },
  };
}

export function StepUpCeremony({
  refusal,
  onElevated,
  onClose,
  deps = REAL,
}: {
  refusal: StepUpRefusal;
  onElevated: () => void;
  onClose: () => void;
  deps?: CeremonyDeps;
}): JSX.Element {
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [totpCode, setTotpCode] = useState("");

  if (refusal.locked) {
    return (
      <div className="vh-ceremony" data-part="ceremony">
        <p role="alert">
          Step-up is locked after repeated failures. Wait it out, then try
          again.
        </p>
        <button type="button" className="vh-quiet-link" onClick={onClose}>
          close
        </button>
      </div>
    );
  }

  if (refusal.needs_oob) {
    return (
      <OobCeremony refusal={refusal} onElevated={onElevated} onClose={onClose} deps={deps} />
    );
  }

  const settle = (ok: boolean, reason?: string): void => {
    setBusy(false);
    if (ok) {
      onElevated();
    } else {
      setFailure(reason ?? "That did not verify.");
    }
  };

  return (
    <div
      className="vh-ceremony"
      data-part="ceremony"
      onClick={(event) => {
        const target = event.target as HTMLElement;
        if (target.closest("[data-action='use passkey']") === null) return;
        if (busy) return;
        setBusy(true);
        setFailure(null);
        deps
          .passkey()
          .then((outcome) => settle(outcome.ok, outcome.reason))
          .catch(() => settle(false, "The passkey ceremony was cancelled."));
      }}
    >
      {isPasskeySupported() && (
        <CertifiedStepUp component={stepUpComponent(refusal)} density="novice" />
      )}
      <form
        className="vh-ceremony-fallback"
        onSubmit={(event) => {
          event.preventDefault();
          if (busy || totpCode.trim() === "") return;
          setBusy(true);
          setFailure(null);
          deps
            .totp(totpCode.trim())
            .then((outcome) => settle(outcome.ok, outcome.reason))
            .catch(() => settle(false, "That code did not verify."));
        }}
      >
        <label>
          or a one-time code
          <input
            value={totpCode}
            onChange={(event) => setTotpCode(event.target.value)}
            inputMode="numeric"
            autoComplete="one-time-code"
          />
        </label>
        <button type="submit" disabled={busy}>
          verify
        </button>
      </form>
      {failure !== null && <p role="alert">{failure}</p>}
      <button type="button" className="vh-quiet-link" onClick={onClose}>
        not now
      </button>
    </div>
  );
}

/**
 * The T3 second-channel leg, driven end to end (STEWARD S7): issue sends
 * the nonce to a SECOND registered channel — never this one, that
 * separation is what the leg buys — and the human types back what they
 * read there. A wrong nonce is a failed verification like any other and
 * counts toward the lockout on the server.
 */
function OobCeremony({
  refusal,
  onElevated,
  onClose,
  deps,
}: {
  refusal: StepUpRefusal;
  onElevated: () => void;
  onClose: () => void;
  deps: CeremonyDeps;
}): JSX.Element {
  const [challenge, setChallenge] = useState<{
    id: string;
    channel: string;
  } | null>(null);
  const [nonce, setNonce] = useState("");
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const commandRef = refusal.command_ref ?? "";

  return (
    <div className="vh-ceremony" data-part="ceremony">
      <CertifiedSecondChannelWait
        component={{
          id: "oob",
          type: "certified.second-channel-wait@1",
          props: {
            channel: challenge?.channel ?? "your bound channel",
            command_ref: commandRef,
            command_summary: refusal.command_summary ?? refusal.why,
          },
        }}
        density="novice"
      />
      {challenge === null ? (
        <button
          type="button"
          data-part="oob-send"
          disabled={busy || commandRef === ""}
          onClick={() => {
            setBusy(true);
            setFailure(null);
            void (
              deps.oobIssue?.(commandRef) ??
              Promise.resolve({ ok: false as const, reason: undefined })
            )
              .then((sent) => {
                setBusy(false);
                if (sent.ok && sent.challenge_id !== undefined) {
                  setChallenge({
                    id: sent.challenge_id,
                    channel: sent.sent_to_channel ?? "your bound channel",
                  });
                } else {
                  setFailure(sent.reason ?? "The confirmation could not be sent.");
                }
              });
          }}
        >
          send the confirmation
        </button>
      ) : (
        <form
          data-part="oob-confirm"
          onSubmit={(event) => {
            event.preventDefault();
            if (busy || nonce.trim() === "") return;
            setBusy(true);
            setFailure(null);
            void (
              deps.oobConfirm?.(challenge.id, commandRef, nonce.trim()) ??
              Promise.resolve({ ok: false as const, reason: undefined })
            )
              .then((outcome) => {
                setBusy(false);
                if (outcome.ok) {
                  onElevated();
                } else {
                  setFailure(outcome.reason ?? "That did not verify.");
                }
              })
              .catch(() => {
                setBusy(false);
                setFailure("That did not verify.");
              });
          }}
        >
          <label>
            the code from {challenge.channel}
            <input
              value={nonce}
              onChange={(event) => setNonce(event.target.value)}
              inputMode="numeric"
              autoComplete="one-time-code"
            />
          </label>
          <button type="submit" disabled={busy}>
            confirm
          </button>
        </form>
      )}
      {failure !== null && <p role="alert">{failure}</p>}
      <button type="button" className="vh-quiet-link" onClick={onClose}>
        not now
      </button>
    </div>
  );
}
