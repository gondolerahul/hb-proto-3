import { useMemo } from "react";
import { Portrait } from "../components/Portrait";
import { Seal } from "../components/Seal";
import {
  fetchAlumni,
  fetchRealized,
  fetchReviewsDue,
  fetchSeasonMaterial,
  firstMeasurableOn,
  type Alumnus,
  type DueMandate,
  type KpiHistory,
  type KpiHistoryPoint,
  type RealizedMandate,
} from "../api/gallery";
import { artKeyFor } from "../api/entities";
import { fetchEntities } from "../api/talent";
import type { TenantRecordOut } from "../api/tenant";
import { Bar, Empty, Failed, Lines, Scaffold, useChoice, useResource } from "../lifecycle";
import "./gallery.css";

/**
 * The Gallery · depth 2 · S+W (D6 §11) — on `talent/colleagues-past`,
 * `strategy/reviews-due`, `strategy/mandates/{id}/realized` and `kpi/history`
 * (R-4 part W).
 *
 * Answers **RD-7** in its hardest form, and wiring made the case harder rather
 * than easier. §11 says the KPI series starts 2026-07-25 with no backfill, so
 * for roughly a quarter this room has almost nothing to show — and now that the
 * numbers are real, "almost nothing" is what it will actually render. **The
 * thin state is the primary state**, and it is the state that got the design
 * budget: an empty frame with a plaque saying what will hang there and when, a
 * strip of ninety day-marks with the measured ones cut, and a chronology with
 * one gate on it.
 *
 * ## The season object does not exist, and is not invented here
 *
 * The fixture's spine was five named seasons — a period with a name, a span, a
 * story and an afterwards. **Nothing on the backend stores any of those four
 * fields.** `api/gallery.ts` says so in as many words and refuses to compose a
 * wrapper that would look like one; what it returns instead is the *material* a
 * season is made of — the Resolutions adopted, and the KPI series that either
 * was or was not running at the time.
 *
 * So the spine is now **the decisions themselves, in the order they were
 * taken**, and the room says that is what it is. Naming a period is editorial
 * work the platform has not done, and a client that made up "The Quiet Weeks"
 * would be writing this company's history for it.
 *
 * What survives from the design, because it was never about seasons:
 *
 *  1. **The hatch is "told, not measured", and it stops at the gate.** Every
 *     decision taken before the first measurable day carries it; the gate is
 *     drawn where it stops. That boundary — between the part of this company's
 *     life that was measured and the part that was only lived — is real, is
 *     computed from `first_measurable_on`, and is the single most useful thing
 *     on the spine.
 *  2. **Draining is about time, not decoration.** Colleagues past are drained
 *     (art bible §7.2) and the longest-serving colleague still working sits on
 *     the same wall in full colour. Without her the drained material reads as a
 *     style; with her it reads as a statement about what is currently true. She
 *     is chosen by earliest `created_at` among live colleagues — a fact, not a
 *     pick.
 *  3. **A prediction that was never made renders no bar.** `predicted_value` is
 *     `null` for an untested promotion and the row is a sentence instead. A
 *     zero-length bar would be a bet nobody placed.
 *
 * ## Gold, and where it went
 *
 * The fixture spent gold on a medallion for monuments "raised by a certified
 * act". `POST /ai/strategy/adopt` **is** the T2 certified act that creates a
 * Resolution — and the record it writes carries `title`, `decision`,
 * `adopted_on`, `concerns_module`, `status` and `proposition`, and **no stamp
 * saying a ceremony happened**. A resolution can also arrive through ordinary
 * record CRUD, so this surface cannot tell the two apart. Marking them all
 * certified would be gold spent on a guess, so nothing here is marked and the
 * gap is stated once.
 *
 * The room's one gold note is a mandate whose review has come due, which is
 * literally "this needs you" — the sanctioned meaning (§2.1), on the one thing
 * in this room that is waiting on the owner.
 */

/**
 * How long the room waits before it will draw a line. **Stated policy, not a
 * figure off the wire** — §11 says the series has no backfill and will be thin
 * "for roughly a quarter", so the room commits to a quarter in public rather
 * than drawing a five-point chart and calling it a trend.
 */
const TREND_NEEDS_DAYS = 90;

/** The four honesty grades (D4 §3.1) — four, not three. `untested` ("never
 *  tried") must not read like `unknown` ("could not be graded"), so they have
 *  different words *and* a different structural tell: untested has no run
 *  behind it, by definition, and the run id is absent rather than dimmed. */
const GRADE_WORD: Record<string, string> = {
  replay: "replay",
  forecast: "forecast",
  untested: "untested · never tried",
  unknown: "unknown · could not be graded",
};

/** `Verdict` in `strategy/realized.py`, as an owner reads it. */
const VERDICT_WORD: Record<string, string> = {
  on_track: "on track",
  off_track: "off track",
  met: "met",
  missed: "missed",
  not_measurable: "cannot be told yet",
};

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

/** `2026-07-25` → `25 July 2026`. Locale-free by hand, for the reason
 *  `HallSurface` gives about `toLocaleString`: the same record must not read
 *  differently on two machines. Anything that is not a plain ISO day is
 *  returned untouched rather than guessed at. */
function readable(day: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(day);
  if (match === null) return day;
  const month = MONTHS[Number(match[2]) - 1];
  if (month === undefined) return day;
  return `${Number(match[3])} ${month} ${match[1]}`;
}

/** Day arithmetic in UTC on a plain date. No `Date.parse` of a naive
 *  timestamp — that reads as local time and slips by the reader's timezone. */
function addDays(day: string, count: number): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(day);
  if (match === null) return null;
  const at = new Date(
    Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]) + count),
  );
  return at.toISOString().slice(0, 10);
}

/**
 * A KPI value as a figure. The same rules `StillSurface.formatMeasure` applies
 * to a plinth reading, because a number must not change shape between two rooms
 * — and `unit: "currency"` prints **unsigned**, since the KPI registry names no
 * currency anywhere and a `₹` here would be a symbol this client chose.
 */
function figure(value: number, unit: string): string {
  const digits = Math.abs(value) < 10 && !Number.isInteger(value) ? 1 : 0;
  const text = new Intl.NumberFormat(undefined, {
    maximumFractionDigits: digits,
  }).format(value);
  if (unit === "percent") return `${text}%`;
  if (unit === "days") return `${text}d`;
  return text;
}

function textOf(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value.trim() : null;
}

/** The day a resolution was adopted. `adopted_on` is what `strategy/adopt`
 *  writes; `created_at` is the row's own stamp and stands in where the blob
 *  does not carry one. */
function dayOf(record: TenantRecordOut): string {
  return textOf(record.data["adopted_on"]) ?? record.created_at.slice(0, 10);
}

function titleOf(record: TenantRecordOut): string {
  return textOf(record.data["title"]) ?? record.id.slice(0, 8);
}

/* ========================================================================== */

export function GallerySurface({ onEcho }: { onEcho: (msg: string) => void }) {
  const material = useResource(fetchSeasonMaterial);

  if (material.phase === "pending") return <GalleryScaffold />;

  if (material.phase === "failed") {
    return (
      <section className="ga">
        <Failed
          what="the Gallery"
          reason={material.reason}
          onRetry={material.retry}
        />
      </section>
    );
  }

  return (
    <GalleryView
      resolutions={material.value.resolutions}
      history={material.value.history}
      onEcho={onEcho}
    />
  );
}

function GalleryView({
  resolutions,
  history,
  onEcho,
}: {
  resolutions: TenantRecordOut[];
  history: KpiHistory;
  onEcho: (msg: string) => void;
}) {
  const recordStarts = firstMeasurableOn(history);

  /* Oldest first: the spine is a walk forward through the company's life, and
     `fetchRecords` orders by nothing this surface should rely on. */
  const walk = useMemo(
    () => [...resolutions].sort((a, b) => dayOf(a).localeCompare(dayOf(b))),
    [resolutions],
  );

  /* L1: derived from the collection, never asserted into it. The intent — open
     on the most recent decision — is a predicate rather than an index somebody
     has to keep true. */
  const { chosen, choose } = useChoice(
    walk,
    (record) => record.id,
    (record) => record.id === walk[walk.length - 1]?.id,
  );

  return (
    <section className="ga">
      <header className="ga-head">
        <span className="t-eyebrow">THE GALLERY · THE GROWTH JOURNEY</span>
        <h1 className="ga-title t-display">What this company has been through</h1>
        <p className="t-narrative ga-lead">
          Every decision this company has adopted, every colleague who is no
          longer here, and every bet with its prediction still attached. The
          measured part of it is younger than the rest, which is stated below
          rather than dressed up.
        </p>
      </header>

      {/* ==================================================== the chronology */}
      <section className="ga-panel ga-seasons m-plate" aria-label="Decisions in order">
        <div className="ga-panel-head">
          <h2 className="t-eyebrow">DECISIONS, IN ORDER</h2>
          <span className="t-mono ga-whisper">
            {recordStarts === null
              ? "nothing measured yet · everything here is told"
              : `the record joins on ${readable(recordStarts)}`}
          </span>
        </div>

        {walk.length === 0 ? (
          <Empty
            icon="seal"
            title="Nothing has been decided here yet."
            body="A decision lands on this wall when a proposition is adopted as a resolution — the certified act that turns something you were considering into something the estate is bound by. Until then this company has a present and no history."
          />
        ) : (
          <div className="ga-spine vh-stagger" role="radiogroup" aria-label="Choose a decision">
            {walk.map((record, i) => {
              const day = dayOf(record);
              const previous = i > 0 ? walk[i - 1] : undefined;
              const measured = recordStarts !== null && day >= recordStarts;
              const previousMeasured =
                previous !== undefined &&
                recordStarts !== null &&
                dayOf(previous) >= recordStarts;
              /* The gate is drawn where the hatch stops — between the last
                 decision taken with nothing being recorded and the first one
                 that has a record behind it. */
              const gate = measured && (previous === undefined || !previousMeasured);
              return (
                <div className="ga-spine-cell" key={record.id} style={{ ["--i" as string]: i }}>
                  {gate && recordStarts !== null && (
                    <div className="ga-gate">
                      <span className="t-eyebrow ga-gate-label">
                        THE RECORD BEGINS · {readable(recordStarts).toUpperCase()}
                      </span>
                    </div>
                  )}
                  <button
                    className="ga-season"
                    role="radio"
                    aria-checked={record.id === chosen?.id}
                    data-told={!measured || undefined}
                    onClick={() => {
                      choose(record.id);
                      onEcho(`opened the decision “${titleOf(record)}”`);
                    }}
                  >
                    <span className="ga-season-mark" aria-hidden="true" />
                    <span className="t-mono ga-season-span">{readable(day)}</span>
                    <span className="ga-season-name t-display">{titleOf(record)}</span>
                    <span className="ga-season-foot">
                      {textOf(record.data["concerns_module"]) ?? "the estate"}
                    </span>
                  </button>
                </div>
              );
            })}
          </div>
        )}

        <p className="ga-note">
          These are decisions, not chapters.{" "}
          <strong>The platform stores no seasons</strong> — a named period with a
          span and a story is not a thing anything here writes — so the walk is
          the record's own order, and naming the stretches of it is work nobody
          has done yet.
        </p>
      </section>

      <div className="ga-row">
        {/* ================================================ the chosen decision */}
        <section className="ga-panel ga-chapter m-plate" aria-label="This decision">
          {chosen === undefined ? (
            <p className="ga-empty">
              With nothing adopted there is nothing to open. This panel carries
              the decision you pick from the walk above.
            </p>
          ) : (
            <Chapter
              record={chosen}
              index={walk.findIndex((r) => r.id === chosen.id)}
              total={walk.length}
              measured={recordStarts !== null && dayOf(chosen) >= recordStarts}
            />
          )}
        </section>

        {/* ============================================== colleagues past */}
        <Wall />
      </div>

      {/* ========================================================= the record */}
      <TheRecord history={history} startedOn={recordStarts} />

      <div className="ga-row">
        <Bets />
      </div>
    </section>
  );
}

/* --------------------------------------------------------------- a decision */

function Chapter({
  record,
  index,
  total,
  measured,
}: {
  record: TenantRecordOut;
  index: number;
  total: number;
  measured: boolean;
}) {
  const decision = textOf(record.data["decision"]);
  const status = textOf(record.data["status"]);
  const concerns = textOf(record.data["concerns_module"]);
  const proposition = textOf(record.data["proposition"]);

  return (
    <>
      <header className="ga-chapter-head">
        {/* A decision has no persona, so it gets a struck seal — art bible §7
            direction C, which is the automatic fallback for anything the estate
            did rather than anyone. Deterministic from the record id, so the
            same decision always wears the same mark. */}
        <span className="m-portrait-well ga-chapter-seal">
          <Seal id={record.id} size={40} tone="live" />
        </span>
        <span className="t-eyebrow">
          DECISION {index + 1} OF {total}
        </span>
        <h2 className="ga-chapter-name t-display">{titleOf(record)}</h2>
        <span className="t-mono ga-chapter-span">
          adopted {readable(dayOf(record))}
          {concerns !== null && ` · ${concerns}`}
        </span>
      </header>

      {/* Lamp plus a word. The hatch on the card above is the fast read; this is
          the correct one, and it is why no card up there shows a figure. */}
      <span className="ga-state">
        <span className="m-lamp" data-positive={measured || undefined} />
        {measured
          ? "measured — the record was running when this was taken"
          : "told, not measured — nothing was being recorded then"}
      </span>

      {decision !== null ? (
        <p className="t-narrative ga-chapter-story">{decision}</p>
      ) : (
        <p className="ga-note">
          The record carries a title and no decision text. Nothing was written
          into the field that says what was actually resolved, so there is
          nothing to read here — it was not lost.
        </p>
      )}

      <hr className="m-rule-fade" />

      <div className="ga-panel-head">
        <h3 className="t-eyebrow">THE RECORD ITSELF</h3>
        <span className="t-mono ga-whisper">
          version {record.version} of def v{record.def_version}
        </span>
      </div>

      <dl className="ga-readings">
        {status !== null && (
          <div className="ga-reading">
            <dt className="t-eyebrow">STATUS</dt>
            <dd>
              <span className="ga-state">
                <span className="m-lamp" data-positive={status === "active" || undefined} />
                {status}
              </span>
            </dd>
          </div>
        )}
        <div className="ga-reading">
          <dt className="t-eyebrow">RESOLUTION</dt>
          <dd>
            <span className="t-mono">{record.id.slice(0, 8)}</span>
          </dd>
        </div>
      </dl>

      {/* Nothing here is marked certified, and that is a statement about the
          record rather than about the act. */}
      <p className="ga-note">
        Adopting a resolution is a certified act — you prove it is you before it
        is written.{" "}
        <strong>The record keeps no stamp of that</strong>, so nothing on this
        wall is marked certified: the ceremony happened and the row does not say
        so, and marking it anyway would be a seal this screen awarded itself.
      </p>

      {/* A statement, not a control. The fixture drew "Walk back to R-14" as a
          button that echoed and walked nowhere — this surface has no route to
          anything and no read for a proposition, so the lineage is printed and
          the affordance is not offered (the Terrace settled this for the
          estate: an echo for an act that did not happen is worse than no
          affordance). */}
      {proposition !== null && (
        <p className="ga-note t-mono">
          It came from proposition {proposition.slice(0, 8)}.
        </p>
      )}
    </>
  );
}

/* --------------------------------------------------------- colleagues past */

function Wall() {
  const alumni = useResource(fetchAlumni);
  const living = useResource(fetchEntities);

  /**
   * The longest-serving colleague still working — the undrained contrast.
   *
   * Chosen by earliest `created_at`, which is a fact rather than a pick: "the
   * first one in the list" would put a different face here every time the
   * roster reordered, and the whole point of the contrast is that it is stable
   * enough to read as a statement about time.
   */
  const stillServing = useMemo(() => {
    if (living.phase !== "ready") return null;
    const candidates = living.value
      .filter((entity) => entity.type === "AGENT" && entity["is_template"] !== true)
      .filter((entity) => {
        const tags = entity["tags"];
        return !(
          Array.isArray(tags) &&
          tags.some((tag) => typeof tag === "string" && tag.startsWith("channel:"))
        );
      })
      .filter((entity) => entity["status"] === "ACTIVE")
      .map((entity) => ({
        id: entity.id,
        name:
          entity.display_name !== null && entity.display_name !== ""
            ? entity.display_name
            : entity.name,
        artName: entity.name,
        since: textOf(entity["created_at"]),
      }))
      .sort((a, b) => (a.since ?? "9999").localeCompare(b.since ?? "9999"));
    return candidates[0] ?? null;
  }, [living]);

  return (
    <section className="ga-panel ga-wall m-plate" aria-label="Colleagues past">
      <div className="ga-panel-head">
        <h2 className="t-eyebrow">COLLEAGUES PAST</h2>
        <span className="t-mono ga-whisper">drained — not currently true</span>
      </div>

      {alumni.phase === "pending" ? (
        <Scaffold label="The wall of colleagues past">
          <div className="m-well ga-ghost-well">
            <Lines n={4} />
          </div>
        </Scaffold>
      ) : alumni.phase === "failed" ? (
        <Failed
          alone={false}
          what="the wall of colleagues past"
          reason={alumni.reason}
          onRetry={alumni.retry}
        />
      ) : alumni.value.length === 0 ? (
        <Empty
          icon="colleague"
          title="Nobody has left yet."
          body="A colleague appears on this wall when their termination has run its ceremony — the memo written, the runs counted, the record closed. Everyone who has ever worked here is still working here."
        />
      ) : (
        <>
          <ul className="ga-alumni">
            {alumni.value.map((alumnus) => (
              <Alum key={alumnus.entity_id} alumnus={alumnus} />
            ))}
          </ul>

          {/* The contrast, and only where there is something to contrast with:
              on a wall with nobody past, an undrained portrait beside nothing
              says nothing. */}
          {stillServing !== null && (
            <>
              <hr className="m-rule-fade ga-wall-rule" />
              <div className="ga-alum">
                <span className="m-portrait-well ga-alum-well">
                  <Portrait
                    id={artKeyFor(stillServing.artName)}
                    size={68}
                    title={`${stillServing.name} — a generated portrait, not a photograph`}
                  />
                </span>
                <span className="ga-alum-text">
                  <span className="t-eyebrow">STILL SERVING</span>
                  <span className="ga-alum-name">{stillServing.name}</span>
                  <span className="ga-alum-served">
                    {stillServing.since === null
                      ? "the record carries no start date"
                      : `here since ${readable(stillServing.since.slice(0, 10))}`}
                  </span>
                  <span className="ga-alum-why">
                    In full colour on purpose — everyone else on this wall is
                    past, and without her the draining reads as a style rather
                    than as a statement about what is currently true.
                  </span>
                </span>
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}

function Alum({ alumnus }: { alumnus: Alumnus }) {
  /* Every count here comes off the termination stamp, so a `null` is "the stamp
     did not carry it" and never zero. A missing count renders no clause at all
     rather than "0 runs", which would say she did nothing. */
  const ran =
    alumnus.runs_total === null
      ? null
      : alumnus.runs_completed === null
        ? `${alumnus.runs_total} runs`
        : `${alumnus.runs_completed} of ${alumnus.runs_total} runs completed`;

  return (
    <li className="ga-alum ga-alum-past">
      <span className="m-portrait-well ga-alum-well">
        <Portrait
          id={alumnus.art_name}
          size={68}
          drained
          title={`${alumnus.name} — a generated portrait, not a photograph`}
        />
      </span>
      <span className="ga-alum-text">
        <span className="ga-alum-name">
          {alumnus.name}
          <span className="t-mono ga-alum-id">{alumnus.entity_id.slice(0, 8)}</span>
        </span>
        <span className="ga-alum-served">
          {alumnus.terminated_at !== null
            ? `left ${readable(alumnus.terminated_at.slice(0, 10))}`
            : "the stamp carries no date"}
          {ran !== null && ` · ${ran}`}
        </span>
        <span className="ga-alum-why">
          {alumnus.memo_artifact_id !== null
            ? "A leaving memo was written and is kept with the record."
            : "No leaving memo was written, so why she left is not on the record."}
        </span>
      </span>
    </li>
  );
}

/* ---------------------------------------------------------------- the record */

function TheRecord({
  history,
  startedOn,
}: {
  history: KpiHistory;
  startedOn: string | null;
}) {
  /* Days *with a measurement*, not days in the window. A window is what we
     asked for; this is what came back. */
  const measuredDays = useMemo(() => {
    const days = new Set<string>();
    for (const series of history.series) {
      for (const point of series.points) {
        if (point.measurable && point.value !== null) days.add(point.captured_on);
      }
    }
    return days.size;
  }, [history]);

  const firstTrendOn = startedOn === null ? null : addDays(startedOn, TREND_NEEDS_DAYS);

  const readings = useMemo(
    () =>
      history.series
        .map((series) => {
          const measured = series.points
            .filter(
              (point): point is KpiHistoryPoint & { value: number } =>
                point.measurable && point.value !== null,
            )
            .sort((a, b) => a.captured_on.localeCompare(b.captured_on));
          const latest = measured[measured.length - 1];
          const first = measured[0];
          if (latest === undefined || first === undefined) return null;
          return { series, latest, first: measured.length > 1 ? first : null };
        })
        .filter((reading): reading is NonNullable<typeof reading> => reading !== null),
    [history],
  );

  return (
    <section className="ga-panel ga-record m-plate" aria-label="The measured record">
      <div className="ga-panel-head">
        <h2 className="t-eyebrow">THE MEASURED RECORD</h2>
        <span className="t-mono ga-whisper">
          {startedOn === null
            ? "the series has not started"
            : `starts ${readable(startedOn)} · nothing before it was backfilled`}
        </span>
      </div>

      <div className="ga-record-body">
        {/* The empty frame with its plaque beneath — a reserved wall, not a
            chart that failed to load. The emptiness is marked rather than left
            ambiguous: unlabelled blank space reads as a bug. */}
        <figure className="ga-frame m-well" data-deep>
          <div className="ga-frame-inner m-ticks">
            <span className="t-eyebrow ga-frame-mark">NOTHING HANGS HERE YET</span>
          </div>
          <figcaption className="ga-plaque m-plate" data-raised>
            <span className="t-eyebrow">RESERVED · THE FIRST TREND</span>
            {startedOn === null ? (
              <>
                <p className="ga-plaque-text">
                  <strong>The record has not started.</strong> No KPI has been
                  snapshotted yet, so there is not one point to draw, let alone a
                  line — and this frame stays reserved until there is.
                </p>
                <p className="ga-note">
                  Nothing can be backfilled into it. The series begins where the
                  measuring begins, and every decision on the walk above was
                  taken before that.
                </p>
              </>
            ) : (
              <>
                <p className="ga-plaque-text">
                  The record is {measuredDays} day{measuredDays === 1 ? "" : "s"}{" "}
                  old. A line drawn through {measuredDays} point
                  {measuredDays === 1 ? "" : "s"} would flatter itself, so this
                  frame stays empty
                  {firstTrendOn !== null && (
                    <>
                      {" "}
                      until <strong>{readable(firstTrendOn)}</strong>, when{" "}
                      {TREND_NEEDS_DAYS} days sit behind it
                    </>
                  )}
                  .
                </p>
                <p className="ga-note">
                  Nothing before {readable(startedOn)} was backfilled and nothing
                  can be — the series begins where the measuring began. The
                  decisions above it are told in words for that reason, not
                  because their figures are hidden somewhere.
                </p>
              </>
            )}
          </figcaption>
        </figure>

        <div className="ga-record-side">
          {/* The strip is drawn only once there is a record to measure. "0 of
              90" beside a plaque that already says the record has not started
              is §7.1's tidy twin — the same reading `HallSurface` refuses when
              it will not print "0 of 0": a pair of zeroes beside designed prose
              reads as an instrument that failed to fill. */}
          {measuredDays > 0 && (
            <div className="ga-days">
              <div className="ga-days-head">
                <span className="t-eyebrow">DAYS OF RECORD</span>
                <span className="t-mono ga-days-count">
                  {measuredDays} of {TREND_NEEDS_DAYS}
                </span>
              </div>
              {/* Ninety marks, N cut. A count of days is not a KPI, so this is
                  drawable today where a chart is not. */}
              <div
                className="ga-days-strip"
                role="img"
                aria-label={`${measuredDays} of ${TREND_NEEDS_DAYS} days recorded`}
              >
                {Array.from({ length: TREND_NEEDS_DAYS }, (_, i) => (
                  <span className="ga-tick" key={i} data-cut={i < measuredDays || undefined} />
                ))}
              </div>
            </div>
          )}

          {readings.length === 0 ? (
            <p className="ga-note">
              No series has a measurable reading in this window, so there is no
              figure to show beside the count. That is the state of the record,
              not a failure to fetch it.
            </p>
          ) : (
            <dl className="ga-readings">
              {readings.map(({ series, latest, first }) => (
                <div className="ga-reading" key={series.key}>
                  <dt className="t-eyebrow">{series.display_name.toUpperCase()}</dt>
                  <dd>
                    <div className="ga-reading-val t-figure">
                      {figure(latest.value, series.unit)}
                    </div>
                    <p className="ga-reading-note t-mono">
                      {first !== null ? (
                        <>
                          from {figure(first.value, series.unit)} on{" "}
                          {readable(first.captured_on)}. {series.measurable_days} day
                          {series.measurable_days === 1 ? "" : "s"} is not a trend; it
                          is shown because it is all there is.
                        </>
                      ) : (
                        <>
                          recorded from {readable(latest.captured_on)} only, so there
                          is no earlier reading and nothing to compare this with yet.
                        </>
                      )}
                    </p>
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------ predicted vs realized -- */

/**
 * The bets, and the mandates they are attached to.
 *
 * One list, two panels' worth of material, because the platform has one door to
 * it: `GET /ai/strategy/reviews-due` names the mandates whose review has come
 * due, and `…/{id}/realized` answers for one of them. There is no "every
 * mandate ever" read, so this room shows the ones that are asking for a
 * decision and says that is what it is showing.
 */
function Bets() {
  const due = useResource(fetchReviewsDue);

  if (due.phase === "pending") {
    return (
      <section className="ga-panel m-plate" aria-label="Predicted versus realized">
        <Scaffold label="The mandates">
          <div className="m-well ga-ghost-well">
            <Lines n={5} />
          </div>
        </Scaffold>
      </section>
    );
  }

  if (due.phase === "failed") {
    return (
      <section className="ga-panel m-plate" aria-label="Predicted versus realized">
        <Failed
          alone={false}
          what="the mandates due for review"
          reason={due.reason}
          onRetry={due.retry}
        />
      </section>
    );
  }

  return (
    <section className="ga-panel m-plate" aria-label="Predicted versus realized">
      <div className="ga-panel-head">
        <h2 className="t-eyebrow">MANDATES DUE · PREDICTED &amp; REALIZED</h2>
        {due.value.length > 0 && (
          <span className="t-mono ga-whisper ga-due">
            {/* Sanctioned gold (§2.1): a review that has come due is literally
                "this needs you". It is the only gold in this room. */}
            <span className="m-lamp" data-lit data-breathing />
            {due.value.length} waiting on you
          </span>
        )}
      </div>

      {due.value.length === 0 ? (
        <Empty
          icon="clock"
          title="No mandate is due for review."
          body="A mandate comes here on the date it said it should be looked at again. None has reached that date, so nothing is asking you to decide whether it worked — which is a quiet estate, not an empty one."
        />
      ) : (
        <ul className="ga-ghosts">
          {due.value.map((mandate) => (
            <Bet key={mandate.record_id} mandate={mandate} />
          ))}
        </ul>
      )}

      <p className="ga-note">
        Every version of a mandate is kept and{" "}
        <strong>none of them can be read</strong> — the record service serves the
        current row and no history of it, so there is no diff to open and no
        ledger to walk. That is the one thing this wall was designed to show and
        cannot.
      </p>
    </section>
  );
}

function Bet({ mandate }: { mandate: DueMandate }) {
  const realized = useResource(() => fetchRealized(mandate.record_id));
  const title = textOf(mandate["title"]) ?? mandate.record_id.slice(0, 8);
  const reviewDue = textOf(mandate["review_due"]);
  const status = textOf(mandate["status"]);

  return (
    <li className="ga-ghost">
      <div className="ga-ghost-head">
        <h3 className="ga-ghost-label t-display">{title}</h3>
        {status !== null && (
          <span className="ga-state">
            <span className="m-lamp" data-positive={status === "issued" || undefined} />
            {status}
          </span>
        )}
      </div>

      <p className="ga-ghost-what">
        {reviewDue !== null
          ? `Its review came due on ${readable(reviewDue)}.`
          : "Its review is due and the record does not say when it fell."}
      </p>

      {realized.phase === "pending" ? (
        /* Bars without a `Scaffold`, deliberately: there is one of these per
           mandate, and `Scaffold`'s live sentence would announce "still
           arriving" once per row. The panel around them is already on screen
           and already announced, so the row's structure is decorative until it
           has content in it — which is the same claim `Scaffold` makes, minus
           the announcement it would repeat five times. */
        <div className="m-well ga-ghost-well" aria-hidden="true">
          <Lines n={2} />
        </div>
      ) : realized.phase === "failed" ? (
        <Failed
          alone={false}
          what="this mandate's outcome"
          reason={realized.reason}
          onRetry={realized.retry}
        />
      ) : (
        <Outcome outcome={realized.value} />
      )}
    </li>
  );
}

function Outcome({ outcome }: { outcome: RealizedMandate }) {
  const predicted = outcome.predicted_value;
  const value = outcome.realized_value;
  const both = predicted !== null && value !== null;
  /* Both bars are scaled to the larger of the two, so the pair is a fair
     comparison of itself and never of another row. */
  const max = both ? Math.max(predicted, value) : 0;
  /* A width is data and cannot live in a stylesheet — the same exception the
     district room's gauge takes. Nothing here animates, so no layout property
     is being transitioned. The 3% floor keeps a very small value visible as a
     bar rather than as nothing. */
  const width = (v: number) => `${max > 0 ? Math.max(3, (v / max) * 100) : 3}%`;

  const grade = outcome.honesty_grade;
  const word = grade === null ? null : (GRADE_WORD[grade] ?? grade);

  return (
    <>
      {both && (
        <dl className="ga-pair">
          <div className="ga-pair-row">
            <dt className="t-eyebrow">PREDICTED</dt>
            <dd>
              <span className="ga-track">
                <span
                  className="ga-bar"
                  data-kind="predicted"
                  style={{ width: width(predicted) }}
                />
              </span>
              <span className="ga-pair-val t-mono">{predicted}</span>
            </dd>
          </div>
          <div className="ga-pair-row">
            <dt className="t-eyebrow">REALIZED</dt>
            <dd>
              <span className="ga-track">
                <span className="ga-bar" data-kind="realized" style={{ width: width(value) }} />
              </span>
              <span className="ga-pair-val t-mono">{value}</span>
            </dd>
          </div>
        </dl>
      )}

      {/* Three different absences, and they are three different facts. Neither
          renders a bar and none of them renders a zero (§7.1). */}
      {predicted === null && (
        <p className="ga-ghost-absent">
          <span className="m-lamp" />
          No prediction was made. Neither a target nor a forecast carries a
          value, so there is nothing to hold the outcome against — only the
          outcome.
        </p>
      )}

      {!outcome.measurable && (
        <p className="ga-ghost-absent">
          <span className="m-lamp" />
          {VERDICT_WORD["not_measurable"]}
          {/* The engine's own reasons, verbatim. "We cannot tell" is a real
              answer and it is worth more with the why attached. */}
          {outcome.missing.length > 0 && ` — ${outcome.missing.join("; ")}.`}
        </p>
      )}

      {outcome.verdict !== null && outcome.verdict !== "not_measurable" && (
        <p className="ga-ghost-delta">
          <span
            className="m-lamp"
            data-positive={
              outcome.verdict === "met" || outcome.verdict === "on_track" || undefined
            }
            data-negative={
              outcome.verdict === "missed" || outcome.verdict === "off_track" || undefined
            }
          />
          {VERDICT_WORD[outcome.verdict] ?? outcome.verdict}
          {outcome.kpi_key !== null && ` · measured on ${outcome.kpi_key}`}
          {outcome.direction !== null && ` · ${outcome.direction} is better`}
        </p>
      )}

      <p className="ga-ghost-over">
        {word === null ? (
          <>
            No honesty grade travelled with this one — the mandate has no
            proposition behind it, so nobody graded the bet when it was placed.
          </>
        ) : (
          <>
            Graded <strong>{word}</strong> when it was made
            {outcome.predicted_from !== null &&
              `, and the prediction is the ${outcome.predicted_from}'s`}
            .
          </>
        )}
      </p>

      {/* Named only where there is one. `untested` has no run by definition
          (STRAT's `_GRADES_NEEDING_A_RUN` excludes it), and the absence of this
          line is the structural tell that keeps `untested` from reading like
          `unknown`. It is a line and not a chip because the Gallery has no route
          to the Glasshouse: a control that echoes and opens nothing is the
          affordance the Terrace already deleted. */}
      {outcome.twin_run_id !== null && (
        <p className="ga-ghost-over">
          The run behind it is <strong>{outcome.twin_run_id}</strong>, in the
          Glasshouse.
        </p>
      )}
    </>
  );
}

/* -------------------------------------------------------------- scaffold -- */

/**
 * The pending state (D7 §3.1): the room's own structure, standing, with the
 * words not yet in it. No spinner — this is one of the seventeen.
 *
 * Plates first, bars inside them: `vh-skeleton`'s ground is a ~6/255 delta on
 * the raw canvas, so a bar on the page background would draw nothing.
 */
function GalleryScaffold() {
  return (
    <section className="ga">
      <Scaffold label="The Gallery">
        <header className="ga-head">
          <Bar width="xs" />
          <Bar width="md" tall />
        </header>
        <div className="ga-panel m-plate">
          <Bar width="xs" />
          <div className="ga-spine">
            {Array.from({ length: 4 }, (_, i) => (
              <div className="ga-spine-cell" key={i}>
                <div className="ga-scaffold-card m-plate">
                  <Bar width="sm" />
                  <Bar width="md" />
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="ga-row">
          {Array.from({ length: 2 }, (_, i) => (
            <div className="ga-panel m-plate" key={i}>
              <Bar width="xs" />
              <Lines n={5} />
            </div>
          ))}
        </div>
      </Scaffold>
    </section>
  );
}

