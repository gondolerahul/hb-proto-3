/**
 * The steward's dock (STEWARD S6/S7/S8) — app-owned chrome, never
 * manifest-composed: her presence mark, her narration with its anchors,
 * the way to talk to her (typed or spoken), and the ceremonies she asks
 * for. Never a face, never a floating avatar (D7's presence row) — in the
 * territory she is the beam; here she is a mark and her words.
 *
 * The ceremony rule is VG-05's, kept: a `step_up` on a narration opens
 * the SAME StepUpCeremony every certified surface uses, elevation runs
 * only through /ai/authn/*, and the retry is the whole utterance resent
 * once — no second success path.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import type { StepUpRefusal } from "../api/authn";
import {
  StepUpCeremony,
  type CeremonyDeps,
} from "../components/certified/StepUpCeremony";
import { connectChannel, type StewardEvent, type StewardHandle } from "./channel";
import {
  INITIAL_STEWARD_STATE,
  reduceSteward,
  setConnected,
  type StewardState,
} from "./state";
import {
  createMicCapture,
  createPcmPlayer,
  type MicCapture,
  type MicHandlers,
  type PcmPlayer,
} from "./voice";

export interface Navigation {
  type: "focus" | "materialize";
  surfaceId?: string;
  district?: string;
}

export interface StewardDeps {
  connect: typeof connectChannel;
  mic: (handlers: MicHandlers) => Promise<MicCapture | null>;
  player: () => PcmPlayer | null;
  ceremony?: CeremonyDeps;
}

const REAL: StewardDeps = {
  connect: connectChannel,
  mic: createMicCapture,
  player: createPcmPlayer,
};

/** What the shell needs to hear from the channel. */
export interface StewardShellProps {
  onNavigate: (navigation: Navigation) => void;
  onTrayDelivered?: () => void;
  /** The shell's current place, reported as the viewport (rule 2: it is
   * the client's job to send it on every depth change). */
  depthLevel: number;
  contextRef: Record<string, unknown>;
  deps?: StewardDeps;
}

function refusalFromAsk(
  ask: { tier: string | null; command_ref: string | null; oob: boolean },
  summary: string,
): StepUpRefusal {
  return {
    error: "step_up_required",
    tier: ask.tier ?? "T2",
    why: summary,
    reason: summary,
    needs_step_up: !ask.oob,
    needs_oob: ask.oob,
    locked: false,
    command_ref: ask.command_ref,
    command_summary: summary,
  };
}

export function StewardDock({
  onNavigate,
  onTrayDelivered,
  depthLevel,
  contextRef,
  deps = REAL,
}: StewardShellProps): JSX.Element {
  const [state, setState] = useState<StewardState>(INITIAL_STEWARD_STATE);
  const [draft, setDraft] = useState("");
  const [micOn, setMicOn] = useState(false);
  const handle = useRef<StewardHandle | null>(null);
  const capture = useRef<MicCapture | null>(null);
  const player = useRef<PcmPlayer | null>(null);
  const lastUtterance = useRef<string | null>(null);
  const speakingRef = useRef(false);
  const navigateRef = useRef(onNavigate);
  navigateRef.current = onNavigate;
  const trayRef = useRef(onTrayDelivered);
  trayRef.current = onTrayDelivered;

  useEffect(() => {
    const channel = deps.connect({
      onEvent: (event: StewardEvent) => {
        if (event.type === "focus") {
          navigateRef.current({
            type: "focus",
            district: event.target_ref.id,
          });
        } else if (event.type === "materialize") {
          navigateRef.current({
            type: "materialize",
            surfaceId: event.surface_id,
          });
        } else if (event.type === "deliver_tray") {
          trayRef.current?.();
        }
        if (event.type === "presence") {
          speakingRef.current = event.state === "speaking";
          if (event.state !== "speaking") player.current?.stop();
        }
        setState((previous) => reduceSteward(previous, event));
      },
      onAudio: (frame) => {
        player.current?.enqueue(frame);
      },
      onConnected: (connected) => {
        setState((previous) => setConnected(previous, connected));
      },
    });
    handle.current = channel;
    return () => {
      capture.current?.stop();
      player.current?.close();
      channel.close();
    };
    // The channel outlives renders; deps are stable by contract.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Rule 2: the viewport rides every depth change.
  useEffect(() => {
    handle.current?.reportDepth(depthLevel);
    handle.current?.reportViewport(contextRef);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [depthLevel, JSON.stringify(contextRef)]);

  const say = useCallback((text: string) => {
    const trimmed = text.trim();
    if (trimmed === "") return;
    lastUtterance.current = trimmed;
    handle.current?.say(trimmed);
  }, []);

  const toggleMic = useCallback(() => {
    if (micOn) {
      capture.current?.stop();
      capture.current = null;
      handle.current?.micClosed();
      setMicOn(false);
      return;
    }
    void deps.mic({
      onFrame: (frame) => handle.current?.sendAudio(frame),
      onSpeech: () => {
        // Client-side barge-in: she stops here first, the server at the
        // next chunk.
        if (speakingRef.current) {
          player.current?.stop();
          handle.current?.micOpen();
        }
      },
    }).then((mic) => {
      if (mic === null) return; // no mic in this browser — button stays off
      capture.current = mic;
      player.current = player.current ?? deps.player();
      handle.current?.micOpen();
      setMicOn(true);
    });
  }, [micOn, deps]);

  const ask = state.stepUpAsk;
  const summary = lastUtterance.current ?? "the last command";

  return (
    <aside className="vh-steward-dock" data-part="steward-dock">
      <div
        className="vh-presence-mark"
        data-part="presence"
        data-state={state.connected ? state.presence : "off"}
        aria-label={`Pragya is ${state.connected ? state.presence : "away"}`}
      >
        ◐
      </div>
      <div className="vh-steward-lines" data-part="narration">
        {state.lines.map((line, index) => (
          <p
            key={`${index}-${line.text.slice(0, 16)}`}
            className={line.kind === "error" ? "vh-problem" : "vh-steward-line"}
          >
            {line.text}
            {line.anchors.map((anchor) => (
              <button
                key={anchor.ref}
                type="button"
                className="vh-quiet-link"
                data-part="anchor"
                onClick={() => {
                  if (anchor.kind === "district") {
                    navigateRef.current({
                      type: "focus",
                      district: anchor.ref,
                    });
                  } else if (anchor.kind === "tray") {
                    trayRef.current?.();
                  }
                }}
              >
                {anchor.label}
              </button>
            ))}
          </p>
        ))}
        {state.transcript !== null && (
          <p className="vh-quiet" data-part="transcript">
            {state.transcript.text}
            {state.transcript.final ? "" : "…"}
          </p>
        )}
      </div>
      <form
        data-part="say"
        onSubmit={(event) => {
          event.preventDefault();
          say(draft);
          setDraft("");
        }}
      >
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={state.connected ? "ask Pragya" : "connecting…"}
          aria-label="ask Pragya"
        />
        <button type="submit" disabled={!state.connected}>
          say
        </button>
        <button
          type="button"
          data-part="mic-toggle"
          aria-pressed={micOn}
          onClick={toggleMic}
        >
          {micOn ? "mic off" : "mic"}
        </button>
      </form>
      {ask !== null && (
        <StepUpCeremony
          refusal={refusalFromAsk(ask, summary)}
          deps={deps.ceremony}
          onElevated={() => {
            handle.current?.reportStepUp(ask.tier, true);
            setState((previous) => ({ ...previous, stepUpAsk: null }));
            // Retry the WHOLE utterance once — the certified-act rule; the
            // gate re-checks the real tier server-side on the re-run.
            const retry = lastUtterance.current;
            if (retry !== null) {
              lastUtterance.current = null;
              handle.current?.say(retry);
            }
          }}
          onClose={() =>
            setState((previous) => ({ ...previous, stepUpAsk: null }))
          }
        />
      )}
    </aside>
  );
}
