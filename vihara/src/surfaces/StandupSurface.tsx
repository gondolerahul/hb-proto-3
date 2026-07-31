import { useCallback, useEffect, useState } from "react";
import { Icon } from "../components/Icon";
import { Portrait } from "../components/Portrait";
import { fetchMorningStory, type MorningCard, type MorningStory } from "../api/line";
import { Bar, Empty, Failed, Lines, Scaffold, useChoice, useResource } from "../lifecycle";
import "./standup.css";

/**
 * The Standup · depth 1–2 · C sequence (D6 §10) — on `GET /ai/genui/line/morning`
 * (R-4 part W).
 *
 * Ninety seconds, one card per colleague, each drillable. On the Line this same
 * surface *is* the Morning Story, and after this round that is true of the data
 * as well as the layout: `morning.py`'s own docstring says the composition was
 * ported server-side precisely so that *"the sentences here and in
 * `StandupSurface.tsx` must tell the same story; if the two ever drift, the
 * phone and the desk disagree about yesterday"*. They now come off one endpoint,
 * so they cannot.
 *
 * **The rule that shapes everything here is L2: every line is relayed by Pragya,
 * never spoken by the colleague.** One voice is not a stylistic preference — it
 * is what keeps notification discipline enforceable, because a tenant who can be
 * addressed by twelve colleagues has twelve channels to mute and will mute the
 * wrong one. The endpoint enforces it at source: a card carries *her* sentences
 * about the colleague and no field for the colleague's own words.
 *
 * Two densities, and a real toggle, because the spec asks for genuinely
 * different things rather than the same layout at two sizes:
 *
 *  - **novice** — a sequence. One card at a time, arrow-keyed, with a progress
 *    rail. This is the register a morning briefing has.
 *  - **operator** — all lines on one sheet, scannable. This is the register a
 *    person who already knows their estate wants.
 *
 * ## What the wiring removed, and why it is not a redesign
 *
 * The fixture's card carried five blocks the morning composition **does not
 * have**: a per-card `preparedAt`, a `facts` well, the KPI a line `moved`, a
 * Glasshouse `grade`, and the text of the ask on `needsYou`. The endpoint gives
 * `sentences`, `waiting` (a bare boolean), a name, a district and an entity id.
 *
 * §7.1 says a missing binding renders **nothing** — so those blocks are gone
 * rather than filled with something plausible, and the header says once, in
 * `t-mono`, where the counts actually live (§7.4: render the gap). In
 * particular the needs-you control **cannot state the ask**, because no ask
 * comes back with the card; it says where the ask is instead, which is the same
 * answer the Line gives ("the ask itself is in the Thread").
 *
 * ## Live view or recording — the header says which
 *
 * `morning.py` serves a stored row when the 02:25 job wrote one, and composes
 * fresh when it did not. That is the difference between *the morning's telling*
 * and *the estate as it stands*, and it is the one distinction between this
 * surface and the Line's. `generated_at` is how it is known and the title says
 * it in words: a recording that presents itself as live is a surface lying
 * about its own freshness.
 *
 * `degraded_reason` is deliberately unread here. Every value it can take
 * (`wallet`, `not_configured`, `tts_failed`, `not_generated`) is about the
 * **voice**, and the desk's Standup has no clip to lose — the Line's
 * `MorningStorySurface` is where those four sentences belong, and it has them.
 */

/** Ninety seconds is the Standup's own budget (D6 §10), not a reading off the
 *  estate — a promise this surface makes about how long it will take you. */
const BUDGET_SECONDS = 90;

/**
 * The backend's naive timestamps are UTC by construction (`datetime.utcnow`,
 * on a `DateTime` column with no zone), and `Date` parses a naive ISO string as
 * **local** time. Stamping the zone on before parsing is the difference between
 * telling a Chennai owner their morning was written at 07:55 and telling them
 * it was written at 02:25 in the middle of the night.
 */
function instantOf(iso: string): Date | null {
  const stamped = /(?:Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`;
  const at = new Date(stamped);
  return Number.isNaN(at.getTime()) ? null : at;
}

/** The telling's clock, in the reader's zone. `null` rather than a guess when
 *  the stamp cannot be read at all. */
function clockOf(iso: string): string | null {
  const at = instantOf(iso);
  if (at === null) return null;
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(at);
}

/** The story's date is a calendar date. Formatting it in the reader's zone
 *  moves it a day either side of midnight, so it is read in UTC. */
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

type Density = "novice" | "operator";

export function StandupSurface({
  onOpenTray,
  onOpenDossier,
  onEcho,
}: {
  onOpenTray?: () => void;
  onOpenDossier?: (id: string) => void;
  onEcho: (msg: string) => void;
}) {
  const story = useResource(fetchMorningStory);

  if (story.phase === "pending") {
    return (
      <section className="su" data-density="novice" data-pending>
        <Scaffold label="The standup">
          {/* Plates first, bars inside them: `vh-skeleton`'s ground is a ~6/255
              delta on the raw canvas, so a bar laid over the background draws
              nothing and the pending state would be a blank room. */}
          <div className="su-scaffold">
            <div className="su-scaffold-head m-plate">
              <Bar width="sm" />
              <Bar width="md" tall />
            </div>
            <div className="su-scaffold-card m-plate">
              <Bar width="sm" tall />
              <Lines n={3} />
            </div>
          </div>
        </Scaffold>
      </section>
    );
  }

  if (story.phase === "failed") {
    return (
      <section className="su" data-density="novice" data-pending>
        <Failed
          what="this morning’s standup"
          reason={story.reason}
          onRetry={story.retry}
        />
      </section>
    );
  }

  return (
    <StandupStory
      story={story.value}
      onOpenTray={onOpenTray}
      onOpenDossier={onOpenDossier}
      onEcho={onEcho}
    />
  );
}

function StandupStory({
  story,
  onOpenTray,
  onOpenDossier,
  onEcho,
}: {
  story: MorningStory;
  onOpenTray?: () => void;
  onOpenDossier?: (id: string) => void;
  onEcho: (msg: string) => void;
}) {
  const [density, setDensity] = useState<Density>("novice");
  const cards = story.cards;
  /* The open card is derived from the collection, never an index held in state
     (L1): a story that comes back one colleague shorter must not leave the
     selection pointing at somebody who is no longer in it. */
  const { chosen, chosenId, choose } = useChoice(cards, (card) => card.entity_id);
  const at = cards.findIndex((card) => card.entity_id === chosenId);

  const step = useCallback(
    (by: number) => {
      const here = cards.findIndex((card) => card.entity_id === chosenId);
      if (here === -1) return;
      const next = Math.min(cards.length - 1, Math.max(0, here + by));
      const moved = cards[next];
      if (next === here || moved === undefined) return;
      choose(moved.entity_id);
      onEcho(`opened ${moved.name}’s standup line`);
    },
    [cards, chosenId, choose, onEcho],
  );

  useEffect(() => {
    if (density !== "novice") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey) return;
      if (e.key === "ArrowRight") step(1);
      if (e.key === "ArrowLeft") step(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [density, step]);

  const waiting = cards.filter((card) => card.waiting).length;
  const day = dayLabel(story.story_date);
  const told = story.generated_at === null ? null : clockOf(story.generated_at);

  /* No `data-pending` here even when the story is empty: the header is real and
     the notice takes the body row, so the composition still holds. */
  return (
    <section className="su" data-density={density}>
      {/* ------------------------------------------------------------- header */}
      <header className="su-head">
        <div className="su-head-lead">
          <span className="t-eyebrow">
            THE STANDUP{day !== null && ` · ${day.toUpperCase()}`} · COVERING
            YESTERDAY
          </span>
          {/* The count is in the title only when there is one. "0 colleagues,
              90 seconds" is a true sentence that reads as a broken screen —
              the reduce-to-zero-and-print-it finding part L raised, one
              surface over. The empty case gets its designed prose below. */}
          <h1 className="su-title t-display">
            {cards.length === 0
              ? "This morning’s standup"
              : `${cards.length} ${cards.length === 1 ? "colleague" : "colleagues"}, ${
                  told !== null ? `told at ${told}` : `${BUDGET_SECONDS} seconds`
                }`}
          </h1>

          {/* L2 said in words, on the surface, not only in the code. */}
          <p className="su-voice t-mono">
            <span className="m-lamp" data-lit />
            Every line below is Pragya’s. Your colleagues prepare them; she is the
            only one who speaks.
          </p>

          {/* The gap, stated once and quietly (§7.4). The morning composition
              carries her sentences and nothing else — the counts behind them,
              the KPI a line moved and the Glasshouse's opinion of it are not on
              this endpoint, and a card here will not pretend otherwise. */}
          {cards.length > 0 && (
            <p className="su-elsewhere t-mono">
              {told !== null
                ? "This is the morning’s telling, made once and read later — not a live view. "
                : "This morning’s telling has not run, so this was composed just now from the estate as it stands. "}
              The counts behind each line are in the colleague’s dossier.
            </p>
          )}
        </div>

        <div className="su-head-side">
          {waiting > 0 && (
            <button className="m-chip su-waiting" onClick={onOpenTray}>
              <span className="m-lamp" data-lit data-breathing />
              {waiting} waiting on you
            </button>
          )}
          <div className="su-density" role="radiogroup" aria-label="Density">
            <span className="t-eyebrow">DENSITY</span>
            {(["novice", "operator"] as const).map((d) => (
              <button
                key={d}
                role="radio"
                aria-checked={density === d}
                className="m-chip"
                data-selected={density === d || undefined}
                onClick={() => setDensity(d)}
              >
                {d}
              </button>
            ))}
          </div>
        </div>
      </header>

      {cards.length === 0 && (
        <Empty
          icon="colleague"
          alone
          title="Nobody has a line this morning."
          body="The standup is one card per colleague, and there are no colleagues in the estate yet. Nothing has gone wrong — there is simply nobody for Pragya to tell you about until someone is hired."
        />
      )}

      {/* =============================================== novice — the sequence */}
      {cards.length > 0 && density === "novice" && chosen !== undefined && (
        <>
          <div className="su-stage">
            <StandupCard
              card={chosen}
              onOpenTray={onOpenTray}
              onOpenDossier={onOpenDossier}
              expanded
            />
          </div>

          <footer className="su-rail">
            <button
              className="m-btn"
              data-rank="quiet"
              onClick={() => step(-1)}
              disabled={at <= 0}
              aria-label="Previous colleague"
            >
              <Icon name="back" size={14} />
            </button>

            <ol className="su-pips">
              {cards.map((card, i) => (
                <li key={card.entity_id}>
                  <button
                    className="su-pip"
                    data-active={i === at || undefined}
                    data-passed={i < at || undefined}
                    onClick={() => choose(card.entity_id)}
                    aria-label={`${card.name}, line ${i + 1} of ${cards.length}`}
                    aria-current={i === at ? "true" : undefined}
                  >
                    {card.waiting && (
                      <span className="su-pip-hand" aria-hidden="true" />
                    )}
                  </button>
                </li>
              ))}
            </ol>

            <span className="su-count t-mono">
              {at + 1} of {cards.length}
            </span>

            <button
              className="m-btn"
              onClick={() => step(1)}
              disabled={at === cards.length - 1}
            >
              Next
              <Icon name="forward" size={14} />
            </button>
          </footer>
        </>
      )}

      {/* ============================================= operator — one sheet */}
      {cards.length > 0 && density === "operator" && (
        <div className="su-sheet vh-stagger">
          {cards.map((card, i) => (
            <div key={card.entity_id} style={{ ["--i" as string]: i }}>
              <StandupCard
                card={card}
                onOpenTray={onOpenTray}
                onOpenDossier={onOpenDossier}
              />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function StandupCard({
  card,
  expanded = false,
  onOpenTray,
  onOpenDossier,
}: {
  card: MorningCard;
  expanded?: boolean;
  onOpenTray?: () => void;
  onOpenDossier?: (id: string) => void;
}) {
  return (
    <article className="su-card m-plate" data-expanded={expanded || undefined}>
      <header className="su-card-head">
        <button
          className="su-who"
          onClick={() => onOpenDossier?.(card.entity_id)}
          aria-label={`Open ${card.name}’s dossier`}
        >
          <div className="m-portrait-well su-portrait">
            <Portrait id={card.entity_id} size={expanded ? 84 : 60} />
          </div>
          <span className="su-who-text">
            <span className="su-who-name t-display">{card.name}</span>
            {/* The district and the id — the two facts the card actually
                carries about who this is. The fixture's `role` and `standing`
                are not on this endpoint and are not guessed at. */}
            <span className="t-mono su-who-meta">
              {card.district} · {card.entity_id}
            </span>
          </span>
        </button>

        {card.waiting && (
          <span className="su-waiting-mark">
            {/* Sanctioned gold (§2.1): this is literally "this needs you". */}
            <span className="m-lamp" data-lit data-breathing />
            <span className="t-eyebrow su-waiting-word">WAITING ON YOU</span>
          </span>
        )}
      </header>

      {/* Joined into one paragraph, exactly as the Line joins them: the job's
          `spoken_text` is `" ".join(sentences)`, so a bulleted list here would
          make the desk and the phone disagree about one telling. */}
      <p className="su-line t-narrative">{card.sentences.join(" ")}</p>

      {card.waiting && (
        <div className="su-card-foot">
          {/* The card knows *that* this colleague is waiting and not *what*
              for — `waiting` is a bare boolean. So the control says where the
              ask is rather than inventing its words, which is the same answer
              the Line gives on the same field. */}
          <button className="m-btn su-needs" onClick={onOpenTray}>
            <Icon name="forward" size={13} />
            The ask is in the tray
          </button>
        </div>
      )}
    </article>
  );
}
