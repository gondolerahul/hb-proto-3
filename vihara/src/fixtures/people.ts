/**
 * People fixtures — the dossier, and later the Talent Office and Gallery.
 *
 * Shaped to D6 §6's bindings (`entities/{id}`, `executions`, `kpi`,
 * `learning.outcomes`) so R-4 swaps the source and not the surface.
 *
 * Reconstructed 2026-07-30 to the exact contract `DossierSurface.tsx` consumes,
 * after the original was lost to a concurrent write. The surface is the
 * authority here — every field below has a call site, and nothing is present
 * "for completeness".
 */

export type Autonomy = "A0" | "A1" | "A2" | "A3";

/**
 * What an autonomy band *means to the owner*, in the owner's terms.
 *
 * A1/A2 are engineer-speak on a page a business owner reads, so the band is
 * always printed with its consequence. That is the same correction the STRAT
 * object-sheet review made three times.
 */
export const AUTONOMY_MEANS: Record<Autonomy, string> = {
  A0: "she proposes, you do everything",
  A1: "she drafts, you approve every act",
  A2: "she acts, and brings the consequential ones to you",
  A3: "she acts, and tells you afterwards",
};

export interface Clause {
  label: string;
  value: string;
}

export interface Competency {
  name: string;
  kind: "tool" | "connector";
  note: string;
  /** Granted by the charter but withheld by governance — shown, not hidden. */
  withheld?: boolean;
}

export interface Slo {
  label: string;
  /** The rendered figure, exactly as it should read. */
  reading: string;
  /** 0..1, the dial's sweep. */
  fill: number;
  /** 0..1, where the target tick sits. */
  target: number;
  targetLabel: string;
  meets: boolean;
  /** What the number is computed from — a percentage with no denominator is a
      claim, not a measurement. */
  basis: string;
}

export interface TraceStep {
  at: string;
  what: string;
}

export interface Decision {
  /** The run id — also the trace's label. */
  id: string;
  ref: string;
  when: string;
  /** Told, not logged. A dossier that shows a log teaches nothing. */
  told: string;
  /** null until DRIVER's estimator exists (D5 §4.1) — renders as nothing. */
  cost: string | null;
  steps: TraceStep[];
}

export interface Proposal {
  id: string;
  raised: string;
  asks: string;
  state: "pending" | "certified" | "declined";
  from: "her" | "you";
}

export interface Dossier {
  id: string;
  name: string;
  role: string;
  district: string;
  quarter: string;
  autonomy: Autonomy;
  standing: "associate" | "probationer" | "senior";
  handRaised: boolean;
  doing: string | null;
  /** Her charter's opening line, in her own voice. */
  ownWords: string;
  probation: { dayOf: number; days: number; until: string } | null;
  charter: Clause[];
  /** The same charter as its governance block, one flip away (operator). */
  governance: string;
  competencies: Competency[];
  slos: Slo[];
  decisions: Decision[];
  proposals: Proposal[];
}

export const DOSSIERS: Dossier[] = [
  {
    id: "AGT-046",
    name: "Meera",
    role: "Collections",
    district: "Collections",
    quarter: "Money Quarter",
    autonomy: "A2",
    standing: "associate",
    handRaised: true,
    doing: "chasing KT-2291",
    ownWords:
      "I chase overdue invoices and escalate when they age past sixty days. I use the customer’s own payment history, never adjectives.",
    probation: null,
    charter: [
      {
        label: "Goal",
        value:
          "Bring days-sales-outstanding to thirty without costing us a customer relationship.",
      },
      {
        label: "Tone",
        value:
          "Firm, specific, and never threatening. Every chase names the invoice, the amount and the agreed terms.",
      },
      {
        label: "Escalation",
        value:
          "Anything over ₹1,00,000, anything disputed, anything past ninety days, and any account that has asked me to stop.",
      },
    ],
    governance: `{
  "autonomy_band": "A2",
  "checkpoints": [
    "before_email_dispatch",
    "before_payment_release",
    "before_outbound_call"
  ],
  "authority": {
    "max_value_inr": 100000,
    "may_write": ["Invoice", "Communication"],
    "may_propose": ["Customer.payment_terms"]
  },
  "escalate_on": ["disputed", "age_days > 90", "dnc_requested"],
  "karuna_profile": "collections.firm"
}`,
    competencies: [
      { name: "tenant_record_write", kind: "tool", note: "updates invoices and communications" },
      { name: "emit_business_signal", kind: "tool", note: "hands work to other colleagues" },
      { name: "send_email", kind: "tool", note: "chases, behind your approval at A2" },
      { name: "place_call", kind: "tool", note: "voice chases, consent-checked first" },
      { name: "read_ledger", kind: "tool", note: "reads the books, never writes them" },
      {
        name: "issue_credit_note",
        kind: "tool",
        note: "would settle a dispute directly",
        withheld: true,
      },
      {
        name: "Zoho Books",
        kind: "connector",
        note: "master of Invoices — she writes back through it",
      },
      { name: "Tata Smartflo", kind: "connector", note: "the voice line she calls from" },
    ],
    slos: [
      {
        label: "On time",
        reading: "84%",
        fill: 0.84,
        target: 0.9,
        targetLabel: "target 90%",
        meets: false,
        basis: "142 of 169 chases sent inside their window",
      },
      {
        label: "Accuracy",
        reading: "96%",
        fill: 0.96,
        target: 0.95,
        targetLabel: "target 95%",
        meets: true,
        basis: "4 corrections across 103 records touched",
      },
    ],
    decisions: [
      {
        id: "4f2a",
        ref: "KT-2291",
        when: "Tuesday",
        told: "I held the Kulkarni reminder back a cycle. They called to say a payment run was already scheduled, and chasing in the middle of one reads as not listening — so I moved my next chase to after the run clears.",
        cost: "₹0.40",
        steps: [
          { at: "09:12", what: "signal call.inbound · Kulkarni finance" },
          { at: "09:12", what: "read Invoice KT-2291 · age 44d" },
          { at: "09:13", what: "read Communication log · 2 prior chases" },
          { at: "09:13", what: "decision: defer chase → next cycle" },
          { at: "09:14", what: "wrote Communication · note, no dispatch" },
        ],
      },
      {
        id: "9c11",
        ref: "3 invoices",
        when: "Tuesday",
        told: "I escalated three invoices past ninety days to you rather than sending a fourth notice. At that age a notice is not what moves it, and my charter says ninety days is yours.",
        cost: "₹0.15",
        steps: [
          { at: "14:02", what: "sweep Invoice · state=overdue · age>90" },
          { at: "14:02", what: "matched 3 records" },
          { at: "14:03", what: "escalation rule: age_days > 90" },
          { at: "14:03", what: "raised HITL-8836 · tray" },
        ],
      },
      {
        id: "b207",
        ref: "Ashoka Retail",
        when: "last week",
        told: "I stopped calling Ashoka Retail. Their finance lead asked for email only, so I recorded the preference against the account — it now binds every colleague, not just me.",
        // No estimate exists for this run's shape yet — renders as nothing.
        cost: null,
        steps: [
          { at: "11:31", what: "signal call.completed · outcome=dnc_request" },
          { at: "11:31", what: "wrote Customer.contact_preference = email" },
          { at: "11:32", what: "emitted consent.updated" },
        ],
      },
    ],
    proposals: [
      {
        id: "P-118",
        raised: "yesterday",
        asks: "Let me send the second reminder without asking you, when the amount is under ₹25,000 and nothing is disputed.",
        state: "pending",
        from: "her",
      },
      {
        id: "P-104",
        raised: "11 March",
        asks: "Add a seven-day grace note before the first chase for accounts that have never been late.",
        state: "certified",
        from: "you",
      },
    ],
  },
  {
    id: "AGT-038",
    name: "Ravi",
    role: "Reconciliation",
    district: "Collections",
    quarter: "Money Quarter",
    autonomy: "A1",
    standing: "probationer",
    handRaised: false,
    doing: "reconciling 14 invoices",
    ownWords:
      "I match payments to invoices and flag what will not reconcile. I would rather stop and ask than guess at a match.",
    probation: { dayOf: 9, days: 30, until: "29 August 2026" },
    charter: [
      { label: "Goal", value: "Nothing unreconciled for more than seven days." },
      {
        label: "Tone",
        value: "Plain and numeric. I report what matched, what did not, and by how much.",
      },
      {
        label: "Escalation",
        value: "Any variance over ₹5,000, any payment I cannot attribute, and any duplicate.",
      },
    ],
    governance: `{
  "autonomy_band": "A1",
  "probation": { "days": 30, "every_act_to_tray": true },
  "checkpoints": ["before_ledger_write"],
  "authority": { "max_value_inr": 5000, "may_write": ["Payment"] },
  "escalate_on": ["variance_inr > 5000", "unattributable", "duplicate"]
}`,
    competencies: [
      { name: "read_ledger", kind: "tool", note: "reads the books" },
      {
        name: "tenant_record_write",
        kind: "tool",
        note: "writes payments, every one to your tray",
      },
      { name: "emit_business_signal", kind: "tool", note: "hands variances to Meera" },
      { name: "Zoho Books", kind: "connector", note: "reads the bank feed" },
    ],
    slos: [
      {
        label: "Matched",
        reading: "91%",
        fill: 0.91,
        target: 0.85,
        targetLabel: "target 85%",
        meets: true,
        basis: "213 of 234 payments attributed without help",
      },
    ],
    decisions: [
      {
        id: "7d40",
        ref: "Bhagwati Mills",
        when: "this morning",
        told: "A ₹2,41,750 payment arrived that matches no single invoice. It is within ₹50 of two invoices added together, but I will not split a payment on a guess — so it is with you.",
        cost: null,
        steps: [
          { at: "07:44", what: "signal payment.received · ₹2,41,750" },
          { at: "07:44", what: "exact match · none" },
          { at: "07:45", what: "combination match · INV-4468 + INV-4451 ± ₹50" },
          { at: "07:45", what: "escalation rule: unattributable" },
          { at: "07:45", what: "raised HITL-8840 · tray" },
        ],
      },
    ],
    proposals: [],
  },
];
