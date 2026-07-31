import { useCallback, useEffect, useRef, useState } from "react";
import { fetchMorningStory, type MorningCard, type MorningStory } from "../api/line";
import { Icon } from "../components/Icon";
import { Portrait } from "../components/Portrait";
import { Bar, Empty, Failed, Lines, Scaffold, useChoice, useResource } from "../lifecycle";
import "./morning.css";

/**
 * The Morning Story · the Line · C (D6 §16–18, R-3c C5) — on
 * `GET /ai/genui/line/morning` (R-4 part W).
 *
 * The Standup in the pocket. `StandupSurface.tsx` is the same composition on the
 * desk and the two are one product — same colleagues, same counts, same rule
 * that **every line is Pragya's** (L2) — and after this round that is true of
 * the data as well as the layout. `morning.py`'s own docstring is why: the
 * composition was ported server-side so that *"the sentences here and in
 * `StandupSurface.tsx` must tell the same story; if the two ever drift, the
 * phone and the desk disagree about yesterday"*. One endpoint, so they cannot.
 *
 * What still separates the two surfaces is register, and it is a real
 * distinction rather than a styling one: the desk's Standup is a live view, and
 * this is *the morning's telling*, made once at 02:25 and read later. The header
 * states which of the two it is holding, in words, because `morning.py` serves a
 * stored row when the job wrote one and composes fresh when it did not — and a
 * recording that presents itself as live is a surface lying about its own
 * freshness.
 *
 * Three decisions a reader would otherwise have to reverse-engineer.
 *
 * 1. **The voice slot is a fixed part of every card, and the degradation lives
 *    in it.** A card whose clip never came back does not lose a control — the
 *    same well, in the same place, holds the reason instead. That is why there
 *    is no disabled play button and no header-level apology: the absence is
 *    stated where its consequence is, on the card that is text. The header only
 *    carries the *shape* of the morning (how many cards lost their voice); the
 *    card carries the *reason*. Neither repeats the other.
 *
 * 2. **Her sentences are joined into one paragraph, not listed.** `spoken_text`
 *    in the job is `f"{name}. " + " ".join(sentences)` — the clip says exactly
 *    this, joined exactly this way. A bulleted list would make the eye and the
 *    ear disagree about the same telling.
 *
 * 3. **The pips are an indicator, not a control.** On the desk each pip is a
 *    button because a mouse is precise. At 390px five tappable pips are five
 *    mis-taps, and the touch floor here is 44px, so navigation is the thumb, two
 *    44px controls and the arrow keys — and the pips only report where you are.
 *
 * ## What the wiring closed
 *
 * **The rail counted a deck it did not have.** With no cards it printed
 * `1 of 0`, stepped a `Math.min/Math.max` over an empty list and offered two
 * disabled controls for a story with nothing in it — a fabricated count, which
 * §7.1 forbids more strictly than it forbids a blank. An empty morning is now a
 * designed state with no rail at all, and it is a state a real tenant reaches:
 * `compose_morning_story` walks the estate's colleagues, so a company that has
 * hired nobody has a story with no cards in it and nothing has gone wrong.
 *
 * **`generated_at` is stamped before it is parsed.** The column is a naive
 * `DateTime` serialised with `isoformat()`, and `Date` reads a naive string as
 * *local* — so the un-stamped read told a Chennai owner their 07:55 morning was
 * written at 02:25, in the middle of the night. The story's *date* is not
 * stamped and is read in UTC instead, because `story_date` is a calendar date
 * and localising it moves the day either side of midnight.
 *
 * **The degrade path is now the common one.** A tenant whose 02:25 job has not
 * run gets a fresh composition, and `morning.py` fills every card's `audio` with
 * `None` and names the absence `not_generated` rather than going quiet. So the
 * all-text morning is not an edge case to survive; it is what most mornings look
 * like, and the four sentences below are the surface.
 *
 * The one commented exception to DESIGN_CONTRACT §1.4 (no inline style beyond
 * the stagger index) is the live drag offset, `--mo-drag`. A thumb's position is
 * measured at 60 Hz, not designed: it is the one value that cannot live in a
 * stylesheet, and routing it through React state would re-render the deck every
 * frame *and* still be an inline style. It is written straight to the element
 * and removed the moment the finger lifts.
 */

/** Gesture distances in device pixels — a thumb's travel, not the design grid,
 *  which is why they are numbers here and not `--s-N`. */
const AXIS_PX = 10; // below this the gesture has no direction yet
const SWIPE_PX = 56; // above this the card was let go of, not nudged

/** The four `degraded_reason` values `morning_job.py` and `morning.py` can
 *  write, and nothing else — `not_configured` when no speech row resolves,
 *  `wallet` when the balance cannot cover the synthesis, `tts_failed` on the
 *  first exception mid-story, `not_generated` when the 02:25 job never ran and
 *  the story was composed on read. */
export type DegradedReason = "wallet" | "not_configured" | "tts_failed" | "not_generated";

/** What the job records, said as the sentence the owner needs. Every branch is
 *  here because every branch can arrive.
 *
 *  Exported because it is a content contract, not an implementation detail:
 *  `tests/line.test.tsx` asserts the surface states the reason the job actually
 *  reported rather than one sentence that would fit all four, and a test that
 *  re-typed these strings would only be checking its own copy of them. */
export const UNVOICED: Record<DegradedReason, string> = {
  wallet:
    "The wallet could not cover her voice this morning. The telling is the same; only the sound is missing.",
  not_configured:
    "Speech has never been set up on this account, so no morning here has been voiced.",
  tts_failed:
    "Her voice failed part-way through the telling. Everything from this card on is text.",
  not_generated:
    "This morning’s telling has not run. What you are reading was composed just now, from the estate as it stands.",
};

/** A silent card on a clean row is reachable: the job only records a reason when
 *  synthesis *raised*, so a speaker that returns an empty stream leaves the card
 *  without a clip and the row without an explanation. Saying so is the only true
 *  sentence available, and it beats borrowing one of the four above. */
const UNVOICED_UNSTATED =
  "No clip came back for this card, and the morning did not record why.";

/**
 * The reason this card has no clip, or `null` where it has one.
 *
 * A reason the server sent that this client has no sentence for is **printed as
 * itself**, never mapped onto the nearest of the four. Substituting a neighbour
 * would put a specific and wrong explanation on screen, which is worse than the
 * vague and true one — and the code is the only thing here that is checkable
 * against the row that produced it.
 */
function unvoicedReason(card: MorningCard, degraded: string | null): string | null {
  if (card.audio !== null) return null;
  if (degraded === null) return UNVOICED_UNSTATED;
  const known = UNVOICED[degraded as DegradedReason];
  if (known !== undefined) return known;
  return `The morning recorded a reason for the missing voice that this app has no sentence for: ${degraded}.`;
}

/**
 * The backend's naive timestamps are UTC by construction (`generated_at` is a
 * `DateTime` column written from `datetime.utcnow` and serialised with
 * `isoformat()`), and `Date` parses a naive ISO string as **local** time. The
 * cron fires at 02:25 UTC; the owner reads this at breakfast in Chennai, where
 * that instant is 07:55, and printing the un-stamped hour would tell them their
 * morning was written in the middle of the night.
 */
function clockOf(iso: string): string | null {
  const stamped = /(?:Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`;
  const at = new Date(stamped);
  if (Number.isNaN(at.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(at);
}

/** The story's date is a calendar date, not an instant. Formatting it in the
 *  reader's zone moves it a day either side of midnight, so it is read in UTC
 *  and only the *time* of the telling is localised. Unparseable → nothing. */
function dayLabel(isoDate: string): string | null {
  const at = new Date(`${isoDate}T00:00:00Z`);
  if (Number.isNaN(at.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: "UTC",
  }).format(at);
}

export function MorningStorySurface({ onEcho }: { onEcho: (msg: string) => void }) {
  const story = useResource(fetchMorningStory);

  if (story.phase === "pending") {
    return (
      <section className="mo">
        <Scaffold label="This morning’s story">
          {/* Plates first, and **every** bar inside one: `vh-skeleton`'s ground
              is a ~6/255 delta on the raw canvas, so a bar laid over the page
              background draws nothing at all. The header's own bars are the
              trap — the real header is prose on the canvas, so ghosting it
              would have drawn three invisible lines and called it a scaffold.
              The deck is one card wide, so the ghost is one card. */}
          <div className="mo-ghost">
            <div className="mo-card m-plate">
              <Bar width="xs" />
              <Bar width="sm" tall />
              <Lines n={3} />
              <div className="m-well mo-voice">
                <Bar width="xs" />
              </div>
            </div>
          </div>
        </Scaffold>
      </section>
    );
  }

  if (story.phase === "failed") {
    return (
      <section className="mo">
        <Failed
          what="this morning’s story"
          reason={story.reason}
          onRetry={story.retry}
        />
      </section>
    );
  }

  return <Deck story={story.value} onEcho={onEcho} />;
}

function Deck({
  story,
  onEcho,
}: {
  story: MorningStory;
  onEcho: (msg: string) => void;
}) {
  const cards = story.cards;

  /* L1. The open card is derived from the collection rather than held as an
     index: a story that comes back one colleague shorter must not leave the
     deck pointing at somebody who is no longer in it, and an empty story must
     not be an assertion into an empty array. */
  const { chosen, chosenId, choose } = useChoice(cards, (card) => card.entity_id);
  const at = cards.findIndex((card) => card.entity_id === chosenId);

  const [playing, setPlaying] = useState(false);

  const trackRef = useRef<HTMLOListElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const prevRef = useRef<HTMLButtonElement>(null);
  const nextRef = useRef<HTMLButtonElement>(null);
  const drag = useRef<{ x: number; y: number; dx: number; axis: "" | "x" | "y" } | null>(null);

  const unvoiced = cards.filter((card) => card.audio === null).length;
  const told = story.generated_at === null ? null : clockOf(story.generated_at);
  const day = dayLabel(story.story_date);

  const step = useCallback(
    (by: number) => {
      const here = cards.findIndex((card) => card.entity_id === chosenId);
      if (here === -1) return;
      const next = Math.min(cards.length - 1, Math.max(0, here + by));
      const moved = cards[next];
      if (next === here || moved === undefined) return;
      // One voice, one clip: leaving a card stops it rather than letting two
      // mornings talk over each other.
      audioRef.current?.pause();
      setPlaying(false);
      choose(moved.entity_id);
      onEcho(`opened ${moved.name}’s morning card`);
      // A control that disables itself under the finger takes the focus with it,
      // and a keyboard user lands on <body> with nothing to press. Hand focus to
      // the control that is still live.
      if (next === cards.length - 1 && document.activeElement === nextRef.current) {
        prevRef.current?.focus();
      }
      if (next === 0 && document.activeElement === prevRef.current) {
        nextRef.current?.focus();
      }
    },
    [cards, choose, chosenId, onEcho],
  );

  // Window-level, exactly as the desk's Standup binds them: while the Morning
  // tab is showing, the arrows always move the story.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "ArrowRight") step(1);
      else if (e.key === "ArrowLeft") step(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step]);

  const toggle = () => {
    const el = audioRef.current;
    if (!el) return;
    if (playing) el.pause();
    else void el.play().catch(() => setPlaying(false));
  };

  const releaseDrag = () => {
    const held = drag.current;
    drag.current = null;
    const track = trackRef.current;
    if (track) {
      delete track.dataset.dragging;
      track.style.removeProperty("--mo-drag");
    }
    return held;
  };

  return (
    <section className="mo" data-empty={cards.length === 0 || undefined}>
      {/* -------------------------------------------------------------- header */}
      <header className="mo-head">
        <span className="t-eyebrow">
          THE MORNING STORY{day !== null && ` · ${day.toUpperCase()}`}
        </span>
        {/* The count is in the title only when there is one. "0 colleagues,
            composed just now" is a true sentence that reads as a broken screen,
            and a fabricated count is the thing §7.1 forbids outright. */}
        <h1 className="mo-title t-display">
          {cards.length === 0
            ? "This morning’s story"
            : `${cards.length} ${cards.length === 1 ? "colleague" : "colleagues"}, ${
                told !== null ? `told at ${told}` : "composed just now"
              }`}
        </h1>

        {/* L2, said on the surface. A promise the product keeps but never
            mentions is a promise the reader cannot rely on. */}
        <p className="mo-onevoice t-mono">
          Every card is Pragya’s telling. Your colleagues do the work; she is the
          only one who speaks.
        </p>

        {/* The shape of the morning, not its excuse — the reason belongs on the
            card that lost its voice. An unlit lamp: this is information, not a
            state that needs you. */}
        {unvoiced > 0 && (
          <p className="mo-degraded t-mono">
            <span className="m-lamp" />
            {unvoiced === cards.length
              ? `None of the ${cards.length} ${cards.length === 1 ? "card is" : "cards are"} voiced.`
              : `${unvoiced} of the ${cards.length} cards are text only.`}
          </p>
        )}
      </header>

      {cards.length === 0 ? (
        /* L2. `compose_morning_story` walks the estate's colleagues, so a story
           with no cards is an estate with nobody in it — not a screen that
           failed. The rail is absent entirely rather than disabled: two dead
           controls and "1 of 0" beneath them was the count this round came to
           delete. */
        <Empty
          icon="colleague"
          alone
          title="Nobody has a card this morning."
          body="The story is one card per colleague, and there are no colleagues in the estate yet. Nothing has gone wrong — there is simply nobody for Pragya to tell you about until someone is hired."
        />
      ) : (
        <>
          {/* ------------------------------------------------------ the deck
              Full-bleed: a card slides off the true screen edge, so the slides
              and not the surface carry the side padding. */}
          <div
            className="mo-view"
            onTouchStart={(e) => {
              if (e.touches.length !== 1) return;
              const t = e.touches[0]!;
              drag.current = { x: t.clientX, y: t.clientY, dx: 0, axis: "" };
            }}
            onTouchMove={(e) => {
              const held = drag.current;
              const t = e.touches[0];
              const track = trackRef.current;
              if (!held || !t || !track) return;
              const dx = t.clientX - held.x;
              const dy = t.clientY - held.y;
              if (held.axis === "") {
                // Axis lock. A card can be taller than the screen, and a vertical
                // read must never turn into a horizontal one part-way down.
                if (Math.abs(dx) < AXIS_PX && Math.abs(dy) < AXIS_PX) return;
                held.axis = Math.abs(dx) > Math.abs(dy) ? "x" : "y";
                if (held.axis === "x") track.dataset.dragging = "";
              }
              if (held.axis !== "x") return;
              held.dx = dx;
              // Nothing behind the first card and nothing after the last, so the
              // deck resists rather than pretending there is more.
              const past = (dx > 0 && at === 0) || (dx < 0 && at === cards.length - 1);
              track.style.setProperty("--mo-drag", `${past ? dx / 4 : dx}px`);
            }}
            onTouchEnd={() => {
              const held = releaseDrag();
              if (!held || held.axis !== "x") return;
              if (held.dx <= -SWIPE_PX) step(1);
              else if (held.dx >= SWIPE_PX) step(-1);
            }}
            onTouchCancel={releaseDrag}
          >
            <ol className="mo-track" ref={trackRef} style={{ ["--i" as string]: at }}>
              {cards.map((card, i) => (
                <li
                  className="mo-slide"
                  key={card.entity_id}
                  // The cards you are not reading are off-screen behind
                  // `overflow: hidden`; hiding them from assistive tech and from
                  // the tab order is what makes that true for everyone.
                  aria-hidden={i === at ? undefined : true}
                >
                  <MorningCardView
                    card={card}
                    active={i === at}
                    playing={i === at && playing}
                    reason={unvoicedReason(card, story.degraded_reason)}
                    onToggle={toggle}
                  />
                </li>
              ))}
            </ol>
          </div>

          {/* ------------------------------------------------------ the rail */}
          <footer className="mo-rail">
            <button
              ref={prevRef}
              className="m-btn mo-step"
              data-rank="quiet"
              onClick={() => step(-1)}
              disabled={at <= 0}
              aria-label="Previous colleague"
            >
              <Icon name="back" size={16} />
            </button>

            {/* Decoration for the eye; the count beside it is the readable form. */}
            <ol className="mo-pips" aria-hidden="true">
              {cards.map((card, i) => (
                <li
                  className="mo-pip"
                  key={card.entity_id}
                  data-active={i === at || undefined}
                  data-passed={i < at || undefined}
                >
                  <span className="mo-pip-bar" />
                  {card.waiting && <span className="mo-pip-hand" />}
                </li>
              ))}
            </ol>

            <span className="mo-count t-mono">
              {at + 1} of {cards.length}
            </span>

            <button
              ref={nextRef}
              className="m-btn mo-step"
              onClick={() => step(1)}
              disabled={at === cards.length - 1}
              aria-label="Next colleague"
            >
              <Icon name="forward" size={16} />
            </button>

            {/* Announced rather than focused: a swipe should not move the caret
                off the button the thumb is still resting on. `.vh-sr-only` is
                already out of flow, so it costs the rail no column. */}
            <p className="vh-sr-only" role="status">
              {chosen !== undefined
                ? `${chosen.name}, card ${at + 1} of ${cards.length}`
                : ""}
            </p>
          </footer>

          {/* One element for the whole deck, keyed to the card it belongs to —
              she is one voice, and two clips must never overlap. Rendered only
              where a clip exists, so there is nothing to play when there is
              nothing to play. */}
          {chosen?.audio != null && (
            <audio
              key={chosen.entity_id}
              ref={audioRef}
              className="mo-clip"
              preload="none"
              src={`data:${chosen.audio.mime};base64,${chosen.audio.data_b64}`}
              onPlay={() => {
                setPlaying(true);
                onEcho(`played ${chosen.name}’s card aloud`);
              }}
              onPause={() => setPlaying(false)}
              onEnded={() => setPlaying(false)}
            />
          )}
        </>
      )}
    </section>
  );
}

function MorningCardView({
  card,
  active,
  playing,
  reason,
  onToggle,
}: {
  card: MorningCard;
  active: boolean;
  playing: boolean;
  /** Why this card has no clip, or `null` where it has one. */
  reason: string | null;
  onToggle: () => void;
}) {
  return (
    <article className="mo-card m-plate">
      <header className="mo-card-head">
        <div className="m-portrait-well mo-portrait">
          <Portrait id={card.entity_id} size={70} />
        </div>
        <div className="mo-who">
          <h2 className="mo-name t-display">{card.name}</h2>
          {/* The two facts the endpoint sends about who this is: the district's
              process code and the entity id. A role or a standing here would
              name a field that is not on the wire. */}
          <span className="mo-meta t-mono">
            {card.district} · {card.entity_id}
          </span>
          {card.waiting && (
            <span className="mo-waiting">
              {/* Sanctioned gold (§4): this is literally "this needs you". Never
                  the lamp alone — the word beside it is the correct read. */}
              <span className="m-lamp" data-lit data-breathing />
              <span className="t-eyebrow mo-waiting-word">WAITING ON YOU</span>
            </span>
          )}
        </div>
      </header>

      {/* Joined, because the clip says these joined. */}
      <p className="mo-telling t-narrative">{card.sentences.join(" ")}</p>

      {card.waiting && (
        <p className="mo-elsewhere t-mono">
          Nothing is approved here. The ask itself is in the Thread.
        </p>
      )}

      <hr className="m-rule-fade" />

      {/* The voice slot. Present on every card; what fills it is what is true. */}
      <div className="m-well mo-voice">
        <span className="t-eyebrow">HER VOICE</span>
        {reason === null ? (
          <button
            className="m-btn mo-listen"
            data-rank="quiet"
            onClick={onToggle}
            tabIndex={active ? undefined : -1}
            // The visible word is the whole label; the name is what tells a
            // screen reader *whose* card, since the button repeats per card.
            aria-label={
              playing ? `Pause ${card.name}’s card` : `Listen to ${card.name}’s card`
            }
          >
            {/* The set has no play triangle. `chevron` is the closest name in
                PATHS and the word carries the state either way. */}
            <Icon name={playing ? "hold" : "chevron"} size={14} />
            {playing ? "Pause" : "Listen"}
          </button>
        ) : (
          <p className="mo-unvoiced t-mono">{reason}</p>
        )}
      </div>
    </article>
  );
}
