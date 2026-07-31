import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "../components/Icon";
import { Portrait } from "../components/Portrait";
import { Seal } from "../components/Seal";
import { Empty, useChoice } from "../lifecycle";
import {
  COLLECTIONS,
  DOCS,
  INFLUENCE_SENTENCE_BINDS,
  THE_CONTRADICTION_GAP,
  type Citation,
  type Collection,
  type Doc,
  type Staleness,
} from "../fixtures/library";
import "./library.css";

/**
 * The Library · depth 2 · S (D6 §13) — what the estate knows.
 *
 * Answers finding **RD-7**: this was built as a "sheet equivalent" and inherited
 * a fallback's budget. It is the room where a business owner finds out *why* a
 * colleague answered the way it did, which makes it one of the load-bearing
 * rooms, not a file list.
 *
 * Three decisions a reader could not recover from the code:
 *
 *  1. **The influence sentence indexes the fixture with a constant**
 *     (`counters[INFLUENCE_SENTENCE_BINDS]`) instead of naming a field in JSX.
 *     "Answered 40 questions" is `distinct_queries`; `retrievals` is a row count
 *     that grows with how finely the chunker split the file, so binding it would
 *     flatter a badly-chunked document. Making the binding a value means the
 *     wrong counter cannot be printed by a slip, and all three are shown below
 *     the sentence with the bound one named — the next reader is told, not
 *     trusted.
 *  2. **The viewer is an outline with a page gutter, and says so.** There is no
 *     page renderer anywhere in the platform, so a page image would be a lie
 *     drawn over an absence. What retrieval genuinely projects — `heading_path`,
 *     `chunk_index`, page — is exactly what the middle column draws, and the
 *     passages are the chunks that were actually returned. A citation opens the
 *     section, scrolls it to centre, and hangs the chunk off the page marker: the
 *     affordance `heading_path` was projected for.
 *  3. **The one gold spend is a superseded document still being cited.** Not the
 *     supersede itself — that is terracotta plus the word — but the fact that two
 *     colleagues have answered customers out of a retired price list *since* it
 *     was retired. That is precisely "this needs you" (§2.1), and it is the only
 *     gold on the surface. Selection, filters and landed passages are all
 *     `--surface-2` plus a strong edge.
 *
 * The contradiction flag is deliberately absent — see `THE_CONTRADICTION_GAP`.
 * Nothing calls `raise_contradiction`, so the surface prints one quiet line
 * saying why there is no panel rather than shipping an empty one.
 */

const STALE_WORD: Record<Staleness, string> = {
  current: "current",
  expiring: "expiring",
  superseded: "superseded",
};

/** The three counters, in the order an operator reads them: question count first. */
const COUNTER_ORDER = ["distinct_queries", "chunk_hits", "retrievals"] as const;

const COUNTER_MEANS: Record<(typeof COUNTER_ORDER)[number], string> = {
  distinct_queries: "questions this document was retrieved for",
  chunk_hits: "distinct passages ever returned",
  retrievals: "rows returned, every passage every time",
};

function markFor(format: string) {
  if (format === "Spreadsheet") return "spreadsheet" as const;
  if (format === "Extracted thread") return "thread" as const;
  return "document" as const;
}

function HeadingPath({ path }: { path: string[] }) {
  return (
    <span className="li-path">
      {path.map((seg, i) => (
        <Fragment key={`${seg}-${i}`}>
          {i > 0 && (
            <span className="li-path-sep" aria-hidden="true">
              ›
            </span>
          )}
          <span className={i === path.length - 1 ? "li-path-leaf" : undefined}>{seg}</span>
        </Fragment>
      ))}
    </span>
  );
}

/** A lamp is never alone: every caller prints the word beside it. */
function StaleLamp({ state }: { state: Staleness }) {
  return (
    <span
      className="m-lamp"
      data-positive={state === "current" || undefined}
      data-negative={state === "superseded" || undefined}
    />
  );
}

export function LibrarySurface({ onEcho }: { onEcho: (msg: string) => void }) {
  const [collection, setCollection] = useState<Collection>("uploads");
  /* L1: was `useState<string>(DOCS[0]!.id)` — a TypeError before render on a
     library nobody has uploaded to, which is every library on day one. */
  const { chosen: doc, choose } = useChoice(DOCS, (d) => d.id);
  const docId = doc?.id;
  const [query, setQuery] = useState("");
  const [openCite, setOpenCite] = useState<string | null>(null);
  /** Marked superseded here, by hand, with no replacement named. */
  const [markedStale, setMarkedStale] = useState<string[]>([]);
  /** Withdrawn from retrieval — the fix for the needs-you case. */
  const [withdrawn, setWithdrawn] = useState<string[]>([]);

  const openRow = useRef<HTMLLIElement | null>(null);

  const shelf = useMemo(() => {
    const q = query.trim().toLowerCase();
    return DOCS.filter(
      (d) => d.collection === collection && (q === "" || d.filename.toLowerCase().includes(q)),
    );
  }, [collection, query]);

  const citesBySection = useMemo(() => {
    const map = new Map<number, Citation[]>();
    if (doc === undefined) return map;
    doc.citations.forEach((c) => {
      const i = doc.sections.findIndex(
        (s) => c.chunkIndex >= s.chunkFrom && c.chunkIndex <= s.chunkTo,
      );
      if (i < 0) return;
      map.set(i, [...(map.get(i) ?? []), c]);
    });
    return map;
  }, [doc]);

  /* The landing. scrollIntoView rather than an animation — nothing here animates
     a layout property, and the reduced-motion preference is honoured because a
     smooth scroll is motion whatever fires it. */
  useEffect(() => {
    const row = openRow.current;
    if (!row) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    row.scrollIntoView({ block: "center", behavior: still ? "auto" : "smooth" });
  }, [openCite, docId]);

  /* L2. Every column below is one document's, so with no documents there is no
     partial library to draw. The copy names what an upload buys, because an
     empty library is the one state where the room has to explain itself. */
  if (doc === undefined) {
    return (
      <section className="li">
        <Empty
          alone
          icon="document"
          title="The estate has read nothing yet."
          body="Anything you put here is chunked, indexed and quotable — a colleague answering a question can then cite the page it came from instead of asserting it. Nothing has been uploaded, and nothing has been written by a colleague either, so there is nothing to cite."
        />
      </section>
    );
  }

  const isMarked = markedStale.includes(doc.id);
  const isWithdrawn = withdrawn.includes(doc.id);
  const staleness: Staleness = isMarked ? "superseded" : doc.staleness;
  /** A hand-mark names no replacement, so nothing is drawn where one would be. */
  const supersededBy = isMarked ? null : doc.supersededBy;

  /* Read out as locals so the "absent means absent" test is one condition, and so
     nothing downstream needs a non-null assertion to print a measured figure. */
  const influence = doc.influence;
  const counters = doc.counters;

  const cite: Citation | null = doc.citations.find((c) => c.id === openCite) ?? null;

  const sectionOf = (c: Citation) =>
    doc.sections.findIndex((s) => c.chunkIndex >= s.chunkFrom && c.chunkIndex <= s.chunkTo);

  const openSection = cite ? sectionOf(cite) : -1;

  const stillIndexing = DOCS.filter((d) => d.indexingNote !== null).length;

  /* Citations are newest first in the fixture, so the head of this list is the
     most recent one — no date string is parsed anywhere on this surface. */
  const citedAfter = doc.citations.filter((c) => c.afterSupersede);
  const latestAfter = citedAfter[0];
  const needsYou = staleness === "superseded" && citedAfter.length > 0 && !isWithdrawn;

  function pickDoc(next: Doc) {
    choose(next.id);
    setOpenCite(null);
  }

  /* An arrow rather than a `function`: a hoisted declaration could in principle
     be called before the guard above, so TypeScript drops the narrowing on
     `doc` inside one. The arrow is created after it and keeps it. */
  const openAt = (c: Citation) => {
    setOpenCite(c.id);
    onEcho(`opened ${doc.filename} at page ${c.page}`);
  };

  return (
    <section className="li">
      {/* ------------------------------------------------------------- header */}
      <header className="li-head">
        <div className="li-head-row">
          <div>
            <span className="t-eyebrow">THE LIBRARY</span>
            <h1 className="li-title t-display">What the estate knows</h1>
          </div>
          <p className="li-head-count t-mono">
            {DOCS.length} documents
            {stillIndexing > 0 && <span> · {stillIndexing} still being read</span>}
          </p>
        </div>

        {/* Collections as a register. Each says where its documents came from —
            "generated" and "from conversations" are otherwise a guess about
            provenance, and provenance is this room's whole subject. */}
        <div className="li-collections" role="group" aria-label="Collections">
          {COLLECTIONS.map((c) => {
            const n = DOCS.filter((d) => d.collection === c.id).length;
            return (
              <button
                key={c.id}
                className="li-coll"
                data-selected={collection === c.id || undefined}
                aria-pressed={collection === c.id}
                onClick={() => setCollection(c.id)}
              >
                <span className="li-coll-top">
                  <span className="li-coll-label">{c.label}</span>
                  <span className="li-coll-count t-mono">{n}</span>
                </span>
                <span className="li-coll-note">{c.note}</span>
              </button>
            );
          })}
        </div>
      </header>

      <div className="li-body">
        {/* ----------------------------------------------------------- shelf */}
        <aside className="li-shelf m-plate">
          <div className="li-panel-head">
            <h2 className="t-eyebrow">ON THE SHELF</h2>
            <span className="li-panel-count t-mono">{shelf.length}</span>
          </div>

          <div className="li-search">
            <Icon name="search" size={13} />
            <input
              type="search"
              value={query}
              placeholder="filename"
              aria-label="Filter this collection by filename"
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>

          {shelf.length === 0 ? (
            /* L2. Two different emptinesses, and they were one sentence before:
               a filter that matched nothing is a fact about the query, and an
               empty collection is a fact about the estate. Telling someone
               "nothing matches that" when they have typed nothing is telling
               them the wrong thing about their own library. */
            <p className="li-shelf-empty">
              {query.trim() === "" ? (
                <>
                  Nothing has been filed under this collection. The others above
                  still have documents in them — the count beside each one is the
                  whole of it.
                </>
              ) : (
                <>
                  Nothing in this collection matches that. The box reads filenames
                  only — searching inside a document is retrieval’s work, and it
                  happens when you or a colleague asks a question.
                </>
              )}
            </p>
          ) : (
            <ul className="li-docs">
              {shelf.map((d) => {
                const state: Staleness = markedStale.includes(d.id) ? "superseded" : d.staleness;
                return (
                  <li key={d.id}>
                    <button
                      className="li-doc"
                      data-selected={d.id === doc.id || undefined}
                      aria-current={d.id === doc.id}
                      onClick={() => pickDoc(d)}
                    >
                      <span className="m-plinth li-doc-mark" aria-hidden="true">
                        <Icon name={markFor(d.format)} size={14} />
                      </span>
                      <span className="li-doc-text">
                        <span className="li-doc-name">{d.filename}</span>
                        <span className="li-doc-meta t-mono">
                          {d.format}
                          {d.pages !== null && <> · {d.pages} pages</>}
                        </span>
                        <span className="li-stale">
                          <StaleLamp state={state} />
                          {STALE_WORD[state]}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </aside>

        {/* ---------------------------------------------------------- viewer */}
        <article className="li-viewer m-plate m-ticks" data-raised>
          <div className="li-view-head">
            <h2 className="li-view-name t-display">{doc.filename}</h2>
            <dl className="li-view-facts">
              <div className="li-view-fact">
                <dt className="t-eyebrow">FORMAT</dt>
                <dd>{doc.format}</dd>
              </div>
              {doc.pages !== null && (
                <div className="li-view-fact">
                  <dt className="t-eyebrow">PAGES</dt>
                  <dd>{doc.pages}</dd>
                </div>
              )}
              {doc.sections.length > 0 && (
                <div className="li-view-fact">
                  <dt className="t-eyebrow">SECTIONS</dt>
                  <dd>{doc.sections.length}</dd>
                </div>
              )}
              <div className="li-view-fact">
                <dt className="t-eyebrow">ID</dt>
                <dd>{doc.id}</dd>
              </div>
            </dl>
          </div>

          {doc.sections.length === 0 ? (
            <p className="li-empty">
              No outline yet. Heading paths and chunk boundaries come out of
              indexing, and this one is still being read — so there is nothing
              here to point at rather than an empty frame.
            </p>
          ) : (
            <>
              {/* The stand-in's own disclosure, above the thing it describes: a
                  reader must know what they are looking at before they read it. */}
              <p className="li-standin t-mono">
                This is the document’s <strong>structure</strong>, not its pages.
                Nothing in the platform renders a page, so what you see is what
                retrieval actually projects — the heading path, the chunk index and
                the page — with the passages that were genuinely returned.
              </p>

              <div className="m-well li-outline-well">
                <ol className="li-outline">
                  {doc.sections.map((s, i) => {
                    const here = citesBySection.get(i) ?? [];
                    const first = here[0];
                    const isOpen = openSection === i && cite !== null;
                    /* The row's insides are the same either way; only a section
                       with a returned passage is a control, because a section with
                       none has nowhere to land. */
                    const inside = (
                      <>
                        <span className="li-sec-page t-mono">p. {s.page}</span>
                        <span className="li-sec-body">
                          <HeadingPath path={s.headingPath} />
                          <span className="li-sec-meta t-mono">
                            <span>
                              chunks {s.chunkFrom}–{s.chunkTo}
                            </span>
                            {here.length > 0 && (
                              <span className="m-chip li-sec-cited">
                                {here.length} {here.length === 1 ? "citation" : "citations"}
                              </span>
                            )}
                          </span>
                        </span>
                      </>
                    );
                    return (
                      <li
                        className="li-sec"
                        key={`${s.page}-${s.chunkFrom}`}
                        data-open={isOpen || undefined}
                        ref={isOpen ? openRow : undefined}
                      >
                        {first ? (
                          <button
                            className="li-sec-row"
                            aria-label={`Open ${s.headingPath.join(" › ")} on page ${s.page}`}
                            onClick={() => openAt(first)}
                          >
                            {inside}
                          </button>
                        ) : (
                          <div className="li-sec-row">{inside}</div>
                        )}

                        {isOpen && cite && (
                          <div className="m-well li-passage vh-enter" data-deep>
                            <div className="li-passage-head">
                              <span className="li-passage-ref">
                                p. {cite.page} · chunk_index {cite.chunkIndex}
                              </span>
                              <HeadingPath path={cite.headingPath} />
                              <button
                                className="li-passage-close"
                                aria-label="Close this passage"
                                onClick={() => setOpenCite(null)}
                              >
                                <Icon name="close" size={12} />
                              </button>
                            </div>
                            {/* One section can hold several citations. Both are
                                reachable from here rather than only from the
                                right-hand list, because once you have landed the
                                neighbouring passage is the next thing you want. */}
                            {here.length > 1 && (
                              <div
                                className="li-passage-switch"
                                role="group"
                                aria-label="Citations in this section"
                              >
                                {here.map((c) => (
                                  <button
                                    key={c.id}
                                    className="m-chip"
                                    data-selected={c.id === cite.id || undefined}
                                    onClick={() => openAt(c)}
                                  >
                                    {c.by.name} · #{c.chunkIndex}
                                  </button>
                                ))}
                              </div>
                            )}
                            <p className="li-passage-text">{cite.passage}</p>
                            <p className="li-passage-foot t-mono">
                              Returned to {cite.by.name} ({cite.by.role}) on {cite.when}, for
                              “{cite.question}”. Chunk {cite.chunkIndex} of the {s.chunkFrom}–
                              {s.chunkTo} that make up this section.
                            </p>
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ol>
              </div>

              <p className="li-viewer-foot t-mono">
                Chunk boundaries, embeddings and the retrieval trace for this
                document are in the Undercroft.
              </p>
            </>
          )}
        </article>

        {/* ------------------------------------------------------ provenance */}
        <aside className="li-prov m-plate">
          <div className="li-panel-head">
            <h2 className="t-eyebrow">PROVENANCE</h2>
            <span className="li-panel-count t-mono">{doc.id}</span>
          </div>

          <div className="li-prov-body">
            {/* -------------------------------------------------- where from */}
            <section className="li-block">
              <h3 className="t-eyebrow">WHERE IT CAME FROM</h3>

              {/* A colleague gets a Portrait; a connector gets a Seal; you get
                  neither. The halftone is an L7 AI disclosure — hanging one on a
                  person would say the opposite of what the medium means. */}
              <div className="li-origin" data-noface={doc.origin.kind === "you" || undefined}>
                {doc.origin.kind === "colleague" && (
                  <span className="m-portrait-well li-origin-well">
                    <Portrait id={doc.origin.id} size={38} />
                  </span>
                )}
                {doc.origin.kind === "connector" && (
                  <span className="m-portrait-well li-origin-well">
                    <Seal id={doc.origin.id} size={30} />
                  </span>
                )}
                <span className="li-origin-text">
                  <span className="li-origin-name">
                    {doc.origin.kind === "you" ? `${doc.origin.name} — you` : doc.origin.name}
                  </span>
                  <span className="li-origin-how">{doc.origin.how}</span>
                </span>
              </div>

              <dl className="li-facts">
                <div className="li-fact">
                  <dt className="t-eyebrow">ADDED</dt>
                  <dd>{doc.uploadedOn}</dd>
                </div>
                {/* Absent dates render nothing at all — not a dash. A generated
                    note has no effective period, and inventing one would be a
                    claim about when it stopped being true. */}
                {doc.effectiveFrom !== null && (
                  <div className="li-fact">
                    <dt className="t-eyebrow">EFFECTIVE FROM</dt>
                    <dd>{doc.effectiveFrom}</dd>
                  </div>
                )}
                {doc.effectiveTo !== null && (
                  <div className="li-fact">
                    <dt className="t-eyebrow">EFFECTIVE TO</dt>
                    <dd>{doc.effectiveTo}</dd>
                  </div>
                )}
              </dl>
            </section>

            {/* --------------------------------------------------- staleness */}
            <section className="li-block">
              <h3 className="t-eyebrow">STALENESS</h3>

              <div className="li-staleness" data-state={staleness}>
                <p className="li-staleness-word">
                  <StaleLamp state={staleness} />
                  {STALE_WORD[staleness]}
                </p>
                <p className="li-staleness-what">
                  {staleness === "superseded" && supersededBy && (
                    <>
                      Replaced by <strong>{supersededBy.filename}</strong> on{" "}
                      {supersededBy.on}. It is still readable and still cited — a
                      superseded document is history, not a mistake.
                    </>
                  )}
                  {staleness === "superseded" && !supersededBy && (
                    <>
                      You marked this superseded without naming what replaced it, so
                      nothing is drawn where the replacement would be. Name one and
                      colleagues will be pointed at it.
                    </>
                  )}
                  {staleness === "expiring" && doc.expiresOn && (
                    <>
                      Its effective period ends {doc.expiresOn}. Nothing happens
                      automatically on that date; colleagues are told the answer came
                      from a document that has run out.
                    </>
                  )}
                  {staleness === "current" && (
                    <>In force. Colleagues may answer from it without a caveat.</>
                  )}
                </p>
                {isWithdrawn && (
                  <p className="li-staleness-what">
                    <span className="li-stale">
                      <span className="m-lamp" />
                      withdrawn from retrieval
                    </span>{" "}
                    — no colleague can cite it again. The record and every citation
                    already made stay exactly where they are.
                  </p>
                )}
              </div>

              <div className="li-acts">
                {staleness === "current" && (
                  <button
                    className="m-btn"
                    onClick={() => {
                      setMarkedStale((xs) => [...xs, doc.id]);
                      onEcho(`marked ${doc.filename} superseded`);
                    }}
                  >
                    <Icon name="clock" size={13} />
                    Mark it superseded
                  </button>
                )}
                {supersededBy && DOCS.some((d) => d.id === supersededBy.id) && (
                  <button
                    className="m-btn"
                    data-rank="quiet"
                    onClick={() => {
                      const next = DOCS.find((d) => d.id === supersededBy.id);
                      if (!next) return;
                      setCollection(next.collection);
                      pickDoc(next);
                      onEcho(`opened ${next.filename}`);
                    }}
                  >
                    <Icon name="forward" size={13} />
                    Open what replaced it
                  </button>
                )}
                {isWithdrawn && (
                  <button
                    className="m-btn"
                    data-rank="quiet"
                    onClick={() => {
                      setWithdrawn((xs) => xs.filter((x) => x !== doc.id));
                      onEcho(`put ${doc.filename} back into retrieval`);
                    }}
                  >
                    <Icon name="undo" size={13} />
                    Put it back
                  </button>
                )}
              </div>
            </section>

            {/* ---------------------------------------------------- needs you
                The surface's one gold spend. Not the supersede — the fact that
                colleagues are still answering customers out of it. */}
            {needsYou && (
              <section className="li-needs vh-enter">
                <p className="li-needs-top">
                  <span className="m-lamp" data-lit />
                  <span className="li-needs-word">this needs you</span>
                </p>
                <p className="li-needs-what">
                  {citedAfter.length === 1
                    ? "One answer has"
                    : `${citedAfter.length} answers have`}{" "}
                  gone out of this document since it was superseded
                  {latestAfter && (
                    <>
                      {" "}
                      — the most recent from {latestAfter.by.name} on {latestAfter.when}
                    </>
                  )}
                  . Until it is withdrawn, colleagues will keep answering customers
                  out of a document you have already replaced.
                </p>
                <div className="li-acts">
                  <button
                    className="m-btn"
                    onClick={() => {
                      setWithdrawn((xs) => [...xs, doc.id]);
                      onEcho(`withdrew ${doc.filename} from retrieval`);
                    }}
                  >
                    Withdraw it from retrieval
                  </button>
                </div>
              </section>
            )}

            {/* --------------------------------------------------- influence */}
            <section className="li-block">
              <h3 className="t-eyebrow">INFLUENCE</h3>

              {influence !== null && counters ? (
                <div className="li-infl">
                  <div className="li-gauge-row">
                    {/* Six segments, per the wireframe. aria-hidden: the reading
                        beside it carries the value in words and numerals. */}
                    <span className="li-gauge" aria-hidden="true">
                      {Array.from({ length: 6 }, (_, i) => (
                        <span
                          key={i}
                          className="li-seg"
                          data-filled={i < Math.round(influence * 6) || undefined}
                        />
                      ))}
                    </span>
                    <span className="li-gauge-read">
                      {Math.round(influence * 6)} of 6 · score {influence.toFixed(2)}
                    </span>
                  </div>

                  {/* The sentence a novice reads. It binds distinct_queries, by
                      indexing the fixture with the constant that names it. */}
                  <p className="li-infl-sentence">
                    Answered{" "}
                    <strong>
                      {counters[INFLUENCE_SENTENCE_BINDS]}{" "}
                      {counters[INFLUENCE_SENTENCE_BINDS] === 1 ? "question" : "questions"}
                    </strong>{" "}
                    {counters.window}.
                  </p>

                  {doc.influenceBasis && <p className="li-infl-basis">{doc.influenceBasis}.</p>}

                  <dl className="m-well li-counters">
                    {COUNTER_ORDER.map((k) => (
                      <div
                        className="li-counter"
                        key={k}
                        data-bound={k === INFLUENCE_SENTENCE_BINDS || undefined}
                      >
                        <dt>
                          {k}
                          {k === INFLUENCE_SENTENCE_BINDS && (
                            <span className="m-chip li-counter-bound">
                              the sentence above
                            </span>
                          )}
                          <span className="vh-sr-only"> — {COUNTER_MEANS[k]}</span>
                        </dt>
                        <dd>{counters[k].toLocaleString("en-IN")}</dd>
                      </div>
                    ))}
                  </dl>
                  <p className="li-counters-why">
                    Three counters, because two of them flatter a badly-split
                    document: <strong>retrievals</strong> is a row count and{" "}
                    <strong>chunk_hits</strong> counts passages, so both rise when
                    the chunker cuts finer, whatever the document was worth.{" "}
                    <strong>distinct_queries</strong> counts questions, which is why
                    it is the one the sentence prints.
                  </p>
                </div>
              ) : (
                /* Absent, not zero. No gauge, no counters, no "0 questions" —
                   the sentence explains that nothing has been measured yet. */
                doc.indexingNote && <p className="li-absent">{doc.indexingNote}</p>
              )}
            </section>

            {/* ---------------------------------------------------- cited by */}
            {doc.citedBy.length > 0 && (
              <section className="li-block">
                <h3 className="t-eyebrow">CITED BY</h3>
                <ul className="li-cited-by">
                  {doc.citedBy.map((p) => (
                    <li className="li-citer" key={p.id}>
                      <span className="m-portrait-well li-citer-well" aria-hidden="true">
                        {/* A Meta-Agent is a role, not a persona — role gets the
                            seal, colleagues get the bust. */}
                        {p.role === "Meta-Agent" ? (
                          <Seal id={p.id} size={24} />
                        ) : (
                          <Portrait id={p.id} size={30} />
                        )}
                      </span>
                      <span className="li-citer-name">
                        <span className="li-citer-who">{p.name}</span>
                        <span className="li-citer-role">{p.role}</span>
                      </span>
                      <span className="li-citer-count">
                        {p.count} {p.count === 1 ? "answer" : "answers"}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* --------------------------------------------------- citations */}
            {doc.citations.length > 0 && (
              <section className="li-block">
                <div className="li-block-head">
                  <h3 className="t-eyebrow">CITATIONS</h3>
                  <span className="li-panel-count t-mono">opens at the passage</span>
                </div>
                <div className="li-cites">
                  {doc.citations.map((c) => (
                    <button
                      key={c.id}
                      className="li-cite"
                      data-open={c.id === openCite || undefined}
                      data-after={c.afterSupersede || undefined}
                      onClick={() => openAt(c)}
                    >
                      <span className="li-cite-text">
                        <span className="li-cite-q">“{c.question}”</span>
                        <span className="li-cite-where">
                          <HeadingPath path={c.headingPath} />
                          <span>· p. {c.page}</span>
                          <span>· #{c.chunkIndex}</span>
                          <span>· {c.by.name}</span>
                          {c.afterSupersede && (
                            <span className="li-cite-after">· after the supersede</span>
                          )}
                        </span>
                      </span>
                      <Icon name="chevron" size={13} className="li-cite-caret" />
                    </button>
                  ))}
                </div>
              </section>
            )}

            {/* ----------------------------------------------------- read by */}
            {doc.readBy.length > 0 && (
              <section className="li-block">
                <h3 className="t-eyebrow">READ BY</h3>
                <div className="li-districts">
                  {doc.readBy.map((d) => (
                    <span className="m-chip" key={d}>
                      <Icon name="district" size={11} />
                      {d}
                    </span>
                  ))}
                </div>
              </section>
            )}

            {/* --------------------------------------------------- the gap
                Stated, so no reader thinks it was forgotten. */}
            <p className="li-gap t-mono">{THE_CONTRADICTION_GAP}</p>
          </div>
        </aside>
      </div>
    </section>
  );
}
