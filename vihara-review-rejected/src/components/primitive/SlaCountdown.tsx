/**
 * `primitive.sla-countdown` (DRIVER D1) — a component whose whole
 * specification is what it must NOT do (D6 §20): never red, never pulse,
 * never sound. An SLA that shouts converts a considered decision into a
 * rushed one, so this is a number that ticks, in the quiet foreground,
 * with no alarm class for CSS to seize on.
 *
 * Past its window it stays quiet too, saying what the platform will do
 * (`on_timeout`) rather than demanding anything.
 */
import { useEffect, useState } from "react";

import type { WireComponent } from "../../manifest/schema";
import { useBindingValues } from "../../renderers/bindings";

export function formatSlaSentence(
  secondsLeft: number,
  onTimeout: string | null,
): string {
  if (secondsLeft <= 0) {
    return onTimeout === "auto_deny"
      ? "past its window — it will decline itself"
      : "past its window";
  }
  const hours = Math.floor(secondsLeft / 3600);
  const minutes = Math.floor((secondsLeft % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m left`;
  if (minutes > 0) return `${minutes}m left`;
  return "under a minute left";
}

/** Direct form for composed surfaces (the tray). */
export function SlaCountdown({
  secondsLeft,
  onTimeout,
}: {
  secondsLeft: number | null;
  onTimeout: string | null;
}): JSX.Element | null {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (secondsLeft === null) return undefined;
    const startedAt = Date.now();
    const tick = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    }, 30_000);
    return () => clearInterval(tick);
  }, [secondsLeft]);

  // No SLA is composed as no line at all — an invented deadline would be
  // the countdown's own version of a fabricated cost.
  if (secondsLeft === null) return null;

  return (
    <span className="vh-sla" role="timer" data-part="sla-countdown">
      {formatSlaSentence(secondsLeft - elapsed, onTimeout)}
    </span>
  );
}

/** Manifest-driven form, fed by the `approval.sla` binding. */
export function SlaCountdownComponent({
  component,
}: {
  component: WireComponent;
  density: "novice" | "operator";
}): JSX.Element | null {
  const [sla] = useBindingValues(component.bindings) as [
    { seconds_left?: number | null; on_timeout?: string | null } | undefined,
  ];
  if (sla === undefined) return null;
  return (
    <SlaCountdown
      secondsLeft={sla.seconds_left ?? null}
      onTimeout={sla.on_timeout ?? null}
    />
  );
}
