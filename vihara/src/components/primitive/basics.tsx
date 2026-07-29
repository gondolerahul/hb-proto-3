/**
 * The v1 primitive set (SUB T5) — deliberately calm, deliberately small.
 * Every figure a primitive shows came through a binding; a missing binding
 * value renders the empty state with its reason (D4 §7), never a blank.
 * Visual depth is G1/G2's work; what G0 pins is the *contract* each
 * component keeps.
 */
import type { WireComponent } from "../../manifest/schema";
import { useBindingValues } from "../../renderers/bindings";

export interface ComponentProps {
  component: WireComponent;
  density: "novice" | "operator";
}

function label(component: WireComponent, key: string): string {
  const value = (component.props ?? {})[key];
  return typeof value === "string" ? value : "";
}

export function EmptyState({ reason }: { reason: string }): JSX.Element {
  return (
    <p className="vh-empty" role="status" data-part="empty-state">
      {reason}
    </p>
  );
}

export function Placeholder({
  component,
  reason,
}: {
  component: WireComponent;
  reason: string;
}): JSX.Element {
  // The refusal ladder's "fail visible" row: never skip, always name.
  return (
    <div className="vh-placeholder" role="note" data-part="placeholder">
      <span className="vh-mono">{component.type}</span> — {reason}
    </div>
  );
}

export function Pulse({ component }: ComponentProps): JSX.Element {
  const [pulse] = useBindingValues(component.bindings) as [
    { beat_at?: string | null; healthy?: boolean } | undefined,
  ];
  if (pulse === undefined) {
    return <EmptyState reason="The pulse has not been read yet." />;
  }
  return (
    <div className="vh-pulse" data-part="pulse" data-healthy={pulse.healthy === true}>
      <span aria-hidden className="vh-pulse-dot" />
      <span>{pulse.healthy === true ? "Steady" : "Missed beats"}</span>
    </div>
  );
}

export function KpiDial({ component }: ComponentProps): JSX.Element {
  const [reading] = useBindingValues(component.bindings) as [
    { value?: number | null; measurable?: boolean; unit?: string } | undefined,
  ];
  const title = label(component, "title");
  if (reading === undefined || reading.measurable !== true) {
    return (
      <div className="vh-kpi" data-part="kpi-dial">
        <h3>{title}</h3>
        <EmptyState reason="Not measurable yet — the data this needs has not arrived." />
      </div>
    );
  }
  return (
    <div className="vh-kpi" data-part="kpi-dial">
      <h3>{title}</h3>
      <output className="vh-figure">{String(reading.value ?? "—")}</output>
      <span className="vh-quiet">{reading.unit ?? ""}</span>
    </div>
  );
}

export function Gauge({ component }: ComponentProps): JSX.Element {
  const [envelope] = useBindingValues(component.bindings) as [
    { spent?: number; cap?: number } | undefined,
  ];
  const title = label(component, "title");
  if (envelope === undefined || typeof envelope.cap !== "number") {
    return (
      <div className="vh-gauge" data-part="gauge">
        <h3>{title}</h3>
        <EmptyState reason="No envelope is set for this yet." />
      </div>
    );
  }
  const fraction =
    envelope.cap > 0 ? Math.min(1, (envelope.spent ?? 0) / envelope.cap) : 0;
  return (
    <div className="vh-gauge" data-part="gauge">
      <h3>{title}</h3>
      <meter value={fraction} max={1} />
    </div>
  );
}

export function Timeline({ component }: ComponentProps): JSX.Element {
  const [entries] = useBindingValues(component.bindings) as [
    Array<{ at?: string; sentence?: string }> | undefined,
  ];
  const title = label(component, "title");
  if (entries === undefined || entries.length === 0) {
    return (
      <div className="vh-timeline" data-part="timeline">
        <h3>{title}</h3>
        <EmptyState reason="Nothing has happened here yet." />
      </div>
    );
  }
  return (
    <div className="vh-timeline" data-part="timeline">
      <h3>{title}</h3>
      <ul>
        {entries.map((entry, index) => (
          <li key={index}>{entry.sentence ?? entry.at ?? ""}</li>
        ))}
      </ul>
    </div>
  );
}
