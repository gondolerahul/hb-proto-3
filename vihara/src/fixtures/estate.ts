/**
 * Prototype fixtures.
 *
 * Shaped to the D5 contracts so R-4 is a swap of the data source and not a
 * rewrite of the surfaces. Every field here exists on a real endpoint; nothing
 * is invented for the sake of the picture, because a prototype that renders a
 * number nothing projects is a prototype that will be redrawn at build time
 * (Phase A exit criterion 3, which the redesign keeps).
 *
 * The content is deliberately *realistic and awkward* — long party names,
 * overdue counts, a disputed invoice, a colleague on probation. A design that
 * only survives tidy content has not been tested.
 */

export interface Colleague {
  id: string;
  name: string;
  role: string;
  autonomy: "A0" | "A1" | "A2" | "A3";
  standing: "associate" | "probationer" | "senior";
  doing: string | null;
  handRaised: boolean;
}

export interface TrayCard {
  id: string;
  kind: "certified" | "ordinary";
  category: string;
  title: string;
  raisedBy: string;
  raisedById: string;
  waitedMinutes: number;
  because: string;
  facts: { label: string; value: string }[];
  paths: { label: string; cost: string | null; rank: "certified" | "default" | "quiet" }[];
}

export interface DistrictSummary {
  code: string;
  process: string;
  quarter: string;
  name: string;
  kpi: { figure: string; label: string; drift: "ahead" | "behind" | "flat" };
  colleagues: Colleague[];
  handsRaised: number;
  signalsPerHour: number;
}

export const COMPANY = { name: "Northwind Textiles", localHour: 21 };

/** The still-surface lines. R7 templates — the figure is a binding. */
export const STILL = {
  headline: "All is well.",
  figure: { template: "₹{collected} collected this week.", collected: "2.4L" },
  handsRaised: 2,
};

export const COLLEAGUES: Colleague[] = [
  { id: "AGT-046", name: "Meera", role: "Collections", autonomy: "A2", standing: "associate", doing: "chasing KT-2291", handRaised: true },
  { id: "AGT-038", name: "Ravi", role: "Reconciliation", autonomy: "A1", standing: "probationer", doing: "reconciling 14 invoices", handRaised: false },
  { id: "AGT-041", name: "Anjali", role: "Dunning", autonomy: "A1", standing: "probationer", doing: "drafting reminder", handRaised: false },
  { id: "AGT-013", name: "Devika", role: "Quoting", autonomy: "A2", standing: "senior", doing: null, handRaised: false },
  { id: "AGT-092", name: "Farhan", role: "Bookkeeping", autonomy: "A1", standing: "associate", doing: "posting 31 entries", handRaised: false },
];

export const DISTRICTS: DistrictSummary[] = [
  {
    code: "P08",
    process: "Order to Cash",
    quarter: "Money Quarter",
    name: "Collections",
    kpi: { figure: "38d", label: "days sales outstanding · target 30", drift: "behind" },
    colleagues: COLLEAGUES.slice(0, 3),
    handsRaised: 1,
    signalsPerHour: 42,
  },
  {
    code: "P03",
    process: "Lead to Quote",
    quarter: "Growth Quarter",
    name: "Acquisition",
    kpi: { figure: "61%", label: "quote win rate · target 55", drift: "ahead" },
    colleagues: [COLLEAGUES[3]!],
    handsRaised: 0,
    signalsPerHour: 18,
  },
  {
    code: "P14",
    process: "Record to Report",
    quarter: "Trust Quarter",
    name: "Books & Compliance",
    kpi: { figure: "0", label: "unreconciled over 7 days", drift: "flat" },
    colleagues: [COLLEAGUES[4]!],
    handsRaised: 1,
    signalsPerHour: 9,
  },
];

export const TRAY: TrayCard[] = [
  {
    id: "HITL-8841",
    kind: "certified",
    category: "Payment release",
    title: "Release ₹1,84,000 to Sundar Textiles Pvt Ltd",
    raisedBy: "Meera",
    raisedById: "AGT-046",
    waitedMinutes: 34,
    because:
      "Invoice INV-4471 matched the goods receipt and the purchase order. Nothing is in dispute. Terms are net 30 and today is day 30.",
    facts: [
      { label: "Amount", value: "₹1,84,000" },
      { label: "Invoice", value: "INV-4471" },
      { label: "Matched", value: "3 of 3 documents" },
      { label: "Wallet after", value: "₹6,12,400" },
    ],
    paths: [
      { label: "Release the payment", cost: "₹1,84,000", rank: "certified" },
      { label: "Hold for my review", cost: null, rank: "quiet" },
    ],
  },
  {
    id: "HITL-8839",
    kind: "ordinary",
    category: "Email dispatch",
    title: "Send the third reminder to Kanwal Trading",
    raisedBy: "Anjali",
    raisedById: "AGT-041",
    waitedMinutes: 112,
    because:
      "Two reminders have gone unanswered on KT-2291, ₹96,500, now 47 days overdue. The next step in the dunning ladder is a firmer notice, and the tone changes at this stage.",
    facts: [
      { label: "Outstanding", value: "₹96,500" },
      { label: "Overdue", value: "47 days" },
      { label: "Reminders sent", value: "2" },
      { label: "Last contact", value: "11 days ago" },
    ],
    paths: [
      { label: "Send it", cost: null, rank: "default" },
      { label: "Soften the tone first", cost: null, rank: "quiet" },
      { label: "Call instead", cost: "₹18", rank: "quiet" },
    ],
  },
];

export interface RecordRow {
  id: string;
  party: string;
  amount: string;
  age: number;
  state: "open" | "overdue" | "disputed" | "paid";
  owner: string;
  updated: string;
}

/** Registry Hall content — the surface RD-7 says was built as a fallback. */
export const INVOICES: RecordRow[] = [
  { id: "INV-4471", party: "Sundar Textiles Pvt Ltd", amount: "₹1,84,000", age: 30, state: "open", owner: "AGT-046", updated: "12 min ago" },
  { id: "KT-2291", party: "Kanwal Trading", amount: "₹96,500", age: 47, state: "overdue", owner: "AGT-041", updated: "2 h ago" },
  { id: "INV-4468", party: "Bhagwati Mills & Weaving Co.", amount: "₹2,41,750", age: 22, state: "disputed", owner: "AGT-046", updated: "1 h ago" },
  { id: "INV-4465", party: "Ashoka Retail", amount: "₹58,200", age: 61, state: "overdue", owner: "AGT-041", updated: "4 h ago" },
  { id: "INV-4462", party: "Meridian Apparel", amount: "₹1,12,000", age: 14, state: "open", owner: "AGT-046", updated: "yesterday" },
  { id: "INV-4459", party: "Sundar Textiles Pvt Ltd", amount: "₹74,300", age: 8, state: "paid", owner: "AGT-092", updated: "yesterday" },
  { id: "INV-4455", party: "Coromandel Garments", amount: "₹3,08,900", age: 39, state: "overdue", owner: "AGT-041", updated: "2 days ago" },
  { id: "INV-4451", party: "Nilgiri Fabrics", amount: "₹41,600", age: 5, state: "open", owner: "AGT-046", updated: "2 days ago" },
];
