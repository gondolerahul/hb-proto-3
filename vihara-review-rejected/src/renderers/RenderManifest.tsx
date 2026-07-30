/**
 * The render entry (SUB T5). The refusal ladder has already ruled by the
 * time anything mounts: a rejected manifest becomes a refused surface
 * (with the sheet-equivalent hand-off where one exists), and every
 * placeholder disposition renders visibly. S and C share one region
 * engine — the Card renderer is the Sheet renderer at pocket density,
 * which is also what serves the Line (D1 §2.1).
 *
 * W is an honest stub until WORLD (G1): it renders the L9 sheet notice
 * and never imports three.js — the bundle gate depends on that staying
 * true.
 */
import type { Assessment, Disposition } from "../manifest/refusals";
import type { WireComponent, WireScaffold } from "../manifest/schema";
import { CERTIFIED_IMPLEMENTATIONS } from "../components/certified/certifiedSet";
import { StillLine } from "../components/narrative/StillLine";
import {
  EmptyState,
  Gauge,
  KpiDial,
  Placeholder,
  Pulse,
  Timeline,
  type ComponentProps,
} from "../components/primitive/basics";
import { SlaCountdownComponent } from "../components/primitive/SlaCountdown";

type ComponentImpl = (props: ComponentProps) => JSX.Element;

/** Bare type → implementation. A registry type with no implementation yet
 * renders a NAMED placeholder — visible, honest, and exactly what tells a
 * build which component G1/G2 owes next. */
const IMPLEMENTATIONS: Record<string, ComponentImpl> = {
  "primitive.pulse": Pulse,
  "primitive.kpi-dial": KpiDial,
  "primitive.gauge": Gauge,
  "primitive.timeline": Timeline,
  "primitive.empty-state": ({ component }) => (
    <EmptyState
      reason={String((component.props ?? {})["reason"] ?? "Nothing here yet.")}
    />
  ),
  "narrative.still-line": StillLine,
  "primitive.sla-countdown": (props) => <SlaCountdownComponent {...props} />,
  // The certified set ships in the shell — never lazy (D7 §3.3): a tray
  // must not wait on a chunk.
  ...CERTIFIED_IMPLEMENTATIONS,
};

export function implementationFor(type: string): ComponentImpl | undefined {
  const bare = type.split("@")[0] ?? type;
  return IMPLEMENTATIONS[bare];
}

export function registerImplementations(
  additions: Record<string, ComponentImpl>,
): void {
  Object.assign(IMPLEMENTATIONS, additions);
}

export function RenderManifest({
  manifest,
  assessment,
}: {
  manifest: WireScaffold;
  assessment: Assessment;
}): JSX.Element {
  if (assessment.verdict === "reject") {
    return (
      <section className="vh-refused" role="alert" data-part="refused-surface">
        <h2>This surface cannot be shown safely.</h2>
        <p>{assessment.reason}</p>
        {manifest.sheet_equivalent !== undefined && (
          <p>
            The sheet version is <code>{manifest.sheet_equivalent}</code>.
          </p>
        )}
      </section>
    );
  }

  if (manifest.renderer === "W") {
    return (
      <section className="vh-world-stub" data-part="world-stub">
        <p>
          The territory arrives with G1. Its sheet,{" "}
          <code>{manifest.sheet_equivalent}</code>, is available now (L9).
        </p>
      </section>
    );
  }

  const byRegion = new Map<string, Disposition[]>();
  for (const disposition of assessment.dispositions) {
    const region = disposition.component.region ?? "body";
    const bucket = byRegion.get(region) ?? [];
    bucket.push(disposition);
    byRegion.set(region, bucket);
  }

  const compact = manifest.renderer === "C";
  return (
    <section
      className={compact ? "vh-card-surface" : "vh-sheet-surface"}
      data-part="surface"
      data-renderer={manifest.renderer}
      data-density={manifest.density}
      data-surface={manifest.surface_id}
    >
      {manifest.layout.regions.map((region) => (
        <div key={region} className="vh-region" data-region={region}>
          {(byRegion.get(region) ?? []).map((disposition) => (
            <RenderDisposition
              key={disposition.component.id}
              disposition={disposition}
              density={manifest.density}
            />
          ))}
        </div>
      ))}
    </section>
  );
}

function RenderDisposition({
  disposition,
  density,
}: {
  disposition: Disposition;
  density: "novice" | "operator";
}): JSX.Element {
  const { component } = disposition;
  if (disposition.kind === "placeholder") {
    return <Placeholder component={component} reason={disposition.reason} />;
  }
  const Impl = implementationFor(component.type);
  if (Impl === undefined) {
    return (
      <Placeholder
        component={component}
        reason="registered, not yet implemented — a later gate owes this component"
      />
    );
  }
  return (
    <div className="vh-component" data-component-id={component.id}>
      <Impl component={component as WireComponent} density={density} />
    </div>
  );
}
