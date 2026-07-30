import { useCallback, useEffect, useState } from "react";
import { Background } from "../background/Background";
import { Shell, type Depth } from "../shell/Shell";
import { StillSurface } from "../surfaces/StillSurface";
import { TerraceSurface } from "../surfaces/TerraceSurface";
import { DistrictSurface } from "../surfaces/DistrictSurface";
import { DossierSurface } from "../surfaces/DossierSurface";
import { BoardroomSurface } from "../surfaces/BoardroomSurface";
import { StandupSurface } from "../surfaces/StandupSurface";
import { StudySurface } from "../surfaces/StudySurface";
import { GlasshouseSurface } from "../surfaces/GlasshouseSurface";
import { UndercroftSurface } from "../surfaces/UndercroftSurface";
import { LibrarySurface } from "../surfaces/LibrarySurface";
import { BridgesSurface } from "../surfaces/BridgesSurface";
import { TalentSurface } from "../surfaces/TalentSurface";
import { TraySurface } from "../surfaces/TraySurface";
import { HallSurface } from "../surfaces/HallSurface";
import { BackgroundPick } from "../boards/BackgroundPick";
import "./prototype.css";

/**
 * R-3a · the prototype.
 *
 * Decision D4: the review artifact is a clickable prototype that already looks
 * finished, because R2 proved wireframe approval does not predict craft
 * approval. So this is real React with the real material system and real
 * content density — not a mockup of it.
 *
 * **Honest scope of R-3a.** Three surfaces plus the shell, all of them Sheet
 * renderer. The World surfaces (Terrace, district rooms, the Glasshouse) are
 * deliberately absent: `UnrealBloomPass` needs float render targets, this VM
 * has no GPU, and craft work cannot be done on something that cannot be seen.
 * They land in R-3b once the owner confirms the background renders on real
 * hardware. Named here rather than discovered as a gap.
 *
 * The three chosen are not arbitrary — they are the ones finding RD-7 says were
 * built as fallbacks, plus depth 0, which RD-4 says was left empty.
 */

type SurfaceId =
  | "still"
  | "terrace"
  | "district"
  | "dossier"
  | "boardroom"
  | "standup"
  | "study"
  | "glasshouse"
  | "undercroft"
  | "library"
  | "bridges"
  | "talent"
  | "tray"
  | "hall"
  | "bg";

const SURFACE_DEPTH: Record<SurfaceId, Depth> = {
  still: 0,
  terrace: 1,
  district: 2,
  dossier: 2,
  boardroom: 2,
  standup: 1,
  study: 2,
  glasshouse: 2,
  undercroft: 3,
  library: 2,
  bridges: 2,
  talent: 2,
  tray: 2,
  hall: 2,
  bg: 1,
};

const SURFACES: { id: SurfaceId; label: string; note: string }[] = [
  { id: "still", label: "Still surface", note: "depth 0 · finding RD-4" },
  { id: "terrace", label: "The Terrace", note: "depth 1 · findings RD-1/RD-2" },
  { id: "district", label: "District room", note: "depth 2 · W+S" },
  { id: "dossier", label: "Dossier", note: "one-on-one · seals" },
  { id: "boardroom", label: "Boardroom", note: "brainstorm · review D" },
  { id: "standup", label: "The Standup", note: "one voice · L2" },
  { id: "study", label: "The Study", note: "your desk · VP-03" },
  { id: "glasshouse", label: "The Glasshouse", note: "drained twin · L6" },
  { id: "undercroft", label: "The Undercroft", note: "depth 3 · manifest" },
  { id: "library", label: "The Library", note: "provenance · influence" },
  { id: "bridges", label: "Bridges & Gates", note: "conflicts · consent" },
  { id: "talent", label: "Talent Office", note: "hire at A1 · VG-18" },
  { id: "tray", label: "The Tray", note: "certified · finding RD-7" },
  { id: "hall", label: "Registry Hall", note: "dense data · finding RD-7" },
  { id: "bg", label: "Background pick", note: "decision D2 · closed" },
];

/** Per-surface breadcrumb, so the shell's trail is data rather than a ternary. */
const BREADCRUMBS: Partial<
  Record<SurfaceId, (go: (s: SurfaceId) => void) => { label: string; onClick?: () => void }[]>
> = {
  terrace: (go) => [{ label: "Terrace", onClick: () => go("still") }],
  district: (go) => [
    { label: "Terrace", onClick: () => go("terrace") },
    { label: "Collections" },
  ],
  dossier: (go) => [
    { label: "Terrace", onClick: () => go("terrace") },
    { label: "Collections", onClick: () => go("district") },
    { label: "Meera" },
  ],
  boardroom: (go) => [
    { label: "Terrace", onClick: () => go("terrace") },
    { label: "The Boardroom" },
  ],
  standup: (go) => [
    { label: "Terrace", onClick: () => go("terrace") },
    { label: "The Standup" },
  ],
  // No district above it: the Study is the desk, not a place in the estate.
  study: () => [{ label: "The Study" }],
  glasshouse: (go) => [
    { label: "Terrace", onClick: () => go("terrace") },
    { label: "The Glasshouse" },
  ],
  undercroft: (go) => [
    { label: "Terrace", onClick: () => go("terrace") },
    { label: "The Undercroft" },
  ],
  library: (go) => [
    { label: "Terrace", onClick: () => go("terrace") },
    { label: "The Library" },
  ],
  bridges: (go) => [
    { label: "Terrace", onClick: () => go("terrace") },
    { label: "Bridges & Gates" },
  ],
  talent: (go) => [
    { label: "Terrace", onClick: () => go("terrace") },
    { label: "Talent Office" },
  ],
  tray: (go) => [
    { label: "Terrace", onClick: () => go("terrace") },
    { label: "The Tray" },
  ],
  hall: (go) => [
    { label: "Terrace", onClick: () => go("terrace") },
    { label: "Halls", onClick: () => go("hall") },
    { label: "Invoices" },
  ],
};

export function Prototype() {
  const [surface, setSurface] = useState<SurfaceId>("still");
  const [echo, setEcho] = useState<string | null>(null);
  const [variant, setVariant] = useState<"legacy" | "brand">("brand");

  const showEcho = useCallback((msg: string) => {
    setEcho(null);
    // One frame, so a repeat of the same message re-triggers the animation.
    requestAnimationFrame(() => setEcho(msg));
    window.setTimeout(() => setEcho(null), 4600);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const n = Number(e.key);
      if (n >= 1 && n <= SURFACES.length) setSurface(SURFACES[n - 1]!.id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (surface === "bg") {
    return (
      <>
        <BackgroundPick />
        <PrototypeNav surface={surface} onPick={setSurface} variant={variant} onVariant={setVariant} />
      </>
    );
  }

  const depth = SURFACE_DEPTH[surface];
  // Atmosphere per surface — the addition R-1 §5 describes.
  const intensity =
    surface === "still" || surface === "terrace"
      ? "full"
      : surface === "hall" || surface === "dossier" || surface === "standup" || surface === "study" || surface === "undercroft" || surface === "library" || surface === "bridges" || surface === "talent"
        ? "hushed"
        : "quiet";

  return (
    <>
      <Background variant={variant} intensity={intensity} />

      {surface === "still" ? (
        // Depth 0 has no chrome, because it *is* the chrome (D6 §2).
        <StillSurface onDescend={() => setSurface("terrace")} />
      ) : (
        <Shell
          depth={depth}
          onDepth={(d) => {
            if (d === 0) setSurface("still");
            if (d === 1) setSurface("terrace");
          }}
          breadcrumb={BREADCRUMBS[surface]?.(setSurface) ?? []}
          echo={echo}
          onUndo={() => showEcho("undone")}
        >
          {surface === "terrace" && (
            <TerraceSurface onOpenDistrict={() => setSurface("district")} onEcho={showEcho} />
          )}
          {surface === "district" && (
            <DistrictSurface
              code="P08"
              onOpenHall={() => setSurface("hall")}
              onOpenDossier={() => setSurface("dossier")}
              onEcho={showEcho}
            />
          )}
          {surface === "dossier" && <DossierSurface onEcho={showEcho} />}
          {surface === "boardroom" && <BoardroomSurface onEcho={showEcho} />}
          {surface === "study" && <StudySurface onEcho={showEcho} />}
          {surface === "glasshouse" && <GlasshouseSurface onEcho={showEcho} />}
          {surface === "undercroft" && <UndercroftSurface onEcho={showEcho} />}
          {surface === "library" && <LibrarySurface onEcho={showEcho} />}
          {surface === "bridges" && <BridgesSurface onEcho={showEcho} />}
          {surface === "talent" && <TalentSurface onEcho={showEcho} />}
          {surface === "standup" && (
            <StandupSurface
              onOpenTray={() => setSurface("tray")}
              onOpenDossier={() => setSurface("dossier")}
              onEcho={showEcho}
            />
          )}
          {surface === "tray" && <TraySurface onEcho={showEcho} />}
          {surface === "hall" && <HallSurface onEcho={showEcho} />}
        </Shell>
      )}

      <PrototypeNav surface={surface} onPick={setSurface} variant={variant} onVariant={setVariant} />
    </>
  );
}

/**
 * Review scaffolding — NOT part of the product. It is how the owner moves
 * between surfaces during R-3 and it is deleted at R-4. Marked so nobody
 * mistakes it for chrome that needs designing.
 */
function PrototypeNav({
  surface,
  onPick,
  variant,
  onVariant,
}: {
  surface: SurfaceId;
  onPick: (s: SurfaceId) => void;
  variant: "legacy" | "brand";
  onVariant: (v: "legacy" | "brand") => void;
}) {
  return (
    <nav className="pn m-glass" data-strong aria-label="Prototype surfaces">
      <span className="t-eyebrow pn-tag">R-3a · REVIEW SCAFFOLD</span>
      <div className="pn-items">
        {SURFACES.map((s, i) => (
          <button
            key={s.id}
            className="pn-item"
            data-active={surface === s.id || undefined}
            onClick={() => onPick(s.id)}
          >
            <kbd>{i + 1}</kbd>
            <span className="pn-item-label">{s.label}</span>
            <span className="pn-item-note t-mono">{s.note}</span>
          </button>
        ))}
      </div>
      <div className="m-rule-v pn-div" />
      <div className="pn-variant">
        <span className="t-eyebrow">SCENE</span>
        {(["legacy", "brand"] as const).map((v) => (
          <button
            key={v}
            className="m-chip"
            data-selected={variant === v || undefined}
            onClick={() => onVariant(v)}
          >
            {v}
          </button>
        ))}
      </div>
    </nav>
  );
}
