/**
 * The Library — what the estate knows (D6 §13).
 *
 * Shaped to the LIB bindings named in the wireframe: `documents` plus LIB's
 * provenance / influence / staleness columns (`lib001`, `lib002`), and the
 * retrieval projections `document_id`, `staleness_state`, `heading_path`,
 * `chunk_index`, `filename`.
 *
 * ## The honesty rules, stated where they bite
 *
 * 1. **The influence sentence binds `distinct_queries`.** See `Counters` below —
 *    this is the one field in the file that a careless reader will get wrong, so
 *    the binding is a *constant the surface indexes with*
 *    (`INFLUENCE_SENTENCE_BINDS`) rather than a comment beside a number.
 * 2. **Absent means absent.** A document that has not finished indexing has
 *    `pages: null`, `influence: null`, `counters: null`. The surface renders
 *    nothing for those — no `0`, no dash. A freight sheet that has answered
 *    nothing is not a freight sheet that has answered zero questions; the second
 *    claims a measurement was taken.
 * 3. **`contradiction` is deliberately not modelled.** Nothing in the platform
 *    calls `raise_contradiction`, so the column exists and is always absent.
 *    There is no `contradictions` field here, because a field would invite a
 *    panel and the panel would be an empty frame pretending to be a feature.
 *    `THE_CONTRADICTION_GAP` below is what the surface prints instead.
 * 4. **Passages are the chunks retrieval actually returned.** Chunk text is in
 *    the store; a rendered page image is not, anywhere in the platform. So the
 *    viewer is structure plus real passages, and sections with no returned
 *    passage carry none and are not clickable.
 */

export type Collection = "uploads" | "drives" | "generated" | "conversations";

/** `staleness_state`, as retrieval projects it. All three are live today. */
export type Staleness = "current" | "expiring" | "superseded";

/**
 * The three counters LIB keeps, and what each one may be used to say.
 *
 * `retrievals` is a **row count**: every chunk returned, every time. It grows in
 * direct proportion to how finely the chunker split the document, so a
 * heavily-split file looks more influential than a coarse one that answered the
 * same questions. `chunk_hits` is distinct chunks ever returned — still a
 * property of the chunker, not of the document.
 *
 * `distinct_queries` is the only one of the three that counts *questions*, which
 * is why LIB shipped it as a third counter rather than reusing either of the
 * first two. The sentence "answered N questions this month" may bind nothing
 * else.
 */
export interface Counters {
  retrievals: number;
  chunk_hits: number;
  distinct_queries: number;
  /** The window the three counters are measured over. A count with no window is
      a claim rather than a measurement, so the surface always prints it. */
  window: string;
}

/**
 * The field the influence sentence prints — as a value, not a comment.
 *
 * The surface reads `counters[INFLUENCE_SENTENCE_BINDS]`, so printing the wrong
 * counter takes an edit here rather than a slip in JSX, and the name is on
 * screen next to the figure in the operator block.
 */
export const INFLUENCE_SENTENCE_BINDS = "distinct_queries" as const;

/** Whoever put the document in the Library. */
export interface Origin {
  /**
   * `you` is the tenant. `colleague` gets a Portrait; `connector` gets a Seal.
   * The tenant gets **neither** — Portrait is an L7 AI disclosure (a halftone
   * that cannot be mistaken for a photograph), and hanging one on a human being
   * would say the opposite of what the medium is for.
   */
  kind: "you" | "colleague" | "connector";
  id: string;
  name: string;
  /** How it arrived, in the owner's words. */
  how: string;
}

/** One section of the document's outline. Page + heading path + chunk span. */
export interface Section {
  page: number;
  /** `heading_path`, exactly as retrieval projects it. */
  headingPath: string[];
  /** `chunk_index` of the first and last chunk inside this section. */
  chunkFrom: number;
  chunkTo: number;
}

/**
 * A citation — a colleague's answer that leaned on this document.
 *
 * `headingPath` + `chunkIndex` + `page` are the reason a citation can open the
 * source *at the passage* rather than at the top of the file: retrieval projects
 * all three, and this is the affordance they were projected for.
 */
export interface Citation {
  id: string;
  headingPath: string[];
  chunkIndex: number;
  page: number;
  /** The chunk's own text. In the store, and therefore honest to print. */
  passage: string;
  /** The question it was returned for. */
  question: string;
  by: { id: string; name: string; role: string };
  when: string;
  /**
   * Dated after the document was superseded. This is the one genuine
   * "this needs you" on the surface: colleagues are still answering out of a
   * retired price list.
   */
  afterSupersede?: boolean;
}

export interface Doc {
  id: string;
  filename: string;
  collection: Collection;
  format: string;
  /** null until indexing finishes — the surface prints nothing. */
  pages: number | null;
  origin: Origin;
  uploadedOn: string;
  /** LIB's `effective_from`. null when the document carries no dated period. */
  effectiveFrom: string | null;
  effectiveTo: string | null;
  staleness: Staleness;
  /** Set only when `staleness === "superseded"` and the replacement is known. */
  supersededBy: { id: string; filename: string; on: string } | null;
  /** Set only when `staleness === "expiring"`. */
  expiresOn: string | null;
  /** LIB's influence score, 0..1. null when nothing has been measured yet. */
  influence: number | null;
  /** What the score is computed from. A gauge with no basis is decoration. */
  influenceBasis: string | null;
  counters: Counters | null;
  citedBy: { id: string; name: string; role: string; count: number }[];
  /** Districts whose colleagues have retrieved it. */
  readBy: string[];
  sections: Section[];
  citations: Citation[];
  /** Present only while the document is still being indexed. Prose, because the
      honest thing to say is a sentence and not an empty gauge. */
  indexingNote: string | null;
}

export const COLLECTIONS: {
  id: Collection;
  label: string;
  /** Where the documents in this collection came from, in the owner's words. */
  note: string;
}[] = [
  { id: "uploads", label: "uploads", note: "You put these here yourself." },
  { id: "drives", label: "drives", note: "Synced from the Google Drive folder you connected." },
  { id: "generated", label: "generated", note: "Written by a colleague, out of your own records." },
  {
    id: "conversations",
    label: "from conversations",
    note: "Lifted out of calls and threads, with the source turn kept.",
  },
];

/**
 * The line the surface prints where a contradictions panel would go.
 *
 * Kept in the fixture rather than the component because it is a statement about
 * the *platform*, not about this document — the day something calls
 * `raise_contradiction`, this constant is what gets deleted.
 */
export const THE_CONTRADICTION_GAP =
  "There is no contradictions section here. The flag exists on the record and nothing in the platform raises it yet — raise_contradiction has no caller — so a panel would be an empty frame pretending to be a feature. Staleness above is live and is measured.";

export const DOCS: Doc[] = [
  {
    id: "DOC-1141",
    filename: "Pricing 2026.pdf",
    collection: "uploads",
    format: "PDF",
    pages: 18,
    origin: { kind: "you", id: "you", name: "Rahul", how: "uploaded from this browser" },
    uploadedOn: "12 March 2026",
    effectiveFrom: "1 April 2026",
    effectiveTo: "30 June 2026",
    staleness: "superseded",
    supersededBy: { id: "DOC-1408", filename: "Pricing 2026-Q3.pdf", on: "2 July 2026" },
    expiresOn: null,
    influence: 0.83,
    influenceBasis: "40 distinct questions across 3 districts, weighted by how often the answer was acted on",
    counters: { retrievals: 214, chunk_hits: 96, distinct_queries: 40, window: "since 1 July 2026" },
    citedBy: [
      { id: "AGT-046", name: "Meera", role: "Collections", count: 22 },
      { id: "AGT-013", name: "Devika", role: "Quoting", count: 14 },
      { id: "META-PRAGYA", name: "Pragya", role: "Meta-Agent", count: 4 },
    ],
    readBy: ["Collections", "Acquisition"],
    sections: [
      { page: 1, headingPath: ["Front matter"], chunkFrom: 0, chunkTo: 2 },
      { page: 2, headingPath: ["Price list", "Cotton — grey"], chunkFrom: 3, chunkTo: 9 },
      { page: 4, headingPath: ["Price list", "Cotton — dyed"], chunkFrom: 10, chunkTo: 17 },
      { page: 7, headingPath: ["Terms of trade", "Payment terms"], chunkFrom: 18, chunkTo: 23 },
      { page: 9, headingPath: ["Terms of trade", "Late payment"], chunkFrom: 24, chunkTo: 29 },
      { page: 12, headingPath: ["Volume bands"], chunkFrom: 30, chunkTo: 38 },
      { page: 15, headingPath: ["Freight and handling"], chunkFrom: 39, chunkTo: 44 },
      { page: 17, headingPath: ["Annexure", "Signed schedule"], chunkFrom: 45, chunkTo: 46 },
    ],
    citations: [
      {
        id: "CIT-9021",
        headingPath: ["Terms of trade", "Late payment"],
        chunkIndex: 25,
        page: 9,
        passage:
          "Invoices fall due thirty days from the date of despatch. Interest of 1.25% per month accrues from the thirty-first day and is charged on the outstanding principal only. Interest is waived where a customer has settled every invoice on time for the preceding four quarters.",
        question: "Can I charge Kulkarni interest on KT-2291?",
        by: { id: "AGT-046", name: "Meera", role: "Collections" },
        when: "22 July, 09:13",
        afterSupersede: true,
      },
      {
        id: "CIT-8874",
        headingPath: ["Volume bands"],
        chunkIndex: 33,
        page: 12,
        passage:
          "Band C applies from 40,000 metres in a rolling quarter and carries 6% off the grey list. The band is assessed on despatched metres, not ordered metres, and a cancelled order does not count toward it.",
        question: "What discount does Ashoka Retail qualify for this quarter?",
        by: { id: "AGT-013", name: "Devika", role: "Quoting" },
        when: "18 July, 15:40",
        afterSupersede: true,
      },
      {
        id: "CIT-8102",
        headingPath: ["Price list", "Cotton — dyed"],
        chunkIndex: 12,
        page: 4,
        passage:
          "Dyed cotton, 40s combed, reactive dye: ₹214 per metre for lots of 5,000 metres and above, ₹228 below. Shade matching to a customer swatch is charged once per shade and not per lot.",
        question: "What did we quote Bhagwati Mills for 40s dyed in April?",
        by: { id: "META-PRAGYA", name: "Pragya", role: "Meta-Agent" },
        when: "26 June, 11:02",
      },
    ],
    indexingNote: null,
  },
  {
    id: "DOC-1408",
    filename: "Pricing 2026-Q3.pdf",
    collection: "uploads",
    format: "PDF",
    pages: 21,
    origin: { kind: "you", id: "you", name: "Rahul", how: "uploaded from this browser" },
    uploadedOn: "2 July 2026",
    effectiveFrom: "1 July 2026",
    effectiveTo: "30 September 2026",
    staleness: "current",
    supersededBy: null,
    expiresOn: null,
    influence: 0.29,
    influenceBasis: "6 distinct questions in its first four weeks, all from Acquisition",
    counters: { retrievals: 19, chunk_hits: 11, distinct_queries: 6, window: "since 1 July 2026" },
    citedBy: [{ id: "AGT-013", name: "Devika", role: "Quoting", count: 6 }],
    readBy: ["Acquisition"],
    sections: [
      { page: 1, headingPath: ["Front matter"], chunkFrom: 0, chunkTo: 2 },
      { page: 2, headingPath: ["Price list", "Cotton — grey"], chunkFrom: 3, chunkTo: 10 },
      { page: 5, headingPath: ["Price list", "Cotton — dyed"], chunkFrom: 11, chunkTo: 19 },
      { page: 8, headingPath: ["Terms of trade", "Payment terms"], chunkFrom: 20, chunkTo: 26 },
      { page: 11, headingPath: ["Terms of trade", "Late payment"], chunkFrom: 27, chunkTo: 32 },
      { page: 14, headingPath: ["Volume bands"], chunkFrom: 33, chunkTo: 41 },
    ],
    citations: [
      {
        id: "CIT-9410",
        headingPath: ["Price list", "Cotton — dyed"],
        chunkIndex: 13,
        page: 5,
        passage:
          "Dyed cotton, 40s combed, reactive dye: ₹231 per metre for lots of 5,000 metres and above, ₹244 below. The July revision reflects the dyestuff surcharge and is held to 30 September.",
        question: "What is 40s dyed at today?",
        by: { id: "AGT-013", name: "Devika", role: "Quoting" },
        when: "27 July, 10:18",
      },
    ],
    indexingNote: null,
  },
  {
    id: "DOC-0967",
    filename: "Terms of trade — Ashoka Retail Pvt Ltd (countersigned).pdf",
    collection: "drives",
    format: "PDF",
    pages: 9,
    origin: {
      kind: "connector",
      id: "CONN-GDRIVE",
      name: "Google Drive",
      how: "synced from Contracts / Customers / Ashoka",
    },
    uploadedOn: "4 February 2026",
    effectiveFrom: "1 February 2026",
    effectiveTo: "30 September 2026",
    staleness: "expiring",
    supersededBy: null,
    expiresOn: "30 September 2026",
    influence: 0.54,
    influenceBasis: "17 distinct questions, nearly all of them about one customer",
    counters: { retrievals: 61, chunk_hits: 24, distinct_queries: 17, window: "since 1 July 2026" },
    citedBy: [
      { id: "AGT-046", name: "Meera", role: "Collections", count: 12 },
      { id: "AGT-041", name: "Anjali", role: "Dunning", count: 5 },
    ],
    readBy: ["Collections"],
    sections: [
      { page: 1, headingPath: ["Parties"], chunkFrom: 0, chunkTo: 1 },
      { page: 2, headingPath: ["Commercial terms", "Credit period"], chunkFrom: 2, chunkTo: 6 },
      { page: 3, headingPath: ["Commercial terms", "Rebates"], chunkFrom: 7, chunkTo: 12 },
      { page: 5, headingPath: ["Dispute resolution"], chunkFrom: 13, chunkTo: 18 },
      { page: 8, headingPath: ["Schedule A", "Agreed rate card"], chunkFrom: 19, chunkTo: 22 },
    ],
    citations: [
      {
        id: "CIT-9188",
        headingPath: ["Commercial terms", "Credit period"],
        chunkIndex: 4,
        page: 2,
        passage:
          "Ashoka Retail is extended a credit period of forty-five days from invoice date, in place of the standard thirty, for so long as this agreement subsists. No interest accrues within the extended period.",
        question: "Is Ashoka Retail actually overdue at 38 days?",
        by: { id: "AGT-046", name: "Meera", role: "Collections" },
        when: "24 July, 08:51",
      },
      {
        id: "CIT-9002",
        headingPath: ["Dispute resolution"],
        chunkIndex: 14,
        page: 5,
        passage:
          "Where an invoice is disputed in writing within fifteen days of receipt, the disputed portion alone is withheld and the balance falls due on the original date. Escalation is to the parties' finance leads before any notice is issued.",
        question: "Can Anjali send a reminder on a disputed invoice?",
        by: { id: "AGT-041", name: "Anjali", role: "Dunning" },
        when: "21 July, 16:07",
      },
    ],
    indexingNote: null,
  },
  {
    id: "DOC-1512",
    filename: "Freight rates — Q3 negotiated.xlsx",
    collection: "drives",
    format: "Spreadsheet",
    // Still indexing. Everything measured is therefore absent, not zero.
    pages: null,
    origin: {
      kind: "connector",
      id: "CONN-GDRIVE",
      name: "Google Drive",
      how: "synced from Logistics / 2026",
    },
    uploadedOn: "29 July 2026",
    effectiveFrom: "1 July 2026",
    effectiveTo: null,
    staleness: "current",
    supersededBy: null,
    expiresOn: null,
    influence: null,
    influenceBasis: null,
    counters: null,
    citedBy: [],
    readBy: [],
    sections: [],
    citations: [],
    indexingNote:
      "Still being read. Until it finishes, no colleague can retrieve it, so there is no influence to show and nothing to count — not zero of anything, simply not yet measured.",
  },
  {
    id: "DOC-1487",
    filename: "Collections escalation ladder (as practised).md",
    collection: "generated",
    format: "Markdown",
    pages: 3,
    origin: {
      kind: "colleague",
      id: "AGT-046",
      name: "Meera",
      how: "written from her own 169 chases this quarter",
    },
    uploadedOn: "19 July 2026",
    effectiveFrom: null,
    effectiveTo: null,
    staleness: "current",
    supersededBy: null,
    expiresOn: null,
    influence: 0.41,
    influenceBasis: "11 distinct questions, and the only document Anjali reads before drafting",
    counters: { retrievals: 44, chunk_hits: 19, distinct_queries: 11, window: "since 1 July 2026" },
    citedBy: [
      { id: "AGT-041", name: "Anjali", role: "Dunning", count: 8 },
      { id: "AGT-046", name: "Meera", role: "Collections", count: 3 },
    ],
    readBy: ["Collections"],
    sections: [
      { page: 1, headingPath: ["What actually moves an invoice"], chunkFrom: 0, chunkTo: 4 },
      { page: 2, headingPath: ["The ladder", "First reminder"], chunkFrom: 5, chunkTo: 8 },
      { page: 2, headingPath: ["The ladder", "Second reminder"], chunkFrom: 9, chunkTo: 12 },
      { page: 3, headingPath: ["The ladder", "When to stop and ask"], chunkFrom: 13, chunkTo: 17 },
    ],
    citations: [
      {
        id: "CIT-9377",
        headingPath: ["The ladder", "When to stop and ask"],
        chunkIndex: 15,
        page: 3,
        passage:
          "Past sixty days a reminder is not what moves an invoice — a person is. Of nineteen accounts I chased past sixty days this quarter, none paid on a notice and eleven paid within a week of the owner calling.",
        question: "Should I send a fourth notice or escalate?",
        by: { id: "AGT-041", name: "Anjali", role: "Dunning" },
        when: "26 July, 09:35",
      },
    ],
    indexingNote: null,
  },
  {
    id: "DOC-1499",
    filename: "Kulkarni finance — payment run (thread, 14 turns)",
    collection: "conversations",
    format: "Extracted thread",
    pages: 1,
    origin: {
      kind: "colleague",
      id: "AGT-046",
      name: "Meera",
      how: "lifted from a call and a WhatsApp thread, with both source turns kept",
    },
    uploadedOn: "22 July 2026",
    effectiveFrom: null,
    effectiveTo: null,
    staleness: "current",
    supersededBy: null,
    expiresOn: null,
    influence: 0.12,
    influenceBasis: "2 distinct questions, both about one invoice",
    counters: { retrievals: 5, chunk_hits: 3, distinct_queries: 2, window: "since 1 July 2026" },
    citedBy: [{ id: "AGT-046", name: "Meera", role: "Collections", count: 2 }],
    readBy: ["Collections"],
    sections: [
      { page: 1, headingPath: ["Call · 22 July 09:12"], chunkFrom: 0, chunkTo: 1 },
      { page: 1, headingPath: ["Thread · 22 July 09:40"], chunkFrom: 2, chunkTo: 3 },
    ],
    citations: [
      {
        id: "CIT-9403",
        headingPath: ["Call · 22 July 09:12"],
        chunkIndex: 0,
        page: 1,
        passage:
          "Their finance lead said a payment run was already scheduled for the 29th and asked us not to chase in the middle of it. She named KT-2291 specifically.",
        question: "Why was the Kulkarni chase deferred?",
        by: { id: "AGT-046", name: "Meera", role: "Collections" },
        when: "22 July, 09:14",
      },
    ],
    indexingNote: null,
  },
];
