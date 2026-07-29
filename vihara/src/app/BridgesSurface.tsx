/**
 * The Bridges & Gates board (DRIVER D11, D6 §14) — two columns:
 * connected systems of record, and the channels/broadcast platforms.
 *
 * The rules this surface keeps:
 *
 * - **A bridge without an expiry date has NOT been checked.**
 *   `credentials_expire_at` ships and is never populated; the board says
 *   "expiry unknown" rather than implying health.
 * - **A `sync.conflict` is a dispute at the bridge** — both versions
 *   shown, master-wins already applied and said so; the dispute is a
 *   record, not a re-fight.
 * - **Binding is the certified act** (connector-binding, T2): credentials
 *   go straight through to the gated endpoint, and a plain session meets
 *   the ceremony.
 * - Consent posture and volume per gate have no tenant read endpoints
 *   yet — honest absence, never an empty gauge.
 */
import { useCallback, useEffect, useState } from "react";

import {
  bindConnector,
  fetchBindings,
  fetchCatalog,
  fetchSocialConnections,
  fetchSyncConflicts,
  type CatalogConnector,
  type ConnectorBinding,
  type SocialConnection,
  type SyncConflict,
} from "../api/bridges";
import { emitEcho } from "../api/genui";
import {
  StepUpCeremony,
  type CeremonyDeps,
} from "../components/certified/StepUpCeremony";
import { useCertifiedAct } from "../components/certified/useCertifiedAct";
import { announce } from "./ribbon";

export interface BridgesLoaders {
  catalog: typeof fetchCatalog;
  bindings: typeof fetchBindings;
  bind: typeof bindConnector;
  social: typeof fetchSocialConnections;
  conflicts: typeof fetchSyncConflicts;
  echo: typeof emitEcho;
  ceremony?: CeremonyDeps;
}

const REAL: BridgesLoaders = {
  catalog: fetchCatalog,
  bindings: fetchBindings,
  bind: bindConnector,
  social: fetchSocialConnections,
  conflicts: fetchSyncConflicts,
  echo: emitEcho,
};

function BridgeRow({
  connector,
  binding,
  loaders,
  onChanged,
}: {
  connector: CatalogConnector;
  binding: ConnectorBinding | undefined;
  loaders: BridgesLoaders;
  onChanged: () => void;
}): JSX.Element {
  const act = useCertifiedAct();
  const [connecting, setConnecting] = useState(false);
  const [credential, setCredential] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  const bound = binding !== undefined && binding.status !== "revoked";
  const expiry = binding?.credentials_expire_at;

  return (
    <li className="vh-bridge" data-part="bridge" data-connector={connector.connector_id}>
      <div className="vh-bridge-line">
        <strong>{connector.display_name}</strong>
        <span className="vh-mono">{connector.masters.join(", ") || "masters nothing"}</span>
        {bound ? (
          <span data-part="bridge-status">
            {String(binding?.status ?? "active")} ·{" "}
            {expiry !== null && expiry !== undefined ? (
              `credentials expire ${String(expiry).slice(0, 10)}`
            ) : (
              <span data-part="expiry-unknown">
                credential expiry unknown — not checked, not implied
              </span>
            )}
          </span>
        ) : connector.bindable ? (
          !connecting ? (
            <button
              type="button"
              data-part="bind-open"
              onClick={() => setConnecting(true)}
            >
              connect… T2
            </button>
          ) : (
            <span className="vh-hire-form">
              <input
                aria-label={`${connector.display_name} credential`}
                type="password"
                placeholder="API credential"
                value={credential}
                onChange={(event) => setCredential(event.target.value)}
              />
              <button
                type="button"
                data-part="bind-confirm"
                onClick={() => {
                  setProblem(null);
                  act
                    .run(async () => {
                      await loaders.bind(connector.connector_id, {
                        api_key: credential,
                      });
                      const sentence = `connected ${connector.display_name}`;
                      void loaders.echo({
                        sentence,
                        action_ref: {
                          kind: "bridges.bind",
                          surface_id: "bridges",
                          params: { connector_id: connector.connector_id },
                        },
                      });
                      announce(sentence);
                      setConnecting(false);
                      setCredential("");
                      onChanged();
                    })
                    .catch(() =>
                      setProblem("The connection could not be made."),
                    );
                }}
              >
                bind
              </button>
            </span>
          )
        ) : (
          <span className="vh-quiet">not bindable</span>
        )}
      </div>
      {act.refusal !== null && (
        <StepUpCeremony
          refusal={act.refusal}
          onElevated={act.onElevated}
          onClose={act.onClose}
          deps={loaders.ceremony}
        />
      )}
      {act.error !== null && <p role="alert">{act.error}</p>}
      {problem !== null && <p role="alert">{problem}</p>}
    </li>
  );
}

export function BridgesSurface({
  loaders = REAL,
}: {
  loaders?: BridgesLoaders;
}): JSX.Element {
  const [catalog, setCatalog] = useState<CatalogConnector[] | null>(null);
  const [bindings, setBindings] = useState<ConnectorBinding[]>([]);
  const [gates, setGates] = useState<SocialConnection[]>([]);
  const [conflicts, setConflicts] = useState<SyncConflict[]>([]);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    void loaders
      .catalog()
      .then(setCatalog)
      .catch(() => setFailed(true));
    void loaders
      .bindings()
      .then(setBindings)
      .catch(() => setBindings([]));
    void loaders
      .social()
      .then(setGates)
      .catch(() => setGates([]));
    void loaders
      .conflicts()
      .then(setConflicts)
      .catch(() => setConflicts([]));
  }, [loaders]);

  useEffect(load, [load]);

  if (failed) {
    return (
      <p role="alert" data-part="bridges-failed">
        The bridges board could not be reached.
      </p>
    );
  }
  if (catalog === null) {
    return <p className="vh-quiet">Walking to the estate edge…</p>;
  }

  const boundBy = new Map(
    bindings.map((binding) => [String(binding.connector_id ?? ""), binding]),
  );

  return (
    <div className="vh-bridges" data-part="bridges-board">
      <section data-part="bridges-column">
        <h3 className="vh-eyebrow">bridges — systems of record</h3>
        <ul className="vh-bridge-list">
          {catalog.map((connector) => (
            <BridgeRow
              key={connector.connector_id}
              connector={connector}
              binding={boundBy.get(connector.connector_id)}
              loaders={loaders}
              onChanged={load}
            />
          ))}
        </ul>

        {conflicts.length > 0 && (
          <div data-part="disputes">
            <h4 className="vh-eyebrow">disputes at the bridge</h4>
            <ul>
              {conflicts.map((conflict) => (
                <li key={conflict.signal_id} data-part="dispute">
                  <span>
                    {conflict.def_name ?? "a record"} — the master (
                    {conflict.connector ?? "external"}) won; the local edit is
                    kept here, not lost:
                  </span>
                  <code>{JSON.stringify(conflict.losing_delta)}</code>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section data-part="gates-column">
        <h3 className="vh-eyebrow">gates — channels & broadcast</h3>
        {gates.length === 0 ? (
          <p className="vh-quiet">No broadcast platform is connected.</p>
        ) : (
          <ul className="vh-gate-list">
            {gates.map((gate, index) => (
              <li key={String(gate.id ?? index)} data-part="gate">
                <strong>{String(gate.platform ?? "a platform")}</strong>
                <span className="vh-mono">{String(gate.status ?? "")}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="vh-quiet" data-part="gates-absences">
          Consent posture and send volume per gate have no tenant read
          endpoint yet — absent rather than drawn as empty gauges.
        </p>
      </section>
    </div>
  );
}
