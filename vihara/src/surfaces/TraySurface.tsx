import { useState } from "react";
import { Icon } from "../components/Icon";
import { TRAY, type TrayCard } from "../fixtures/estate";
import "./tray.css";

/**
 * The Tray · any depth · C · **certified** (D6 §4).
 *
 * D8 row 24 calls this the single most consequential replacement in the product
 * — it retires `HITLPanel`. Under redesign decision D1 it stops being an "L9
 * sheet equivalent" and becomes a first-class room with its own grammar.
 *
 * The five-field order from spec §6.1 is preserved exactly, because it is the
 * order a person needs to decide and not a layout preference:
 *
 *   1  who raised it, and how long it has waited
 *   2  what is being asked
 *   3  why — in the colleague's own words
 *   4  the facts it rests on
 *   5  the paths, with cost where cost is known
 *
 * `paths[].cost` is `null` on the endpoint until DRIVER's estimator exists
 * (D5 §4.1). A null cost renders as **no cost line at all** — never as "₹0",
 * never as "—". Inventing a zero on a payment card is the worst available bug,
 * so the absence is a rendering rule and `tests/tray_cost.test.tsx` holds it.
 */
export function TraySurface({ onEcho }: { onEcho: (msg: string) => void }) {
  const [openId, setOpenId] = useState<string>(TRAY[0]!.id);
  const [settled, setSettled] = useState<Record<string, string>>({});

  const pending = TRAY.filter((c) => !settled[c.id]);

  return (
    <section className="tr">
      <header className="tr-head">
        <div>
          <span className="t-eyebrow">THE TRAY</span>
          <h1 className="tr-title t-display">
            {pending.length === 0
              ? "Nothing needs you."
              : `${pending.length} ${pending.length === 1 ? "thing needs" : "things need"} you`}
          </h1>
        </div>
        <div className="tr-head-meta">
          <span className="m-chip">
            <Icon name="clock" size={12} />
            oldest waited {Math.max(...TRAY.map((c) => c.waitedMinutes))}m
          </span>
        </div>
      </header>

      <div className="tr-list vh-stagger">
        {TRAY.map((card, i) => (
          <TrayCardView
            key={card.id}
            card={card}
            index={i}
            open={openId === card.id && !settled[card.id]}
            settledAs={settled[card.id]}
            onOpen={() => setOpenId(card.id)}
            onSettle={(pathLabel) => {
              setSettled((s) => ({ ...s, [card.id]: pathLabel }));
              onEcho(`${pathLabel} · ${card.id}`);
              const next = TRAY.find((c) => c.id !== card.id && !settled[c.id]);
              if (next) setOpenId(next.id);
            }}
          />
        ))}
      </div>
    </section>
  );
}

function TrayCardView({
  card,
  index,
  open,
  settledAs,
  onOpen,
  onSettle,
}: {
  card: TrayCard;
  index: number;
  open: boolean;
  settledAs: string | undefined;
  onOpen: () => void;
  onSettle: (pathLabel: string) => void;
}) {
  const certified = card.kind === "certified";

  if (settledAs) {
    return (
      <article className="tr-card tr-card-settled m-plate" style={{ ["--i" as string]: index }}>
        <span className="m-lamp" data-positive />
        <span className="tr-settled-text t-muted">{card.title}</span>
        <span className="t-eyebrow">{settledAs.toUpperCase()}</span>
      </article>
    );
  }

  return (
    <article
      className={certified ? "tr-card m-glass" : "tr-card m-plate"}
      data-gold={certified || undefined}
      data-open={open || undefined}
      style={{ ["--i" as string]: index }}
    >
      {/* ---------------------------------------- 1 · who, and how long waited */}
      <button className="tr-card-head" onClick={onOpen} aria-expanded={open}>
        <span className="tr-raiser">
          <span className="m-plinth tr-raiser-seal" aria-hidden="true">
            <span className="t-mono">{card.raisedBy.slice(0, 1)}</span>
          </span>
          <span className="tr-raiser-text">
            <span className="tr-raiser-name t-display">{card.raisedBy}</span>
            <span className="t-mono tr-raiser-id">{card.raisedById}</span>
          </span>
        </span>

        <span className="tr-head-right">
          <span className="t-eyebrow" data-certified={certified || undefined}>
            {certified && (
              <span className="m-medallion tr-seal" aria-hidden="true">
                <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="#2a1d08" strokeWidth="3.6" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 6 9 17l-5-5" />
                </svg>
              </span>
            )}
            {certified ? "CERTIFIED · " : ""}
            {card.category.toUpperCase()}
          </span>
          <span className="tr-waited t-mono">waited {card.waitedMinutes}m</span>
          <Icon name="chevron" size={14} className="tr-caret" />
        </span>
      </button>

      {/* ------------------------------------------------ 2 · what is asked */}
      <h2 className="tr-ask t-display">{card.title}</h2>

      {open && (
        <div className="tr-body vh-enter-fade">
          {/* --------------------------------- 3 · why, in her own words */}
          <blockquote className="tr-because">
            <p className="t-narrative">{card.because}</p>
            <cite className="t-mono">— {card.raisedBy}</cite>
          </blockquote>

          {/* ----------------------------------- 4 · the facts it rests on */}
          <div className="m-well tr-facts" data-deep>
            <dl>
              {card.facts.map((f) => (
                <div className="tr-fact" key={f.label}>
                  <dt className="t-eyebrow">{f.label}</dt>
                  <dd className="tr-fact-value t-mono">{f.value}</dd>
                </div>
              ))}
            </dl>
          </div>

          {/* ------------------------------------------------ 5 · the paths */}
          <div className="tr-paths">
            {card.paths.map((p) => (
              <button
                key={p.label}
                className="m-btn tr-path"
                data-rank={p.rank === "certified" ? "certified" : p.rank === "quiet" ? "quiet" : undefined}
                onClick={() => onSettle(p.label)}
              >
                {p.rank === "certified" && <Icon name="key" size={14} />}
                <span>{p.label}</span>
                {/* A null cost renders as nothing. Never "₹0", never a dash. */}
                {p.cost !== null && <span className="tr-path-cost t-mono">{p.cost}</span>}
              </button>
            ))}
          </div>

          {certified && (
            <p className="tr-cert-note t-mono">
              <Icon name="seal" size={12} />
              This act is certified. It is rendered from a frozen component, never
              from a manifest, and it will ask for your passkey.
            </p>
          )}
        </div>
      )}
    </article>
  );
}
