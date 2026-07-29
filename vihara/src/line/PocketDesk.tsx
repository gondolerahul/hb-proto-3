/**
 * The Pocket Desk (LINE L8, wireframes §16–18) — pinned live cards,
 * vitals always on top. Pins live in `surface.line_pins` (LEARN's
 * preference store — the namespace exists; a code-reviewed key, not a
 * new table). The live numbers ride the ONE shared estate stream.
 */
import { useEffect, useState } from "react";

import { emitEcho } from "../api/genui";
import { fetchPreferences, writePreference } from "../api/study";
import { useLiveEstate } from "../estate/useLiveEstate";

export interface DeskLoaders {
  preferences: typeof fetchPreferences;
  write: typeof writePreference;
  echo: typeof emitEcho;
}

const REAL: DeskLoaders = {
  preferences: fetchPreferences,
  write: writePreference,
  echo: emitEcho,
};

const PINS_KEY = "surface.line_pins";

export function PocketDesk({
  loaders = REAL,
}: {
  loaders?: DeskLoaders;
}): JSX.Element {
  const live = useLiveEstate();
  const [pins, setPins] = useState<string[]>([]);

  useEffect(() => {
    let alive = true;
    void loaders
      .preferences(PINS_KEY)
      .then((prefs) => {
        const value = prefs[PINS_KEY]?.value;
        if (alive && Array.isArray(value)) {
          setPins(value.filter((v): v is string => typeof v === "string"));
        }
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [loaders]);

  if (live.phase === "loading") {
    return <p className="vh-quiet">Reading the estate…</p>;
  }
  if (live.phase === "failed") {
    return (
      <p role="alert" data-part="desk-failed">
        The desk could not be read: {live.reason}
      </p>
    );
  }

  const estate = live.estate;
  const waiting = estate.beacons.length;
  const togglePin = (code: string): void => {
    const next = pins.includes(code)
      ? pins.filter((pin) => pin !== code)
      : [...pins, code];
    setPins(next);
    void loaders.write(PINS_KEY, next).catch(() => undefined);
    void loaders.echo({
      sentence: `${pins.includes(code) ? "unpinned" : "pinned"} ${code} on the pocket desk`,
      action_ref: {
        kind: "desk.pin",
        surface_id: "line.desk",
        params: { district: code },
      },
    });
  };

  return (
    <section data-part="pocket-desk" aria-label="Pocket desk">
      {/* Vitals, always on top — never pinnable away. */}
      <div className="vh-desk-vitals" data-part="desk-vitals">
        <span
          className="vh-pulse"
          data-healthy={estate.estate.pulse.healthy ? "true" : "false"}
        >
          <span className="vh-pulse-dot" /> {" "}
          {estate.estate.pulse.healthy ? "all well" : "attention needed"}
        </span>
        <span className={waiting > 0 ? "vh-beacon-count" : "vh-quiet"}>
          {waiting === 0
            ? "nothing waiting"
            : waiting === 1
              ? "1 decision waiting"
              : `${waiting} decisions waiting`}
        </span>
      </div>
      <ul className="vh-desk-cards" data-part="desk-cards">
        {estate.districts
          .filter((district) => pins.length === 0 || pins.includes(district.process_code))
          .map((district) => (
            <li key={district.process_code} className="vh-morning-card">
              <header>
                <strong>{district.process_code}</strong>{" "}
                {district.weather.sentence !== null && (
                  <span className="vh-quiet">{district.weather.sentence}</span>
                )}
                <button
                  type="button"
                  className="vh-quiet-link"
                  data-part="pin-toggle"
                  aria-pressed={pins.includes(district.process_code)}
                  onClick={() => togglePin(district.process_code)}
                >
                  {pins.includes(district.process_code) ? "unpin" : "pin"}
                </button>
              </header>
              <p className="vh-quiet">
                {district.traffic.in_1h} in · {district.traffic.out_1h} out
                {district.traffic.parked > 0 &&
                  ` · ${district.traffic.parked} parked`}
              </p>
            </li>
          ))}
      </ul>
    </section>
  );
}
