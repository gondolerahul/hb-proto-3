import { useMemo, useState } from "react";
import { Icon } from "../components/Icon";
import { INVOICES, type RecordRow } from "../fixtures/estate";
import "./hall.css";

/**
 * Registry Hall · depth 2 · S (D6 §7).
 *
 * The dense-data case, and the clearest example of finding **RD-7**: full CRUD
 * over the record service was built as the "sheet equivalent" of a world
 * surface, and inherited a fallback's design budget. Under decision D1 it is a
 * first-class room.
 *
 * Three choices that make a dense table feel designed rather than dumped:
 *
 *  - **The table is set into a well**, not drawn on a plate. Carved-out reads as
 *    data; drawn-on-top reads as a screenshot of a spreadsheet.
 *  - **State is a lamp plus a word**, never colour alone (art bible §8, and
 *    WCAG 1.4.1). The lamp is the fast read; the word is the correct one.
 *  - **Row rules are interior box-shadows at 5% alpha**, so the grid is present
 *    when you look for it and gone when you are reading one row. A visible
 *    1px border on every cell is what makes enterprise tables exhausting.
 *
 * The header row is sticky, the numeric columns are tabular and right-ranged,
 * and the party column is the only one allowed to be wide — it holds the one
 * value with real-world length variance.
 */

type SortKey = "age" | "amount" | "party";

const STATE_LABEL: Record<RecordRow["state"], string> = {
  open: "Open",
  overdue: "Overdue",
  disputed: "Disputed",
  paid: "Paid",
};

export function HallSurface({ onEcho }: { onEcho: (msg: string) => void }) {
  const [sort, setSort] = useState<SortKey>("age");
  const [filter, setFilter] = useState<RecordRow["state"] | "all">("all");
  const [selected, setSelected] = useState<string | null>(null);

  const rows = useMemo(() => {
    const parseAmount = (s: string) => Number(s.replace(/[₹,]/g, ""));
    return INVOICES.filter((r) => filter === "all" || r.state === filter).sort((a, b) => {
      if (sort === "age") return b.age - a.age;
      if (sort === "amount") return parseAmount(b.amount) - parseAmount(a.amount);
      return a.party.localeCompare(b.party);
    });
  }, [sort, filter]);

  const total = rows.reduce((n, r) => n + Number(r.amount.replace(/[₹,]/g, "")), 0);

  return (
    <section className="hl">
      {/* ------------------------------------------------------------- header */}
      <header className="hl-head">
        <div className="hl-head-title">
          <span className="t-eyebrow">REGISTRY HALL · INVOICE</span>
          <h1 className="hl-title t-display">Invoices</h1>
        </div>

        <dl className="hl-summary">
          <div>
            <dt className="t-eyebrow">SHOWING</dt>
            <dd className="hl-summary-val t-mono">
              {rows.length} of {INVOICES.length}
            </dd>
          </div>
          <div className="m-rule-v hl-summary-div" />
          <div>
            <dt className="t-eyebrow">VALUE</dt>
            <dd className="hl-summary-val t-mono">₹{total.toLocaleString("en-IN")}</dd>
          </div>
        </dl>
      </header>

      {/* -------------------------------------------------------- the controls */}
      <div className="hl-controls">
        <div className="hl-control-group" role="group" aria-label="Filter by state">
          <Icon name="filter" size={13} className="hl-control-icon" />
          {(["all", "overdue", "disputed", "open", "paid"] as const).map((s) => (
            <button
              key={s}
              className="m-chip"
              data-selected={filter === s || undefined}
              onClick={() => setFilter(s)}
            >
              {s === "all" ? "everything" : s}
            </button>
          ))}
        </div>

        <div className="hl-control-group" role="group" aria-label="Sort">
          <span className="t-eyebrow">SORT</span>
          {(["age", "amount", "party"] as const).map((s) => (
            <button
              key={s}
              className="m-chip"
              data-selected={sort === s || undefined}
              onClick={() => setSort(s)}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* ----------------------------------------------------------- the table */}
      <div className="m-well hl-table-well">
        <table className="hl-table">
          <caption className="vh-sr-only">
            Invoices, sorted by {sort}, filtered to {filter}
          </caption>
          <thead>
            <tr>
              <th scope="col" className="hl-th-id">
                <span className="t-eyebrow">REFERENCE</span>
              </th>
              <th scope="col">
                <span className="t-eyebrow">PARTY</span>
              </th>
              <th scope="col" className="hl-num">
                <span className="t-eyebrow">AMOUNT</span>
              </th>
              <th scope="col" className="hl-num">
                <span className="t-eyebrow">AGE</span>
              </th>
              <th scope="col">
                <span className="t-eyebrow">STATE</span>
              </th>
              <th scope="col">
                <span className="t-eyebrow">OWNER</span>
              </th>
              <th scope="col" className="hl-th-updated">
                <span className="t-eyebrow">UPDATED</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.id}
                data-selected={selected === r.id || undefined}
                data-state={r.state}
                onClick={() => setSelected(selected === r.id ? null : r.id)}
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setSelected(selected === r.id ? null : r.id);
                  }
                }}
              >
                <td className="hl-td-id">
                  <span className="t-mono">{r.id}</span>
                </td>
                <td className="hl-td-party">{r.party}</td>
                <td className="hl-num hl-td-amount">
                  <span className="t-mono">{r.amount}</span>
                </td>
                <td className="hl-num">
                  <span className="t-mono hl-age" data-hot={r.age > 40 || undefined}>
                    {r.age}d
                  </span>
                </td>
                <td>
                  {/* Lamp + word. Never colour alone. */}
                  <span className="hl-state">
                    <span
                      className="m-lamp"
                      data-negative={r.state === "overdue" || undefined}
                      data-lit={r.state === "disputed" || undefined}
                      data-positive={r.state === "paid" || undefined}
                    />
                    {STATE_LABEL[r.state]}
                  </span>
                </td>
                <td>
                  <span className="t-mono hl-owner">{r.owner}</span>
                </td>
                <td className="hl-td-updated">
                  <span className="t-mono">{r.updated}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* --------------------------------------------------- the selected rail */}
      {selected && (
        <footer className="hl-selected m-glass vh-enter">
          <span className="t-eyebrow">SELECTED</span>
          <span className="hl-selected-id t-mono">{selected}</span>
          <div className="hl-selected-acts">
            <button
              className="m-btn"
              data-rank="quiet"
              onClick={() => onEcho(`opened the dossier for ${selected}`)}
            >
              <Icon name="record" size={13} />
              Open
            </button>
            <button
              className="m-btn"
              data-rank="quiet"
              onClick={() => onEcho(`asked Meera to chase ${selected}`)}
            >
              <Icon name="colleague" size={13} />
              Ask Meera to chase
            </button>
            <button className="m-btn" onClick={() => onEcho(`marked ${selected} disputed`)}>
              Mark disputed
            </button>
          </div>
          <button
            className="hl-selected-close"
            onClick={() => setSelected(null)}
            aria-label="Clear the selection"
          >
            <Icon name="close" size={14} />
          </button>
        </footer>
      )}
    </section>
  );
}
