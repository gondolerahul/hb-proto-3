import { useMemo, useState } from "react";
import { Icon } from "../components/Icon";
import { Seal } from "../components/Seal";
import {
  AVAILABLE,
  BRIDGES,
  EXPIRY_GAP,
  GATES,
  type Bridge,
  type Dispute,
  type Gate,
} from "../fixtures/bridges";
import "./bridges.css";

/**
 * Bridges & Gates · depth 2 · S (D6 §14).
 *
 * The estate's edge: what it is connected to, who masters what, and how it is
 * allowed to reach people. Under **RD-7** this was an "L9 sheet equivalent" and
 * inherited a fallback's budget; it is a first-class room and the two states
 * that actually happen at an edge get real idioms rather than warning banners.
 *
 * Three decisions a reader could not recover from the code:
 *
 *  1. **The credential gap is placed at the top of the Bridges column, not in a
 *     footnote — and it is the only block on the surface written as narrative
 *     prose.** `credentials_expire_at` ships and nothing has ever written it, so
 *     the expiry sweep is correct and permanently empty. The dangerous reading
 *     is the calm one: a tenant seeing no expiry warnings concludes their keys
 *     have been checked. Absence of an expiry is absence of *information*, and
 *     we cannot distinguish "never expires" from "dies next Tuesday". That is a
 *     security claim, so it gets prose at reading size and a material of its own
 *     — a **dot lattice**, the instrument register for a gauge with nothing
 *     behind it, reused on every credential row so the same absence always
 *     wears the same texture. `credentialExpiresAt` is still rendered when
 *     present, so the day the platform writes one, this is already right.
 *
 *  2. **A dispute is a seam, not an alert.** Both versions sit as two columns of
 *     one table with a machined vertical rule between them, and the rule goes
 *     gold *only on the rows that actually disagree* — which is sanctioned under
 *     §2.1 because an unresolved dispute is precisely "this needs you". Rows
 *     that agree are shown rather than hidden: the tension comes from seeing
 *     that most of the record matches and the argument is narrow and stubborn.
 *     Master-wins is offered as the **default** and stated in words with its
 *     provenance, never applied silently — a default that needs no person would
 *     not have reached a person.
 *
 *  3. **Reconnecting does not fake a sync.** The certified acts fire the echo
 *     and change nothing else, because we have no result to report yet;
 *     re-declaring a master *does* update the row, because the declaration is
 *     the act itself. Consent posture likewise, because the registry entry is
 *     the whole state. Where an act's outcome is not ours to know, the surface
 *     stays quiet rather than drawing a success.
 *
 * Operator layout. The novice variant would drop the scope chips, the
 * per-object provenance column and the collapsed second dispute, keeping "what
 * is connected" and "what needs attention" (§14).
 */

const HEALTH: Record<Bridge["health"], { word: string; lamp: "positive" | "negative" | null }> = {
  flowing: { word: "flowing", lamp: "positive" },
  behind: { word: "behind", lamp: null },
  "under-repair": { word: "under repair", lamp: "negative" },
};

const CONSENT: Record<Gate["consent"]["posture"], string> = {
  "opt-in": "opt-in on record",
  "legitimate-interest": "legitimate interest",
  revoked: "revoked",
};

const BRIDGE_NAME: Record<string, string> = {};
for (const b of BRIDGES) BRIDGE_NAME[b.id] = b.name;

export function BridgesSurface({ onEcho }: { onEcho: (msg: string) => void }) {
  const allDisputes = useMemo(() => BRIDGES.flatMap((b) => b.disputes), []);
  const first = allDisputes[0];

  const [openDispute, setOpenDispute] = useState<string | null>(first ? first.id : null);
  /** dispute id → the words of how it was settled. */
  const [settled, setSettled] = useState<Record<string, string>>({});
  /** `${bridgeId}:${object}` → the name of the system now declared master. */
  const [declared, setDeclared] = useState<Record<string, string>>({});
  /** gate id → posture, once the tenant has changed it here. */
  const [posture, setPosture] = useState<Record<string, Gate["consent"]["posture"]>>({});
  const [connected, setConnected] = useState<string[]>([]);

  const waiting = allDisputes.filter((d) => !settled[d.id]).length;
  const repairing = BRIDGES.filter((b) => b.health === "under-repair");

  return (
    <section className="bg">
      {/* --------------------------------------------------------------- head */}
      <header className="bg-head">
        <span className="t-eyebrow">BRIDGES &amp; GATES</span>
        <h1 className="bg-title t-display">The estate's edge</h1>
        <p className="t-narrative bg-lead">
          Four systems of record and five ways of reaching a person. Everything on
          this surface is a promise to something outside the estate, and every one
          of those promises can break without asking you first.
        </p>
      </header>

      {/* ------------------------------------------------- the state of the edge */}
      <dl className="bg-edge m-plate m-ticks">
        <div className="bg-edge-item">
          <dt className="t-eyebrow">BRIDGES</dt>
          <dd className="bg-edge-val">
            {BRIDGES.length} connected
            {repairing.length > 0 && (
              <>
                <span className="m-lamp" data-negative />
                <span className="t-muted">
                  {repairing.length} under repair
                </span>
              </>
            )}
          </dd>
        </div>

        <div className="m-rule-v bg-edge-div" />

        <div className="bg-edge-item">
          <dt className="t-eyebrow">GATES</dt>
          <dd className="bg-edge-val">{GATES.length} open</dd>
        </div>

        <div className="m-rule-v bg-edge-div" />

        <div className="bg-edge-item">
          <dt className="t-eyebrow">DISPUTES</dt>
          <dd className="bg-edge-val">
            {waiting > 0 ? (
              <>
                <span className="m-lamp" data-lit />
                {waiting} waiting on you
              </>
            ) : (
              <>
                <span className="m-lamp" data-positive />
                all settled
              </>
            )}
          </dd>
        </div>

        <div className="m-rule-v bg-edge-div" />

        {/* The gap, stated in the summary strip. There is no figure to give here
            and none is invented — the cell is a sentence. */}
        <div className="bg-edge-item" data-wide>
          <dt className="t-eyebrow">CREDENTIAL EXPIRY</dt>
          <dd className="bg-edge-val">
            Not known for any bridge. Nothing has ever written an expiry date, so
            there is nothing here to have checked.
          </dd>
        </div>
      </dl>

      <div className="bg-cols">
        {/* ================================================== column 1 · bridges */}
        <div className="bg-col">
          <div className="bg-col-head">
            <h2 className="t-eyebrow">BRIDGES · SYSTEMS OF RECORD</h2>
            <span className="bg-col-count">
              what the estate reads from and writes back to
            </span>
          </div>

          {/* -------------------------------------------------------- the gap */}
          <section className="m-well bg-gap" aria-labelledby="bg-gap-h">
            <div className="bg-gap-head">
              <Icon name="clock" size={13} />
              <h3 className="t-eyebrow" id="bg-gap-h">
                {EXPIRY_GAP.eyebrow}
              </h3>
            </div>
            <p className="bg-gap-body">{EXPIRY_GAP.body}</p>
            <p className="bg-gap-body" data-key>
              {EXPIRY_GAP.consequence}
            </p>
            <p className="bg-note">{EXPIRY_GAP.observed}</p>
          </section>

          {BRIDGES.map((b) => (
            <BridgeCard
              key={b.id}
              bridge={b}
              declared={declared}
              settled={settled}
              openDispute={openDispute}
              onToggleDispute={(id) => setOpenDispute((cur) => (cur === id ? null : id))}
              onSettle={(id, how, echo) => {
                setSettled((s) => ({ ...s, [id]: how }));
                onEcho(echo);
              }}
              onDeclare={(object, master) => {
                setDeclared((d) => ({ ...d, [`${b.id}:${object}`]: master }));
                onEcho(`declared ${master} master of ${object}`);
              }}
              onEcho={onEcho}
            />
          ))}

          {/* ----------------------------------------------- available, not bound */}
          <section className="m-plate bg-avail" aria-labelledby="bg-avail-h">
            <h3 className="t-eyebrow" id="bg-avail-h">
              IN THE CATALOGUE · NOT CONNECTED
            </h3>
            {AVAILABLE.map((a) => (
              <div className="bg-avail-row" key={a.id}>
                <span className="m-portrait-well bg-ident-well" aria-hidden="true">
                  <Seal id={a.id} size={30} />
                </span>
                <span className="bg-avail-text">
                  <span className="bg-avail-name">{a.name}</span>
                  <span className="bg-avail-what">{a.what}</span>
                </span>
                {connected.includes(a.id) ? (
                  <span className="m-chip bg-settled-how">
                    <span className="m-lamp" data-positive />
                    binding signed
                  </span>
                ) : (
                  <button
                    className="m-btn bg-mini"
                    data-rank="certified"
                    onClick={() => {
                      setConnected((c) => [...c, a.id]);
                      onEcho(`connected ${a.name}`);
                    }}
                  >
                    <Icon name="key" size={13} />
                    Connect
                  </button>
                )}
              </div>
            ))}
            <p className="bg-cert-note">
              <Icon name="seal" size={12} />
              Connecting a system and declaring who masters an object are
              certified acts. Each is rendered from a frozen component, never from
              a manifest, and each will ask for your passkey.
            </p>
          </section>
        </div>

        {/* ==================================================== column 2 · gates */}
        <div className="bg-col">
          <div className="bg-col-head">
            <h2 className="t-eyebrow">GATES · HOW WE REACH PEOPLE</h2>
            <span className="bg-col-count">consent, do-not-contact, volume</span>
          </div>

          {GATES.map((g) => (
            <GateCard
              key={g.id}
              gate={g}
              posture={posture[g.id] ?? g.consent.posture}
              onPosture={(next) => {
                setPosture((p) => ({ ...p, [g.id]: next }));
                onEcho(
                  next === "revoked"
                    ? `revoked ${g.name} consent for promotions`
                    : `restored ${g.name} consent for promotions`,
                );
              }}
              onEcho={onEcho}
            />
          ))}

          <p className="bg-cert-note">
            <Icon name="seal" size={12} />
            Changing a consent posture is a certified act. It is written to the
            consent registry with your name on it, every colleague is bound by it
            within the second, and it will ask for your passkey.
          </p>
        </div>
      </div>
    </section>
  );
}

/* ========================================================================== */
/*  A BRIDGE                                                                  */
/* ========================================================================== */

function BridgeCard({
  bridge,
  declared,
  settled,
  openDispute,
  onToggleDispute,
  onSettle,
  onDeclare,
  onEcho,
}: {
  bridge: Bridge;
  declared: Record<string, string>;
  settled: Record<string, string>;
  openDispute: string | null;
  onToggleDispute: (id: string) => void;
  onSettle: (id: string, how: string, echo: string) => void;
  onDeclare: (object: string, master: string) => void;
  onEcho: (msg: string) => void;
}) {
  const health = HEALTH[bridge.health];
  const repair = bridge.credentialFailedAt !== null;

  return (
    <article className="m-plate bg-bridge" data-repair={repair || undefined}>
      {/* ----------------------------------------------------------- identity */}
      <div className="bg-bridge-head">
        <div className="bg-ident">
          {/* A connector has no persona, so it is sealed rather than portrayed. */}
          <span className="m-portrait-well bg-ident-well" aria-hidden="true">
            <Seal id={bridge.id} size={36} />
          </span>
          <span className="bg-ident-text">
            <h3 className="bg-ident-name t-display">{bridge.name}</h3>
            <span className="bg-ident-sub">{bridge.transport}</span>
          </span>
        </div>

        {/* Lamp plus word. The lamp is the fast read, the word is the correct
            one — neither carries it alone. */}
        <p className="bg-health" role="status">
          <span
            className="m-lamp"
            data-positive={health.lamp === "positive" || undefined}
            data-negative={health.lamp === "negative" || undefined}
          />
          <strong>{health.word}</strong>
          <span>
            ·{" "}
            {bridge.health === "under-repair"
              ? `nothing since ${bridge.lastSyncedAt}`
              : `synced ${bridge.lastSyncedAt}`}
          </span>
        </p>
      </div>

      {/* --------------------------------------------------------- credential */}
      <Credential bridge={bridge} onEcho={onEcho} />

      {/* -------------------------------------------------------------- scopes */}
      <div className="bg-scopes">
        <span className="t-eyebrow">SCOPE</span>
        {bridge.scopes.map((s) => (
          <span className="m-chip bg-scope" key={s}>
            {s}
          </span>
        ))}
      </div>

      {/* ----------------------------------------------------------- mastering */}
      <div className="m-well">
        <table className="bg-master-table">
          <caption className="vh-sr-only">
            Which system masters each object {bridge.name} carries
          </caption>
          <thead>
            <tr>
              <th scope="col">
                <span className="t-eyebrow">OBJECT</span>
              </th>
              <th scope="col">
                <span className="t-eyebrow">MASTERED BY</span>
              </th>
              <th scope="col" className="bg-obj-when-head">
                <span className="t-eyebrow">DECLARED</span>
              </th>
              <th scope="col">
                <span className="vh-sr-only">Act</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {bridge.objects.map((o) => {
              const local = declared[`${bridge.id}:${o.object}`];
              const masterName = local ?? (o.master ? BRIDGE_NAME[o.master] : undefined);
              const elsewhere = !local && o.master !== null && o.master !== bridge.id;

              return (
                <tr key={o.object}>
                  <th scope="row" className="bg-obj-name">
                    {o.object}
                  </th>
                  <td>
                    {masterName !== undefined ? (
                      <span
                        className="bg-obj-master"
                        data-elsewhere={elsewhere || undefined}
                      >
                        <span className="m-lamp" />
                        <span className={elsewhere ? "bg-obj-elsewhere" : undefined}>
                          {masterName}
                          {elsewhere ? " — mastered elsewhere" : ""}
                        </span>
                      </span>
                    ) : (
                      /* No declaration row exists. The absence is named; it is
                         not filled in with a guess or a dash. */
                      <span className="bg-obj-none">never declared</span>
                    )}
                  </td>
                  <td className="bg-obj-when-cell">
                    {local ? (
                      <span className="bg-obj-when">moments ago · by you</span>
                    ) : o.declaredOn && o.declaredBy ? (
                      <span className="bg-obj-when">
                        {o.declaredOn} · by {o.declaredBy}
                      </span>
                    ) : null}
                  </td>
                  <td className="bg-obj-act">
                    {masterName === undefined && (
                      <button
                        className="m-btn bg-mini"
                        data-rank="certified"
                        onClick={() => onDeclare(o.object, bridge.name)}
                      >
                        <Icon name="key" size={12} />
                        Declare {bridge.name} master
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* ------------------------------------------------------------ disputes */}
      {bridge.disputes.length > 0 && (
        <div className="bg-disputes">
          <h4 className="t-eyebrow">
            {bridge.disputes.length === 1
              ? "A DISPUTE AT THIS BRIDGE"
              : `${bridge.disputes.length} DISPUTES AT THIS BRIDGE`}
          </h4>

          {bridge.disputes.map((d) =>
            settled[d.id] ? (
              <p className="bg-settled" key={d.id} role="status">
                <span className="m-lamp" data-positive />
                <span className="bg-settled-text">
                  {d.recordId} · {d.recordLabel}
                </span>
                <span className="m-chip bg-settled-how">{settled[d.id]}</span>
              </p>
            ) : openDispute === d.id ? (
              <DisputeView
                key={d.id}
                dispute={d}
                onSettle={(how, echo) => onSettle(d.id, how, echo)}
                onDeclare={(object, master) => onDeclare(object, master)}
              />
            ) : (
              <button
                className="bg-dispute-shut"
                key={d.id}
                aria-expanded={false}
                onClick={() => onToggleDispute(d.id)}
              >
                <span className="m-lamp" data-lit />
                <span className="bg-dispute-shut-text">
                  <span className="bg-dispute-shut-title">
                    {d.recordId} · {d.recordLabel}
                  </span>
                  <span className="bg-dispute-meta">
                    {d.masterSide.system} and {d.otherSide.system} disagree on{" "}
                    {d.fields.filter((f) => f.differs).length} of {d.fields.length}{" "}
                    fields · found {d.detectedAt}
                  </span>
                </span>
                <Icon name="chevron" size={14} className="bg-caret" />
              </button>
            ),
          )}
        </div>
      )}
    </article>
  );
}

/* ========================================================================== */
/*  THE CREDENTIAL — where the platform gap bites                             */
/* ========================================================================== */

function Credential({ bridge, onEcho }: { bridge: Bridge; onEcho: (msg: string) => void }) {
  /* Three distinct states, and the whole point of the block is that the third is
     not the second. A failed credential was FOUND by a sync breaking; an unknown
     expiry has never been looked at by anything. */
  if (bridge.credentialFailedAt !== null) {
    return (
      <div className="m-well bg-cred" data-expiry="failed">
        <span className="bg-cred-icon" aria-hidden="true">
          <Icon name="alert" size={14} />
        </span>
        <span className="bg-cred-text">
          <span className="bg-cred-state">
            The credential died, and a sync is how we found out.
          </span>
          <span className="bg-cred-why">
            It failed at {bridge.credentialFailedAt} and nothing has moved since.
            No sweep predicted this and none could have — see the block above.
            Reconnecting asks for your passkey, and this bridge also needs
            somebody at the machine it runs on.
          </span>
        </span>
        {/* Reconnecting fires the echo and changes nothing else: we have no sync
            result to report yet, and drawing one would be inventing it. */}
        <button
          className="m-btn bg-mini"
          data-rank="certified"
          onClick={() => onEcho(`started reconnecting ${bridge.name}`)}
        >
          <Icon name="key" size={13} />
          Reconnect
        </button>
      </div>
    );
  }

  if (bridge.credentialExpiresAt !== null) {
    /* Unreachable today. Kept because the day the platform writes the field,
       this branch is already correct and nobody has to remember to add it. */
    return (
      <div className="m-well bg-cred" data-expiry="known">
        <span className="bg-cred-icon" aria-hidden="true">
          <Icon name="key" size={14} />
        </span>
        <span className="bg-cred-text">
          <span className="bg-cred-state">Expires {bridge.credentialExpiresAt}.</span>
          <span className="bg-cred-why">
            The nightly sweep reads this date and will raise a hand before it
            passes.
          </span>
        </span>
      </div>
    );
  }

  return (
    <div className="m-well bg-cred" data-expiry="unknown">
      <span className="bg-cred-icon" aria-hidden="true">
        <Icon name="clock" size={14} />
      </span>
      <span className="bg-cred-text">
        <span className="bg-cred-state">We do not know when this expires.</span>
        <span className="bg-cred-why">
          The field exists on this binding and has never been written to. This is
          not a clean bill of health — it is the absence of one.
        </span>
      </span>
    </div>
  );
}

/* ========================================================================== */
/*  A DISPUTE AT THE BRIDGE                                                   */
/* ========================================================================== */

function DisputeView({
  dispute,
  onSettle,
  onDeclare,
}: {
  dispute: Dispute;
  onSettle: (how: string, echo: string) => void;
  onDeclare: (object: string, master: string) => void;
}) {
  const d = dispute;
  const differing = d.fields.filter((f) => f.differs).length;

  return (
    <section className="bg-dispute vh-enter-fade" aria-labelledby={`bg-d-${d.id}`}>
      <header className="bg-dispute-head">
        <div className="bg-dispute-what">
          <span className="t-eyebrow">{d.object.toUpperCase()} · SYNC CONFLICT</span>
          <h5 className="bg-dispute-title t-display" id={`bg-d-${d.id}`}>
            {d.recordId} · {d.recordLabel}
          </h5>
          <span className="bg-dispute-meta">
            {differing} of {d.fields.length} fields disagree · found {d.detectedAt} ·{" "}
            {d.id}
          </span>
        </div>
        {/* A dispute nobody has settled is the definition of "this needs you",
            which is what buys the lit lamp here under §2.1. */}
        <p className="bg-dispute-waiting" role="status">
          <span className="m-lamp" data-lit />
          waiting on you
        </p>
      </header>

      <div className="bg-diff-scroll">
        <table className="bg-diff">
          <caption className="vh-sr-only">
            {d.recordId} as {d.masterSide.system} holds it, beside the same record
            as {d.otherSide.system} holds it
          </caption>
          <colgroup>
            <col />
            <col />
            <col className="bg-diff-seam-col" />
            <col />
          </colgroup>
          <thead>
            <tr>
              <th scope="col">
                <span className="t-eyebrow">FIELD</span>
              </th>
              <th scope="col">
                <span className="bg-side">
                  <span className="m-portrait-well bg-ident-well" aria-hidden="true">
                    <Seal id={d.masterSide.sealId} size={28} />
                  </span>
                  <span className="bg-side-text">
                    <span className="bg-side-name">{d.masterSide.system}</span>
                    <span className="m-chip bg-side-role" data-selected>
                      declared master
                    </span>
                    <span className="bg-side-when">wrote {d.masterSide.wroteAt}</span>
                  </span>
                </span>
              </th>
              {/* The seam. It carries no text of its own — the vertical rule is
                  the whole point, and the ≠ marks land on it row by row. */}
              <th scope="col" className="bg-seam">
                <span className="vh-sr-only">Agreement</span>
              </th>
              <th scope="col">
                <span className="bg-side">
                  <span className="m-portrait-well bg-ident-well" aria-hidden="true">
                    <Seal id={d.otherSide.sealId} size={28} />
                  </span>
                  <span className="bg-side-text">
                    <span className="bg-side-name">{d.otherSide.system}</span>
                    <span className="m-chip bg-side-role">the other side</span>
                    <span className="bg-side-when">wrote {d.otherSide.wroteAt}</span>
                  </span>
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            {d.fields.map((f) => (
              <tr key={f.field} data-differs={f.differs || undefined}>
                <th scope="row">
                  <span className="bg-field">
                    <span className="bg-field-name">{f.field}</span>
                    {/* The word, not the colour, is the information. */}
                    {f.differs && <span className="bg-field-differs">differs</span>}
                  </span>
                </th>
                <td>
                  <span className="bg-val">{f.master}</span>
                </td>
                <td className="bg-seam">
                  {f.differs && (
                    <span className="bg-seam-mark" aria-hidden="true">
                      ≠
                    </span>
                  )}
                </td>
                <td>
                  <span className="bg-val">{f.other}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ------------------------------------------------------- the resolution */}
      <div className="bg-resolve">
        <p className="bg-resolve-note">
          Unless you say otherwise, <strong>{d.masterSide.system} wins</strong> —{" "}
          {d.masterBecause}. That default is not applied on its own: a
          disagreement a rule could settle would never have reached you. The
          other side's values are kept either way, and you can read them in the
          Undercroft afterwards.
        </p>
        <div className="bg-resolve-acts">
          <button
            className="m-btn"
            onClick={() =>
              onSettle(
                `${d.masterSide.system} won`,
                `let ${d.masterSide.system} win on ${d.recordId}`,
              )
            }
          >
            <Icon name="check" size={13} />
            Let {d.masterSide.system} win
          </button>
          <button
            className="m-btn"
            data-rank="quiet"
            onClick={() =>
              onSettle(
                `${d.otherSide.system}'s version kept`,
                `took ${d.otherSide.system}'s version of ${d.recordId}`,
              )
            }
          >
            Take {d.otherSide.system}'s version
          </button>
          <button
            className="m-btn"
            data-rank="quiet"
            onClick={() =>
              onSettle("sent to Ravi", `asked Ravi to reconcile ${d.recordId}`)
            }
          >
            <Icon name="colleague" size={13} />
            Ask Ravi to reconcile it
          </button>
          {/* The structural fix rather than the per-record one, and the only act
              here that is certified — it changes who wins every future round. */}
          <button
            className="m-btn"
            data-rank="certified"
            onClick={() => onDeclare(d.object, d.otherSide.system)}
          >
            <Icon name="key" size={13} />
            Make {d.otherSide.system} master of {d.object} instead
          </button>
        </div>
      </div>
    </section>
  );
}

/* ========================================================================== */
/*  A GATE                                                                    */
/* ========================================================================== */

function GateCard({
  gate,
  posture,
  onPosture,
  onEcho,
}: {
  gate: Gate;
  posture: Gate["consent"]["posture"];
  onPosture: (next: Gate["consent"]["posture"]) => void;
  onEcho: (msg: string) => void;
}) {
  const revoked = posture === "revoked";
  const perDay = gate.volume.sevenDay === null ? null : Math.round(gate.volume.sevenDay / 7);

  return (
    <article className="m-plate bg-gate">
      <div className="bg-bridge-head">
        <div className="bg-ident">
          {/* A channel has no persona either. */}
          <span className="m-portrait-well bg-ident-well" aria-hidden="true">
            <Seal id={gate.id} size={36} />
          </span>
          <span className="bg-ident-text">
            <h3 className="bg-ident-name t-display">{gate.name}</h3>
            <span className="bg-ident-sub">{gate.transport}</span>
          </span>
        </div>
        <span className="m-chip bg-scope">{gate.kind}</span>
      </div>

      <dl className="bg-gate-facts">
        {/* ------------------------------------------------------------ consent */}
        <div className="bg-fact">
          <dt className="t-eyebrow">CONSENT</dt>
          <dd className="bg-fact-val">
            <span className="m-lamp" data-positive={posture === "opt-in" || undefined} />
            <span>{CONSENT[posture]}</span>
            {revoked && <span className="m-chip bg-scope">promotions off</span>}
            {posture !== gate.consent.posture && (
              <span className="m-chip bg-scope">changed by you, just now</span>
            )}
          </dd>
          <dd className="bg-fact-why">
            {posture === gate.consent.posture
              ? gate.consent.note
              : revoked
                ? "Written to the consent registry with your name on it. Every colleague is bound by it from this second, and none of them can override it."
                : "Restored in the consent registry with your name on it. Promotional intents on this gate will start passing again."}
          </dd>
          {gate.consent.recordedOn !== null && (
            <dd className="bg-obj-when">
              scope: {gate.consent.scope} · recorded {gate.consent.recordedOn}
            </dd>
          )}
          {/* recordedOn is null on a legitimate-interest gate because nothing was
              ever recorded. No date is invented and no dash is drawn — the scope
              line simply stands alone. */}
          {gate.consent.recordedOn === null && (
            <dd className="bg-obj-when">scope: {gate.consent.scope}</dd>
          )}
        </div>

        {/* ---------------------------------------------------------------- DNC */}
        <div className="bg-fact">
          <dt className="t-eyebrow">DO NOT CONTACT</dt>
          {gate.dnc.listed !== null ? (
            <>
              <dd className="bg-fact-val">
                <span className="t-mono">
                  {gate.dnc.listed.toLocaleString("en-IN")}
                </span>
                <span>on the list</span>
              </dd>
              <dd className="bg-fact-why">Checked {gate.dnc.enforcedAt}.</dd>
            </>
          ) : (
            /* Nothing is listed because nothing can be: a broadcast gate has no
               recipient to suppress. That is a sentence, not a zero. */
            <dd className="bg-fact-why">{gate.dnc.enforcedAt}.</dd>
          )}
        </div>

        {/* ------------------------------------------------------------- volume */}
        <div className="bg-fact">
          <dt className="t-eyebrow">VOLUME · LAST SEVEN DAYS</dt>
          {gate.volume.sevenDay !== null && perDay !== null ? (
            <dd className="bg-volume">
              <span className="bg-volume-figure">
                {gate.volume.sevenDay.toLocaleString("en-IN")}
              </span>
              <span className="bg-volume-unit">
                {gate.volume.unit} · about {perDay} a day
                {gate.volume.capPerDay !== null &&
                  ` · ceiling ${gate.volume.capPerDay.toLocaleString("en-IN")} a day`}
              </span>
            </dd>
          ) : null}
          {/* Where the count is not ours, there is no figure and no dash — only
              the reason there is no figure. */}
          {gate.volume.note !== null && (
            <dd className="bg-fact-why">{gate.volume.note}</dd>
          )}
        </div>
      </dl>

      <div className="bg-resolve-acts">
        {gate.consent.promotional && (
          <button
            className="m-btn bg-mini"
            data-rank="certified"
            onClick={() => onPosture(revoked ? "opt-in" : "revoked")}
          >
            <Icon name="key" size={13} />
            {revoked ? "Restore promotions" : "Revoke consent for promotions"}
          </button>
        )}
        <button
          className="m-btn bg-mini"
          data-rank="quiet"
          onClick={() => onEcho(`opened the consent record for ${gate.name}`)}
        >
          <Icon name="record" size={13} />
          The consent record
        </button>
      </div>
    </article>
  );
}
