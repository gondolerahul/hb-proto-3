/**
 * Bridges & Gates — the estate's edge (D6 §14).
 *
 * Bound to `connectors/{catalog,bindings,status}` (shipped), the consent
 * registry, and `social_connections`.
 *
 * Shaped to the D5 contracts so R-4 is a swap of the data source. Two honesty
 * rules are stated here rather than in the surface, because they are properties
 * of the *data* and a later author reading only the component would reinvent
 * them wrongly:
 *
 * ─── 1 · `credentialExpiresAt` is null on every row, and that is the truth ───
 *
 * The platform ships `credentials_expire_at` on every binding and **nothing has
 * ever written to it.** So the nightly expiry sweep is correctly implemented and
 * always finds nothing. The field is typed `string | null` here and left null
 * everywhere, because that is what the endpoint returns today — not because the
 * fixture is lazy.
 *
 * The consequence the surface must honour: **a blank expiry is absence of
 * information, not a clean bill of health.** We cannot distinguish "this
 * credential never expires" from "this credential dies next Tuesday", and a UI
 * that renders the blank as calm would be telling the tenant their keys have
 * been checked when nothing has ever looked at them. That is a security design
 * bug, not a styling choice.
 *
 * `credentialFailedAt` is the field that *does* get populated, and it is only
 * ever set **after** the fact — a sync returns 401 and we learn the credential
 * died some hours ago. Every expiry we have ever found, we found by breaking.
 *
 * ─── 2 · a mastering declaration can name another system, or nobody ─────────
 *
 * `MasterDeclaration.master` is the id of whichever bridge masters that object,
 * which is frequently *not* the bridge the row is listed under — that is the
 * whole point of declaring one. `null` means no declaration row exists. It is an
 * absence, and it renders as an absence: never "the estate", never a guess.
 */

/** Sync health. `under-repair` is the designed idiom for a dead credential. */
export type SyncHealth = "flowing" | "behind" | "under-repair";

export interface MasterDeclaration {
  object: string;
  /**
   * Bridge id that masters this object. May be a *different* bridge than the
   * one this row sits under. `null` = never declared; render the absence.
   */
  master: string | null;
  declaredOn: string | null;
  /** The person or colleague who signed the declaration. */
  declaredBy: string | null;
  /** Rows the two sides currently disagree on. */
  conflicts: number;
}

export interface DisputeField {
  field: string;
  /** The master's value. */
  master: string;
  /** The challenger's value. */
  other: string;
  differs: boolean;
}

/**
 * A `sync.conflict`. Both sides wrote the same record and neither yielded.
 * Master-wins is the *default* resolution, not the automatic one — the whole
 * reason this reaches a person is that a default is not a decision.
 */
export interface Dispute {
  id: string;
  object: string;
  recordId: string;
  recordLabel: string;
  detectedAt: string;
  masterSide: { system: string; sealId: string; wroteAt: string };
  otherSide: { system: string; sealId: string; wroteAt: string };
  /** Why the master is the master, in the words of the declaration. */
  masterBecause: string;
  fields: DisputeField[];
}

export interface Bridge {
  id: string;
  name: string;
  /** How it actually reaches us — a desktop agent is a different animal. */
  transport: string;
  health: SyncHealth;
  lastSyncedAt: string;
  /** Always null today. See rule 1 above. */
  credentialExpiresAt: string | null;
  /** Set only after a sync has already broken. See rule 1 above. */
  credentialFailedAt: string | null;
  /** What the binding is allowed to touch. Operator density shows all of them. */
  scopes: string[];
  objects: MasterDeclaration[];
  disputes: Dispute[];
}

export interface Gate {
  id: string;
  name: string;
  kind: "channel" | "broadcast";
  transport: string;
  consent: {
    posture: "opt-in" | "legitimate-interest" | "revoked";
    /** What the posture covers, in the registry's own words. */
    scope: string;
    recordedOn: string | null;
    note: string;
  };
  dnc: { listed: number; enforcedAt: string };
  volume: {
    /** Trailing seven days. `null` where the count is not ours to report. */
    sevenDay: number | null;
    unit: string;
    /** A hard ceiling where the vendor imposes one, else null. */
    capPerDay: number | null;
    note: string | null;
  };
}

// ============================================================================
// BRIDGES — four systems of record, one of them broken.
// ============================================================================

export const BRIDGES: Bridge[] = [
  {
    id: "zoho-books",
    name: "Zoho Books",
    transport: "OAuth · zoho.in datacentre",
    health: "flowing",
    lastSyncedAt: "6 minutes ago",
    credentialExpiresAt: null,
    credentialFailedAt: null,
    scopes: ["invoices.read", "invoices.write", "contacts.read", "contacts.write", "settlements.read"],
    objects: [
      {
        object: "Invoices",
        master: "zoho-books",
        declaredOn: "3 July 2026",
        declaredBy: "Rahul",
        conflicts: 2,
      },
      {
        object: "Customers",
        master: "zoho-books",
        declaredOn: "3 July 2026",
        declaredBy: "Rahul",
        conflicts: 0,
      },
      // The awkward one, and the commonest: nobody ever said who wins.
      { object: "Contacts", master: null, declaredOn: null, declaredBy: null, conflicts: 0 },
    ],
    disputes: [
      {
        id: "CONF-2214",
        object: "Invoices",
        recordId: "INV-4468",
        recordLabel: "Bhagwati Mills & Weaving Co.",
        detectedAt: "1 hour ago",
        masterSide: { system: "Zoho Books", sealId: "zoho-books", wroteAt: "today 13:41" },
        otherSide: { system: "Shopify", sealId: "shopify", wroteAt: "today 13:44" },
        masterBecause: "you declared Zoho Books master of Invoices on 3 July 2026",
        fields: [
          { field: "Amount", master: "₹2,41,750", other: "₹2,38,400", differs: true },
          { field: "Terms", master: "Net 30", other: "Net 45", differs: true },
          { field: "State", master: "Disputed", other: "Open", differs: true },
          { field: "Party", master: "Bhagwati Mills & Weaving Co.", other: "Bhagwati Mills & Weaving Co.", differs: false },
          { field: "Issued", master: "8 July 2026", other: "8 July 2026", differs: false },
        ],
      },
      {
        id: "CONF-2209",
        object: "Invoices",
        recordId: "INV-4455",
        recordLabel: "Coromandel Garments",
        detectedAt: "yesterday 19:20",
        masterSide: { system: "Zoho Books", sealId: "zoho-books", wroteAt: "yesterday 19:02" },
        otherSide: { system: "Razorpay", sealId: "razorpay", wroteAt: "yesterday 19:18" },
        masterBecause: "you declared Zoho Books master of Invoices on 3 July 2026",
        fields: [
          { field: "Paid", master: "₹0", other: "₹1,50,000", differs: true },
          { field: "State", master: "Overdue", other: "Part-paid", differs: true },
          { field: "Amount", master: "₹3,08,900", other: "₹3,08,900", differs: false },
        ],
      },
    ],
  },
  {
    // A bridge under repair. Found by a sync breaking, not by the sweep.
    id: "tally-prime",
    name: "Tally Prime",
    transport: "desktop agent on ACCOUNTS-PC · office LAN",
    health: "under-repair",
    lastSyncedAt: "today 14:02",
    credentialExpiresAt: null,
    credentialFailedAt: "today 14:02",
    scopes: ["ledger.read", "ledger.write", "vouchers.read"],
    objects: [
      {
        object: "Ledger entries",
        master: "tally-prime",
        declaredOn: "19 April 2026",
        declaredBy: "Rahul",
        conflicts: 0,
      },
      { object: "Vouchers", master: null, declaredOn: null, declaredBy: null, conflicts: 0 },
    ],
    disputes: [],
  },
  {
    id: "shopify",
    name: "Shopify",
    transport: "OAuth · northwind-textiles.myshopify.com",
    health: "flowing",
    lastSyncedAt: "2 minutes ago",
    credentialExpiresAt: null,
    credentialFailedAt: null,
    scopes: ["read_orders", "write_orders", "read_customers"],
    objects: [
      {
        object: "Orders",
        master: "shopify",
        declaredOn: "3 July 2026",
        declaredBy: "Rahul",
        conflicts: 0,
      },
      // Mastered elsewhere — the declaration is doing its job.
      {
        object: "Customers",
        master: "zoho-books",
        declaredOn: "3 July 2026",
        declaredBy: "Rahul",
        conflicts: 0,
      },
    ],
    disputes: [],
  },
  {
    id: "razorpay",
    name: "Razorpay",
    transport: "API key · webhooks to /signals/inbound",
    health: "behind",
    lastSyncedAt: "3 hours ago",
    credentialExpiresAt: null,
    credentialFailedAt: null,
    scopes: ["payments.read", "settlements.read", "refunds.read"],
    objects: [
      {
        object: "Settlements",
        master: "razorpay",
        declaredOn: "21 May 2026",
        declaredBy: "Rahul",
        conflicts: 1,
      },
    ],
    disputes: [],
  },
];

/**
 * `connectors/catalog` minus `connectors/bindings`. Connecting one is
 * `certified.connector-binding@1`, so it asks for a passkey.
 */
export const AVAILABLE: { id: string; name: string; what: string }[] = [
  { id: "unicommerce", name: "Unicommerce", what: "warehouse and dispatch" },
  { id: "gst-portal", name: "GST portal", what: "returns and 2B reconciliation" },
  { id: "icici-corp", name: "ICICI corporate banking", what: "statements, read only" },
];

// ============================================================================
// GATES — how the estate reaches people.
// ============================================================================

export const GATES: Gate[] = [
  {
    id: "whatsapp",
    name: "WhatsApp Business",
    kind: "channel",
    transport: "Cloud API · +91 98xxx xx210",
    consent: {
      posture: "opt-in",
      scope: "transactional and promotional",
      recordedOn: "at first reply, per contact",
      note: "Opt-in is per contact and stored against the contact, not against this gate. A contact who never replied is never messaged.",
    },
    dnc: { listed: 1284, enforcedAt: "before every send, and again at dispatch" },
    volume: { sevenDay: 412, unit: "messages", capPerDay: 1000, note: "Meta's tier-2 template ceiling." },
  },
  {
    id: "email-ses",
    name: "Email",
    kind: "channel",
    transport: "Amazon SES · billing@northwind.co",
    consent: {
      posture: "legitimate-interest",
      scope: "transactional only — invoices, reminders, statements",
      recordedOn: null,
      note: "No opt-in is recorded because none is claimed. Anything promotional on this gate would need one, and the gate refuses promotional intents outright.",
    },
    dnc: { listed: 46, enforcedAt: "before every send" },
    volume: { sevenDay: 3918, unit: "emails", capPerDay: null, note: null },
  },
  {
    id: "sms-dlt",
    name: "SMS",
    kind: "channel",
    transport: "Airtel IQ · DLT header NRTHWD",
    consent: {
      posture: "opt-in",
      scope: "transactional templates registered on DLT",
      recordedOn: "9 February 2026",
      note: "Only the six registered templates can leave this gate. An unregistered body is refused by the carrier, not by us.",
    },
    dnc: { listed: 1284, enforcedAt: "TRAI DND scrub, then our own list" },
    volume: { sevenDay: 289, unit: "messages", capPerDay: 500, note: "Carrier throughput on the registered header." },
  },
  {
    id: "voice-smartflo",
    name: "Voice",
    kind: "channel",
    transport: "Tata Smartflo · outbound from +91 80xxx xx044",
    consent: {
      posture: "opt-in",
      scope: "collections calls to parties with an open invoice",
      recordedOn: "at contract, per party",
      note: "Every call is announced as automated in its first sentence, and the recording notice is read before anything is asked.",
    },
    dnc: { listed: 1284, enforcedAt: "before dialling" },
    volume: { sevenDay: 96, unit: "calls", capPerDay: null, note: "Calling hours are 09:30–18:30 IST and are not a cap." },
  },
  {
    // The revoked posture. A correct, restricting posture — not a fault.
    id: "linkedin",
    name: "LinkedIn",
    kind: "broadcast",
    transport: "social_connections · page Northwind Textiles",
    consent: {
      posture: "revoked",
      scope: "promotions — revoked 9 July 2026",
      recordedOn: "9 July 2026",
      note: "Company updates still post. Nothing promotional goes out on this gate until you restore it, and no colleague can override that.",
    },
    dnc: { listed: 0, enforcedAt: "not applicable — this gate broadcasts, it does not contact" },
    volume: {
      sevenDay: null,
      unit: "posts",
      capPerDay: null,
      note: "Posts are composed in LinkedIn's own tool, so the count is theirs and not ours to report.",
    },
  },
];

/**
 * The gap, in prose, because it is the one thing on this surface a tenant could
 * otherwise read backwards. Lives in the fixture so the wording travels with
 * the data it is about.
 */
export const EXPIRY_GAP = {
  eyebrow: "CREDENTIAL EXPIRY · WHAT WE DO NOT KNOW",
  body:
    "Every binding below has a field for when its credential expires, and nothing has ever written one. The nightly sweep is real, it runs, and it correctly finds nothing — because there is nothing there to find.",
  consequence:
    "So a bridge with no expiry date has not been checked and found healthy. We cannot tell you whether its key never expires or dies next Tuesday. Both look identical from here, and we will not draw one as the other.",
  observed:
    "Every expiry we have ever found, we found by a sync breaking hours after the fact. That is how Tally Prime was found at 14:02 today.",
};
