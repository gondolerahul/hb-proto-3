import { useState } from "react";
import { Icon } from "../components/Icon";
import { Portrait } from "../components/Portrait";
import { Seal } from "../components/Seal";
import { GradeSeal } from "./BoardroomSurface";
import {
  ALUMNI,
  GHOSTS,
  MANDATES,
  MONUMENTS,
  RECORD,
  SEASONS,
  STILL_SERVING,
  type Ghost,
  type Season,
} from "../fixtures/gallery";
import "./gallery.css";

/**
 * The Gallery · depth 2 · S+W (D6 §11).
 *
 * Answers **RD-7** in its hardest form. The Gallery is the surface most likely to
 * have been built as a fallback, because it has the least to show: §11 says the
 * KPI series starts 2026-07-25 with no backfill, so for roughly a quarter there
 * is no history here at all. A fallback would have shipped an empty chart and an
 * apology. This is a room.
 *
 * Three decisions a reader could not reverse-engineer:
 *
 *  1. **The young state IS the design, not a degraded one.** The record's panel
 *     is an *empty frame with a plaque* — the honest gallery idiom: the wall
 *     space is reserved, and the plaque says what will hang there and when
 *     (23 October 2026, once ninety days sit behind it). Beside it, ninety tick
 *     marks with five cut. A timeline carrying one measured marker and a sentence
 *     explaining that the record starts here is more trustworthy than a fake
 *     history, and it is what the owner will actually see for a quarter — so it
 *     is what got the design budget.
 *  2. **"Told, not measured" is a material, not a caption.** Every season before
 *     25 July has no figures behind it, and rather than repeating that in prose
 *     five times it is the season card's own hatch — the same "not currently
 *     true" texture as the ghost bars and the drained portraits. The hatch stops
 *     at the gate where the record begins, so the spine shows you the boundary
 *     between the part of this company's life that was measured and the part that
 *     was only lived. The word is still there in the chapter beside it: the
 *     texture is the fast read, never the only one.
 *  3. **Draining is about time, not about decoration.** Colleagues past are
 *     drained (art bible §7.2) and Meera — still serving — sits on the same wall
 *     in full colour. Without her the drained material reads as a style; with
 *     her it reads as a statement about what is currently true. Monuments follow
 *     the same rule: a raiser who still serves is not drained, and a dismantled
 *     connector loses the warm base its standing siblings keep.
 *
 * Gold appears in exactly one content place: the medallion on a monument raised
 * by a certified act, and the word "certified" beside it. Selected seasons,
 * in-force mandates and beaten predictions get material and words instead.
 */

const SEASON_COUNT = SEASONS.length;
const STANDING = MONUMENTS.filter((m) => m.dismantledOn === null).length;

/**
 * The comparison, in words, with the lamp it earns.
 *
 * `better` decides the direction, because "41 where 34 was predicted" is worse
 * for days-outstanding and better for hours returned, and a bar cannot say which.
 */
function compare(g: Ghost, predicted: number): { text: string; tone: "positive" | "negative" | "plain" } {
  const d = g.realized - predicted;
  if (d === 0) {
    return { text: `exactly as predicted, at ${predicted}${g.unit}.`, tone: "plain" };
  }
  const good = g.better === "lower" ? d < 0 : d > 0;
  return {
    text: `${Math.abs(d)}${g.unit} ${d > 0 ? "above" : "below"} the prediction — ${
      good ? "better than the bet" : "worse than the bet"
    }.`,
    tone: good ? "positive" : "negative",
  };
}

export function GallerySurface({ onEcho }: { onEcho: (msg: string) => void }) {
  const [seasonId, setSeasonId] = useState<string>(
    (SEASONS.find((s) => s.current) ?? SEASONS[0]!).id,
  );
  const [openLedger, setOpenLedger] = useState<string | null>(null);

  const season: Season = SEASONS.find((s) => s.id === seasonId) ?? SEASONS[0]!;
  const seasonIndex = SEASONS.findIndex((s) => s.id === season.id);
  const raised = MONUMENTS.filter((m) => m.seasonId === season.id);
  const nameOf = (id: string) => SEASONS.find((s) => s.id === id)?.name ?? id;

  return (
    <section className="ga">
      {/* ------------------------------------------------------------- header */}
      <header className="ga-head">
        <span className="t-eyebrow">THE GALLERY · THE GROWTH JOURNEY</span>
        <h1 className="ga-title t-display">Four and a half months of a company</h1>
        <p className="t-narrative ga-lead">
          {SEASON_COUNT} seasons, {STANDING} monuments still standing, {GHOSTS.length}{" "}
          bets with their predictions still attached, and {ALUMNI.length} colleagues
          who are no longer here. The measured part of it is {RECORD.daysRecorded}{" "}
          days old, which is stated below rather than dressed up.
        </p>
      </header>

      {/* ======================================================== the seasons */}
      <section className="ga-panel ga-seasons m-plate" aria-label="Seasons">
        <div className="ga-panel-head">
          <h2 className="t-eyebrow">SEASONS</h2>
          <span className="t-mono ga-whisper">
            periods, not dates · the record joins at the last gate
          </span>
        </div>

        <div className="ga-spine vh-stagger" role="radiogroup" aria-label="Choose a season">
          {SEASONS.map((s, i) => {
            const previous = i > 0 ? SEASONS[i - 1]! : null;
            /* The gate is drawn where the hatch stops — between the last season
               told in words and the first one with a record behind it. */
            const gate = s.measured && (previous === null || !previous.measured);
            return (
              <div className="ga-spine-cell" key={s.id} style={{ ["--i" as string]: i }}>
                {gate && (
                  <div className="ga-gate">
                    <span className="t-eyebrow ga-gate-label">
                      THE RECORD BEGINS · {RECORD.startedOn.toUpperCase()}
                    </span>
                  </div>
                )}
                <button
                  className="ga-season"
                  role="radio"
                  aria-checked={s.id === season.id}
                  data-told={!s.measured || undefined}
                  onClick={() => {
                    setSeasonId(s.id);
                    onEcho(`opened ${s.name.toLowerCase()}`);
                  }}
                >
                  <span className="ga-season-mark" aria-hidden="true" />
                  <span className="t-mono ga-season-span">{s.span}</span>
                  <span className="ga-season-name t-display">{s.name}</span>
                  <span className="ga-season-foot">
                    {s.days} days
                    {s.current && " · now"}
                  </span>
                </button>
              </div>
            );
          })}
        </div>
      </section>

      <div className="ga-row">
        {/* ===================================================== the chapter */}
        <section className="ga-panel ga-chapter m-plate" aria-label="This season">
          <header className="ga-chapter-head">
            <span className="t-eyebrow">
              SEASON {seasonIndex + 1} OF {SEASON_COUNT}
            </span>
            <h2 className="ga-chapter-name t-display">{season.name}</h2>
            <span className="t-mono ga-chapter-span">
              {season.span} · {season.days} days
            </span>
          </header>

          {/* Lamp plus a word. The hatch on the card is the fast read; this is the
              correct one, and it is why no season above shows a figure. */}
          <span className="ga-state">
            <span className="m-lamp" data-positive={season.measured || undefined} />
            {season.measured
              ? "measured — the record was running"
              : "told, not measured — nothing was being recorded"}
          </span>

          <p className="t-narrative ga-chapter-story">{season.story}</p>

          {season.afterwards !== null && (
            <div className="ga-after">
              <span className="t-eyebrow">AND AFTERWARDS</span>
              <p className="ga-after-text">{season.afterwards}</p>
            </div>
          )}

          <hr className="m-rule-fade" />

          <div className="ga-panel-head">
            <h3 className="t-eyebrow">RAISED IN THIS SEASON</h3>
            <span className="t-mono ga-whisper">
              {raised.length === 0 ? "nothing" : `${raised.length} on this wall`}
            </span>
          </div>

          {raised.length === 0 ? (
            <p className="ga-empty">
              No monument was raised in this season. It was spent keeping what was
              already standing, and the record of that is in the mandates below
              rather than on this wall.
            </p>
          ) : (
            <ul className="ga-mons">
              {raised.map((m) => (
                <li className="ga-mon" key={m.id}>
                  {/* A raiser with a persona gets a bust; a district, a bridge or
                      an act of the estate has no persona and gets a seal (art
                      bible §7, C as the automatic fallback). */}
                  <span
                    className="m-portrait-well ga-mon-well"
                    data-past={m.dismantledOn !== null || undefined}
                  >
                    {m.by ? (
                      <Portrait
                        id={m.by.id}
                        size={44}
                        drained={!m.by.stillServing}
                        title={`${m.by.name} — a generated portrait, not a photograph`}
                      />
                    ) : (
                      <Seal
                        id={m.entityId}
                        size={40}
                        tone={m.dismantledOn === null ? "live" : "drained"}
                      />
                    )}
                  </span>

                  <span className="ga-mon-text">
                    <span className="ga-mon-name">
                      {m.name}
                      {m.certified && (
                        <>
                          <span className="m-medallion ga-medallion" aria-hidden="true">
                            <Icon name="check" size={11} />
                          </span>
                          <span className="t-eyebrow" data-certified>
                            CERTIFIED
                          </span>
                        </>
                      )}
                    </span>
                    <span className="ga-mon-what">{m.what}</span>
                    <span className="ga-mon-meta">
                      <span className="ga-mon-kind">
                        <Icon name={m.icon} size={11} />
                        {m.kind}
                      </span>
                      <span aria-hidden="true">·</span>
                      raised {m.raisedOn}
                      {m.by && (
                        <>
                          <span aria-hidden="true">·</span>
                          by {m.by.name}
                        </>
                      )}
                      {m.dismantledOn !== null && (
                        <>
                          <span aria-hidden="true">·</span>
                          <span className="ga-state">
                            <span className="m-lamp" />
                            dismantled {m.dismantledOn}
                          </span>
                        </>
                      )}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* ============================================== colleagues past */}
        <section className="ga-panel ga-wall m-plate" aria-label="Colleagues past">
          <div className="ga-panel-head">
            <h2 className="t-eyebrow">COLLEAGUES PAST</h2>
            <span className="t-mono ga-whisper">drained — not currently true</span>
          </div>

          <ul className="ga-alumni">
            {ALUMNI.map((a) => (
              <li className="ga-alum ga-alum-past" key={a.id}>
                <span className="m-portrait-well ga-alum-well">
                  <Portrait
                    id={a.id}
                    size={52}
                    drained
                    title={`${a.name} — a generated portrait, not a photograph`}
                  />
                </span>
                <span className="ga-alum-text">
                  <span className="ga-alum-name">
                    {a.name}
                    <span className="t-mono ga-alum-id">{a.id}</span>
                  </span>
                  <span className="ga-alum-served">
                    {a.role} · {a.served} · left in {nameOf(a.seasonLeftId).toLowerCase()}
                  </span>
                  <span className="ga-alum-why">{a.why}</span>
                </span>
              </li>
            ))}
          </ul>

          <hr className="m-rule-fade ga-wall-rule" />

          {/* The contrast. One colleague still serving, on the same wall, not
              drained — otherwise the draining reads as a style choice. */}
          <div className="ga-alum">
            <span className="m-portrait-well ga-alum-well">
              <Portrait
                id={STILL_SERVING.id}
                size={52}
                title={`${STILL_SERVING.name} — a generated portrait, not a photograph`}
              />
            </span>
            <span className="ga-alum-text">
              <span className="t-eyebrow">STILL SERVING</span>
              <span className="ga-alum-name">
                {STILL_SERVING.name}
                <span className="t-mono ga-alum-id">{STILL_SERVING.id}</span>
              </span>
              <span className="ga-alum-served">
                {STILL_SERVING.role} · {STILL_SERVING.served}
              </span>
              <span className="ga-alum-why">{STILL_SERVING.note}</span>
            </span>
          </div>
        </section>
      </div>

      {/* ========================================================= the record */}
      <section className="ga-panel ga-record m-plate" aria-label="The measured record">
        <div className="ga-panel-head">
          <h2 className="t-eyebrow">THE MEASURED RECORD</h2>
          <span className="t-mono ga-whisper">
            starts {RECORD.startedOn} · nothing before it was backfilled
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
              <p className="ga-plaque-text">
                The record is {RECORD.daysRecorded} days old. A line drawn through{" "}
                {RECORD.daysRecorded} points would flatter itself, so this frame
                stays empty until <strong>{RECORD.firstTrendOn}</strong>, when{" "}
                {RECORD.trendNeedsDays} days sit behind it.
              </p>
              <p className="ga-note">
                Nothing before {RECORD.startedOn} was backfilled and nothing can be
                — the series begins where the measuring began. The seasons before
                it are told in words for that reason, not because their figures are
                hidden somewhere.
              </p>
            </figcaption>
          </figure>

          <div className="ga-record-side">
            <div className="ga-days">
              <div className="ga-days-head">
                <span className="t-eyebrow">DAYS OF RECORD</span>
                <span className="t-mono ga-days-count">
                  {RECORD.daysRecorded} of {RECORD.trendNeedsDays}
                </span>
              </div>
              {/* Ninety marks, five cut. A count of days is not a KPI, so this is
                  drawable today where a chart is not. */}
              <div
                className="ga-days-strip"
                role="img"
                aria-label={`${RECORD.daysRecorded} of ${RECORD.trendNeedsDays} days recorded`}
              >
                {Array.from({ length: RECORD.trendNeedsDays }, (_, i) => (
                  <span
                    className="ga-tick"
                    key={i}
                    data-cut={i < RECORD.daysRecorded || undefined}
                  />
                ))}
              </div>
            </div>

            <dl className="ga-readings">
              {RECORD.readings.map((r) => (
                <div className="ga-reading" key={r.label}>
                  <dt className="t-eyebrow">{r.label}</dt>
                  <dd>
                    <div className="ga-reading-val t-figure">{r.reading}</div>
                    <p className="ga-reading-note t-mono">
                      {r.first !== null ? (
                        <>
                          from {r.first.value} on {r.first.on}. {RECORD.daysRecorded}{" "}
                          days is not a trend; it is shown because it is all there
                          is.
                        </>
                      ) : (
                        <>
                          recorded from {r.recordedFrom} only, so there is no
                          earlier reading and nothing to compare this with yet.
                        </>
                      )}
                    </p>
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </section>

      <div className="ga-row">
        {/* ================================= predicted vs realized — the ghost */}
        <section className="ga-panel m-plate" aria-label="Predicted versus realized">
          <div className="ga-panel-head">
            <h2 className="t-eyebrow">PREDICTED &amp; REALIZED</h2>
            <span className="t-mono ga-whisper">
              every promotion, with its prediction still attached
            </span>
          </div>

          <ul className="ga-ghosts">
            {GHOSTS.map((g) => {
              /* Both bars are scaled to the larger of the two, so the pair is a
                 fair comparison of itself and never of another row. */
              const max = Math.max(g.predicted ?? 0, g.realized);
              /* A width is data and cannot live in a stylesheet — the same
                 exception the district room's meters take. Nothing here animates,
                 so no layout property is being transitioned. The 3% floor keeps a
                 very small value visible as a bar rather than as nothing. */
              const width = (v: number) => `${Math.max(3, (v / max) * 100)}%`;
              const verdict = g.predicted === null ? null : compare(g, g.predicted);

              return (
                <li className="ga-ghost" key={g.id}>
                  <div className="ga-ghost-head">
                    <h3 className="ga-ghost-label t-display">{g.label}</h3>
                    <GradeSeal grade={g.grade} compact />
                  </div>

                  <p className="ga-ghost-what">{g.what}</p>

                  <dl className="ga-pair">
                    {/* No prediction renders no ghost row at all. A zero-length
                        bar would be a bet nobody made. */}
                    {g.predicted !== null && (
                      <div className="ga-pair-row">
                        <dt className="t-eyebrow">PREDICTED</dt>
                        <dd>
                          <span className="ga-track">
                            <span
                              className="ga-bar"
                              data-kind="predicted"
                              style={{ width: width(g.predicted) }}
                            />
                          </span>
                          <span className="ga-pair-val t-mono">
                            {g.predicted}
                            {g.unit}
                          </span>
                        </dd>
                      </div>
                    )}

                    <div className="ga-pair-row">
                      <dt className="t-eyebrow">REALIZED</dt>
                      <dd>
                        <span className="ga-track">
                          <span
                            className="ga-bar"
                            data-kind="realized"
                            style={{ width: width(g.realized) }}
                          />
                        </span>
                        <span className="ga-pair-val t-mono">
                          {g.realized}
                          {g.unit}
                        </span>
                      </dd>
                    </div>
                  </dl>

                  {verdict === null ? (
                    <p className="ga-ghost-absent">
                      <span className="m-lamp" />
                      No prediction was made. This was promoted without a run behind
                      it, so there is nothing to hold the outcome against — only the
                      outcome.
                    </p>
                  ) : (
                    <p className="ga-ghost-delta">
                      <span
                        className="m-lamp"
                        data-positive={verdict.tone === "positive" || undefined}
                        data-negative={verdict.tone === "negative" || undefined}
                      />
                      {verdict.text}
                    </p>
                  )}

                  <p className="ga-ghost-over">
                    {g.over} · promoted {g.promotedOn} in{" "}
                    {nameOf(g.seasonId).toLowerCase()}
                  </p>

                  {/* The run is offered only where there is one. `untested` has no
                      run by definition (decisions.ts §1), and a disabled button
                      over that absence would imply one exists. */}
                  {g.grade.twinRunId !== null && (
                    <div className="ga-acts">
                      <button
                        className="m-chip"
                        onClick={() => onEcho(`opened twin run ${g.grade.twinRunId}`)}
                      >
                        <Icon name="search" size={11} />
                        {g.grade.twinRunId}
                      </button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </section>

        {/* ====================================================== the mandates */}
        <section className="ga-panel m-plate" aria-label="Mandates">
          <div className="ga-panel-head">
            <h2 className="t-eyebrow">MANDATES</h2>
            <span className="t-mono ga-whisper">
              {MANDATES.filter((m) => m.state === "in-force").length} in force ·
              every version diffable
            </span>
          </div>

          <ul className="ga-mandates">
            {MANDATES.map((m) => {
              const open = openLedger === m.id;
              return (
                <li className="ga-mandate" key={m.id}>
                  <div className="ga-mandate-top">
                    <span className="t-mono ga-mandate-id">{m.id}</span>
                    <h3 className="ga-mandate-title t-display">{m.title}</h3>
                    <span className="ga-state">
                      <span
                        className="m-lamp"
                        data-positive={m.state === "in-force" || undefined}
                      />
                      {m.state === "in-force"
                        ? "in force"
                        : `superseded by ${m.supersededBy}`}
                    </span>
                  </div>

                  <p className="ga-mandate-meta">
                    adopted {m.adoptedOn} in {nameOf(m.seasonId).toLowerCase()}
                    {m.resolution !== null && (
                      <>
                        {" · from "}
                        {m.resolution.id} — {m.resolution.title}
                      </>
                    )}
                    {/* Certified is the one meaning gold carries here. Absent
                        where there was no certified act — not back-dated into one. */}
                    {m.certifiedAs !== null && (
                      <>
                        {" · "}
                        <span className="t-eyebrow" data-certified>
                          CERTIFIED {m.certifiedAs}
                        </span>
                      </>
                    )}
                  </p>

                  {m.origin !== null && (
                    <p className="ga-note">
                      {m.origin} <strong>There is no resolution behind this one</strong>,
                      so there is nothing to walk back to.
                    </p>
                  )}

                  <div className="ga-acts">
                    <button
                      className="m-chip"
                      aria-expanded={open}
                      onClick={() => {
                        setOpenLedger(open ? null : m.id);
                        if (!open) onEcho(`opened the version ledger for ${m.id}`);
                      }}
                    >
                      <Icon name="chevron" size={11} />
                      {m.versions.length} version{m.versions.length === 1 ? "" : "s"}
                    </button>

                    {m.resolution !== null && (
                      <button
                        className="m-btn"
                        data-rank="quiet"
                        onClick={() =>
                          onEcho(`walked back from mandate ${m.id} to its resolution`)
                        }
                      >
                        <Icon name="undo" size={12} />
                        Walk back to {m.resolution.id}
                      </button>
                    )}
                  </div>

                  {open && (
                    <ol className="ga-versions m-well vh-enter-fade" data-deep>
                      {m.versions.map((v) => (
                        <li className="ga-version" key={v.v}>
                          <span className="ga-version-head t-mono">
                            {v.v} · {v.on} · {v.by}
                          </span>
                          {v.removed !== null && (
                            <span className="ga-diff" data-op="del">
                              <span className="ga-diff-sign" aria-hidden="true">
                                −
                              </span>
                              <span>
                                <span className="vh-sr-only">removed: </span>
                                {v.removed}
                              </span>
                            </span>
                          )}
                          <span className="ga-diff" data-op="add">
                            <span className="ga-diff-sign" aria-hidden="true">
                              +
                            </span>
                            <span>
                              <span className="vh-sr-only">
                                {v.removed === null ? "first version: " : "added: "}
                              </span>
                              {v.added}
                            </span>
                          </span>
                        </li>
                      ))}
                    </ol>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      </div>
    </section>
  );
}
