import { useState } from "react";
import { isPasskeySupported } from "../api/authn";
import { fetchThreadHistory, type PragyaHistoryTurn } from "../api/pragya";
import { fetchTrayList, type Tray } from "../api/trays";
import { Icon } from "../components/Icon";
import {
  Bar,
  Empty,
  Failed,
  Lines,
  Scaffold,
  useResource,
  type Resource,
} from "../lifecycle";
import { TraySurface } from "../surfaces/TraySurface";
import "./thread.css";

/** A stable empty collection, for the reason `TraySurface` keeps one: a fresh
 *  `[]` per render is a new identity for no change on screen. */
const NONE: readonly Tray[] = [];

/**
 * The tier this act will be made to prove at, or `null` where it will not be.
 *
 * The §11.3 verification column, read off the block the composer struck rather
 * than re-derived: `certified_block` in `genui/trays.py` classifies the act with
 * the same `classify(intent_for_approval(...))` the gate itself uses, so this is
 * the gate's own answer arriving on the wire and not a second copy of the rules.
 */
function proves(tray: Tray): "T2" | "T3" | null {
  const tier = tray.certified.tier;
  return tier === "T2" || tier === "T3" ? tier : null;
}

/**
 * What the act is called, as the card above prints it — `""` read as absent for
 * the reason `TraySurface` gives: the registry types `summary` as a required
 * string, so a server with nothing to say sends an empty one, and a bar naming
 * an empty act is worse than a bar naming none.
 */
function summaryOf(tray: Tray): string | null {
  const value = tray.certified.props["summary"];
  if (value === null || value === undefined) return null;
  const text = String(value);
  return text === "" ? null : text;
}

/**
 * The backend's naive timestamps are UTC by construction (`created_at` is a
 * `DateTime` column defaulted to `datetime.utcnow`, serialised with
 * `isoformat()` and therefore with no offset), and `Date` parses a naive ISO
 * string as **local** time. Stamping the zone on before parsing is the
 * difference between telling a Chennai owner she wrote at 06:58 and telling
 * them she wrote at 12:28.
 */
function instantOf(iso: string): Date | null {
  const stamped = /(?:Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`;
  const at = new Date(stamped);
  return Number.isNaN(at.getTime()) ? null : at;
}

/** The turn's wall clock, in the reader's zone. `null` rather than a guess when
 *  the stamp cannot be read at all — §7.1 applies to a time as much as to a
 *  figure. */
function clockOf(iso: string): string | null {
  const at = instantOf(iso);
  if (at === null) return null;
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(at);
}

/** The day the thread reaches, read off its newest turn. An instant, so it is
 *  formatted in the reader's zone — unlike the Morning Story's `story_date`,
 *  which is a calendar date and is read in UTC. */
function dayLabel(iso: string): string | null {
  const at = instantOf(iso);
  if (at === null) return null;
  return new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(at);
}

/**
 * The Thread · the Line · C (D6 §16–18, R-3c C4) — on `GET /ai/genui/trays` and
 * `/ai/pragya/history` (R-4 part W).
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
 *    It is passed one prop besides the echo bus, and it is the one that
 *    component asked for and did not get until this round: **`renderer="C"`**.
 *    C5 wants the bus to tell a phone tap from an operator click, and
 *    `useCertifiedAct` takes the renderer as a parameter rather than sniffing
 *    for it — inferring it from the DOM or from a module global is how the two
 *    front doors would eventually agree by accident. It changes what the Tray
 *    *reports*, never what it draws, which is what keeps the byte-equality half
 *    of C4 a true statement rather than a coincidence.
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
 *    **And it names its act off the wire** (R-4 part W). It used to read the
 *    one `kind: "certified"` card out of `fixtures/estate`, which was true
 *    while the Tray read the same fixture and became a lie the moment the Tray
 *    was wired: the bar would name Meera's ₹1,84,000 release while the cards on
 *    screen were the tenant's own. So the Thread reads `GET /ai/genui/trays` —
 *    the same endpoint, through the same client function — and the bar stands
 *    under an act that is actually on the screen above it. Three rules follow
 *    from that read and each is a refusal to guess:
 *
 *    - **T2 and T3 only.** `TIER_REQUIRES` (`ai/inward_auth/sessions.py`) is the
 *      whole of it: T2 wants an ELEVATED session — a passkey — and T3 wants
 *      OOB_CONFIRMED, a code on a second channel. T0 and T1 want a bound
 *      session and nothing else, so a bar over one of those would promise a
 *      ceremony that never fires, and an owner who learns the promise is empty
 *      has learnt the wrong thing about every other one.
 *    - **Exactly one, or none.** Every tray carries a certified block now, so
 *      "the certified card" no longer picks one out. Where two acts are waiting
 *      there is no single act this bar could be bound to, and binding it to the
 *      first would be the exact confusion the ceremony's reference exists to
 *      prevent — so it renders nothing, and each card's own certified note goes
 *      on saying what taking *it* will ask for (§7.4).
 *    - **No command reference at all.** `GET /ai/genui/trays` carries none. The
 *      server mints one when it refuses — `enforce_tier(..., command_ref=
 *      f"approval:{approval_id}")` in `ai/router.py` — and `StepUpCeremony`
 *      prints that one, bound to the refusal it came with. Minting a matching
 *      string here would be the client inventing the thing that stops one
 *      command's confirmation authorising another, which `SecondChannelLeg`
 *      says in as many words. So the bar names the act and does not claim a
 *      binding it has not been given.
 *
 * 3. **The decisions are lifted out of time; the rest of the day is not.** A
 *    thread is chronological, but two approvals worth ₹2.8L do not belong
 *    underneath eleven hours of prose on a screen you read with one thumb. So
 *    what needs you is pinned first and the narrative runs newest-first below
 *    it — a phone is opened to catch up, not to re-read — and nothing scrolls
 *    itself, because a surface that moves under your thumb on open is a surface
 *    that has lost your place before you found it.
 *
 *    **The day is `/ai/pragya/history` now** (R-4 part W), and that read took
 *    two compositions away with it. The seam returns a role, the words of the
 *    turn and when it was written, and nothing else — so the **story card** (a
 *    title, a template, and a figure in a well off `kpi.current` /
 *    `records.aggregate` / `runs.history` / `approval.detail`) and the **voice
 *    note** (a gold seam and the length of a recording) are two shapes it
 *    cannot answer. §7.1 says a binding that produced nothing renders nothing,
 *    so both are deleted rather than filled with something plausible — the same
 *    call `StandupSurface` made about the five blocks its own endpoint does not
 *    carry — and `.th-turns-note` states the absence once, quietly, where the
 *    turns are. Nothing here composes a title for a paragraph or a figure out
 *    of one.
 *
 *    **And the thread has two speakers, which the fixture did not.** The
 *    history is the conversation, so the owner's own turns arrive beside hers.
 *    That is not a breach of L3 and the lead says why: nobody but Pragya writes
 *    *to* you. They take her shape with the speaker named rather than a second
 *    material, because a reader's own words are not a different kind of fact.
 *
 * 4. **The surface has one `<h1>` and it is the Tray's.** The document outline
 *    says the same thing the layout does: the thing that needs you is the title
 *    of this screen, and it is titled by the component that owns it. The day
 *    below it is an `<h2>` in all four of its states, including the two — empty
 *    and failed — that only became reachable when it came off a constant.
 */
export function ThreadSurface({ onEcho }: { onEcho: (msg: string) => void }) {
  /* The same list the Tray below is showing, off the same endpoint. Two reads
     of one resource rather than one read shared between them, because the
     alternative is handing `TraySurface` its collection as a prop — and the
     moment the Line can feed the Tray something the desk cannot, "the component,
     mounted" (R-3c C4) stops being a property anyone can check.

     A failure here is deliberately silent: the Tray is reading the same
     endpoint and renders `Failed` for it with a retry. A second copy of that
     news, in a bar whose subject is a ceremony, would read as the ceremony
     having failed. */
  const trays = useResource(fetchTrayList);
  const list = trays.phase === "ready" ? trays.value : NONE;
  const history = useResource(fetchThreadHistory);

  /* Carried as a pair rather than filtered and re-classified at the render:
     the tier the bar prints has to be the one that decided the act belongs
     here, not a second reading of the same field. */
  const asking = list.flatMap((tray) => {
    const tier = proves(tray);
    return tier === null ? [] : [{ tray, tier }];
  });
  const only = asking.length === 1 ? asking[0] : undefined;

  /* The server's own re-render, which is what this line always said it was
     waiting for. The bar used to go when the echo sentence happened to contain
     the card's id — true of the fixture Tray's `"Release the payment · HITL-8841"`
     and false of the wired one, which echoes §8's form ("approved Meera's run")
     and carries the id on `action_ref.params.subject` where an id belongs. So
     the Thread stops reading prose for facts: an act taken above is an act
     answered on the server, and the way to know whether it is still waiting is
     to ask the endpoint that lists what is waiting.

     The bar is absent while that read is in flight, and that is not a flicker to
     be smoothed over — between the two reads this surface does not know whether
     the act is still owed, and a ceremony offered on a stale measurement is the
     thing this whole block exists to prevent. */
  const reread = trays.phase === "pending" ? undefined : trays.retry;
  const relay = (msg: string) => {
    reread?.();
    onEcho(msg);
  };

  return (
    <section className="th" aria-label="Pragya’s thread">
      <header className="th-head">
        {/* No day here any more. It used to be a constant, and the honest source
            for it is the newest turn — which the section below owns, and which
            may not exist at all. Naming a day at the top of a thread nothing has
            been said in would be a date on which nothing happened. */}
        <span className="t-eyebrow">THE THREAD</span>
        {/* L3 said in words, on the surface — the same way the Standup says L2.
            A promise the product keeps but never mentions is a promise nobody
            can rely on. */}
        <p className="th-lead t-narrative">
          Every line here that is not yours is mine. Your colleagues prepare what
          I say and none of them can write to you, so there is one thread to read
          and one voice in it.
        </p>
      </header>

      {/* ======================================================= what needs you
          `TraySurface` itself. See decision 1 — this is the round's invariant,
          and the reason the Line cannot be a separate app that merely looks
          similar. */}
      <div className="th-certified m-ticks">
        <div className="th-tray">
          {/* `renderer="C"` is the prop this component asked for and did not
              get until now: C5 wants the echo bus to tell a phone tap from an
              operator click, and the hook takes the renderer as a parameter
              rather than sniffing for it. It changes what the Tray *reports*,
              never what it draws — which is what keeps the byte-equality half
              of C4 a true statement. */}
          <TraySurface onEcho={relay} renderer="C" />
        </div>

        {only !== undefined && (
          <StepUpBar tier={only.tier} commandSummary={summaryOf(only.tray)} />
        )}
      </div>

      <hr className="m-rule-fade th-rule" />

      {/* ========================================================= the day told */}
      <Day history={history} />
    </section>
  );
}

/* ---------------------------------------------------------------- the day -- */

/**
 * Her day, in four states.
 *
 * The heading is outside every branch on purpose: it is the section's name
 * whether or not the section has anything in it, and a room that loses its
 * label while it is loading has moved under the reader between two frames.
 */
function Day({ history }: { history: Resource<PragyaHistoryTurn[]> }) {
  if (history.phase === "pending") {
    return (
      <section className="th-turns" aria-labelledby="th-earlier">
        <h2 className="t-eyebrow" id="th-earlier">
          EARLIER
        </h2>
        <Scaffold label="The thread">
          {/* Plates first, bars inside them. `vh-skeleton`'s ground is a ~6/255
              delta on the raw canvas, so a bar laid straight on the background
              draws nothing at all and the pending state would be a blank
              column — which on the Line is the whole screen below the fold. */}
          <div className="th-list">
            {[0, 1, 2].map((i) => (
              <div className="th-ghost m-plate" key={i}>
                <Bar width="xs" />
                <Lines n={i === 0 ? 3 : 2} />
              </div>
            ))}
          </div>
        </Scaffold>
      </section>
    );
  }

  if (history.phase === "failed") {
    return (
      <section className="th-turns" aria-labelledby="th-earlier">
        <h2 className="t-eyebrow" id="th-earlier">
          EARLIER
        </h2>
        {/* `alone={false}`: the Tray above is still working and still taking
            acts, so this is one block that failed and not the screen. */}
        <Failed
          what="the thread"
          reason={history.reason}
          onRetry={history.retry}
          alone={false}
        />
      </section>
    );
  }

  const turns = history.value;

  if (turns.length === 0) {
    return (
      <section className="th-turns" aria-labelledby="th-earlier">
        <h2 className="t-eyebrow" id="th-earlier">
          EARLIER
        </h2>
        {/* L2. An empty thread is what a tenant sees before they have ever
            spoken to her, and it must not read as a screen that failed. */}
        <Empty
          icon="thread"
          title="Nothing has been said yet."
          body="This is the one thread in the product and there is nothing in it. Your colleagues cannot write to you at all — everything here is Pragya relaying what they did — so an empty thread means a quiet estate, not a lost message."
        />
      </section>
    );
  }

  /* Newest first: a phone is opened to catch up, not to re-read. The endpoint
     returns oldest-first — conversation order, which is the right order for a
     conversation and the wrong one for a catch-up — so the reversal is this
     surface's own decision and not a shape the wire imposed. */
  const newest = [...turns].reverse();
  const day = dayLabel(newest[0]!.at);

  return (
    <section className="th-turns" aria-labelledby="th-earlier">
      <h2 className="t-eyebrow" id="th-earlier">
        EARLIER{day !== null && ` · ${day.toUpperCase()}`}
      </h2>
      {/* The gap, stated once and quietly (§7.4). The conversation seam carries
          a role, the words and a timestamp; a story card's figure and a voice
          note's duration are not on it, so nothing below is drawn around a
          number this surface would have had to compose. */}
      <p className="th-turns-note t-mono">
        Newest first, and every turn is the words themselves. The history keeps
        no recording and no figure of its own, so nothing here is drawn around a
        number.
      </p>

      <ol className="th-list vh-stagger">
        {newest.map((turn, i) => (
          <li
            key={`${turn.at}·${i}`}
            className="th-turn"
            style={{ ["--i" as string]: i }}
          >
            <Turn turn={turn} />
          </li>
        ))}
      </ol>
    </section>
  );
}

/**
 * One turn.
 *
 * Her ground state is bare prose and no plate: most of what she says does not
 * need an object drawn around it, and a thread where every line is a card is a
 * list. The owner's own turns take the same shape with the speaker named —
 * `role` is `user` or `pragya` and anything this client has not met is read as
 * the owner's rather than as hers, because attributing an unknown speaker to
 * Pragya is the one direction of that mistake that breaks L3.
 */
function Turn({ turn }: { turn: PragyaHistoryTurn }) {
  const yours = turn.role !== "pragya";
  const at = clockOf(turn.at);

  return (
    <div className="th-note" data-yours={yours || undefined}>
      <p className="th-note-head">
        <span className="t-eyebrow">{yours ? "YOU" : "PRAGYA"}</span>
        {/* Absent rather than a placeholder where the stamp cannot be read. */}
        {at !== null && <span className="th-when t-mono">{at}</span>}
      </p>
      <p className="th-prose t-narrative">{turn.content}</p>
    </div>
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
 *
 * **The two tiers ask for different things and the bar says which.** With the
 * tier coming off the wire rather than off a one-row fixture, T3 is reachable
 * here for the first time, and `StepUpCeremony` sends it to `SecondChannelLeg`:
 * a code issued to a *second* registered channel and typed back, never a
 * passkey on this phone. So a T3 bar that said "this phone cannot ask" would
 * report a capability the act does not want, and one that promised a passkey
 * would name the wrong factor — on the one surface whose subject is which
 * factor is about to be asked for.
 */
function StepUpBar({
  tier,
  commandSummary,
}: {
  tier: "T2" | "T3";
  /** Null where the server sent an empty `summary` — §7.1, no line rather than
   *  a labelled blank. */
  commandSummary: string | null;
}) {
  const [canAsk] = useState(isPasskeySupported);
  /* Only the passkey leg depends on this browser. The second channel is the
     estate's, and any phone that can be typed into can answer it. */
  const ready = tier === "T3" || canAsk;

  return (
    <div className="th-step m-well">
      <p className="th-step-head">
        {/* Never colour alone: the lamp is the fast read, the word beside it is
            the correct one. Unlit for ready — a lit lamp is a raised hand, and
            this bar is not asking for anything. */}
        <span className="m-lamp" data-negative={!ready || undefined} />
        <span className="t-eyebrow" data-certified>
          STEP-UP · {tier}
        </span>
        <span className="th-step-state t-mono">
          {tier === "T3"
            ? "a second channel is asked"
            : canAsk
              ? "this phone can ask"
              : "this phone cannot ask"}
        </span>
      </p>

      <p className="th-step-line t-narrative">
        {tier === "T3"
          ? "Taking the gold path above sends a code to a second channel you have registered and asks you to type it back here — at the moment you decide and never before. No key is asked of this phone, so it does not matter what this phone can hold."
          : canAsk
            ? "Taking the gold path above asks this phone for your passkey — the same key the desk asks for, at the moment you decide and never before."
            : "This browser cannot ask for a passkey, so the gold path above cannot be finished here. It will have to be finished at the desk."}
      </p>

      {/* Which act, and no more than that. The reference the confirmation binds
          to is minted by the server at the moment it refuses and is printed by
          the ceremony that carries it; the list this bar reads carries none, and
          a matching string composed here would be exactly the client-invented
          reference `SecondChannelLeg` refuses to send a nonce against. */}
      {commandSummary !== null && (
        <p className="th-step-bound t-mono">
          <Icon name="key" size={12} />
          <span className="th-step-cmd">{commandSummary}</span>
        </p>
      )}
    </div>
  );
}
