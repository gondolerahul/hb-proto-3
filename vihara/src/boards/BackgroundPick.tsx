import { useEffect, useState } from "react";
import { Background } from "../background/Background";
import "./boardPick.css";

/**
 * R-1 · The owner pick that decision D2 left open.
 *
 * Two backgrounds, judged the only way the choice is meaningful: with real UI
 * on top of them. The sample below is deliberately the hardest case — a gold
 * certified block and a raised beacon *together*, because the whole question is
 * whether the legacy copper glow lets a gold beacon still win the eye
 * (art bible §2.1). Judge the beacon, not the floor.
 */

type Variant = "legacy" | "brand";
type Intensity = "full" | "quiet" | "hushed";

const VARIANT_NOTE: Record<Variant, string> = {
  legacy:
    "Exactly the file you approved — copper/steel-blue lava on #382b02, bloom 0.8/0.4/0.1, byte-identical.",
  brand:
    "Same shader, same hex grid, same bloom, same mouse lift. Only four colours differ: gold replaces copper, a desaturated cool neutral replaces electric blue.",
};

const INTENSITY_NOTE: Record<Intensity, string> = {
  full: "Depth 0 and the Terrace — the atmosphere is the surface.",
  quiet: "District rooms and the Boardroom — atmosphere at the rim, calm in the middle.",
  hushed: "Trays, Halls, the Undercroft — near-flat, because a breathing floor under a table of invoices competes with the invoices.",
};

export function BackgroundPick() {
  const [variant, setVariant] = useState<Variant>("legacy");
  const [intensity, setIntensity] = useState<Intensity>("full");

  // A/B on one key, because switching fast is how you actually see a difference.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "b" || e.key === "B") {
        setVariant((v) => (v === "legacy" ? "brand" : "legacy"));
      }
      if (e.key === "i" || e.key === "I") {
        setIntensity((i) => (i === "full" ? "quiet" : i === "quiet" ? "hushed" : "full"));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      <Background variant={variant} intensity={intensity} />

      <div className="bp">
        {/* ---------------------------------------------------- the control bar */}
        <header className="bp-bar m-glass" data-strong>
          <div className="bp-bar-brand">
            <span className="m-lamp" data-lit />
            <span className="bp-wordmark">Vihara</span>
            <span className="t-eyebrow">R-1 · BACKGROUND PICK · DECISION D2</span>
          </div>

          <div className="bp-controls">
            <div className="bp-seg" role="radiogroup" aria-label="Background variant">
              <span className="t-eyebrow">SCENE</span>
              {(["legacy", "brand"] as const).map((v) => (
                <button
                  key={v}
                  role="radio"
                  aria-checked={variant === v}
                  className="m-chip"
                  data-selected={variant === v || undefined}
                  onClick={() => setVariant(v)}
                >
                  {v === "legacy" ? "Legacy (verbatim)" : "Brand re-key"}
                </button>
              ))}
            </div>

            <div className="bp-seg" role="radiogroup" aria-label="Atmosphere intensity">
              <span className="t-eyebrow">ATMOSPHERE</span>
              {(["full", "quiet", "hushed"] as const).map((i) => (
                <button
                  key={i}
                  role="radio"
                  aria-checked={intensity === i}
                  className="m-chip"
                  data-selected={intensity === i || undefined}
                  onClick={() => setIntensity(i)}
                >
                  {i}
                </button>
              ))}
            </div>
          </div>
        </header>

        {/* ------------------------------------------------------- the sample UI */}
        <main className="bp-stage">
          <section className="bp-still">
            <p className="t-narrative bp-still-line">All is well.</p>
            <p className="t-narrative bp-still-line">
              <span className="num">₹2.4L</span> collected this week.
            </p>
            <p className="t-narrative bp-still-line bp-still-gold">
              Two colleagues are waiting for you.
            </p>
            <div className="bp-still-pulse">
              <span className="m-lamp" data-breathing />
              <span className="t-mono">the pulse</span>
            </div>
          </section>

          <div className="bp-cards">
            {/* A working plate — the material system's ordinary case. */}
            <article className="bp-card m-plate m-ticks vh-lift">
              <span className="t-eyebrow">P08 · MONEY QUARTER</span>
              <h3 className="t-display bp-card-title">Collections</h3>
              <div className="bp-kpi">
                <span className="t-figure">38d</span>
                <span className="bp-kpi-delta">
                  <span className="m-lamp" data-negative />
                  <span className="t-mono">9 days over target</span>
                </span>
              </div>
              <hr className="m-rule-fade" />
              <ul className="bp-rows">
                {(
                  [
                    { id: "AGT-046", name: "Meera", doing: "chasing KT-2291" },
                    { id: "AGT-038", name: "Ravi", doing: "reconciling 14 invoices" },
                    { id: "AGT-041", name: "Anjali", doing: "drafting reminder" },
                  ] as const
                ).map(({ id, name, doing }, i) => (
                  <li key={id} className="bp-row" style={{ ["--i" as string]: i }}>
                    <span className="m-plinth bp-row-plinth" aria-hidden="true">
                      <span className="t-mono">{name.slice(0, 1)}</span>
                    </span>
                    <span className="bp-row-name t-display">{name}</span>
                    <span className="t-mono bp-row-id">{id}</span>
                    <span className="t-mono bp-row-doing">{doing}</span>
                  </li>
                ))}
              </ul>
            </article>

            {/* A certified block — the one place gold is spent as material. */}
            <article className="bp-card bp-card-certified m-glass" data-gold>
              <div className="bp-cert-head">
                <span className="t-eyebrow" data-certified>
                  CERTIFIED · PAYMENT
                </span>
                <span className="m-medallion bp-seal" aria-hidden="true">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#2a1d08" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M20 6 9 17l-5-5" />
                  </svg>
                </span>
              </div>
              <h3 className="t-display bp-card-title">Release ₹1,84,000 to Sundar Textiles</h3>
              <p className="t-narrative bp-cert-body">
                Meera matched invoice <span className="t-mono">INV-4471</span> against
                the goods receipt and the purchase order. Nothing is in dispute.
              </p>
              <div className="m-well bp-cert-well">
                <dl className="bp-cert-facts">
                  {[
                    ["Invoice", "₹1,84,000"],
                    ["Terms", "Net 30 · due today"],
                    ["Matched", "3 of 3 documents"],
                  ].map(([k, v]) => (
                    <div key={k} className="bp-cert-fact">
                      <dt className="t-eyebrow">{k}</dt>
                      <dd className="t-mono bp-cert-val">{v}</dd>
                    </div>
                  ))}
                </dl>
              </div>
              <div className="bp-cert-actions">
                <button className="m-btn" data-rank="certified">
                  Approve with passkey
                </button>
                <button className="m-btn" data-rank="quiet">
                  Hold
                </button>
              </div>
            </article>
          </div>
        </main>

        {/* ------------------------------------------------------------ the note */}
        <footer className="bp-note m-glass">
          <div>
            <span className="t-eyebrow">SCENE · {variant.toUpperCase()}</span>
            <p className="t-narrative bp-note-body">{VARIANT_NOTE[variant]}</p>
          </div>
          <div className="m-rule-v bp-note-div" />
          <div>
            <span className="t-eyebrow">ATMOSPHERE · {intensity.toUpperCase()}</span>
            <p className="t-narrative bp-note-body">{INTENSITY_NOTE[intensity]}</p>
          </div>
          <div className="m-rule-v bp-note-div" />
          <p className="t-mono bp-keys">
            <kbd>B</kbd> swaps the scene · <kbd>I</kbd> cycles atmosphere · move the
            mouse to lift tiles
          </p>
        </footer>
      </div>
    </>
  );
}
