/**
 * The Library (DRIVER D9, D6 §13) — collections by source, the document
 * with its provenance, influence and staleness.
 *
 * The rules this surface exists to keep:
 *
 * - **"Answered N questions" binds `questions_answered`** (LIB's
 *   `distinct_queries`), never `retrievals` — a row count overstates
 *   influence in proportion to how finely the chunker split the file.
 * - **Staleness renders live** (it is), with ⚠ SUPERSEDED carrying its
 *   reason; **no contradiction section exists** until something calls
 *   `raise_contradiction` — an empty accusation panel would train the
 *   owner to ignore it.
 * - **Citations open at the passage** — the viewer is the passage read,
 *   which is why retrieval projects `heading_path` and `chunk_index`.
 * - A bridge-less document does not imply it was checked: provenance
 *   absent renders as "uploaded before provenance existed".
 */
import { useEffect, useState } from "react";

import { emitEcho } from "../api/genui";
import {
  fetchDocuments,
  fetchInfluence,
  fetchPassage,
  type DocumentOut,
  type InfluenceOut,
  type PassageOut,
} from "../api/library";

export interface LibraryLoaders {
  documents: typeof fetchDocuments;
  influence: typeof fetchInfluence;
  passage: typeof fetchPassage;
  echo: typeof emitEcho;
}

const REAL: LibraryLoaders = {
  documents: fetchDocuments,
  influence: fetchInfluence,
  passage: fetchPassage,
  echo: emitEcho,
};

const COLLECTION_LABELS: Record<string, string> = {
  upload: "uploads",
  drive: "drives",
  drive_sync: "drives",
  generated: "generated",
  conversation: "from conversations",
};

function collectionOf(document: DocumentOut): string {
  const kind = document.source_kind ?? "upload";
  return COLLECTION_LABELS[kind] ?? kind;
}

function DocumentPane({
  document,
  loaders,
}: {
  document: DocumentOut;
  loaders: LibraryLoaders;
}): JSX.Element {
  const [influence, setInfluence] = useState<InfluenceOut | null>(null);
  const [passage, setPassage] = useState<PassageOut | null>(null);
  const [viewerOpen, setViewerOpen] = useState(false);

  useEffect(() => {
    setInfluence(null);
    setPassage(null);
    setViewerOpen(false);
    void loaders
      .influence(document.id)
      .then(setInfluence)
      .catch(() => setInfluence(null));
  }, [document.id, loaders]);

  return (
    <section className="vh-doc-pane" data-part="doc-pane">
      <h3>{document.filename}</h3>

      <div data-part="provenance">
        <h4 className="vh-eyebrow">provenance</h4>
        {document.source_kind === null ? (
          <p className="vh-quiet">
            Uploaded before provenance existed — honest blank, not a checked
            box.
          </p>
        ) : (
          <p>
            {document.source_kind} · added{" "}
            {document.created_at.slice(0, 10)}
            {document.effective_from !== null &&
              ` · effective from ${document.effective_from}`}
          </p>
        )}
      </div>

      <div data-part="influence">
        <h4 className="vh-eyebrow">influence</h4>
        {influence === null ? (
          <p className="vh-quiet">No influence recorded in the window.</p>
        ) : (
          <p data-part="influence-sentence">
            answered <output>{influence.questions_answered}</output> questions
            in {influence.window_days} days · read by up to{" "}
            {influence.peak_distinct_colleagues} colleagues
          </p>
        )}
      </div>

      {document.staleness_state !== null &&
        document.staleness_state !== "fresh" && (
          <p className="vh-staleness" data-part="staleness" role="note">
            ⚠ {document.staleness_state.toUpperCase()}
            {document.staleness_reason !== null &&
              ` — ${document.staleness_reason}`}
          </p>
        )}

      <button
        type="button"
        className="vh-quiet-link"
        data-part="open-viewer"
        onClick={() => {
          setViewerOpen(true);
          if (passage === null) {
            void loaders
              .passage(document.id, 0)
              .then((loaded) => {
                setPassage(loaded);
                void loaders.echo({
                  sentence: `opened ${document.filename} at the first passage`,
                  action_ref: {
                    kind: "library.open",
                    surface_id: "library",
                    params: { document_id: document.id },
                  },
                });
              })
              .catch(() => setPassage({ chunks: [] }));
          }
        }}
      >
        ▸ viewer
      </button>
      {viewerOpen && passage !== null && (
        <div className="vh-passage" data-part="passage">
          {(passage.chunks ?? []).length === 0 ? (
            <p className="vh-quiet">The passage could not be read.</p>
          ) : (
            (passage.chunks ?? []).map((chunk) => (
              <blockquote key={chunk.chunk_index}>
                {chunk.heading_path !== null &&
                  chunk.heading_path !== undefined && (
                    <cite className="vh-mono">{chunk.heading_path}</cite>
                  )}
                <p>{chunk.content}</p>
              </blockquote>
            ))
          )}
        </div>
      )}
    </section>
  );
}

export function LibrarySurface({
  loaders = REAL,
}: {
  loaders?: LibraryLoaders;
}): JSX.Element {
  const [documents, setDocuments] = useState<DocumentOut[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [collection, setCollection] = useState<string | null>(null);
  const [selected, setSelected] = useState<DocumentOut | null>(null);

  useEffect(() => {
    void loaders
      .documents()
      .then(setDocuments)
      .catch(() => setFailed(true));
  }, [loaders]);

  if (failed) {
    return (
      <p role="alert" data-part="library-failed">
        The library could not be reached.
      </p>
    );
  }
  if (documents === null) {
    return <p className="vh-quiet">Opening the library…</p>;
  }

  const collections = [...new Set(documents.map(collectionOf))];
  const active = collection ?? collections[0] ?? null;
  const shelf = documents.filter((doc) => collectionOf(doc) === active);

  return (
    <div className="vh-library" data-part="library">
      <header className="vh-library-header">
        <h2>Library</h2>
        <nav aria-label="collections">
          {collections.map((name) => (
            <button
              key={name}
              type="button"
              className="vh-quiet-link"
              disabled={name === active}
              onClick={() => {
                setCollection(name);
                setSelected(null);
              }}
            >
              {name}
            </button>
          ))}
        </nav>
      </header>

      {documents.length === 0 ? (
        <p className="vh-quiet" data-part="library-empty">
          Nothing is on the shelves yet — the Library fills as documents
          land.
        </p>
      ) : (
        <div className="vh-library-body">
          <ul className="vh-shelf" data-part="shelf">
            {shelf.map((doc) => (
              <li key={doc.id}>
                <button
                  type="button"
                  className="vh-quiet-link"
                  onClick={() => setSelected(doc)}
                >
                  {doc.filename}
                  {doc.staleness_state !== null &&
                    doc.staleness_state !== "fresh" && <span> ⚠</span>}
                </button>
              </li>
            ))}
          </ul>
          {selected !== null && (
            <DocumentPane document={selected} loaders={loaders} />
          )}
        </div>
      )}
    </div>
  );
}
