import { useState } from "react";
import { isPasskeySupported } from "../api/authn";
import { Icon } from "../components/Icon";
import { TRAY } from "../fixtures/estate";
import { THREAD, THREAD_DAY, STEP_UP, type ThreadTurn } from "../fixtures/thread";
import { TraySurface } from "../surfaces/TraySurface";
import "./thread.css";

/**
 * The Thread · the Line · C (D6 §16–18, R-3c C4).
 *
 * Pragya's thread and nothing else. There are no per-agent threads here and
 * there is no way to open one, because L3 is not a default the surface picks —
 * it is the property that keeps notification discipline enforceable. A tenant
 * who can be addressed by twelve colleagues has twelve channels to mute and
 * will mute the wrong one.
 *
 * Four decisions a reader would otherwise have to reverse-engineer.
 *
 * 1. **The certified section is `TraySurface`. The component, mounted.** Not a
 *    phone-shaped imitation, not a compact variant, not a fork. If the Line drew
 *    a certified act differently from where it is approved, the step-up beside
 *    it would be a picture of a security control, and `tests/line.test.tsx`
 *    holds the identity rather than leaving it to convention. The only thing
 *    `thread.css` is allowed to change about it is **geometry** — the room it
 *    sits in and the 44px touch floor a phone owes it (§6). No colour, no type,
 *    no material: those are what "the same act" means.
 *
 * 2. **The step-up bar sits under the paths, not over them, and it draws no
 *    fingerprint.** A ceremony you pass *before* deciding has already granted
 *    the elevation by the time you decide, which is the shape step-up exists to
 *    prevent; so the bar states what taking a gold path will ask for and asks
 *    for nothing itself. And the prompt belongs to the platform — in an
 *    installed PWA it is Face or Touch ID — so the bar reports whether this
 *    browser can raise it and otherwise stays out of the way. A fingerprint we
 *    drew ourselves would look exactly like the real one and mean nothing.
 *
 * 3. **The decisions are lifted out of time; the rest of the day is not.** A
 *    thread is chronological, but two approvals worth ₹2.8L do not belong
 *    underneath eleven hours of prose on a screen you read with one thumb. So
 *    what needs you is pinned first and the narrative runs newest-first below
 *    it — a phone is opened to catch up, not to re-read — and nothing scrolls
 *    itself, because a surface that moves under your thumb on open is a surface
 *    that has lost your place before you found it.
 *
 * 4. **The surface has one `<h1>` and it is the Tray's.** The document outline
 *    says the same thing the layout does: the thing that needs you is the title
 *    of this screen, and it is titled by the component that owns it.
 */
export function ThreadSurface({ onEcho }: { onEcho: (msg: string) => void }) {
  /* The one certified card waiting. Read off the estate's own tray fixture, not
     copied into `fixtures/thread.ts`, so the ceremony below cannot be made to
     name a different act than the one it authorises. */
  const certified = TRAY.find((c) => c.kind === "certified");
  const stepUp = certified ? STEP_UP[certified.id] : undefined;

  /* The Tray owns whether a card is still waiting, and the echo it fires when a
     path is taken carries that card's id. The Thread listens on that channel
     rather than keeping a second copy of the Tray's state: two copies drift, and
     the one that drifts here is a step-up bar standing under a command that has
     already been settled. R-4 replaces this with the server's own re-render. */
  const [settled, setSettled] = useState(false);
  const relay = (msg: string) => {
    if (certified && msg.includes(certified.id)) setSettled(true);
    onEcho(msg);
  };

  return (
    <section className="th" aria-label="Pragya’s thread">
      <header className="th-head">
        <span className="t-eyebrow">
          THE THREAD · {THREAD_DAY.label.toUpperCase()}
        </span>
        {/* L3 said in words, on the surface — the same way the Standup says L2.
            A promise the product keeps but never mentions is a promise nobody
            can rely on. */}
        <p className="th-lead t-narrative">
          Every line here is mine. Your colleagues prepare what I say and none of
          them can write to you, so there is one thread to read and one voice in
          it.
        </p>
      </header>

      {/* ======================================================= what needs you
          `TraySurface` itself. See decision 1 — this is the round's invariant,
          and the reason the Line cannot be a separate app that merely looks
          similar. */}
      <div className="th-certified m-ticks">
        <div className="th-tray">
          <TraySurface onEcho={relay} />
        </div>

        {certified && stepUp && !settled && (
          <StepUpBar
            tier={stepUp.tier}
            commandRef={stepUp.commandRef}
            commandSummary={certified.title}
          />
        )}
      </div>

      <hr className="m-rule-fade th-rule" />

      {/* ========================================================= the day told */}
      <section className="th-turns" aria-labelledby="th-earlier">
        <h2 className="t-eyebrow" id="th-earlier">
          EARLIER TODAY
        </h2>
        <p className="th-turns-note t-mono">
          Newest first. Where she spoke, the recording stays in the morning story
          and the words are written out here.
        </p>

        <ol className="th-list vh-stagger">
          {[...THREAD].reverse().map((turn, i) => (
            <li key={turn.id} className="th-turn" style={{ ["--i" as string]: i }}>
              <Turn turn={turn} />
            </li>
          ))}
        </ol>
      </section>
    </section>
  );
}

/** 41 → "0:41". The channel reports the recording's length; the thread prints
 *  it and rounds nothing — a duration is a measurement. */
function spoken(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${(seconds % 60).toString().padStart(2, "0")}`;
}

function Turn({ turn }: { turn: ThreadTurn }) {
  if (turn.kind === "note") {
    /* Her ground state. No plate: most of what she says does not need an object
       drawn around it, and a thread where every line is a card is a list. */
    return (
      <div className="th-note">
        <span className="th-when t-mono">{turn.at}</span>
        <p className="th-prose t-narrative">{turn.text}</p>
      </div>
    );
  }

  if (turn.kind === "voice") {
    /* The gold seam is §2.1's sanctioned "Pragya's beam while narrating", spent
       only on the turns she actually spoke — which is what makes it information
       rather than decoration, and keeps the budget at two hairlines a day. Same
       device the Tray uses for her words (tray.css `.tr-because`). */
    return (
      <div className="th-voice">
        <p className="th-voice-head">
          <span className="t-eyebrow">VOICE NOTE</span>
          <span className="th-when t-mono">
            {turn.at} · {spoken(turn.seconds)}
          </span>
        </p>
        <p className="th-prose t-narrative">{turn.text}</p>
      </div>
    );
  }

  return (
    <article className="th-card m-plate">
      <header className="th-card-head">
        <span className="t-eyebrow">STORY</span>
        <span className="th-when t-mono">{turn.at}</span>
      </header>
      <h3 className="th-card-title t-display">{turn.title}</h3>

      {/* §7.1 — where the binding produced nothing, the card renders nothing.
          Never a zero, never a dash. The template below is written to stand up
          without it, and on TH-5 it says why the figure is missing. */}
      {turn.figure && (
        <div className="m-well th-fig">
          <span className="th-fig-val t-figure">{turn.figure.value}</span>
          <span className="th-fig-label t-eyebrow">{turn.figure.label}</span>
        </div>
      )}

      <p className="th-prose t-narrative">{turn.template}</p>
    </article>
  );
}

/**
 * `certified.step-up@1` — the bar, not the ceremony.
 *
 * The registry gives this component `role="dialog"`, and on the desk that is
 * right: the ceremony interrupts. Here it would be a lie. The prompt on a phone
 * is the platform's own sheet, raised by `navigator.credentials.get` at the
 * moment a gold path is taken, so what the Line owes the person is the two
 * sentences a dialog cannot say in advance — which key will be asked for, and
 * whether this browser can ask for it at all.
 *
 * `isPasskeySupported()` is read once, at mount: it is a capability of the
 * browser, and a bar that changed its mind about that mid-session would read as
 * a fault. Where the answer is no, the surface renders the gap rather than
 * drawing a working ceremony over a known absence (§7.4).
 */
function StepUpBar({
  tier,
  commandRef,
  commandSummary,
}: {
  tier: "T2" | "T3";
  commandRef: string;
  commandSummary: string;
}) {
  const [canAsk] = useState(isPasskeySupported);

  return (
    <div className="th-step m-well">
      <p className="th-step-head">
        {/* Never colour alone: the lamp is the fast read, the word beside it is
            the correct one. Unlit for ready — a lit lamp is a raised hand, and
            this bar is not asking for anything. */}
        <span className="m-lamp" data-negative={!canAsk || undefined} />
        <span className="t-eyebrow" data-certified>
          STEP-UP · {tier}
        </span>
        <span className="th-step-state t-mono">
          {canAsk ? "this phone can ask" : "this phone cannot ask"}
        </span>
      </p>

      <p className="th-step-line t-narrative">
        {canAsk
          ? "Taking the gold path above asks this phone for your passkey — the same key the desk asks for, at the moment you decide and never before."
          : "This browser cannot ask for a passkey, so the gold path above cannot be finished here. It will have to be finished at the desk."}
      </p>

      {/* What the ceremony is bound to. The ref is the server's, and it is what
          stops one command's confirmation from authorising another — so it is
          printed beside the act rather than kept out of sight. */}
      <p className="th-step-bound t-mono">
        <Icon name="key" size={12} />
        <span className="th-step-ref">{commandRef}</span>
        <span className="th-step-cmd">{commandSummary}</span>
      </p>
    </div>
  );
}
