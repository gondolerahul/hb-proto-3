import { useMemo, useState } from "react";

import { Icon } from "../components/Icon";
import { Seal } from "../components/Seal";
import { CERTIFIED_ACTS, StepUpCeremony, useCertifiedAct } from "../components/certified";
import {
  fetchBindings,
  fetchCatalog,
  fetchSocialConnections,
  fetchSyncConflicts,
  type CatalogConnector,
  type ConnectorBinding,
  type SocialConnection,
  type SyncConflict,
} from "../api/bridges";
import { fetchEstate, type EstateBridge } from "../api/estate";
import { fetchConsent, type ConsentChannel, type ConsentView } from "../api/undercroft";
import { Bar, Empty, Failed, Lines, Scaffold, useResource } from "../lifecycle";
import "./bridges.css";

/**
 * Bridges & Gates · depth 2 · S (D6 §14). Wired in R-4 part W.
 *
 * The estate's edge, on the network: `GET /ai/connectors/catalog` +
 * `/bindings` for what we are connected to, `GET /ai/genui/estate` for the one
 * field the connectors door does not project, `GET /ai/signals?type_prefix=
 * sync.conflict` for the disputes, and — new this increment — **`GET
 * /ai/consent`** for the gates, which is the endpoint D8's E1 built and the
 * reason this surface's right-hand column was a fixture.
 *
 * The look is unchanged. What changed is where every field comes from, and the
 * four places where the honest answer turned out to be *nothing at all*.
 *
 * ## 1 · The credential gap, which is sharper than it was
 *
 * `credentials_expire_at` ships on `connector_bindings` and **nothing has ever
 * written one**, so the nightly sweep (`connectors/credential_expiry.py`) is
 * correctly implemented and permanently finds nothing. Wiring found a second
 * layer to that: `GET /ai/connectors/bindings` does not even *project* the
 * column — `_binding_view` returns status, policy, `has_credential` and
 * `last_error`, and stops. The only door that ships the field is the estate
 * projection, which is why this surface reads the estate at all, and every
 * binding comes back `null` there.
 *
 * So the block says both things, because they are different: nobody has written
 * an expiry, **and** the endpoint a reader would check does not carry the field.
 * The dangerous reading is the calm one — a tenant seeing no expiry warnings
 * concludes their keys have been checked. Absence of an expiry is absence of
 * *information*; we cannot tell "never expires" from "dies next Tuesday", and
 * drawing a green tick there would be a security design bug rather than a
 * cosmetic one. It keeps its own material — the dot lattice, the instrument
 * register for a gauge with nothing behind it — and the `credentials_expire_at`
 * branch is still rendered when present, so the day the platform writes one
 * this is already right.
 *
 * **The expiry-sweep cell is gone.** It said "ran 03:00 today · nothing to
 * find". The sweep is real and nothing reports when it last ran, so that line
 * was two invented facts standing immediately beside the caveat — and it was
 * exactly the sentence a tenant would read as safety (§7.1).
 *
 * ## 2 · A dispute has one side, so it is drawn with one
 *
 * The old sheet drew both versions as two columns of one table with a machined
 * seam between them. `sync.conflict` carries `losing_delta` and nothing else:
 * `record_service.py` raises it *after* master-wins has already been applied,
 * and the master's own values are not in the payload. A second column would
 * have to be invented, and there is no honest content for the ≠ marks. So the
 * seam is gone and what is left is the rejected write, named as what it is.
 *
 * Two consequences follow, and both are corrections rather than losses:
 *
 *  - **No lit lamp.** A conflict where master-wins has already been applied is
 *    not "this needs you", and §2.1 gives gold to nothing else. The old card
 *    said "waiting on you" about a decision the platform had already taken.
 *  - **The four resolution buttons are gone.** Nothing on the platform accepts
 *    "let the master win", "take the other version" or "send it to Ravi". The
 *    one act that is real — changing which system masters an object — is a
 *    two-step certified migration (`propose` then `apply`) and belongs to its
 *    own flow rather than to a button on a conflict card.
 *
 * ## 3 · Who masters an object is not a read this platform serves
 *
 * The mastering table's MASTERED BY / DECLARED / provenance columns had no
 * source. A declaration lives in `TenantEntityDef.sor`, and `GET
 * /ai/tenant/defs` projects name, module, domain tag, owner and fields — not
 * `sor`. The catalogue *does* say which objects a connector **can** master, and
 * that is real, so the table keeps its object column and states the absence in
 * the place the answer would have been.
 *
 * ## 4 · No act on this surface writes
 *
 * Binding a connector is genuinely T2 (`enforce_kind(CONNECTOR_BINDING)` in
 * `ai/connectors/router.py`), and it is deliberately not drawn — the same call
 * `DossierSurface` makes about `certified.autonomy-change`, for a stronger
 * reason. `POST /ai/connectors/{id}/bind` takes a credential *set*, the
 * catalogue declares an `auth` kind and never the fields, and an OAuth
 * connector needs a redirect leg this app does not implement. Posting `{}`
 * would succeed after the ceremony and leave an ACTIVE binding that cannot
 * authenticate — a connected-looking estate that is not connected, which is the
 * silent success `acts.ts` §6 names as the dangerous kind. The gate is printed
 * from `CERTIFIED_ACTS` so the claim is checkable rather than asserted.
 *
 * Consent is the opposite case and is wired: the grant control routes through
 * `useCertifiedAct`, whose `certified.consent` row is gate kind `absent`, so
 * pressing it performs nothing, echoes nothing, and renders the platform's own
 * sentence about why. `GET /ai/consent` is the whole door — the registry's
 * router says a write belongs to the flows that have the counterparty's word,
 * never to a panel that lists them.
 *
 * Operator layout. The novice variant would drop the scope chips, the
 * per-object table and the collapsed second dispute, keeping "what is
 * connected" and "what needs attention" (§14).
 */

/** Binding status, as `BindingStatus` writes it. A status this table has not
 *  met prints itself rather than borrowing a neighbour's word. */
const HEALTH: Record<string, { word: string; lamp: "positive" | "negative" | null }> = {
  active: { word: "active", lamp: "positive" },
  paused: { word: "paused", lamp: null },
  error: { word: "under repair", lamp: "negative" },
};

/** The registry's three postures, as an owner reads them. The word carries the
 *  meaning; the lamp beside it is only the fast read (§4). */
const POSTURE: Record<ConsentChannel["posture"], string> = {
  open: "open on every purpose we model",
  restricted: "restricted",
  closed: "closed",
};

/** The consent grant's gate, quoted from the certified table rather than
 *  described. `absent` is the whole point — see §4 above. */
const BIND_GATE = CERTIFIED_ACTS["certified.connector-binding"].gate;

/** Why no bind control is drawn, per auth kind. Copy, not data — the catalogue
 *  ships the kind and this file supplies the consequence, once. */
const NO_BIND_REASON: Record<string, string> = {
  oauth2:
    "an OAuth redirect leg, which this app does not implement — the bind endpoint takes a finished token set, not a login",
  api_key:
    "a credential set whose field names the catalogue does not declare, and this surface will not guess them",
  gateway:
    "a gateway process on a machine of yours, and somebody standing at it",
};

interface EdgeMaterial {
  catalog: CatalogConnector[];
  bindings: ConnectorBinding[];
  projected: EstateBridge[];
  conflicts: SyncConflict[];
}

interface GateMaterial {
  consent: ConsentView;
  social: SocialConnection[];
}

/** A binding's status string, defensively — `_binding_view` types it loosely
 *  and a missing status is not "active". */
function statusOf(binding: ConnectorBinding): string | null {
  const status = binding["status"];
  return typeof status === "string" && status !== "" ? status : null;
}

function idOf(binding: ConnectorBinding): string | null {
  const id = binding["connector_id"];
  return typeof id === "string" && id !== "" ? id : null;
}

function stringsOf(binding: ConnectorBinding, key: string): string[] {
  const value = binding[key];
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

function errorOf(binding: ConnectorBinding): string | null {
  const last = binding["last_error"];
  return typeof last === "string" && last !== "" ? last : null;
}

/** A date the wire wrote, trimmed to the day. Never reformatted through ICU —
 *  `toLocaleString` would change shape between two browsers. */
function day(at: string | null): string | null {
  return at === null || at === "" ? null : at.slice(0, 10);
}

export function BridgesSurface({ onEcho }: { onEcho: (msg: string) => void }) {
  /* One read for the left column. `Promise.all` rather than four hooks: the
     four answers describe one thing, and a card drawn from three of them while
     the fourth is still coming would show a bridge with its disputes missing —
     which reads as a bridge with no disputes. */
  const edge = useResource<EdgeMaterial>(async () => {
    const [catalog, bindings, estate, conflicts] = await Promise.all([
      fetchCatalog(),
      fetchBindings(),
      fetchEstate(),
      fetchSyncConflicts(),
    ]);
    return { catalog, bindings, projected: estate.bridges, conflicts };
  });

  const gates = useResource<GateMaterial>(async () => {
    const [consent, social] = await Promise.all([
      fetchConsent(),
      fetchSocialConnections(),
    ]);
    return { consent, social };
  });

  /* Both are one-shot reads fired at the same moment, so the surface is early
     until both have answered. One `Scaffold`, one live sentence — two of them
     would announce the same room twice. */
  if (edge.phase === "pending" || gates.phase === "pending") return <BridgesScaffold />;

  return (
    <section className="bg">
      <header className="bg-head">
        <span className="t-eyebrow">BRIDGES &amp; GATES</span>
        <h1 className="bg-title t-display">The estate&apos;s edge</h1>
        <p className="t-narrative bg-lead">
          Systems of record on one side, ways of reaching a person on the other.
          Everything on this surface is a promise to something outside the
          estate, and every one of those promises can break without asking you
          first.
        </p>
      </header>

      <EdgeStrip edge={edge.phase === "ready" ? edge.value : null} gates={gates.phase === "ready" ? gates.value : null} />

      <div className="bg-cols">
        <div className="bg-col">
          <div className="bg-col-head">
            <h2 className="t-eyebrow">BRIDGES · SYSTEMS OF RECORD</h2>
            <span className="bg-col-count">
              what the estate reads from and writes back to
            </span>
          </div>

          {edge.phase === "failed" ? (
            <Failed
              what="the estate’s bridges"
              reason={edge.reason}
              onRetry={edge.retry}
              alone={false}
            />
          ) : (
            <BridgesColumn material={edge.value} />
          )}
        </div>

        <div className="bg-col">
          <div className="bg-col-head">
            <h2 className="t-eyebrow">GATES · HOW WE REACH PEOPLE</h2>
            <span className="bg-col-count">
              consent, do-not-contact, and who asked us to stop
            </span>
          </div>

          {gates.phase === "failed" ? (
            <Failed
              what="the consent registry"
              reason={gates.reason}
              onRetry={gates.retry}
              alone={false}
            />
          ) : (
            <GatesColumn material={gates.value} onEcho={onEcho} />
          )}
        </div>
      </div>
    </section>
  );
}

/* ========================================================================== */
/*  THE STATE OF THE EDGE                                                     */
/* ========================================================================== */

/**
 * The instrument strip.
 *
 * Every cell here is a count of rows the server sent, or a sentence. There is
 * no cell for anything derived: the estate's own `conflicts_open` is a
 * hard-coded `0` in `genui/estate.py` and is deliberately not read, because a
 * zero nobody counted is worse than no figure at all (§7.1).
 */
function EdgeStrip({
  edge,
  gates,
}: {
  edge: EdgeMaterial | null;
  gates: GateMaterial | null;
}) {
  return (
    <dl className="bg-edge m-plate m-ticks">
      {edge !== null && (
        <>
          <div className="bg-edge-item">
            <dt className="t-eyebrow">BRIDGES</dt>
            <dd className="bg-edge-val">
              {edge.bindings.length} bound
              {edge.bindings.filter((b) => statusOf(b) === "error").length > 0 && (
                <>
                  <span className="m-lamp" data-negative />
                  <span className="t-muted">
                    {edge.bindings.filter((b) => statusOf(b) === "error").length} under
                    repair
                  </span>
                </>
              )}
            </dd>
          </div>

          <div className="m-rule-v bg-edge-div" />

          <div className="bg-edge-item">
            <dt className="t-eyebrow">DISPUTES</dt>
            {/* No lamp. Master-wins was applied when each of these was raised,
                so none of them is waiting on anybody. */}
            <dd className="bg-edge-val">
              {edge.conflicts.length} recorded · already settled by the master
            </dd>
          </div>

          <div className="m-rule-v bg-edge-div" />
        </>
      )}

      {gates !== null && (
        <>
          <div className="bg-edge-item">
            <dt className="t-eyebrow">GATES</dt>
            <dd className="bg-edge-val">
              {gates.consent.channels.length} known to the registry
            </dd>
          </div>

          <div className="m-rule-v bg-edge-div" />

          <div className="bg-edge-item">
            <dt className="t-eyebrow">ASKED US TO STOP</dt>
            <dd className="bg-edge-val">
              {gates.consent.totals.dnc + gates.consent.totals.unsubscribed} people
            </dd>
          </div>

          <div className="m-rule-v bg-edge-div" />
        </>
      )}

      {/* The gap, stated in the summary strip. There is no figure to give here
          and none is invented — the cell is a sentence. */}
      <div className="bg-edge-item" data-wide>
        <dt className="t-eyebrow">CREDENTIAL EXPIRY</dt>
        <dd className="bg-edge-val">
          Not known for any bridge. Nothing has ever written an expiry date, and
          the bindings endpoint does not carry the field at all.
        </dd>
      </div>
    </dl>
  );
}

/* ========================================================================== */
/*  THE BRIDGES COLUMN                                                        */
/* ========================================================================== */

function BridgesColumn({ material }: { material: EdgeMaterial }) {
  const { catalog, bindings, projected, conflicts } = material;

  const byId = useMemo(() => {
    const map: Record<string, CatalogConnector> = {};
    for (const connector of catalog) map[connector.connector_id] = connector;
    return map;
  }, [catalog]);

  const bound = useMemo(
    () => new Set(bindings.map(idOf).filter((id): id is string => id !== null)),
    [bindings],
  );

  const available = catalog.filter(
    (connector) => connector.bindable && !bound.has(connector.connector_id),
  );

  return (
    <>
      {/* -------------------------------------------------------- the gap --
          First, and the only block on this surface written as narrative prose
          at reading size. It is a security claim, so it is not a footnote. */}
      <section className="m-well bg-gap" aria-labelledby="bg-gap-h">
        <div className="bg-gap-head">
          <Icon name="clock" size={13} />
          <h3 className="t-eyebrow" id="bg-gap-h">
            CREDENTIAL EXPIRY · WHAT WE DO NOT KNOW
          </h3>
        </div>
        <p className="bg-gap-body">
          Every binding below has a column for when its credential expires, and
          nothing has ever written one. The nightly sweep is real, it runs, and
          it correctly finds nothing — because there is nothing there to find.
          The endpoint that lists your bindings does not even return the column;
          the only door that carries it is the estate projection, and it is
          empty on every row.
        </p>
        <p className="bg-gap-body" data-key>
          So a bridge with no expiry date has not been checked and found
          healthy. We cannot tell you whether its key never expires or dies next
          Tuesday. Both look identical from here, and we will not draw one as
          the other.
        </p>
        <p className="bg-note">
          Every expiry this estate has ever found, it found by a sync breaking
          hours after the fact — which is what a bridge marked under repair below
          is, and why the sweep has never been the thing that told you.
        </p>
      </section>

      {bindings.length === 0 ? (
        /* L2. An estate with no bindings is a young estate, not a broken one —
           the unlit lamp and the prose say which. */
        <Empty
          icon="drive"
          title="Nothing is connected to this estate yet."
          body="A bridge is a system of record outside the estate — your books, your store, your bank — that your colleagues read from and write back to. Until one is bound, everything the estate knows was typed into it or learnt inside it."
        />
      ) : (
        bindings.map((binding) => {
          const id = idOf(binding);
          if (id === null) return null;
          return (
            <BridgeCard
              key={id}
              connectorId={id}
              binding={binding}
              connector={byId[id]}
              projected={projected.find((bridge) => bridge.connector === id)}
              conflicts={conflicts.filter((conflict) => conflict.connector === id)}
            />
          );
        })
      )}

      {/* ------------------------------------------- available, not bound -- */}
      <section className="m-plate bg-avail" aria-labelledby="bg-avail-h">
        <h3 className="t-eyebrow" id="bg-avail-h">
          IN THE CATALOGUE · NOT CONNECTED
        </h3>
        {available.length === 0 ? (
          <p className="bg-note">
            Every connector this platform ships is already bound here.
          </p>
        ) : (
          available.slice(0, 8).map((connector) => (
            <div className="bg-avail-row" key={connector.connector_id}>
              <span className="m-portrait-well bg-ident-well" data-sm aria-hidden="true">
                <Seal id={connector.connector_id} size={28} />
              </span>
              <span className="bg-avail-text">
                <span className="bg-avail-name">{connector.display_name}</span>
                <span className="bg-avail-what">
                  {connector.domain} · {connector.auth.replace(/_/g, " ")}
                </span>
              </span>
              {/* Where a Connect button was. Binding needs a credential set this
                  surface cannot compose, and a bind posted without one succeeds
                  and leaves a binding that cannot authenticate. */}
              <span className="bg-absent">
                needs {NO_BIND_REASON[connector.auth] ?? "a credential set this surface cannot compose"}
              </span>
            </div>
          ))
        )}
        <p className="bg-cert-note">
          <Icon name="seal" size={12} />
          Binding a connector is a certified act and the gate is real —{" "}
          {BIND_GATE.kind === "server" ? BIND_GATE.call : "no endpoint"}, refused
          until you prove it is you. No control is drawn for it here because the
          credential each connector needs is not something the catalogue
          declares, and a bind sent without one would leave you looking connected
          to a system that cannot answer.
        </p>
      </section>
    </>
  );
}

/* ========================================================================== */
/*  A BRIDGE                                                                  */
/* ========================================================================== */

function BridgeCard({
  connectorId,
  binding,
  connector,
  projected,
  conflicts,
}: {
  connectorId: string;
  binding: ConnectorBinding;
  connector: CatalogConnector | undefined;
  projected: EstateBridge | undefined;
  conflicts: SyncConflict[];
}) {
  const [open, setOpen] = useState<string | null>(conflicts[0]?.signal_id ?? null);

  const status = statusOf(binding);
  const health = status === null ? undefined : HEALTH[status];
  const lastError = errorOf(binding);
  const repair = status === "error";

  const tools = stringsOf(binding, "tool_allow");
  const writes = stringsOf(binding, "write_allow");

  return (
    <article className="m-plate bg-bridge" data-repair={repair || undefined}>
      {/* ----------------------------------------------------------- identity */}
      <div className="bg-bridge-head">
        <div className="bg-ident">
          {/* A connector has no persona, so it is sealed rather than portrayed. */}
          <span className="m-portrait-well bg-ident-well" aria-hidden="true">
            <Seal id={connectorId} size={36} />
          </span>
          <span className="bg-ident-text">
            <h3 className="bg-ident-name t-display">
              {connector?.display_name ?? connectorId}
            </h3>
            {/* Backend and auth kind, from the catalogue. There is no "synced 6
                minutes ago" any more: nothing on the wire records when a
                binding last ran, so the line that claimed it is gone. */}
            {connector !== undefined && (
              <span className="bg-ident-sub">
                {connector.backend.replace(/_/g, " ")} · {connector.auth.replace(/_/g, " ")}
              </span>
            )}
          </span>
        </div>

        {/* Lamp plus word. The lamp is the fast read, the word is the correct
            one — neither carries it alone. A status the table has not met
            prints itself rather than borrowing a word. */}
        {status !== null && (
          <p className="bg-health">
            <span
              className="m-lamp"
              data-positive={health?.lamp === "positive" || undefined}
              data-negative={health?.lamp === "negative" || undefined}
            />
            <strong>{health?.word ?? status}</strong>
          </p>
        )}
      </div>

      {/* --------------------------------------------------------- credential */}
      <Credential
        lastError={lastError}
        expiresAt={projected?.credentials_expire_at ?? null}
        hasCredential={binding["has_credential"] === true}
      />

      {/* -------------------------------------------------------------- scopes
          `tool_allow` empty means every tool the connector publishes is
          permitted — the model's own rule, and an inversion a reader would get
          backwards if the row simply rendered as blank. */}
      <div className="bg-scopes">
        <span className="t-eyebrow">SCOPE</span>
        {tools.length === 0 ? (
          <span className="bg-absent">
            no tool allow-list — every tool this connector publishes is permitted
          </span>
        ) : (
          tools.map((tool) => (
            <span className="m-chip bg-scope" key={`t:${tool}`}>
              {tool}
            </span>
          ))
        )}
        {/* A write scope is the dangerous half of a binding and is labelled as
            one. The word carries it, not a colour or a weight — the same rule
            every lamp on this surface follows (§4). */}
        {writes.map((write) => (
          <span className="m-chip bg-scope" key={`w:${write}`}>
            writes {write}
          </span>
        ))}
      </div>

      {/* ----------------------------------------------------------- mastering */}
      <div className="m-well bg-master-scroll">
        <table className="bg-master-table">
          <caption className="vh-sr-only">
            Objects {connector?.display_name ?? connectorId} is able to master
          </caption>
          <thead>
            <tr>
              <th scope="col">
                <span className="t-eyebrow">OBJECT</span>
              </th>
              <th scope="col">
                <span className="t-eyebrow">MASTERED BY</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {(connector?.masters ?? []).length === 0 ? (
              <tr>
                <th scope="row" className="bg-obj-name">
                  —
                </th>
                <td>
                  <span className="bg-obj-none">
                    this connector masters nothing; it reads and it feeds
                  </span>
                </td>
              </tr>
            ) : (
              (connector?.masters ?? []).map((object) => (
                <tr key={object}>
                  <th scope="row" className="bg-obj-name">
                    {object}
                  </th>
                  <td>
                    {/* The answer this platform does not serve. A declaration
                        lives on the entity def's `sor` and the defs endpoint
                        does not project it, so there is nothing to read — not a
                        dash, and certainly not this connector's own name. */}
                    <span className="bg-obj-none">
                      not a read this estate serves
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <p className="bg-note">
        The catalogue says which objects this connector is <em>able</em> to
        master. Which system masters each one today is declared on the object
        itself, and no endpoint returns that declaration — so the column is
        empty rather than filled with the likeliest guess.
      </p>

      {/* ------------------------------------------------------------ disputes */}
      {conflicts.length > 0 && (
        <div className="bg-disputes">
          <h4 className="t-eyebrow">
            {conflicts.length === 1
              ? "A DISPUTE AT THIS BRIDGE"
              : `${conflicts.length} DISPUTES AT THIS BRIDGE`}
          </h4>

          {conflicts.map((conflict) =>
            open === conflict.signal_id ? (
              <DisputeView key={conflict.signal_id} conflict={conflict} />
            ) : (
              <button
                className="bg-dispute-shut"
                key={conflict.signal_id}
                aria-expanded={false}
                onClick={() => setOpen(conflict.signal_id)}
              >
                {/* Unlit. The platform decided this one when it raised it. */}
                <span className="m-lamp" />
                <span className="bg-dispute-shut-text">
                  <span className="bg-dispute-shut-title">
                    {conflict.record_id ?? conflict.signal_id}
                    {conflict.def_name !== null && ` · ${conflict.def_name}`}
                  </span>
                  <span className="bg-dispute-meta">
                    {Object.keys(conflict.losing_delta).length} field
                    {Object.keys(conflict.losing_delta).length === 1 ? "" : "s"} were
                    rejected
                    {day(conflict.created_at) !== null && ` · ${day(conflict.created_at)}`}
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

/**
 * Four states, and the whole point of the block is that the last is not the
 * others. A broken binding was found by a sync failing; a binding with no
 * credential stored is a fact the endpoint reports; an unknown expiry has never
 * been looked at by anything at all.
 */
function Credential({
  lastError,
  expiresAt,
  hasCredential,
}: {
  lastError: string | null;
  expiresAt: string | null;
  hasCredential: boolean;
}) {
  if (lastError !== null) {
    return (
      <div className="m-well bg-cred" data-expiry="failed">
        <span className="bg-cred-icon" aria-hidden="true">
          <Icon name="alert" size={14} />
        </span>
        <span className="bg-cred-text">
          <span className="bg-cred-state">
            This bridge broke, and a call failing is how we found out.
          </span>
          {/* The server's own words, verbatim. Not paraphrased: `last_error` is
              the only account anybody has of what went wrong. */}
          <span className="bg-cred-why">
            {lastError} — no sweep predicted this and none could have. See the
            block above.
          </span>
        </span>
      </div>
    );
  }

  if (expiresAt !== null) {
    /* Unreachable today. Kept because the day the platform writes the field,
       this branch is already correct and nobody has to remember to add it. */
    return (
      <div className="m-well bg-cred" data-expiry="known">
        <span className="bg-cred-icon" aria-hidden="true">
          <Icon name="key" size={14} />
        </span>
        <span className="bg-cred-text">
          <span className="bg-cred-state">Expires {day(expiresAt)}.</span>
          <span className="bg-cred-why">
            The nightly sweep reads this date and raises a hand a fortnight
            before it passes.
          </span>
        </span>
      </div>
    );
  }

  if (!hasCredential) {
    return (
      <div className="m-well bg-cred" data-expiry="unknown">
        <span className="bg-cred-icon" aria-hidden="true">
          <Icon name="key" size={14} />
        </span>
        <span className="bg-cred-text">
          <span className="bg-cred-state">
            This binding holds no credential at all.
          </span>
          <span className="bg-cred-why">
            The policy is set and the secret is not. Nothing can authenticate to
            the far side, so nothing has.
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
          A credential is stored and no expiry has ever been written beside it.
          This is not a clean bill of health — it is the absence of one.
        </span>
      </span>
    </div>
  );
}

/* ========================================================================== */
/*  A DISPUTE AT THE BRIDGE                                                   */
/* ========================================================================== */

/**
 * One side, because one side is what the signal carries.
 *
 * `record_service.py` applies master-wins and *then* raises `sync.conflict`
 * with `losing_delta` — the write that was refused. The master's own values are
 * not in the payload and are not readable from anywhere else, so the seam and
 * its ≠ marks are gone rather than drawn against an invented column.
 */
function DisputeView({ conflict }: { conflict: SyncConflict }) {
  const fields = Object.entries(conflict.losing_delta);

  return (
    <section
      className="bg-dispute vh-enter-fade"
      aria-labelledby={`bg-d-${conflict.signal_id}`}
    >
      <header className="bg-dispute-head">
        <div className="bg-dispute-what">
          <span className="t-eyebrow">
            {(conflict.def_name ?? "RECORD").toUpperCase()} · SYNC CONFLICT
          </span>
          <h5 className="bg-dispute-title t-display" id={`bg-d-${conflict.signal_id}`}>
            {conflict.record_id ?? conflict.signal_id}
          </h5>
          <span className="bg-dispute-meta">
            {fields.length} field{fields.length === 1 ? "" : "s"} rejected
            {day(conflict.created_at) !== null && ` · ${day(conflict.created_at)}`} ·{" "}
            {conflict.signal_id}
          </span>
        </div>
      </header>

      <div className="bg-diff-scroll">
        <table className="bg-diff">
          <caption className="vh-sr-only">
            The values this estate tried to write to {conflict.record_id ?? "the record"}{" "}
            and the external master refused
          </caption>
          <thead>
            <tr>
              <th scope="col">
                <span className="t-eyebrow">FIELD</span>
              </th>
              <th scope="col">
                <span className="t-eyebrow">WHAT WE TRIED TO WRITE</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {fields.map(([field, value]) => (
              <tr key={field}>
                <th scope="row">
                  <span className="bg-field">
                    <span className="bg-field-name">{field}</span>
                  </span>
                </th>
                <td>
                  <span className="bg-val">
                    {typeof value === "string" ? value : JSON.stringify(value)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="bg-resolve">
        <p className="bg-resolve-note">
          <strong>The master already won.</strong> The external system changed
          this record under us, so the estate&apos;s write was refused rather
          than applied, and what you are reading is the copy that lost. Nothing
          is waiting on you and there is nothing here to decide.
        </p>
        <p className="bg-note">
          What the master holds is not on this record. The conflict carries the
          rejected write and nothing else, and no endpoint returns the winning
          side — so the other column is absent rather than filled in. Changing
          which system wins next time is a two-step certified migration on the
          object itself, and it does not belong on a card about one row.
        </p>
      </div>
    </section>
  );
}

/* ========================================================================== */
/*  THE GATES COLUMN                                                          */
/* ========================================================================== */

function GatesColumn({
  material,
  onEcho,
}: {
  material: GateMaterial;
  onEcho: (msg: string) => void;
}) {
  const act = useCertifiedAct({ renderer: "S", surface: "bridges", onEcho });
  const { consent, social } = material;

  return (
    <>
      {act.problem !== null && (
        <div className="m-plate bg-problem" role="status">
          <span className="m-lamp" data-negative aria-hidden="true" />
          <span className="bg-problem-text">
            {act.problem.message}
            {act.problem.kind === "gap" && (
              <span className="bg-problem-reason">Closed by {act.problem.closedBy}.</span>
            )}
          </span>
          <button className="m-btn" data-rank="quiet" onClick={act.clearProblem}>
            Dismiss
          </button>
        </div>
      )}

      {consent.channels.length === 0 ? (
        /* L2. An empty registry is the commonest honest state and the most
           easily misread: nobody has asked to be left alone, which is not the
           same as a registry that has been consulted and found clear. */
        <Empty
          icon="thread"
          title="Nobody has asked this estate to stop."
          body="The consent registry holds a row the moment somebody opts in, opts out, unsubscribes or lands on a do-not-contact list, and it holds none. That is a young estate rather than a permissive one — every send is still checked against this registry before it leaves."
          note={`asked ${consent.as_of.slice(0, 10)}`}
        />
      ) : (
        consent.channels.map((channel) => (
          <GateCard
            key={channel.channel}
            channel={channel}
            busy={act.busy}
            onGrant={() => {
              void act.run(
                {
                  act: "certified.consent",
                  echo: `opened ${channel.channel} for marketing`,
                  summary: `open the ${channel.channel} gate for marketing`,
                  subject: channel.channel,
                },
                /* Never reached: `certified.consent` is gate kind `absent`, so
                   the hook refuses before performing. Present rather than
                   omitted because the day a write exists, this is the call. */
                () => Promise.resolve(),
              );
            }}
          />
        ))
      )}

      {/* Broadcast gates. A social connection is a page we post to, not a
          person we contact, so it carries no consent posture and is not given
          one — it is listed as the different thing it is. */}
      <section className="m-plate bg-avail" aria-labelledby="bg-social-h">
        <h3 className="t-eyebrow" id="bg-social-h">
          BROADCAST · PAGES THIS ESTATE POSTS TO
        </h3>
        {social.length === 0 ? (
          <p className="bg-note">No page is connected to this estate.</p>
        ) : (
          social.map((connection, i) => {
            const platform = connection["platform"];
            const account = connection["account_name"];
            const active = connection["is_active"] === true;
            return (
              <div className="bg-avail-row" key={String(connection["id"] ?? i)}>
                <span className="m-portrait-well bg-ident-well" data-sm aria-hidden="true">
                  <Seal id={String(platform ?? i)} size={28} />
                </span>
                <span className="bg-avail-text">
                  <span className="bg-avail-name">
                    {typeof platform === "string" ? platform : "a connected page"}
                  </span>
                  {typeof account === "string" && account !== "" && (
                    <span className="bg-avail-what">{account}</span>
                  )}
                </span>
                <span className="m-chip bg-scope">
                  <span className="m-lamp" data-positive={active || undefined} />
                  {active ? "connected" : "not connected"}
                </span>
              </div>
            );
          })
        )}
        <p className="bg-note">
          A broadcast gate reaches nobody in particular, so there is no consent
          to hold and no do-not-contact list to check. Nothing here is counted
          into the figures above.
        </p>
      </section>

      <p className="bg-cert-note">
        <Icon name="seal" size={12} />
        Opening a gate is a certified act and this estate cannot record one yet:{" "}
        <code>GET /ai/consent</code> is the whole door. Closing one has no
        control here either, and that is not an oversight — a revocation belongs
        to the flow that has the person&apos;s own word for it, never to a panel
        that lists them.
      </p>

      {act.ceremony !== null && (
        <StepUpCeremony
          prompt={act.ceremony}
          onElevated={act.onElevated}
          onClose={act.onClose}
        />
      )}
    </>
  );
}

/* ========================================================================== */
/*  A GATE                                                                    */
/* ========================================================================== */

function GateCard({
  channel,
  busy,
  onGrant,
}: {
  channel: ConsentChannel;
  busy: boolean;
  onGrant: () => void;
}) {
  const purposes = Object.entries(channel.purposes);

  return (
    <article className="m-plate bg-gate">
      <div className="bg-bridge-head">
        <div className="bg-ident">
          {/* A channel has no persona either. */}
          <span className="m-portrait-well bg-ident-well" aria-hidden="true">
            <Seal id={channel.channel} size={36} />
          </span>
          <span className="bg-ident-text">
            <h3 className="bg-ident-name t-display">{channel.channel}</h3>
            <span className="bg-ident-sub">the registry&apos;s own answer</span>
          </span>
        </div>
      </div>

      <dl className="bg-gate-facts">
        {/* ------------------------------------------------------------ consent */}
        <div className="bg-fact">
          <dt className="t-eyebrow">POSTURE</dt>
          <dd className="bg-fact-val">
            <span className="m-lamp" data-positive={channel.posture === "open" || undefined} />
            <span>{POSTURE[channel.posture]}</span>
          </dd>
          {/* The registry's own reason, verbatim. This surface owns no second
              copy of the precedence rules — a panel that computed its own
              answer would eventually disagree with the gate that refuses the
              send, and the owner would believe the panel. */}
          <dd className="bg-fact-why">{channel.reason}</dd>
          <dd className="bg-obj-when">
            {purposes
              .map(([purpose, allowed]) => `${purpose}: ${allowed ? "allowed" : "refused"}`)
              .join(" · ")}
          </dd>
          {/* Recording is not on this list and its absence is deliberate: the
              registry models marketing and transactional, and publishing a
              posture for a purpose nothing sets would be inventing one. */}
        </div>

        {/* ---------------------------------------------------------------- DNC */}
        <div className="bg-fact">
          <dt className="t-eyebrow">DO NOT CONTACT</dt>
          <dd className="bg-fact-val">
            <span className="t-mono">{channel.dnc}</span>
            <span>on the list</span>
          </dd>
          <dd className="bg-fact-why">
            {channel.unsubscribed} more have unsubscribed. Both are checked
            before every send, and again at dispatch.
          </dd>
        </div>

        {/* --------------------------------------------------------- on record */}
        <div className="bg-fact">
          <dt className="t-eyebrow">ON RECORD</dt>
          <dd className="bg-fact-val">
            <span className="t-mono">{channel.granted}</span>
            <span>said yes</span>
            <span className="t-mono">{channel.denied}</span>
            <span>said no</span>
          </dd>
          {/* Volume was a fixture. Nothing counts sends per channel over a
              window, so there is no seven-day figure and none is drawn. */}
          <dd className="bg-fact-why">
            How much has gone out through this gate is not counted anywhere, so
            there is no volume here and no ceiling to show against it.
          </dd>
        </div>
      </dl>

      <div className="bg-acts">
        {/* The one act, and it is the unsafe direction. Pressing it performs
            nothing and says why — `certified.consent` maps to no write
            endpoint, and the hook refuses rather than pretending. */}
        <button
          className="m-btn bg-mini"
          data-rank="certified"
          disabled={busy}
          onClick={onGrant}
        >
          <Icon name="key" size={13} />
          Open this gate for marketing
        </button>
      </div>
    </article>
  );
}

/* ========================================================================== */
/*  THE PENDING STATE                                                         */
/* ========================================================================== */

/**
 * The surface's own structure with the words not yet in it (D7 §3.1). No
 * spinner: this is one of the seventeen.
 *
 * The plates are drawn first and the bars go inside them — `vh-skeleton`'s
 * ground is a ~6/255 delta on the raw canvas, so a bar on the page background
 * draws nothing at all.
 */
function BridgesScaffold() {
  return (
    <section className="bg">
      <Scaffold label="The estate’s edge">
        <header className="bg-head">
          <Bar width="xs" />
          <Bar width="md" tall />
        </header>

        <div className="bg-edge m-plate">
          {[0, 1, 2].map((i) => (
            <div className="bg-edge-item" key={i}>
              <Bar width="xs" />
              <Bar width="sm" />
            </div>
          ))}
        </div>

        <div className="bg-cols">
          {[0, 1].map((column) => (
            <div className="bg-col" key={column}>
              <div className="bg-col-head">
                <Bar width="xs" />
              </div>
              {[0, 1].map((i) => (
                <article className="m-plate bg-bridge" key={i}>
                  <div className="bg-bridge-head">
                    <Bar width="sm" tall />
                  </div>
                  <div className="m-well bg-cred">
                    <Lines n={2} />
                  </div>
                  <div className="m-well bg-master-scroll">
                    <Lines n={3} />
                  </div>
                </article>
              ))}
            </div>
          ))}
        </div>
      </Scaffold>
    </section>
  );
}
