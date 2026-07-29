/**
 * The T2 ceremony surface (DRIVER D1). The certified block inside it is
 * the pinned `certified.step-up` component, byte-identical to its golden —
 * the wiring lives AROUND the block (click delegation on `data-action`),
 * never inside it, so the display stays deterministic and golden-tested.
 *
 * A failed factor is reported, not retried silently — the server counts
 * it toward the lockout and the human deserves to see the count coming.
 * T3 (`needs_oob`) renders the second-channel-wait state; driving the
 * out-of-band leg end-to-end is STEWARD's work and is said so on screen.
 */
import { useState } from "react";

import {
  isPasskeySupported,
  stepUpWithPasskey,
  stepUpWithTotp,
  type StepUpRefusal,
} from "../../api/authn";
import type { WireComponent } from "../../manifest/schema";
import { CertifiedSecondChannelWait, CertifiedStepUp } from "./certifiedSet";

export interface CeremonyDeps {
  passkey: typeof stepUpWithPasskey;
  totp: typeof stepUpWithTotp;
}

const REAL: CeremonyDeps = { passkey: stepUpWithPasskey, totp: stepUpWithTotp };

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
      <div className="vh-ceremony" data-part="ceremony">
        <CertifiedSecondChannelWait
          component={{
            id: "oob",
            type: "certified.second-channel-wait@1",
            props: {
              channel: "your bound channel",
              command_ref: refusal.command_ref ?? "",
              command_summary: refusal.command_summary ?? refusal.why,
            },
          }}
          density="novice"
        />
        <p className="vh-quiet">
          The second-channel confirmation arrives with the steward (G3); until
          then this act completes from the legacy console.
        </p>
        <button type="button" className="vh-quiet-link" onClick={onClose}>
          close
        </button>
      </div>
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
