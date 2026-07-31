import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Background } from "../background/Background";
import { Shell, DEPTH_LABELS, type Depth } from "../shell/Shell";
import { Palette, type PaletteItem } from "../shell/Palette";
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
import { GallerySurface } from "../surfaces/GallerySurface";
import { TraySurface } from "../surfaces/TraySurface";
import { HallSurface } from "../surfaces/HallSurface";
import {
  ancestorsOf,
  parseRoute,
  pathOf,
  ROOT,
  SURFACES,
  surfaceOf,
  type Route,
  type SurfaceId,
} from "./routes";
import { endSession } from "./session";

/**
 * The estate, behind the session gate.
 *
 * Decision D4 built this as a clickable prototype so that R-4 would be a
 * data-source swap rather than a rebuild. R-4 §4 (D7) collects on the other half
 * of that promise: **`PrototypeNav` is gone.** The review scaffold — a fixed
 * strip of sixteen buttons and a scene toggle, plus number-key shortcuts that
 * fired while you were typing — is replaced by the two things the product was
 * always going to navigate by: ⌘K, and the address bar.
 *
 * Four decisions a reader would otherwise have to reverse-engineer:
 *
 *  1. **The chord lives here, not in `Shell`.** Depth 0 has no shell (D6 §2), and
 *     a navigator that does not exist at the front door is not the navigator.
 *     `Prototype` owns the palette's open state and mounts it at every depth;
 *     the rail keeps only the button that says the chord exists.
 *
 *  2. **The back stack is seeded to the depth ladder (N3).** Arriving straight
 *     at `/tray` — which is exactly what the Line's `notificationclick` does —
 *     leaves a history with one entry, and Back exits the product from the room
 *     it just delivered you to. So on arrival the ancestors of the landing route
 *     are pushed beneath it, and Back *rises*: tray, terrace, still, gone. It is
 *     done once per document, guarded by a ref rather than by an empty
 *     dependency array, because StrictMode runs mount effects twice and the
 *     second run would double the ladder.
 *
 *  3. **Breadcrumbs are read off `above`, not written per surface.** The old
 *     table hard-coded "Collections" and "Meera" — fixture facts that would
 *     become lies the moment the URL named a different district or colleague.
 *     The chain is now derived, so a crumb can only ever say what the route
 *     says. It buys back its specificity in W, when the subject has a name.
 *
 *  4. **An unrecognised URL is corrected, not faked.** It resolves to the front
 *     door *and* rewrites the address bar to match, so the two never disagree.
 *     A "not found" surface is a real surface with real copy and it belongs to
 *     the lifecycle round, not to a silent fallback here.
 */

/** The palette's rung headings. The Line is filed apart because it is a
 *  different document, not a deeper room. */
const ELSEWHERE = "Elsewhere";

export function Prototype() {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.pathname));
  const [echo, setEcho] = useState<string | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const seeded = useRef(false);

  const def = surfaceOf(route.surface);

  const go = useCallback((next: Route) => {
    const path = pathOf(next);
    if (path !== window.location.pathname) {
      window.history.pushState(next, "", path);
    }
    setRoute(next);
  }, []);

  const goTo = useCallback((id: SurfaceId, subject: string | null = null) => go({ surface: id, subject }), [go]);

  /* N3 — the ladder, seeded beneath wherever the URL dropped us. The first rung
     REPLACES the entry we arrived on (so no ghost of the raw URL survives, and
     an unrecognised path is corrected here rather than rendered as itself); the
     rest are pushed on top. */
  useEffect(() => {
    if (seeded.current) return;
    seeded.current = true;
    const here = parseRoute(window.location.pathname);
    const ladder = [...ancestorsOf(here), here];
    const bottom = ladder[0]!;
    window.history.replaceState(bottom, "", pathOf(bottom));
    for (const rung of ladder.slice(1)) {
      window.history.pushState(rung, "", pathOf(rung));
    }
  }, []);

  /* Back and Forward read the address bar rather than the pushed state: the
     seeded entries and the entries a person made are then handled by one path,
     and an entry this app never pushed still resolves rather than throwing. */
  useEffect(() => {
    const onPop = () => setRoute(parseRoute(window.location.pathname));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const showEcho = useCallback((msg: string) => {
    setEcho(null);
    // One frame, so a repeat of the same message re-triggers the animation.
    requestAnimationFrame(() => setEcho(msg));
    window.setTimeout(() => setEcho(null), 4600);
  }, []);

  const items = useMemo<PaletteItem[]>(() => {
    const rows: PaletteItem[] = SURFACES.map((s) => ({
      id: s.id,
      label: s.label,
      note: s.note,
      group: DEPTH_LABELS[s.depth],
      href: pathOf({ surface: s.id, subject: null }),
      aka: s.aka,
    }));
    rows.push({
      id: "line",
      label: "The Line",
      note: "the same estate, in your pocket",
      group: ELSEWHERE,
      href: "/line.html",
      away: true,
      aka: "phone mobile pocket thread morning desk push",
    });
    return rows;
  }, []);

  /* Each rung has one canonical room, because the dial is a *place* control and
     a rung that landed somewhere different each time would not be one. Rung 2 is
     the district room — the archetypal room, and the only depth-2 surface the
     ladder above it actually passes through. Clicking the rung you are already
     on does nothing rather than re-entering the surface. */
  const onDepth = useCallback(
    (d: Depth) => {
      if (d === def.depth) return;
      goTo(d === 0 ? ROOT.id : d === 1 ? "terrace" : d === 2 ? "district" : "undercroft");
    },
    [def.depth, goTo],
  );

  const breadcrumb = useMemo(() => {
    const rungs = ancestorsOf(route)
      // The root is the mark on the rail, not a crumb — every trail would open
      // with the same word otherwise.
      .filter((r) => r.surface !== ROOT.id)
      .map((r) => ({ label: surfaceOf(r.surface).label, onClick: () => go(r) }));
    return [...rungs, { label: def.label }];
  }, [route, def.label, go]);

  return (
    <>
      <Background intensity={def.intensity} />

      {route.surface === "still" ? (
        // Depth 0 has no chrome, because it *is* the chrome (D6 §2).
        <StillSurface onDescend={() => goTo("terrace")} />
      ) : (
        <Shell
          depth={def.depth}
          onDepth={onDepth}
          breadcrumb={breadcrumb}
          echo={echo}
          onUndo={() => showEcho("undone")}
          onPalette={() => setPaletteOpen(true)}
          onLeave={() => endSession("left")}
        >
          {route.surface === "terrace" && (
            <TerraceSurface
              onOpenDistrict={(code) => goTo("district", code)}
              onEcho={showEcho}
            />
          )}
          {route.surface === "district" && (
            <DistrictSurface
              // P08 is the district the room fixture describes, and it is what
              // this surface has always opened on. W replaces the fallback with
              // the estate's own first district; it is not a value invented here.
              code={route.subject ?? "P08"}
              onOpenHall={() => goTo("hall")}
              onOpenDossier={(id) => goTo("dossier", id)}
              onEcho={showEcho}
            />
          )}
          {route.surface === "dossier" && <DossierSurface onEcho={showEcho} />}
          {route.surface === "boardroom" && <BoardroomSurface onEcho={showEcho} />}
          {route.surface === "study" && <StudySurface onEcho={showEcho} />}
          {route.surface === "glasshouse" && <GlasshouseSurface onEcho={showEcho} />}
          {route.surface === "undercroft" && <UndercroftSurface onEcho={showEcho} />}
          {route.surface === "library" && <LibrarySurface onEcho={showEcho} />}
          {route.surface === "bridges" && <BridgesSurface onEcho={showEcho} />}
          {route.surface === "talent" && <TalentSurface onEcho={showEcho} />}
          {route.surface === "gallery" && <GallerySurface onEcho={showEcho} />}
          {route.surface === "standup" && (
            <StandupSurface
              onOpenTray={() => goTo("tray")}
              onOpenDossier={(id) => goTo("dossier", id)}
              onEcho={showEcho}
            />
          )}
          {route.surface === "tray" && <TraySurface onEcho={showEcho} />}
          {route.surface === "hall" && <HallSurface onEcho={showEcho} />}
        </Shell>
      )}

      {paletteOpen && (
        <Palette
          items={items}
          // The row's own `href` is parsed rather than its id trusted: the link
          // a person could copy and the place clicking it goes are then the same
          // fact, and they cannot drift apart.
          onGo={(item) => go(parseRoute(new URL(item.href, window.location.origin).pathname))}
          onClose={() => setPaletteOpen(false)}
        />
      )}
    </>
  );
}
