import { Fragment, useMemo, useState } from "react";

import { Icon } from "../components/Icon";
import { Bar, Empty, Failed, Lines, Scaffold, useChoice, useResource } from "../lifecycle";
import {
  fetchDocuments,
  fetchInfluence,
  fetchPassage,
  type DocumentOut,
  type InfluenceOut,
  type PassageOut,
} from "../api/library";
import { grouped } from "./BoardroomSurface";
import "./library.css";

/**
 * The Library · depth 2 · S (D6 §13) — what the estate knows. On
 * `/ai/documents/*` (R-4 part W).
 *
 * Answers finding **RD-7**: this was built as a "sheet equivalent" and
 * inherited a fallback's budget. It is the room where a business owner finds
 * out *why* a colleague answered the way it did, which makes it one of the
 * load-bearing rooms rather than a file list.
 *
 * Three reads, and each column is one of them:
 *
 *   the shelf       `GET /ai/documents`
 *   the viewer      `GET /ai/documents/{id}/passage`
 *   the influence   `GET /ai/documents/{id}/influence`
 *
 * ## The four collections are the wire's own, not a metaphor
 *
 * `provenance.SourceKind` is a closed set — `upload`, `connected_drive`,
 * `generated_artifact`, `conversation_derived` — and it maps one-to-one onto
 * the four collections this surface already drew. A fifth appears only when a
 * document carries a kind this client does not recognise: a shelf that quietly
 * dropped a document would be a library lying about its own contents.
 *
 * ## The rendered gaps, and which of them are still true
 *
 * **The contradiction flag stays a gap, and it is now stateable more exactly.**
 * `staleness_state` really does carry `contradicted` — it is in the vocabulary
 * every read returns — and `raise_contradiction` in `library/staleness.py` has
 * **no caller anywhere in the platform** except its own tests. So the state is
 * reachable in the schema and unreachable in fact. Staleness above it is live
 * and is measured by a nightly sweep. That is the same finding the fixture
 * carried, checked again rather than copied forward.
 *
 * **Citations are gone, and that is new.** The surface used to open a citation
 * at its passage: who asked what, which colleague answered, and out of which
 * chunk. `retrieval_usages` holds all of it and **no endpoint exposes a row of
 * it** — `/influence` answers off the daily rollup, in counts only. §7.1 says a
 * binding that cannot be answered renders nothing, so the citation list, the
 * cited-by portraits and the read-by districts are absent rather than
 * invented, and the surface says so once.
 *
 * **The viewer is the document's opening, not its outline.** No endpoint lists
 * a document's chunks; `/passage` answers around a chunk index you already
 * know. So the middle column shows what retrieval holds at the head of the
 * file — real chunk indices, real heading paths, real text — and says that is
 * what it is. A page image would be a lie drawn over an absence: nothing in
 * the platform renders a page, and there is no page number on the wire at all.
 *
 * **Nothing here writes.** "Mark it superseded" and "withdraw it from
 * retrieval" were controls over endpoints that do not exist — `/ai/documents`
 * ships a list, a passage, an influence read, an upload and a search, and no
 * mutation of provenance or staleness. Staleness is the sweep's to set. A
 * control that does nothing is worse than no control, so they are gone and the
 * reason is on the surface.
 *
 * ## The one gold spend, and why it survived the wiring
 *
 * It was: a superseded document still being cited. Citations are gone, so it
 * would have gone with them — except the same claim is computable from what
 * the wire *does* answer. A document whose `staleness_state` is `superseded`
 * or `contradicted` and whose influence window shows **active days** is one
 * colleagues are still answering out of. That is precisely "this needs you"
 * (§2.1), it is now measured rather than asserted, and it is the only gold on
 * the surface.
 */

/* ============================================================== collections */

interface CollectionDef {
  id: string;
  label: string;
  /** Where its documents came from, in the owner's words. Provenance is this
   *  room's whole subject, so "generated" and "from conversations" may not be
   *  left as a guess. */
  note: string;
}

/** Where the shelf opens. A named kind rather than `COLLECTIONS[0]`, so the
 *  default cannot silently become whichever collection happens to be first. */
const OPENS_ON = "upload";

/** `library/provenance.py`'s closed set, in the order an owner meets them. */
const COLLECTIONS: CollectionDef[] = [
  { id: OPENS_ON, label: "uploads", note: "You put these here yourself." },
  {
    id: "connected_drive",
    label: "drives",
    note: "Mirrored from a drive you connected.",
  },
  {
    id: "generated_artifact",
    label: "generated",
    note: "Written by the estate, out of your own records.",
  },
  {
    id: "conversation_derived",
    label: "from conversations",
    note: "Lifted out of a conversation rather than filed as a file.",
  },
];

/** Anything whose `source_kind` this client does not know. Shown only when it
 *  has documents in it — a shelf that silently dropped one would be worse than
 *  a shelf with an awkward extra heading. */
const ELSEWHERE: CollectionDef = {
  id: "",
  label: "elsewhere",
  note: "Filed under a provenance this screen does not recognise.",
};

function collectionOf(doc: DocumentOut): string {
  const kind = doc.source_kind;
  if (kind === null) return ELSEWHERE.id;
  return COLLECTIONS.some((c) => c.id === kind) ? kind : ELSEWHERE.id;
}

/* ================================================================ staleness */

/** `provenance.StalenessState` — five values, and the surface uses the sweep's
 *  own words so a reader can match what is on screen to what wrote it. */
const STALENESS: Record<string, { word: string; tone: "good" | "bad" | "plain" }> = {
  fresh: { word: "fresh", tone: "good" },
  aging: { word: "aging", tone: "plain" },
  stale: { word: "stale", tone: "bad" },
  superseded: { word: "superseded", tone: "bad" },
  contradicted: { word: "contradicted", tone: "bad" },
};

/** A lamp is never alone: every caller prints the word beside it. */
function StaleLamp({ tone }: { tone: "good" | "bad" | "plain" }) {
  return (
    <span
      className="m-lamp"
      data-positive={tone === "good" || undefined}
      data-negative={tone === "bad" || undefined}
    />
  );
}

/* ================================================================== helpers */

function markFor(fileType: string): "spreadsheet" | "thread" | "document" {
  const kind = fileType.toLowerCase();
  if (kind.includes("sheet") || kind.includes("csv") || kind.includes("xls")) {
    return "spreadsheet";
  }
  if (kind.includes("thread") || kind.includes("conversation")) return "thread";
  return "document";
}

/** The stamp is naive UTC on the wire (`datetime.utcnow` on a zoneless column)
 *  and `Date` reads a naive ISO string as **local**, which is a five-and-a-half
 *  hour lie in IST. `null` rather than a guess when it cannot be read. */
function dayOf(iso: string | null): string | null {
  if (iso === null || iso === "") return null;
  const stamped = /T/.test(iso) && !/(?:Z|[+-]\d{2}:?\d{2})$/.test(iso) ? `${iso}Z` : iso;
  const at = new Date(stamped);
  if (Number.isNaN(at.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: /T/.test(iso) ? undefined : "UTC",
  }).format(at);
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

/* ================================================================ the surface */

export function LibrarySurface({ onEcho }: { onEcho: (msg: string) => void }) {
  const documents = useResource(fetchDocuments);

  if (documents.phase === "pending") return <LibraryScaffold />;

  if (documents.phase === "failed") {
    return (
      <section className="li">
        <Failed
          what="the Library"
          reason={documents.reason}
          onRetry={documents.retry}
        />
      </section>
    );
  }

  return <Shelves docs={documents.value} onEcho={onEcho} />;
}

function Shelves({
  docs,
  onEcho,
}: {
  docs: DocumentOut[];
  onEcho: (msg: string) => void;
}) {
  const [collection, setCollection] = useState<string>(OPENS_ON);
  const [query, setQuery] = useState("");

  /* L1: was `useState<string>(DOCS[0]!.id)` — a TypeError before render on a
     library nobody has uploaded to, which is every library on day one. */
  const { chosen: doc, choose } = useChoice(docs, (d) => d.id);

  const shelf = useMemo(() => {
    const wanted = query.trim().toLowerCase();
    return docs.filter(
      (d) =>
        collectionOf(d) === collection &&
        (wanted === "" || d.filename.toLowerCase().includes(wanted)),
    );
  }, [docs, collection, query]);

  const elsewhere = docs.filter((d) => collectionOf(d) === ELSEWHERE.id).length;
  const stillReading = docs.filter((d) => d.upload_status !== "completed").length;

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
          body="Anything you put here is chunked, indexed and quotable — a colleague answering a question can then cite the passage it came from instead of asserting it. Nothing has been uploaded, and nothing has been written by a colleague either, so there is nothing to cite."
        />
      </section>
    );
  }

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
            {docs.length} {docs.length === 1 ? "document" : "documents"}
            {/* A count of what is not yet readable, never a count of zero. */}
            {stillReading > 0 && <span> · {stillReading} still being read</span>}
          </p>
        </div>

        {/* Collections as a register, one per `source_kind`. */}
        <div className="li-collections" role="group" aria-label="Collections">
          {[...COLLECTIONS, ...(elsewhere > 0 ? [ELSEWHERE] : [])].map((c) => {
            const n = docs.filter((d) => collectionOf(d) === c.id).length;
            return (
              <button
                key={c.label}
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
            /* L2, and deliberately bespoke rather than the `Empty` well: this
               column is 260px wide and the well's own air would push the list
               off the screen. Two different emptinesses, and they were one
               sentence before — a filter that matched nothing is a fact about
               the query, an empty collection is a fact about the estate, and
               telling someone "nothing matches that" when they have typed
               nothing tells them the wrong thing about their own library. */
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
                const state = STALENESS[d.staleness_state ?? ""];
                return (
                  <li key={d.id}>
                    <button
                      className="li-doc"
                      data-selected={d.id === doc.id || undefined}
                      aria-current={d.id === doc.id}
                      onClick={() => choose(d.id)}
                    >
                      <span className="m-plinth li-doc-mark" aria-hidden="true">
                        <Icon name={markFor(d.file_type)} size={14} />
                      </span>
                      <span className="li-doc-text">
                        <span className="li-doc-name">{d.filename}</span>
                        <span className="li-doc-meta t-mono">{d.file_type}</span>
                        {/* An unassessed document gets no word at all rather
                            than being called fresh on this screen's authority. */}
                        {state !== undefined && (
                          <span className="li-stale">
                            <StaleLamp tone={state.tone} />
                            {state.word}
                          </span>
                        )}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </aside>

        {/* ---------------------------------------------------------- viewer */}
        <Viewer key={doc.id} doc={doc} onEcho={onEcho} />

        {/* ------------------------------------------------------ provenance */}
        <Provenance key={`prov-${doc.id}`} doc={doc} all={docs} onOpen={choose} />
      </div>
    </section>
  );
}

/* =================================================================== viewer */

/** One chunk as `read_passage` returns it. Read off the response by hand
 *  because `PassageOut` in `src/api/library.ts` describes a `chunks` array and
 *  the endpoint answers with `passages` — see the report; the wrapper is not
 *  this round's to change. */
interface Passage {
  chunkId: string;
  chunkIndex: string;
  headingPath: string[];
  content: string;
  isCited: boolean;
}

function passagesOf(payload: PassageOut): Passage[] {
  const rows = payload["passages"];
  if (!Array.isArray(rows)) return [];
  const out: Passage[] = [];
  for (const row of rows) {
    if (typeof row !== "object" || row === null) continue;
    const cell = row as Record<string, unknown>;
    const content = cell["content"];
    if (typeof content !== "string" || content === "") continue;
    const heading = cell["heading_path"];
    out.push({
      chunkId: String(cell["chunk_id"] ?? ""),
      chunkIndex: String(cell["chunk_index"] ?? ""),
      /* `heading_path` is one string on the wire; the crumb is drawn from its
         separators, and a path with none is one segment rather than none. */
      headingPath:
        typeof heading === "string" && heading !== ""
          ? heading.split(/\s*[>›/]\s*/).filter((seg) => seg !== "")
          : [],
      content,
      isCited: cell["is_cited"] === true,
    });
  }
  return out;
}

function Viewer({ doc, onEcho }: { doc: DocumentOut; onEcho: (msg: string) => void }) {
  const passage = useResource(() => fetchPassage(doc.id, 0));
  /* Open by default, and the state holds what has been *closed*. The endpoint
     answers two or three chunks, so a viewer that made you click each one to
     read it would be a file list wearing a viewer's layout — the point of this
     column is the text. */
  const [closed, setClosed] = useState<string[]>([]);

  const rows = passage.phase === "ready" ? passagesOf(passage.value) : [];

  return (
    <article className="li-viewer m-plate m-ticks" data-raised>
      <div className="li-view-head">
        <h2 className="li-view-name t-display">{doc.filename}</h2>
        <dl className="li-view-facts">
          <div className="li-view-fact">
            <dt className="t-eyebrow">FORMAT</dt>
            <dd>{doc.file_type}</dd>
          </div>
          <div className="li-view-fact">
            <dt className="t-eyebrow">STATUS</dt>
            <dd>{doc.upload_status}</dd>
          </div>
          {doc.memory_domain !== null && (
            <div className="li-view-fact">
              <dt className="t-eyebrow">DOMAIN</dt>
              <dd>{doc.memory_domain}</dd>
            </div>
          )}
          <div className="li-view-fact">
            <dt className="t-eyebrow">ID</dt>
            <dd>{doc.id}</dd>
          </div>
        </dl>
      </div>

      {passage.phase === "pending" && (
        <div className="li-ghost" aria-hidden="true">
          <Bar width="md" />
          <Lines n={4} />
        </div>
      )}

      {passage.phase === "failed" && (
        <Failed
          what="this document’s passages"
          alone={false}
          reason={passage.reason}
          onRetry={passage.retry}
        />
      )}

      {passage.phase === "ready" && rows.length === 0 && (
        <p className="li-empty">
          Nothing has been indexed from this file yet, so there is no passage to
          show. Chunks and their heading paths come out of indexing, and until
          that has run there is nothing here to point at rather than an empty
          frame.
        </p>
      )}

      {passage.phase === "ready" && rows.length > 0 && (
        <>
          {/* The stand-in's own disclosure, above the thing it describes: a
              reader must know what they are looking at before they read it. */}
          <p className="li-standin t-mono">
            This is the document’s <strong>opening</strong>, as retrieval holds
            it — not its pages, and not an outline of the whole file. Nothing in
            the platform renders a page, and no endpoint lists a document’s
            chunks; what you see is the chunk index, the heading path and the
            text that was actually stored.
          </p>

          <div className="m-well li-outline-well">
            <ol className="li-outline">
              {rows.map((row) => {
                const isOpen = !closed.includes(row.chunkId);
                return (
                  <li
                    className="li-sec"
                    key={row.chunkId}
                    data-open={isOpen || undefined}
                  >
                    <button
                      className="li-sec-row"
                      aria-expanded={isOpen}
                      onClick={() => {
                        setClosed((previous) =>
                          isOpen
                            ? [...previous, row.chunkId]
                            : previous.filter((id) => id !== row.chunkId),
                        );
                        if (!isOpen) {
                          onEcho(`opened ${doc.filename} at chunk ${row.chunkIndex}`);
                        }
                      }}
                    >
                      <span className="li-sec-page t-mono">#{row.chunkIndex}</span>
                      <span className="li-sec-body">
                        {row.headingPath.length > 0 ? (
                          <HeadingPath path={row.headingPath} />
                        ) : (
                          /* No heading path is a real answer about how this
                             file was split, not a blank to fill. */
                          <span className="li-path-none t-mono">
                            no heading path was stored for this chunk
                          </span>
                        )}
                        <span className="li-sec-meta t-mono">
                          {row.isCited && (
                            <span className="m-chip li-sec-cited">the chunk asked for</span>
                          )}
                        </span>
                      </span>
                    </button>

                    {isOpen && (
                      <div className="m-well li-passage vh-enter" data-deep>
                        <div className="li-passage-head">
                          <span className="li-passage-ref">chunk_index {row.chunkIndex}</span>
                          <button
                            className="li-passage-close"
                            aria-label="Close this passage"
                            onClick={() =>
                              setClosed((previous) => [...previous, row.chunkId])
                            }
                          >
                            <Icon name="close" size={12} />
                          </button>
                        </div>
                        <p className="li-passage-text">{row.content}</p>
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
  );
}

/* =============================================================== provenance */

/** The counter the influence sentence prints — as a value, not a comment.
 *
 *  The panel reads `counters[INFLUENCE_SENTENCE_BINDS]`, so printing the wrong
 *  one takes an edit here rather than a slip in JSX, and the name is on screen
 *  next to the figure. `questions_answered` is `distinct_queries` under its
 *  honest name: `retrievals` is a **row count** that grows with how finely the
 *  chunker split the file, so binding it would flatter a badly-chunked
 *  document. The sentence "answered N questions" may bind nothing else. */
const INFLUENCE_SENTENCE_BINDS = "questions_answered" as const;

const COUNTER_ORDER = [
  "questions_answered",
  "retrievals",
  "peak_distinct_colleagues",
] as const;

const COUNTER_MEANS: Record<(typeof COUNTER_ORDER)[number], string> = {
  questions_answered: "questions this document was retrieved for, summed by day",
  retrievals: "rows returned, every passage every time",
  peak_distinct_colleagues: "the most colleagues that used it on any one day",
};

function Provenance({
  doc,
  all,
  onOpen,
}: {
  doc: DocumentOut;
  all: DocumentOut[];
  onOpen: (id: string) => void;
}) {
  const influence = useResource(() => fetchInfluence(doc.id));

  const state = STALENESS[doc.staleness_state ?? ""];
  const replacement =
    doc.superseded_by_id === null
      ? null
      : (all.find((d) => d.id === doc.superseded_by_id) ?? null);

  const reading: InfluenceOut | null =
    influence.phase === "ready" ? influence.value : null;
  /* `active_days` counts rollup rows in the window. Zero of them means nothing
     has been measured — either the document has never been retrieved or the
     rollup has not run — and every counter beside it is a `COALESCE(…, 0)`
     rather than an observation. So the whole panel is an absence, not a row of
     zeros: "answered 0 questions" claims a measurement was taken. */
  const measured = reading !== null && reading.active_days > 0;

  /* The one gold spend. Not the supersede — the fact that colleagues are still
     answering out of it. */
  const needsYou =
    measured &&
    (doc.staleness_state === "superseded" || doc.staleness_state === "contradicted");

  return (
    <aside className="li-prov m-plate">
      <div className="li-panel-head">
        <h2 className="t-eyebrow">PROVENANCE</h2>
        <span className="li-panel-count t-mono">{doc.id.slice(0, 8)}</span>
      </div>

      <div className="li-prov-body">
        {/* -------------------------------------------------- where from */}
        <section className="li-block">
          <h3 className="t-eyebrow">WHERE IT CAME FROM</h3>

          <div className="li-origin" data-noface>
            <span className="li-origin-text">
              <span className="li-origin-name">
                {(COLLECTIONS.find((c) => c.id === doc.source_kind) ?? ELSEWHERE).label}
              </span>
              <span className="li-origin-how">
                {(COLLECTIONS.find((c) => c.id === doc.source_kind) ?? ELSEWHERE).note}
              </span>
            </span>
          </div>

          <dl className="li-facts">
            {dayOf(doc.created_at) !== null && (
              <div className="li-fact">
                <dt className="t-eyebrow">ADDED</dt>
                <dd>{dayOf(doc.created_at)}</dd>
              </div>
            )}
            {/* Absent dates render nothing at all — not a dash. A generated
                note has no effective period, and inventing one would be a claim
                about when it stopped being true. */}
            {dayOf(doc.effective_from) !== null && (
              <div className="li-fact">
                <dt className="t-eyebrow">EFFECTIVE FROM</dt>
                <dd>{dayOf(doc.effective_from)}</dd>
              </div>
            )}
            {doc.source_uri !== null && (
              <div className="li-fact">
                <dt className="t-eyebrow">SOURCE</dt>
                <dd className="t-mono li-source-uri">{doc.source_uri}</dd>
              </div>
            )}
          </dl>

          <p className="li-gap t-mono">
            Who put it here is not on this record — the platform stores the
            provenance of a document and not a person beside it, so no name is
            shown rather than a plausible one.
          </p>
        </section>

        {/* --------------------------------------------------- staleness */}
        <section className="li-block">
          <h3 className="t-eyebrow">STALENESS</h3>

          <div className="li-staleness" data-state={doc.staleness_state ?? undefined}>
            {state === undefined ? (
              <>
                <p className="li-staleness-word">
                  <StaleLamp tone="plain" />
                  not assessed
                </p>
                <p className="li-staleness-what">
                  The staleness sweep has not reached this document, so nothing
                  is known about whether it is still true. That is not the same
                  as it being current, and this screen will not say it is.
                </p>
              </>
            ) : (
              <>
                <p className="li-staleness-word">
                  <StaleLamp tone={state.tone} />
                  {state.word}
                </p>
                {/* The sweep's own sentence. Every transition records one
                    precisely so the flag's basis is visible — a flag whose
                    basis is invisible is a flag people learn to dismiss. */}
                {doc.staleness_reason !== null && (
                  <p className="li-staleness-what">{doc.staleness_reason}</p>
                )}
                {doc.staleness_state === "superseded" && (
                  <p className="li-staleness-what">
                    {replacement !== null ? (
                      <>
                        Replaced by <strong>{replacement.filename}</strong>. It is
                        still readable and still cited — a superseded document is
                        history, not a mistake.
                      </>
                    ) : doc.superseded_by_id !== null ? (
                      <>
                        The document that replaced it is not in this library’s
                        list, so it is named by id only:{" "}
                        <span className="t-mono">{doc.superseded_by_id}</span>.
                      </>
                    ) : (
                      <>
                        Nothing is named as its replacement, so nothing is drawn
                        where one would be.
                      </>
                    )}
                  </p>
                )}
              </>
            )}
          </div>

          {replacement !== null && (
            <div className="li-acts">
              <button
                className="m-btn"
                data-rank="quiet"
                onClick={() => onOpen(replacement.id)}
              >
                <Icon name="forward" size={13} />
                Open what replaced it
              </button>
            </div>
          )}

          <p className="li-gap t-mono">
            Staleness is computed by a nightly sweep and there is no way to set
            it by hand — `/ai/documents` answers a list, a passage, an influence
            read, an upload and a search, and nothing that writes provenance. So
            there is no “mark it superseded” here, and no way to withdraw a
            document from retrieval.
          </p>
        </section>

        {/* ---------------------------------------------------- needs you */}
        {needsYou && reading !== null && (
          <section className="li-needs vh-enter">
            <p className="li-needs-top">
              <span className="m-lamp" data-lit />
              <span className="li-needs-word">this needs you</span>
            </p>
            <p className="li-needs-what">
              This document is {STALENESS[doc.staleness_state ?? ""]?.word} and
              colleagues are still answering out of it: it was used on{" "}
              {reading.active_days} of the last {reading.window_days} days. Until
              it is taken out of retrieval, answers will keep coming from a
              document the estate has already stopped believing.
            </p>
            <p className="li-gap t-mono">
              Nothing in the platform withdraws a document from retrieval, so
              there is no control here to do it with. Uploading its replacement
              is what moves the sweep on.
            </p>
          </section>
        )}

        {/* --------------------------------------------------- influence */}
        <section className="li-block">
          <h3 className="t-eyebrow">INFLUENCE</h3>

          {influence.phase === "pending" && (
            <div className="li-ghost" aria-hidden="true">
              <Lines n={2} />
            </div>
          )}

          {influence.phase === "failed" && (
            <Failed
              what="this document’s influence"
              alone={false}
              reason={influence.reason}
              onRetry={influence.retry}
            />
          )}

          {influence.phase === "ready" &&
            (measured && reading !== null ? (
              <div className="li-infl">
                <div className="li-gauge-row">
                  {/* Six segments, per the wireframe, and bound to a figure the
                      endpoint actually answers: days active out of the window.
                      aria-hidden — the reading beside it carries the value in
                      words and numerals. */}
                  <span className="li-gauge" aria-hidden="true">
                    {Array.from({ length: 6 }, (_, i) => (
                      <span
                        key={i}
                        className="li-seg"
                        data-filled={
                          i < Math.round((reading.active_days / reading.window_days) * 6) ||
                          undefined
                        }
                      />
                    ))}
                  </span>
                  <span className="li-gauge-read">
                    used on {reading.active_days} of the last {reading.window_days} days
                  </span>
                </div>

                {/* The sentence a novice reads. It binds `questions_answered`,
                    by indexing the reading with the constant that names it. */}
                <p className="li-infl-sentence">
                  Answered{" "}
                  <strong>
                    {grouped(reading[INFLUENCE_SENTENCE_BINDS])}{" "}
                    {reading[INFLUENCE_SENTENCE_BINDS] === 1 ? "question" : "questions"}
                  </strong>{" "}
                  in {reading.window_days} days.
                </p>

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
                          <span className="m-chip li-counter-bound">the sentence above</span>
                        )}
                        <span className="vh-sr-only"> — {COUNTER_MEANS[k]}</span>
                      </dt>
                      <dd>{grouped(reading[k])}</dd>
                    </div>
                  ))}
                </dl>

                <p className="li-counters-why">
                  Two counters, because one of them flatters a badly-split
                  document: <strong>retrievals</strong> is a row count, so it
                  rises when the chunker cuts finer whatever the document was
                  worth. <strong>questions_answered</strong> counts questions,
                  which is why it is the one the sentence prints — and it is
                  summed by day, so a question asked on two days counts twice.
                </p>

                <p className="li-gap t-mono">
                  There is no chunk_hits counter on this endpoint and no
                  influence score: the rollup keeps rows, questions, colleagues
                  and days, and a score would be this screen inventing a
                  weighting nobody chose.
                </p>
              </div>
            ) : (
              /* Absent, not zero. No gauge, no counters, no "0 questions" —
                 every figure on this endpoint is a `COALESCE(…, 0)` over a
                 window with no rows in it. */
              <p className="li-absent">
                Nothing has been measured for this document. Either no colleague
                has retrieved it yet, or the nightly rollup has not covered it —
                the counts would read zero either way, so none is shown.
              </p>
            ))}
        </section>

        {/* --------------------------------------------------- the gaps
            Stated, so no reader thinks either was forgotten. */}
        <p className="li-gap t-mono">
          There is no citations list here, and no cited-by. Every retrieval is
          logged with the colleague and the question, and nothing exposes a row
          of it — the influence read answers counts off a daily rollup. So the
          passage a colleague answered out of cannot be opened from this room
          yet, and it is not drawn as if it could.
        </p>
        <p className="li-gap t-mono">
          There is no contradictions section either. `contradicted` is a real
          staleness state and `raise_contradiction` has no caller anywhere in
          the platform, so a panel would be an empty frame pretending to be a
          feature. Staleness above is live and is measured.
        </p>
      </div>
    </aside>
  );
}

/**
 * The pending state: the Library's own three columns, standing, with the words
 * not yet in them (D7 §3.1 — layout first, data second, and no spinner on any
 * of the seventeen).
 *
 * The plates are drawn first and the bars go *inside* them. `vh-skeleton`'s
 * ground is a 6/255 delta on the raw canvas, so a bar on the page background is
 * invisible; on a plate it reads.
 */
function LibraryScaffold() {
  return (
    <section className="li">
      <Scaffold label="The Library">
        <div className="li-ghost-room">
          <header className="li-head">
            <div className="li-ghost">
              <Bar width="xs" />
              <Bar width="md" tall />
            </div>
          </header>
          <div className="li-body">
            <aside className="li-shelf m-plate">
              <Bar width="sm" />
              <Lines n={5} />
            </aside>
            <article className="li-viewer m-plate" data-raised>
              <Bar width="md" tall />
              <Lines n={4} />
            </article>
            <aside className="li-prov m-plate">
              <Bar width="sm" />
              <Lines n={4} />
            </aside>
          </div>
        </div>
      </Scaffold>
    </section>
  );
}
