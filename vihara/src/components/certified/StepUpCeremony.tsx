import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";

import { Icon } from "../Icon";
import {
  confirmOob,
  isPasskeySupported,
  issueOob,
  stepUpWithPasskey,
  stepUpWithTotp,
} from "../../api/authn";
import type { WireComponent } from "../../manifest/schema";
import { CertifiedSecondChannelWait, CertifiedStepUp } from "./certifiedSet";
import {
  isNoPasskeyEnrolled,
  stepUpLockoutReason,
  type CertifiedRefusal,
} from "./refusal";
import "./ceremony.css";

/**
 * The step-up ceremony (R-4 part C, C1) — the most consequential modal in the
 * product, and the reason §6 says what is drawn today "is not a ceremony".
 *
 * The brief for it was: *a deliberate act, not a browser prompt with a
 * wrapper.* Five decisions carry that, and they are all decisions about
 * restraint rather than about ornament:
 *
 * 1. **The act is restated, never remembered.** The largest thing in the panel
 *    is `command_summary` — the server's own description of what is about to
 *    happen — rendered by the pinned `certified.step-up` component, not by this
 *    file. What you are authorising is the one thing on screen that unpinned
 *    code may not draw. The card behind the modal is not the record; this is.
 * 2. **Opaque, not glass.** The panel is `m-plate[data-raised]` with corner
 *    ticks. The estate's floating layers are glass; at the moment money moves
 *    the panel has to be the most solid object on screen, and glass would let
 *    the room show through the one surface that must own the decision.
 * 3. **One factor forward, one behind a word.** The passkey is the gold
 *    control. TOTP is §11.3's fallback and reads like one — a quiet
 *    disclosure, not a competing field. Two equally weighted inputs make a
 *    ceremony into a form.
 * 4. **The lockout is shown coming.** `/ai/authn/step-up` counts every failure
 *    and returns the running total; it is rendered, with the reason, so the
 *    third attempt is a decision rather than a surprise. A failed factor is
 *    reported and never silently retried.
 * 5. **Leaving is easy.** Escape, the scrim, and a plain "Not now" all close
 *    it. Abandoning a ceremony is the safe direction and must never be the
 *    hard one — the same asymmetry that governs consent (D3 §3.4).
 *
 * **Four legs, and why the pinned block is on only two of them.** The refusal
 * says which ceremony is owed and this file only routes to it (`locked` →
 * `LockedOut`, neither flag → `CannotStepUp`, `needs_oob` → `SecondChannelLeg`,
 * otherwise `PasskeyLeg`); nothing here re-derives a tier.
 *
 * The two legs that can offer an action render the pinned component for it —
 * `certified.step-up` and `certified.second-channel-wait` — and delegate its
 * `data-action` click from the container, so the block stays a pure function of
 * props and the goldens keep their value. The other two have no action to
 * offer, and a device with no passkey has none either, so those render the
 * statement in this file's own markup instead: DESIGN_CONTRACT §7.4 forbids
 * drawing a control that goes nowhere, and a dead gold button on this modal
 * would teach exactly the lesson §6 is trying to prevent.
 */

export interface CeremonyDeps {
  passkey: typeof stepUpWithPasskey;
  totp: typeof stepUpWithTotp;
  oobIssue: typeof issueOob;
  oobConfirm: typeof confirmOob;
  passkeySupported: () => boolean;
}

const REAL_DEPS: CeremonyDeps = {
  passkey: stepUpWithPasskey,
  totp: stepUpWithTotp,
  oobIssue: issueOob,
  oobConfirm: confirmOob,
  passkeySupported: isPasskeySupported,
};

export interface CeremonyPrompt {
  refusal: CertifiedRefusal;
  /** The caller's own words, used only when the server named nothing. */
  summary: string;
}

export interface StepUpCeremonyProps {
  prompt: CeremonyPrompt;
  onElevated: () => void;
  onClose: () => void;
  deps?: CeremonyDeps;
}

function stepUpBlock(prompt: CeremonyPrompt): WireComponent {
  return {
    id: "step-up",
    type: "certified.step-up@1",
    props: {
      tier: prompt.refusal.tier,
      command_ref: prompt.refusal.command_ref ?? "",
      command_summary: prompt.refusal.command_summary ?? prompt.summary,
    },
  };
}

function statementOf(prompt: CeremonyPrompt): {
  summary: string;
  commandRef: string | null;
} {
  return {
    summary: prompt.refusal.command_summary ?? prompt.summary,
    commandRef: prompt.refusal.command_ref,
  };
}

// ── the shell: scrim, focus, escape ──────────────────────────────────────────

/**
 * The modal shell. The focus contract is the part worth reading: focus enters
 * the panel on open, cycles inside it, and returns to whatever opened it on
 * close. A ceremony you can tab out of is a ceremony you can complete without
 * looking at, which is the failure mode the whole of part C exists to prevent.
 */
function CeremonyShell({
  label,
  busy,
  onClose,
  children,
}: {
  label: string;
  busy: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const opener = document.activeElement;
    panelRef.current?.focus();
    return () => {
      if (opener instanceof HTMLElement) opener.focus();
    };
  }, []);

  const onKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const panel = panelRef.current;
      if (panel === null) return;
      const focusable = Array.from(
        panel.querySelectorAll<HTMLElement>(
          'button:not(:disabled), input:not(:disabled), [href], [tabindex]:not([tabindex="-1"])',
        ),
      );
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (first === undefined || last === undefined) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    },
    [onClose],
  );

  return (
    <div
      className="cy-scrim"
      onKeyDown={onKeyDown}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        className="cy-panel m-plate m-ticks"
        data-raised
        data-part="ceremony"
        role="dialog"
        aria-modal="true"
        aria-label={label}
        aria-busy={busy || undefined}
        tabIndex={-1}
      >
        {children}
      </div>
    </div>
  );
}

/**
 * The statement, in this file's markup — for the three paths the pinned block
 * cannot serve, because none of them has a `use passkey` action to offer.
 *
 * It mirrors the block's header deliberately (seal, eyebrow, hairline, then the
 * act) so a locked owner and a passkeyless owner are looking at the same modal
 * as everyone else, not at a degraded one. `tone` is the only difference: gold
 * where the act is still live, a negative lamp where it is held.
 */
function CeremonyStatement({
  prompt,
  eyebrow,
  tone,
}: {
  prompt: CeremonyPrompt;
  eyebrow: string;
  tone: "certified" | "held";
}) {
  const { summary, commandRef } = statementOf(prompt);
  return (
    <div className="cy-statement">
      <header className="cy-head">
        {tone === "certified" ? (
          <span className="m-medallion cy-seal" aria-hidden="true">
            <Icon name="check" size={9} />
          </span>
        ) : (
          <span className="m-lamp" data-negative />
        )}
        <span className="t-eyebrow" data-certified={tone === "certified" || undefined}>
          {eyebrow}
        </span>
      </header>
      <hr className="m-rule-fade cy-rule" />
      <h2 className="cy-ask t-display">{summary}</h2>
      {commandRef !== null && commandRef !== "" && (
        <p className="m-well cy-ref t-mono" data-deep>
          {commandRef}
        </p>
      )}
    </div>
  );
}

/** What the authenticator is doing, said in words beside a lamp — never a
 * spinner. A spinner here is precisely the "browser prompt with a wrapper"
 * this modal exists not to be. */
function Working({ children }: { children: ReactNode }) {
  return (
    <p className="cy-status t-mono" role="status">
      <span className="m-lamp" data-lit data-breathing />
      {children}
    </p>
  );
}

/**
 * The server's two sentences: why this act is certified (the classifier's
 * words) and what this session holds (the session's). Both verbatim — this
 * modal never paraphrases a refusal, because a paraphrase is where a security
 * explanation goes wrong.
 *
 * `current_level`/`required_level` are deliberately *not* repeated here: the
 * reason sentence already names both, and a "BOUND → ELEVATED" chip beside
 * "session holds BOUND" is the same fact twice. They earn their place in
 * `CannotStepUp`, where the sentence is at its most technical and the levels
 * are the only part a person can act on.
 */
function RefusalReading({ refusal }: { refusal: CertifiedRefusal }) {
  return (
    <div className="cy-reading">
      {refusal.why !== "" && <p className="cy-why t-narrative">{refusal.why}</p>}
      <p className="cy-reason t-mono">{refusal.reason}</p>
    </div>
  );
}

function Failure({
  message,
  attempts,
}: {
  message: string;
  attempts: number | null;
}) {
  return (
    <p className="cy-fail" role="alert">
      <span className="m-lamp" data-negative />
      <span className="cy-fail-text">
        {message}
        {attempts !== null && attempts > 0 && (
          <span className="cy-fail-count t-mono">
            {attempts} failed {attempts === 1 ? "attempt" : "attempts"} on this
            session
          </span>
        )}
      </span>
    </p>
  );
}

function NotNow({ onClose }: { onClose: () => void }) {
  return (
    <button type="button" className="m-btn cy-leave" data-rank="quiet" onClick={onClose}>
      Not now
    </button>
  );
}

// ── the ceremony ─────────────────────────────────────────────────────────────

export function StepUpCeremony({
  prompt,
  onElevated,
  onClose,
  deps = REAL_DEPS,
}: StepUpCeremonyProps) {
  const { refusal } = prompt;
  if (refusal.locked) {
    return <LockedOut prompt={prompt} onClose={onClose} />;
  }
  if (!refusal.needs_step_up && !refusal.needs_oob) {
    return <CannotStepUp prompt={prompt} onClose={onClose} />;
  }
  if (refusal.needs_oob) {
    return (
      <SecondChannelLeg
        prompt={prompt}
        onElevated={onElevated}
        onClose={onClose}
        deps={deps}
      />
    );
  }
  return (
    <PasskeyLeg
      prompt={prompt}
      onElevated={onElevated}
      onClose={onClose}
      deps={deps}
    />
  );
}

/**
 * Locked. No factor is offered, because offering one would spend an attempt the
 * owner cannot see the cost of — and the server refuses it anyway. The reason
 * carries the wall-clock time the lock lifts, so this says when rather than
 * "later".
 */
function LockedOut({
  prompt,
  onClose,
}: {
  prompt: CeremonyPrompt;
  onClose: () => void;
}) {
  const { summary } = statementOf(prompt);
  return (
    <CeremonyShell label={`Step-up is locked: ${summary}`} busy={false} onClose={onClose}>
      <CeremonyStatement prompt={prompt} eyebrow="STEP-UP LOCKED" tone="held" />
      <p className="cy-why t-narrative" role="alert">
        This is not going to run right now. Too many step-ups failed, so
        sensitive acts are held until the lock lifts. Reading the estate is
        unaffected.
      </p>
      <p className="cy-reason t-mono">{prompt.refusal.reason}</p>
      <footer className="cy-foot">
        <NotNow onClose={onClose} />
      </footer>
    </CeremonyShell>
  );
}

/**
 * Refused, with no ceremony that could lift it.
 *
 * `sessions.require_tier` only sets `needs_step_up` when the session already
 * resolves to a user — an unbound channel has no one to prove, so it comes back
 * with all three flags false. Every other path in this file would have offered a
 * passkey button there, and it would have failed on every press: a control that
 * goes nowhere on the modal whose whole subject is trust (DESIGN_CONTRACT §7.4).
 *
 * This is also the one place `current_level` / `required_level` are shown. The
 * server's sentence here is at its most technical ("T2 needs ELEVATED but this
 * channel is not bound to a user — enroll it from the console first"), and the
 * two levels as a labelled pair are the part of it a person can act on.
 */
function CannotStepUp({
  prompt,
  onClose,
}: {
  prompt: CeremonyPrompt;
  onClose: () => void;
}) {
  const { refusal } = prompt;
  const { summary } = statementOf(prompt);
  return (
    <CeremonyShell label={`Refused: ${summary}`} busy={false} onClose={onClose}>
      <CeremonyStatement prompt={prompt} eyebrow="NOT PERMITTED HERE" tone="held" />
      <p className="cy-why t-narrative" role="alert">
        Nothing here can raise this session far enough for that act. Proving it
        is you again would not change the answer.
      </p>
      <p className="cy-reason t-mono">{refusal.reason}</p>
      {refusal.current_level !== null && refusal.required_level !== null && (
        <div className="m-well cy-levels" data-deep>
          <dl>
            <div className="cy-level">
              <dt className="t-eyebrow">THIS SESSION HOLDS</dt>
              <dd className="t-mono">{refusal.current_level}</dd>
            </div>
            <div className="cy-level">
              <dt className="t-eyebrow">THE ACT NEEDS</dt>
              <dd className="t-mono">{refusal.required_level}</dd>
            </div>
          </dl>
        </div>
      )}
      <footer className="cy-foot">
        <NotNow onClose={onClose} />
      </footer>
    </CeremonyShell>
  );
}

/** The T2 leg: a platform passkey, with §11.3's one-time code behind it. */
function PasskeyLeg({
  prompt,
  onElevated,
  onClose,
  deps,
}: {
  prompt: CeremonyPrompt;
  onElevated: () => void;
  onClose: () => void;
  deps: CeremonyDeps;
}) {
  const codeId = useId();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [attempts, setAttempts] = useState<number | null>(null);
  /* The server's own sentence when a lock closes mid-ceremony, not a boolean:
     this modal never paraphrases a security answer, and "locked" alone cannot
     say whether the lock was already in force or was just spent. */
  const [locked, setLocked] = useState<string | null>(null);
  const [code, setCode] = useState("");
  /* Three ways the code leg opens: the owner asks for it, the device has no
     platform authenticator, or the account turns out to have no passkey
     enrolled (a 400 the begin endpoint raises, not a failed attempt). */
  const [codeOpen, setCodeOpen] = useState(false);
  const [noPasskey, setNoPasskey] = useState(!deps.passkeySupported());

  const settle = (ok: boolean, reason: string | undefined, failed?: number) => {
    setBusy(false);
    if (ok) {
      onElevated();
      return;
    }
    setAttempts(typeof failed === "number" ? failed : null);
    setFailure(reason ?? "That did not verify.");
  };

  const runPasskey = () => {
    if (busy) return;
    setBusy(true);
    setFailure(null);
    deps
      .passkey()
      .then((outcome) => {
        if (outcome.locked === true) {
          setLocked(outcome.reason ?? "That step-up did not verify.");
          return;
        }
        settle(outcome.ok, outcome.reason, outcome.failed_attempts);
      })
      .catch((raised: unknown) => {
        setBusy(false);
        const lockout = stepUpLockoutReason(raised);
        if (lockout !== null) {
          setLocked(lockout);
          return;
        }
        if (isNoPasskeyEnrolled(raised)) {
          // Not a failed attempt — the account simply has no passkey. Hand
          // over the other factor rather than reporting a verification error.
          setNoPasskey(true);
          setCodeOpen(true);
          return;
        }
        setFailure("Your device did not complete the passkey. Nothing happened.");
      });
  };

  const runTotp = () => {
    if (busy || code.trim() === "") return;
    setBusy(true);
    setFailure(null);
    deps
      .totp(code.trim())
      .then((outcome) => {
        if (outcome.locked === true) {
          setLocked(outcome.reason ?? "That code did not verify.");
          return;
        }
        settle(outcome.ok, outcome.reason, outcome.failed_attempts);
      })
      .catch((raised: unknown) => {
        setBusy(false);
        const lockout = stepUpLockoutReason(raised);
        if (lockout !== null) {
          setLocked(lockout);
          return;
        }
        setFailure("That code did not verify.");
      });
  };

  if (locked !== null) {
    return (
      <LockedOut
        prompt={{
          ...prompt,
          refusal: { ...prompt.refusal, locked: true, reason: locked },
        }}
        onClose={onClose}
      />
    );
  }

  const { summary } = statementOf(prompt);
  const tier = prompt.refusal.tier;

  return (
    <CeremonyShell label={`Prove it is you: ${summary}`} busy={busy} onClose={onClose}>
      {/* No header of this file's own on this path: the pinned block already
          carries the seal and the eyebrow, and a second gold label 40px above
          the first is how a modal starts looking like a template. */}
      <div
        className="cy-block"
        onClick={(event) => {
          // Delegation, not a prop: the pinned block stays a pure function of
          // its props and the state a WebAuthn call needs stays out here.
          const target = event.target as HTMLElement;
          if (target.closest('[data-action="use passkey"]') === null) return;
          runPasskey();
        }}
      >
        {noPasskey ? (
          <CeremonyStatement
            prompt={prompt}
            eyebrow={`PROVE IT IS YOU · ${tier}`}
            tone="certified"
          />
        ) : (
          <CertifiedStepUp component={stepUpBlock(prompt)} />
        )}
      </div>

      <RefusalReading refusal={prompt.refusal} />

      {busy && <Working>Waiting for your device. Nothing has happened yet.</Working>}

      {noPasskey && (
        <p className="cy-gap t-mono">
          No passkey is available here, so this account proves itself with a
          one-time code instead.
        </p>
      )}

      {!noPasskey && !codeOpen && (
        <button
          type="button"
          className="cy-alt"
          onClick={() => setCodeOpen(true)}
        >
          Use a one-time code instead
        </button>
      )}

      {(codeOpen || noPasskey) && (
        <form
          className="cy-code"
          onSubmit={(event) => {
            event.preventDefault();
            runTotp();
          }}
        >
          <label className="t-eyebrow" htmlFor={codeId}>
            ONE-TIME CODE
          </label>
          <div className="cy-code-row">
            <input
              id={codeId}
              className="m-well cy-code-input t-mono"
              data-deep
              value={code}
              onChange={(event) => setCode(event.target.value)}
              inputMode="numeric"
              autoComplete="one-time-code"
              spellCheck={false}
              disabled={busy}
            />
            <button
              type="submit"
              className="m-btn cy-verify"
              disabled={busy || code.trim() === ""}
            >
              Verify
            </button>
          </div>
        </form>
      )}

      {failure !== null && <Failure message={failure} attempts={attempts} />}

      <footer className="cy-foot">
        <NotNow onClose={onClose} />
        <p className="cy-note t-mono">
          Proving it is you elevates this session for a while, not for ever. It
          does not approve anything on its own.
        </p>
      </footer>
    </CeremonyShell>
  );
}

/**
 * The T3 out-of-band leg (STEWARD S7). Both legs or nothing: the nonce goes to
 * a *second* registered channel and never rides this one, which is the only
 * thing the second leg buys. The human reads it there and types it back here.
 *
 * `command_ref` is server-supplied and the nonce binds to it — a client-invented
 * reference would let one command's confirmation authorise another — so with no
 * reference there is nothing to send, and the send control is not drawn.
 */
function SecondChannelLeg({
  prompt,
  onElevated,
  onClose,
  deps,
}: {
  prompt: CeremonyPrompt;
  onElevated: () => void;
  onClose: () => void;
  deps: CeremonyDeps;
}) {
  const nonceId = useId();
  const [challenge, setChallenge] = useState<{ id: string; channel: string } | null>(
    null,
  );
  const [nonce, setNonce] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [attempts, setAttempts] = useState<number | null>(null);

  const commandRef = prompt.refusal.command_ref;
  const { summary } = statementOf(prompt);

  const send = () => {
    if (busy || commandRef === null || commandRef === "") return;
    setBusy(true);
    setFailure(null);
    void deps.oobIssue(commandRef).then((sent) => {
      setBusy(false);
      if (sent.ok && sent.challenge_id !== undefined) {
        setChallenge({
          id: sent.challenge_id,
          channel: sent.sent_to_channel ?? "your second channel",
        });
      } else {
        setFailure(sent.reason ?? "The confirmation could not be sent.");
      }
    });
  };

  const confirm = () => {
    if (busy || challenge === null || nonce.trim() === "") return;
    if (commandRef === null) return;
    setBusy(true);
    setFailure(null);
    deps
      .oobConfirm(challenge.id, commandRef, nonce.trim())
      .then((outcome) => {
        setBusy(false);
        if (outcome.ok) {
          onElevated();
          return;
        }
        setAttempts(
          typeof outcome.failed_attempts === "number" ? outcome.failed_attempts : null,
        );
        setFailure(outcome.reason ?? "That code did not verify.");
      })
      .catch(() => {
        setBusy(false);
        setFailure("That code did not verify.");
      });
  };

  return (
    <CeremonyShell label={`Confirm on a second channel: ${summary}`} busy={busy} onClose={onClose}>
      <CertifiedSecondChannelWait
        component={{
          id: "oob",
          type: "certified.second-channel-wait@1",
          props: {
            channel: challenge?.channel ?? "a second registered channel",
            command_ref: commandRef ?? "",
            command_summary: prompt.refusal.command_summary ?? prompt.summary,
          },
        }}
      />

      <RefusalReading refusal={prompt.refusal} />

      {busy && <Working>Sending on your second channel.</Working>}

      {commandRef === null || commandRef === "" ? (
        // The server refused without naming the command, so there is nothing
        // the nonce could bind to. Say that; never draw a send button that
        // would issue an unbound challenge.
        <p className="cy-gap t-mono">
          This refusal named no command, so nothing can be sent to a second
          channel. Take the act again from the surface it belongs to.
        </p>
      ) : challenge === null ? (
        <button
          type="button"
          className="m-btn cy-send"
          data-rank="certified"
          data-part="oob-send"
          disabled={busy}
          onClick={send}
        >
          <Icon name="forward" size={14} />
          Send the confirmation
        </button>
      ) : (
        <form
          className="cy-code"
          data-part="oob-confirm"
          onSubmit={(event) => {
            event.preventDefault();
            confirm();
          }}
        >
          <label className="t-eyebrow" htmlFor={nonceId}>
            THE CODE FROM {challenge.channel.toUpperCase()}
          </label>
          <div className="cy-code-row">
            <input
              id={nonceId}
              className="m-well cy-code-input t-mono"
              data-deep
              value={nonce}
              onChange={(event) => setNonce(event.target.value)}
              inputMode="numeric"
              autoComplete="one-time-code"
              spellCheck={false}
              disabled={busy}
            />
            <button
              type="submit"
              className="m-btn cy-verify"
              disabled={busy || nonce.trim() === ""}
            >
              Confirm
            </button>
          </div>
        </form>
      )}

      {failure !== null && <Failure message={failure} attempts={attempts} />}

      <footer className="cy-foot">
        <NotNow onClose={onClose} />
        <p className="cy-note t-mono">
          The code never travels over this screen. If it arrives here, it did not
          come from us.
        </p>
      </footer>
    </CeremonyShell>
  );
}
