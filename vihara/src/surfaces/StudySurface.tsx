import { useState } from "react";
import { Icon } from "../components/Icon";
import {
  DENSITY,
  DUNNING,
  NOTIFY,
  PASSKEYS,
  WALLET,
  YOU,
  type NotifyPref,
} from "../fixtures/study";
import "./study.css";

/**
 * The Study · depth 2 · S (D6 §15a) — the eighteenth surface, VP-03.
 *
 * **Not a place in the estate: the desk you sit at.** Reachable from the shell,
 * never from the territory — which is why it is the one depth-2 surface with no
 * district above it in the trail.
 *
 * Four rules carried from the R2 resolution, all load-bearing:
 *
 *  1. **Passkey enrolment lives here and nowhere deeper.** It is the prerequisite
 *     for every certified (T2) act, so it must not sit at operator depth. Adding
 *     one is the WebAuthn ceremony; **deleting one is plain** — the safe
 *     direction is never made harder than the unsafe one.
 *  2. **Density is stated here and learned everywhere else.** The switch writes
 *     the preference *and clears the learned value* (the store's own rule), and
 *     the learned state is shown beside it rather than hidden. A product that
 *     quietly adapts and will not say so cannot be trusted to have adapted right.
 *  3. **Dunning is explicable here.** This is the one surface that must explain
 *     why the estate has gone quiet, because everywhere else quiet reads as calm
 *     — the product's own design working against the tenant at the worst moment.
 *     The ladder is therefore **always** visible, not revealed once a rung is
 *     reached: a tenant who is current can see what would happen, and a tenant in
 *     `read-only` finds themselves on a ladder they had already been shown.
 *  4. **Notification prefs are the `notify.*` namespace.** No new store.
 *
 * The surface has no operator secrets — the same four panels at both densities.
 */
export function StudySurface({ onEcho }: { onEcho: (msg: string) => void }) {
  const [density, setDensity] = useState<"novice" | "operator" | null>(DENSITY.stated);
  const [notify, setNotify] = useState<NotifyPref[]>(NOTIFY);
  const [keys, setKeys] = useState(PASSKEYS);

  const runway = Math.floor(WALLET.balanceINR / (WALLET.weeklyBurnINR / 7));

  return (
    <section className="sy">
      <header className="sy-head">
        <span className="t-eyebrow">THE STUDY</span>
        <h1 className="sy-title t-display">Your desk</h1>
        <p className="t-narrative sy-lead">
          Everything here is about you and this account — not about the estate. It
          is the one room your colleagues never enter.
        </p>
      </header>

      <div className="sy-grid">
        {/* ================================================================ you */}
        <section className="sy-panel m-plate">
          <h2 className="t-eyebrow">YOU</h2>
          <dl className="sy-facts">
            {[
              ["Name", YOU.name],
              ["Email", YOU.email],
              ["Company", YOU.company],
              ["Role", YOU.role],
              ["With us since", YOU.since],
            ].map(([k, v]) => (
              <div className="sy-fact" key={k}>
                <dt className="t-eyebrow">{k}</dt>
                <dd className="sy-fact-val">{v}</dd>
              </div>
            ))}
          </dl>
        </section>

        {/* =========================================================== security */}
        <section className="sy-panel m-plate">
          <div className="sy-panel-head">
            <h2 className="t-eyebrow">SECURITY · PASSKEYS</h2>
            <span className="t-mono sy-count">{keys.length} on this account</span>
          </div>

          <ul className="sy-keys">
            {keys.map((k) => (
              <li className="sy-key" key={k.id}>
                <span className="sy-key-icon" aria-hidden="true">
                  <Icon name="key" size={15} />
                </span>
                <span className="sy-key-text">
                  <span className="sy-key-label">
                    {k.label}
                    {k.thisDevice && <span className="m-chip sy-key-here">this device</span>}
                  </span>
                  <span className="t-mono sy-key-meta">
                    added {k.addedOn} · last used {k.lastUsed}
                  </span>
                </span>
                {/* Deleting is plain — one click, no ceremony. The safe direction
                    is never harder than the unsafe one. */}
                <button
                  className="sy-key-remove"
                  aria-label={`Remove ${k.label}`}
                  disabled={keys.length === 1}
                  title={keys.length === 1 ? "Your only passkey cannot be removed" : undefined}
                  onClick={() => {
                    setKeys((ks) => ks.filter((x) => x.id !== k.id));
                    onEcho(`removed the passkey on ${k.label}`);
                  }}
                >
                  <Icon name="close" size={13} />
                </button>
              </li>
            ))}
          </ul>

          <button
            className="m-btn"
            data-rank="certified"
            onClick={() => onEcho("added a passkey")}
          >
            <Icon name="key" size={14} />
            Add a passkey
          </button>

          <p className="sy-note t-mono">
            A passkey is the key to every certified act — releasing money, signing,
            changing what a colleague is allowed to do. Adding one asks your device
            to prove it is you. We never see a password, because there isn’t one.
          </p>
        </section>

        {/* ============================================================ density */}
        <section className="sy-panel m-plate">
          <div className="sy-panel-head">
            <h2 className="t-eyebrow">DENSITY</h2>
            {/* The learned value, shown beside the switch — never hidden. */}
            <span className="t-mono sy-count">
              learned: {DENSITY.learned} · {DENSITY.observations} observations
            </span>
          </div>

          <div className="sy-density" role="radiogroup" aria-label="Density">
            {(["novice", "operator"] as const).map((d) => (
              <button
                key={d}
                role="radio"
                aria-checked={density === d}
                className="sy-choice"
                data-selected={density === d || undefined}
                onClick={() => {
                  setDensity(d);
                  onEcho(`set density to ${d}`);
                }}
              >
                <span className="sy-choice-name">{d}</span>
                <span className="sy-choice-note">
                  {d === "novice"
                    ? "Fewer things at once, and prose where a number would do."
                    : "Everything on one sheet, and the trace one flip away."}
                </span>
              </button>
            ))}
          </div>

          <p className="sy-note t-mono">
            {density === null ? (
              <>
                You have not chosen, so we are using what we have observed —{" "}
                <strong>{DENSITY.learned}</strong>, from {DENSITY.observations}{" "}
                sessions. Choosing here <strong>replaces</strong> that and stops us
                inferring it.
              </>
            ) : (
              <>
                You chose <strong>{density}</strong>, so the learned value is
                cleared and we will not infer it again. Clearing your choice hands
                it back to observation.
              </>
            )}
          </p>

          {density !== null && (
            <button
              className="m-btn"
              data-rank="quiet"
              onClick={() => {
                setDensity(null);
                onEcho("cleared your density choice");
              }}
            >
              <Icon name="undo" size={13} />
              Let it be learned again
            </button>
          )}
        </section>

        {/* ====================================================== notifications */}
        <section className="sy-panel m-plate">
          <h2 className="t-eyebrow">NOTIFICATIONS</h2>
          <ul className="sy-toggles">
            {notify.map((n) => (
              <li className="sy-toggle" key={n.key}>
                <button
                  className="sy-switch"
                  role="switch"
                  aria-checked={n.on}
                  aria-label={n.label}
                  onClick={() => {
                    setNotify((list) =>
                      list.map((x) => (x.key === n.key ? { ...x, on: !x.on } : x)),
                    );
                    onEcho(`turned ${n.label.toLowerCase()} ${n.on ? "off" : "on"}`);
                  }}
                >
                  <span className="sy-switch-knob" />
                </button>
                <span className="sy-toggle-text">
                  <span className="sy-toggle-label">{n.label}</span>
                  <span className="sy-toggle-note">{n.detail}</span>
                  <span className="t-mono sy-toggle-key">{n.key}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>

        {/* ==================================================== billing & wallet
            The panel that has to be kind. See §3 of the component docstring. */}
        <section className="sy-panel sy-wallet m-plate" data-state={WALLET.state}>
          <div className="sy-panel-head">
            <h2 className="t-eyebrow">BILLING &amp; WALLET</h2>
            <span className="m-chip sy-plan">{WALLET.plan}</span>
          </div>

          <div className="sy-balance">
            <span className="t-figure">₹{WALLET.balanceINR.toLocaleString("en-IN")}</span>
            <span className="sy-balance-side">
              <span className="m-lamp" data-positive={WALLET.state === "current" || undefined} />
              <span className="t-mono">
                {WALLET.state === "current" ? "subscription current" : WALLET.state}
              </span>
            </span>
          </div>

          {/* Runway, derived from actual burn — "how long do I have" is the
              question behind the balance, and a balance alone does not answer it. */}
          <p className="sy-runway t-mono">
            About <strong>{runway} days</strong> at last week’s pace of ₹
            {WALLET.weeklyBurnINR.toLocaleString("en-IN")}. Renews{" "}
            {WALLET.renewsOn}; last top-up ₹
            {WALLET.lastTopUp.amountINR.toLocaleString("en-IN")} on{" "}
            {WALLET.lastTopUp.on}.
          </p>

          <div className="sy-panel-acts">
            <button className="m-btn" onClick={() => onEcho("opened top-up")}>
              Top up
            </button>
            <button className="m-btn" data-rank="quiet" onClick={() => onEcho("opened invoices")}>
              Invoices
            </button>
          </div>

          <hr className="m-rule-fade" />

          {/* The ladder, always visible. Not revealed once a rung is reached. */}
          <div className="sy-ladder">
            <div className="sy-ladder-head">
              <span className="t-eyebrow">IF CREDIT RUNS OUT</span>
              <span className="t-mono sy-ladder-note">
                shown always, so it is never a surprise
              </span>
            </div>
            <ol className="sy-rungs">
              {DUNNING.map((r) => (
                <li className="sy-rung" key={r.state} data-here={WALLET.state === r.state || undefined}>
                  <span className="sy-rung-mark" aria-hidden="true" />
                  <span className="sy-rung-text">
                    <span className="sy-rung-label">{r.label}</span>
                    <span className="sy-rung-what">{r.what}</span>
                  </span>
                </li>
              ))}
            </ol>
            <p className="sy-note t-mono">
              Nothing is ever deleted for non-payment, and the record stays
              complete at every rung. A full export is yours to take at any time,
              including after a suspension.
            </p>
          </div>
        </section>
      </div>
    </section>
  );
}
