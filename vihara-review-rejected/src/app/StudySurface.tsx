/**
 * The Study (DRIVER D12, D6 §15a) — the eighteenth surface, VP-03's
 * resolution: not a place in the estate, the desk you sit at. Reachable
 * from the shell, never from the territory.
 *
 * The four rules from the draft:
 *
 * 1. **Passkey enrolment lives here and nowhere deeper** — it gates
 *    every T2 act; deleting one is plain (the safe direction).
 * 2. **Density is stated here, learned everywhere else** — the switch
 *    writes the preference (which clears the learned value, the store's
 *    own rule) and the learned state shows beside it.
 * 3. **Dunning is explicable here** — a read-only tenant sees the ladder
 *    in words, because everywhere else quiet reads as calm.
 * 4. **Notifications are `notify.*`** — no new store.
 */
import { useCallback, useEffect, useState } from "react";

import {
  deletePasskey,
  isPasskeySupported,
  listPasskeys,
  registerPasskey,
  type PasskeyCredential,
} from "../api/authn";
import { emitEcho } from "../api/genui";
import {
  fetchBalance,
  fetchMe,
  fetchPreferences,
  fetchSubscription,
  writePreference,
  type Me,
  type PreferenceValue,
  type SubscriptionInfo,
  type WalletBalance,
} from "../api/study";
import { announce } from "./ribbon";

export interface StudyLoaders {
  me: typeof fetchMe;
  passkeys: typeof listPasskeys;
  enroll: typeof registerPasskey;
  removePasskey: typeof deletePasskey;
  preferences: typeof fetchPreferences;
  write: typeof writePreference;
  balance: typeof fetchBalance;
  subscription: typeof fetchSubscription;
  echo: typeof emitEcho;
  passkeySupported?: () => boolean;
}

const REAL: StudyLoaders = {
  me: fetchMe,
  passkeys: listPasskeys,
  enroll: registerPasskey,
  removePasskey: deletePasskey,
  preferences: fetchPreferences,
  write: writePreference,
  balance: fetchBalance,
  subscription: fetchSubscription,
  echo: emitEcho,
};

const NOTIFY_ROWS: { key: string; label: string }[] = [
  { key: "notify.push_enabled", label: "push on this device" },
  { key: "notify.morning_story", label: "morning story" },
];

function dunningSentence(status: string | null): string | null {
  if (status === "read_only" || status === "read-only") {
    return (
      "The estate is quiet because billing is past due: colleagues have " +
      "stopped acting and inbound work is parked, not dropped. Settling " +
      "the balance wakes everything exactly where it paused."
    );
  }
  if (status === "suspended") {
    return (
      "The account is suspended for non-payment. Nothing has been " +
      "deleted; the estate resumes when the balance clears."
    );
  }
  return null;
}

export function StudySurface({
  loaders = REAL,
}: {
  loaders?: StudyLoaders;
}): JSX.Element {
  const [me, setMe] = useState<Me | null>(null);
  const [failed, setFailed] = useState(false);
  const [passkeys, setPasskeys] = useState<PasskeyCredential[]>([]);
  const [prefs, setPrefs] = useState<Record<string, PreferenceValue>>({});
  const [balance, setBalance] = useState<WalletBalance | null>(null);
  const [subscription, setSubscription] = useState<SubscriptionInfo | null>(
    null,
  );
  const [enrolProblem, setEnrolProblem] = useState<string | null>(null);

  const load = useCallback(() => {
    void loaders
      .me()
      .then(setMe)
      .catch(() => setFailed(true));
    void loaders
      .passkeys()
      .then(setPasskeys)
      .catch(() => setPasskeys([]));
    void loaders
      .preferences()
      .then(setPrefs)
      .catch(() => setPrefs({}));
    void loaders
      .balance()
      .then(setBalance)
      .catch(() => setBalance(null));
    void loaders
      .subscription()
      .then(setSubscription)
      .catch(() => setSubscription(null));
  }, [loaders]);

  useEffect(load, [load]);

  if (failed) {
    return (
      <p role="alert" data-part="study-failed">
        The study could not be reached.
      </p>
    );
  }
  if (me === null) {
    return <p className="vh-quiet">Sitting down…</p>;
  }

  const densityPref = prefs["density.default"];
  const density =
    typeof densityPref?.value === "string" ? densityPref.value : "novice";
  const supported = (loaders.passkeySupported ?? isPasskeySupported)();
  const subscriptionStatus =
    (subscription?.subscription_status ?? subscription?.status ?? null) as
      | string
      | null;
  const dunning = dunningSentence(subscriptionStatus);

  return (
    <div className="vh-study" data-part="study">
      <section data-part="identity">
        <h3 className="vh-eyebrow">you</h3>
        <p>
          {me.full_name ?? me.email}
          <br />
          <span className="vh-mono">{me.email}</span>
        </p>
      </section>

      <section data-part="security">
        <h3 className="vh-eyebrow">security</h3>
        <p className="vh-quiet">
          A passkey is the key to every certified act (T2).
        </p>
        <ul className="vh-passkeys">
          {passkeys.map((passkey) => (
            <li key={passkey.id} data-part="passkey">
              <span>{passkey.label ?? "an unnamed passkey"}</span>
              <span className="vh-mono">
                added {passkey.created_at.slice(0, 10)}
              </span>
              <button
                type="button"
                className="vh-quiet-link"
                data-part="remove-passkey"
                onClick={() => {
                  void loaders
                    .removePasskey(passkey.id)
                    .then(() => {
                      void loaders.echo({
                        sentence: "removed a passkey",
                        action_ref: { kind: "study.passkey-remove", surface_id: "study" },
                      });
                      load();
                    })
                    .catch(() => undefined);
                }}
              >
                remove
              </button>
            </li>
          ))}
          {passkeys.length === 0 && (
            <li className="vh-quiet" data-part="no-passkeys">
              No passkey yet — certified acts will keep asking until one
              exists.
            </li>
          )}
        </ul>
        {supported ? (
          <button
            type="button"
            data-part="add-passkey"
            onClick={() => {
              setEnrolProblem(null);
              void loaders
                .enroll()
                .then(() => {
                  const sentence = "added a passkey";
                  void loaders.echo({
                    sentence,
                    action_ref: { kind: "study.passkey-add", surface_id: "study" },
                  });
                  announce(sentence);
                  load();
                })
                .catch(() =>
                  setEnrolProblem("The passkey ceremony was cancelled."),
                );
            }}
          >
            add a passkey
          </button>
        ) : (
          <p className="vh-quiet" data-part="passkey-unsupported">
            This device cannot hold a passkey; use one that can, or the
            one-time code fallback at each ceremony.
          </p>
        )}
        {enrolProblem !== null && <p role="alert">{enrolProblem}</p>}
      </section>

      <section data-part="density">
        <h3 className="vh-eyebrow">density</h3>
        <div role="radiogroup" aria-label="density">
          {(["novice", "operator"] as const).map((option) => (
            <label key={option}>
              <input
                type="radio"
                name="density"
                value={option}
                checked={density === option}
                onChange={() => {
                  void loaders.write("density.default", option).then(() => {
                    const sentence = `set density to ${option}`;
                    void loaders.echo({
                      sentence,
                      action_ref: { kind: "study.density", surface_id: "study" },
                    });
                    announce(sentence);
                    load();
                  });
                }}
              />
              {option}
            </label>
          ))}
        </div>
        {densityPref?.learned === true && (
          <p className="vh-quiet" data-part="density-learned">
            (learned from how you work — stating a choice here overrides it)
          </p>
        )}
      </section>

      <section data-part="notifications">
        <h3 className="vh-eyebrow">notifications</h3>
        {NOTIFY_ROWS.map((row) => {
          const current = prefs[row.key]?.value === true;
          return (
            <label key={row.key} className="vh-notify-row">
              <input
                type="checkbox"
                checked={current}
                onChange={() => {
                  void loaders.write(row.key, !current).then(() => {
                    void loaders.echo({
                      sentence: `turned ${row.label} ${current ? "off" : "on"}`,
                      action_ref: { kind: "study.notify", surface_id: "study" },
                    });
                    load();
                  });
                }}
              />
              {row.label}
            </label>
          );
        })}
      </section>

      <section data-part="billing">
        <h3 className="vh-eyebrow">billing & wallet</h3>
        {balance !== null ? (
          <p>
            <output>{String(balance.balance ?? "—")}</output> credits
            {subscription?.tier !== null &&
              subscription?.tier !== undefined &&
              ` · ${String(subscription.tier)}`}
          </p>
        ) : (
          <p className="vh-quiet">The wallet could not be read.</p>
        )}
        {dunning !== null ? (
          <p data-part="dunning-explained" role="note">
            {dunning}
          </p>
        ) : (
          subscriptionStatus !== null && (
            <p className="vh-quiet" data-part="subscription-status">
              subscription: {subscriptionStatus}
            </p>
          )
        )}
      </section>
    </div>
  );
}
