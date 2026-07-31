import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { useEffect } from "react";
import { act, cleanup, fireEvent, render, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * R-4 part L — the fetch lifecycle.
 *
 * The surfaces are about to stop reading module constants and start reading a
 * network, and before this round **none of them could survive an empty or a
 * failed response**. This file holds the five properties that fix costs, and it
 * is written as a set of *behaviours under an empty collection* rather than as
 * unit tests of the new components, because the components were never the risky
 * part — the seven surfaces that crash before render were.
 *
 * How the empty case is produced: every fixture module is mocked here so that
 * exactly one collection comes back `[]` and everything else is the real
 * fixture. That is the shape a first-day tenant's response actually has — a
 * populated estate with one empty list in it — and it needs no API wiring,
 * which belongs to part W.
 *
 * | | Held here by |
 * |---|---|
 * | L1 | seven surfaces render an empty collection instead of throwing, plus a scan that stops the assertion coming back |
 * | L2 | the empty state is prose, and never a fabricated figure |
 * | L3 | the failure state is legibly *not* the empty state — different words, different material, and a retry |
 * | L4 | a throwing surface is caught, is not swallowed, and does not take its siblings with it |
 * | L5 | the pending state is the surface's own structure; no spinner exists to reach for |
 */

/* --------------------------------------------------------------------------
   The empty responses. `vi.mock` is hoisted, so these run before any import
   below; each keeps the real module and empties one collection.
   -------------------------------------------------------------------------- */

vi.mock("../src/fixtures/estate", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  TRAY: [],
}));
vi.mock("../src/fixtures/decisions", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  PROPOSITIONS: [],
}));
vi.mock("../src/fixtures/people", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  DOSSIERS: [],
}));
vi.mock("../src/fixtures/glasshouse", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  SCENARIOS: [],
}));
vi.mock("../src/fixtures/library", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  DOCS: [],
}));
vi.mock("../src/fixtures/gallery", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  SEASONS: [],
}));
vi.mock("../src/fixtures/talent", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  CANDIDATES: [],
}));

/* --------------------------------------------------------------------------
   The empty responses, part W edition.

   As each of the seven stops reading a module constant and starts reading the
   network, emptying its fixture stops producing the empty case — the surface
   simply ignores the fixture. So a wired surface gets its endpoint mocked to
   an empty response here instead, and the fixture mock above stays for the
   ones that are still unwired. The assertions below wait rather than reading
   synchronously, which holds for both: a surface that renders its empty state
   on the first pass satisfies a `waitFor` immediately.

   Add one line per surface as it is wired. The Tray is the first.
   -------------------------------------------------------------------------- */

vi.mock("../src/api/trays", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchTrayList: () => Promise.resolve([]),
}));

/* The Boardroom reads three collections; the empty case is all three empty.
   `fetchBusinessKpis` is mocked too because an unmocked one reaches axios and
   turns this file's empty case into a *failure* case — which is a different
   designed state and would pass this test for the wrong reason. */
vi.mock("../src/api/strategy", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchBusinessKpis: () => Promise.resolve([]),
}));
vi.mock("../src/api/tenant", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchRecords: () => Promise.resolve([]),
}));

/* The Glasshouse: an estate that has never run a twin. */
vi.mock("../src/api/twin", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchScenarios: () => Promise.resolve([]),
}));

/* The Library: nothing has been uploaded and nothing has been written. */
vi.mock("../src/api/library", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchDocuments: () => Promise.resolve([]),
}));

/* The Dossier: nobody has been hired. `fetchEntities` is the roster read, and
   emptying it is the whole empty case — the dossier itself is never requested,
   because there is no colleague to request one for. */
vi.mock("../src/api/talent", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchEntities: () => Promise.resolve([]),
}));

/* The Talent Office reads three seams, not one. Part W wired it to E4's brief
   and past-case reads, and `fetchEntities` moved to `api/entities` — so mocking
   only `api/talent` left two of the three reaching axios, and the surface drew
   its *failure* state while this file asserted its *empty* one. Both are
   designed and they are not interchangeable: "no candidates came back" and "we
   could not ask" are different sentences, and a test that accepts either is
   testing neither. */
vi.mock("../src/api/talentBrief", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  /* The empty case is the SHAPE with nothing in it, not `[]`. Both reads answer
     an object carrying its own `absent` list, and returning a bare array here
     crashed `Office` on `briefs.briefs.length` — a mock that is the wrong shape
     tests the surface against a response the server cannot send. */
  fetchBriefs: () => Promise.resolve({ briefs: [], absent: [] }),
  fetchPastCases: () =>
    Promise.resolve({
      as_of: "2026-07-31T00:00:00Z",
      cases: [],
      replayable_means: "a case is replayable when the twin can materialise its window",
      max_window_days: 30,
      absent: [],
    }),
}));

vi.mock("../src/api/entities", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchEntities: () => Promise.resolve([]),
}));

/* The Gallery reads four things and every one of them is empty on a company
   with no history. `fetchSeasonMaterial` is mocked whole rather than through
   its two parts: it composes `fetchRecords` and `fetchKpiHistory`, and the
   second would otherwise reach axios and turn this file's *empty* case into a
   *failure* case — a different designed state that would pass for the wrong
   reason. The spread keeps `firstMeasurableOn`, which is a pure derivation the
   surface still needs. */
vi.mock("../src/api/gallery", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchSeasonMaterial: () =>
    Promise.resolve({
      resolutions: [],
      history: { from: "2026-05-02", to: "2026-07-31", series: [] },
    }),
  fetchAlumni: () => Promise.resolve([]),
  fetchReviewsDue: () => Promise.resolve([]),
}));

import { Empty } from "../src/lifecycle/Empty";
import { Failed } from "../src/lifecycle/Failed";
import { Bar, Lines, Scaffold } from "../src/lifecycle/Scaffold";
import { SurfaceBoundary } from "../src/lifecycle/SurfaceBoundary";
import { useChoice } from "../src/lifecycle/useChoice";
import { UNANSWERED, useResource } from "../src/lifecycle/useResource";

import { BoardroomSurface } from "../src/surfaces/BoardroomSurface";
import { DossierSurface } from "../src/surfaces/DossierSurface";
import { GallerySurface } from "../src/surfaces/GallerySurface";
import { GlasshouseSurface } from "../src/surfaces/GlasshouseSurface";
import { LibrarySurface } from "../src/surfaces/LibrarySurface";
import { TalentSurface } from "../src/surfaces/TalentSurface";
import { TraySurface } from "../src/surfaces/TraySurface";

const SRC = path.resolve(__dirname, "..", "src");

function walk(dir: string, match: RegExp): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) return walk(full, match);
    return match.test(full) ? [full] : [];
  });
}

/** Comments explain what a file deliberately does *not* do, and several of the
 *  L1 fixes carry the old crashing line in a comment so a reader knows what was
 *  wrong. A scan that cannot tell an explanation from code punishes that. */
const strip = (source: string): string =>
  source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

beforeEach(() => {
  /* jsdom ships no `matchMedia`; the Library asks it about reduced motion
     before scrolling a citation into view. */
  if (typeof window.matchMedia !== "function") {
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
  }
});

/* ==========================================================================
   L1 · the crashing initialisers
   ========================================================================== */

/** Surface, and one phrase from the copy it is now able to reach. */
const SEVEN: [string, () => JSX.Element, string][] = [
  ["The Tray", () => <TraySurface onEcho={vi.fn()} />, "without needing you"],
  ["The Boardroom", () => <BoardroomSurface onEcho={vi.fn()} />, "tabled nothing this sitting"],
  ["The Dossier", () => <DossierSurface onEcho={vi.fn()} />, "not hired anyone yet"],
  ["The Glasshouse", () => <GlasshouseSurface onEcho={vi.fn()} />, "Nothing has been tried in here"],
  ["The Library", () => <LibrarySurface onEcho={vi.fn()} />, "has read nothing yet"],
  /* Was "no seasons behind it yet". Part W found that **the platform stores no
     season object at all**, so the surface no longer counts them — the walk is
     the adopted decisions, and its empty state is about those. */
  ["The Gallery", () => <GallerySurface onEcho={vi.fn()} />, "Nothing has been decided here yet"],
  /* Was "No candidates have come back". Part W wired the room to E4's brief
     read, and a brief is the precondition for a shortlist — so the empty state
     of this room is now about the ask, not about the answers. */
  ["The Talent Office", () => <TalentSurface onEcho={vi.fn()} />, "have not asked for a colleague yet"],
];

describe("L1 — an empty collection is a state, not a TypeError", () => {
  it.each(SEVEN)("%s renders", (_name, mount) => {
    /* Without the fix this throws inside `useState`, before React has produced
       a single node — which is why it cannot be caught by an empty-state branch
       further down the component and had to be fixed at the initialiser. */
    expect(() => render(mount())).not.toThrow();
  });

  it.each(SEVEN)("%s says what the emptiness means", async (_name, mount, phrase) => {
    /* `waitFor` rather than a synchronous read, for the reason given beside
       the API mocks above: a wired surface paints its scaffold first (D7 §3.1)
       and its empty state on the next tick, and an unwired one satisfies this
       on the first pass. One assertion covers both sides of part W. */
    const { container } = render(mount());
    await waitFor(() => expect(container.textContent).toContain(phrase));
  });

  it("the Tray reaches the copy it already carried", async () => {
    /* The sharpest case in the readiness report: `TraySurface` has said
       "Nothing needs you." since it was written, eleven lines below the
       `TRAY[0]!` that stopped it ever being rendered. */
    const { container } = render(<TraySurface onEcho={vi.fn()} />);
    await waitFor(() =>
      expect(container.querySelector(".tr-title")?.textContent).toBe("Nothing needs you."),
    );
  });

  it("the Tray prints no figure where it has no figure", async () => {
    /* `Math.min()` of nothing is `Infinity`. "soonest Infinitym" is a number
       nobody measured, which §7.1 forbids more strictly than it forbids a
       blank. (It was `Math.max()` and "oldest waited -Infinitym" before the
       Tray was wired; the trap is the same one either way round.) */
    const { container } = render(<TraySurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".tr-title")).not.toBeNull());
    expect(container.textContent).not.toContain("Infinity");
    expect(container.textContent).not.toContain("NaN");
    expect(container.querySelector(".tr-head-meta")).toBeNull();
  });

  it("no surface asserts into a module collection at index zero", () => {
    /* The regression gate. `noUncheckedIndexedAccess` is on precisely to catch
       `TRAY[0]!`, and the `!` suppresses exactly the check it was added for, so
       nothing but a scan can stop it coming back.
       Scoped to SCREAMING_CASE identifiers — those are the module-level
       collections that become a network response. A guarded local like
       `e.touches[0]!` is a different thing and is left alone. */
    const offenders: string[] = [];
    for (const dir of ["surfaces", "line"]) {
      for (const file of walk(path.join(SRC, dir), /\.tsx?$/)) {
        const source = strip(readFileSync(file, "utf8"));
        for (const hit of source.matchAll(/\b([A-Z][A-Z0-9_]*)\s*\[\s*0\s*\]\s*!/g)) {
          offenders.push(`${path.relative(SRC, file)}: ${hit[1]}[0]!`);
        }
      }
    }
    expect(
      offenders,
      `Derive from the collection instead — see src/lifecycle/useChoice.ts:\n  ${offenders.join("\n  ")}`,
    ).toEqual([]);
  });
});

describe("useChoice — the idiom the seven now share", () => {
  const rows = [
    { id: "a", best: false },
    { id: "b", best: true },
  ];

  it("returns undefined rather than throwing on an empty collection", () => {
    const { result } = renderHook(() => useChoice([] as typeof rows, (r) => r.id));
    expect(result.current.chosen).toBeUndefined();
    expect(result.current.chosenId).toBeUndefined();
  });

  it("opens on the preferred row, not on index zero", () => {
    const { result } = renderHook(() => useChoice(rows, (r) => r.id, (r) => r.best));
    expect(result.current.chosenId).toBe("b");
  });

  it("falls back to the head of the collection with no preference", () => {
    const { result } = renderHook(() => useChoice(rows, (r) => r.id));
    expect(result.current.chosenId).toBe("a");
  });

  it("re-derives when the chosen row leaves the collection", () => {
    /* The second bug the assertion was hiding. With the id in state and a
       `?? DOSSIERS[0]!` on the read, a fetch that dropped the chosen row put a
       *different* colleague's dossier under the selection the person made. */
    const { result, rerender } = renderHook(({ items }) => useChoice(items, (r) => r.id), {
      initialProps: { items: rows },
    });
    act(() => result.current.choose("b"));
    expect(result.current.chosenId).toBe("b");

    rerender({ items: rows.filter((r) => r.id !== "b") });
    expect(result.current.chosenId).toBe("a");
  });
});

/* ==========================================================================
   L2 · the empty state
   ========================================================================== */

describe("L2 — a surface with nothing to show says so in prose", () => {
  const mount = () =>
    render(
      <Empty
        title="Nothing needs you."
        body="Nothing has been escalated, and work is still running."
      />,
    );

  it("renders the title and the reason", () => {
    const { container } = mount();
    expect(container.textContent).toContain("Nothing needs you.");
    expect(container.textContent).toContain("Nothing has been escalated");
  });

  it("invents no figure and draws no empty chart (§7.1, §7.3)", () => {
    const { container } = mount();
    for (const forbidden of ["₹0", "—", "0 items", "N/A", "n/a", "unknown", "null", "undefined"]) {
      expect(container.textContent).not.toContain(forbidden);
    }
    expect(container.querySelector("canvas")).toBeNull();
    expect(container.querySelector("table")).toBeNull();
    /* The only vector in the block is the icon on the mark, and it is hidden
       from the accessibility tree — nothing here is a chart with no data in it. */
    for (const svg of container.querySelectorAll("svg")) {
      expect(svg.closest('[aria-hidden="true"]')).not.toBeNull();
    }
  });

  it("carries an unlit lamp — an absence is not a fault state", () => {
    const lamp = mount().container.querySelector(".m-lamp");
    expect(lamp).not.toBeNull();
    expect(lamp!.hasAttribute("data-negative")).toBe(false);
    expect(lamp!.hasAttribute("data-lit")).toBe(false);
  });

  it("offers an act only when the caller gives it one", () => {
    expect(mount().container.querySelector("button")).toBeNull();

    cleanup();
    const onClick = vi.fn();
    const { container } = render(
      <Empty title="Nothing here." body="Not yet." act={{ label: "Upload one", onClick }} />,
    );
    const button = container.querySelector("button");
    expect(button?.textContent).toBe("Upload one");
    fireEvent.click(button!);
    expect(onClick).toHaveBeenCalledOnce();
  });
});

/* ==========================================================================
   L3 · the failure state
   ========================================================================== */

describe("L3 — a failure that could be mistaken for calm is the bug", () => {
  it("says, in words, that this is not an empty room", () => {
    const { container } = render(<Failed what="the Tray" onRetry={vi.fn()} />);
    expect(container.textContent).toContain("could not load the Tray");
    expect(container.textContent).toContain("not an empty the Tray");
    expect(container.textContent).toContain("Nothing has been changed");
  });

  it("is a different material from empty, not a differently coloured one", () => {
    /* The whole point of L3. `bridges.css` teaches the estate two textures —
       a dot lattice for "never known", a repair hatch for "broken" — and the
       two states inherit them rather than differing only in a word nobody
       reads or a hue nobody can see. */
    const failed = render(<Failed what="the Tray" />).container.firstElementChild!;
    cleanup();
    const empty = render(<Empty title="Nothing." body="Nothing at all." />).container
      .firstElementChild!;

    expect(failed.getAttribute("data-state")).toBe("failed");
    expect(empty.getAttribute("data-state")).toBe("empty");
    expect(failed.className).not.toBe(empty.className);
  });

  it("lights the negative lamp and prints the word beside it (§4)", () => {
    const { container } = render(<Failed what="the Tray" />);
    expect(container.querySelector(".m-lamp[data-negative]")).not.toBeNull();
    expect(container.querySelector(".t-eyebrow")?.textContent).toBe("COULD NOT LOAD");
  });

  it("offers a retry, and fires it", () => {
    const onRetry = vi.fn();
    const { container } = render(<Failed what="the Tray" onRetry={onRetry} />);
    const button = container.querySelector("button")!;
    expect(button.textContent).toContain("Try again");
    fireEvent.click(button);
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("renders no button at all when there is nothing to retry", () => {
    /* Never a dead control. This is the screen where trust is already thin. */
    const { container } = render(<Failed what="the Tray" />);
    expect(container.querySelector("button")).toBeNull();
  });

  it("keeps the machine's own words without letting them be the message", () => {
    const { container } = render(<Failed what="the Tray" reason="504 from /api/v1/trays" />);
    expect(container.querySelector(".lc-reason")?.textContent).toBe("504 from /api/v1/trays");
    expect(container.querySelector(".lc-title")?.textContent).not.toContain("504");
  });

  it("announces itself once, politely", () => {
    const { container } = render(<Failed what="the Tray" />);
    expect(container.firstElementChild!.getAttribute("role")).toBe("status");
  });
});

/* ==========================================================================
   L4 · the boundary
   ========================================================================== */

function Detonate({ armed }: { armed: boolean }): JSX.Element {
  if (armed) throw new Error("cost is not defined");
  return <p>the room</p>;
}

describe("L4 — one surface cannot take the shell down", () => {
  /* React logs a caught error itself, so console.error is silenced and then
     inspected rather than left to fill the run's output. */
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  it("catches the throw and keeps everything outside it standing", () => {
    const { container } = render(
      <div>
        <p>the rail</p>
        <SurfaceBoundary surface="The Tray">
          <Detonate armed />
        </SurfaceBoundary>
      </div>,
    );
    expect(container.textContent).toContain("the rail");
    expect(container.textContent).toContain("The Tray stopped part-way through");
  });

  it("does not swallow it", () => {
    const onError = vi.fn();
    render(
      <SurfaceBoundary surface="The Tray" onError={onError}>
        <Detonate armed />
      </SurfaceBoundary>,
    );

    // Trail one: the console, with the surface named and the original error.
    const logged = (console.error as unknown as { mock: { calls: unknown[][] } }).mock.calls;
    expect(logged.some((c) => String(c[0]).includes("The Tray threw while rendering"))).toBe(true);
    // Trail two: the caller's own reporter.
    expect(onError).toHaveBeenCalledOnce();
  });

  it("prints the message on screen rather than a generic apology", () => {
    const { container } = render(
      <SurfaceBoundary surface="The Tray">
        <Detonate armed />
      </SurfaceBoundary>,
    );
    expect(container.querySelector(".lc-reason")?.textContent).toBe("cost is not defined");
  });

  it("survives a throw that is not an Error", () => {
    render(
      <SurfaceBoundary surface="The Tray">
        <ThrowString />
      </SurfaceBoundary>,
    );
    // Nothing above threw a second time; the boundary rendered.
    expect(document.body.textContent).toContain("The Tray stopped");
  });

  it("retries the child, and says so again while it is still broken", () => {
    /* The retry is a real second attempt at the subtree — the boundary bumps a
       key so the child remounts rather than being handed back the state that
       just threw. A still-broken room gets the same honest answer instead of a
       button that appears to do nothing. */
    let armed = true;
    function Room() {
      if (armed) throw new Error("once");
      return <p>the room</p>;
    }

    const { container } = render(
      <SurfaceBoundary surface="The Tray">
        <Room />
      </SurfaceBoundary>,
    );
    expect(container.textContent).toContain("The Tray stopped");

    fireEvent.click(container.querySelector("button")!);
    expect(container.textContent).toContain("The Tray stopped");

    armed = false;
    fireEvent.click(container.querySelector("button")!);
    expect(container.textContent).toContain("the room");
  });

  it("mounts the child afresh on retry", () => {
    /* React unmounts the failed subtree, so a retry is a clean mount and the
       boundary needs no key to make it one — the property the docstring claims,
       held here rather than assumed. */
    const mounts: string[] = [];
    let armed = true;
    function Room() {
      useEffect(() => {
        mounts.push("mounted");
      }, []);
      if (armed) throw new Error("once");
      return <p>the room</p>;
    }

    const { container } = render(
      <SurfaceBoundary surface="The Tray">
        <Room />
      </SurfaceBoundary>,
    );
    expect(mounts).toEqual([]);

    armed = false;
    fireEvent.click(container.querySelector("button")!);
    expect(mounts).toEqual(["mounted"]);
  });

  it("clears when the surface it guards changes", () => {
    /* Otherwise a crash in the Tray keeps rendering over every room you visit
       afterwards, and one broken surface becomes a broken product. */
    const { container, rerender } = render(
      <SurfaceBoundary surface="The Tray">
        <Detonate armed />
      </SurfaceBoundary>,
    );
    expect(container.textContent).toContain("The Tray stopped");

    rerender(
      <SurfaceBoundary surface="The Library">
        <Detonate armed={false} />
      </SurfaceBoundary>,
    );
    expect(container.textContent).toBe("the room");
  });
});

function ThrowString(): JSX.Element {
  // eslint-disable-next-line @typescript-eslint/no-throw-literal
  throw "no message on this one";
}

/* ==========================================================================
   L5 · scaffold, then hydrate
   ========================================================================== */

describe("L5 — the pending state is layout, never a spinner", () => {
  it("draws the surface's own structure in the skeleton sweep", () => {
    const { container } = render(
      <Scaffold label="The Tray">
        <Bar width="sm" tall />
        <Lines n={3} />
      </Scaffold>,
    );
    expect(container.querySelectorAll(".vh-skeleton").length).toBe(4);
    expect(container.querySelector(".lc-bar[data-tall]")).not.toBeNull();
    expect(container.querySelector('[role="progressbar"]')).toBeNull();
  });

  it("tells a screen reader once, and hides the bars from it", () => {
    const { container } = render(
      <Scaffold label="The Tray">
        <Lines n={4} />
      </Scaffold>,
    );
    const status = container.querySelector('[role="status"]');
    expect(status?.textContent).toBe("The Tray is still arriving.");
    expect(container.querySelector('[aria-hidden="true"] .lc-bar')).not.toBeNull();
  });

  it("has no spinner anywhere to reach for", () => {
    /* D7 §3.1 names the Glasshouse the only surface permitted a visible loading
       state. The enforcement is that the shape does not exist: no rotation
       keyframe and no progressbar under any surface, the Line, or the lifecycle
       module itself. */
    const offenders: string[] = [];

    for (const dir of ["surfaces", "line", "lifecycle"]) {
      for (const file of walk(path.join(SRC, dir), /\.(tsx?|css)$/)) {
        const rel = path.relative(SRC, file);
        const source = strip(readFileSync(file, "utf8"));

        if (/progressbar|spinner/i.test(source)) offenders.push(`${rel}: a spinner`);

        for (const at of source.matchAll(/@keyframes\s+[\w-]+\s*\{/g)) {
          let depth = 1;
          let i = at.index! + at[0].length;
          const start = i;
          while (i < source.length && depth > 0) {
            if (source[i] === "{") depth += 1;
            else if (source[i] === "}") depth -= 1;
            i += 1;
          }
          const body = source.slice(start, i - 1);
          if (/rotate|turn\b|360deg/.test(body)) offenders.push(`${rel}: a rotating @keyframes`);
        }
      }
    }

    expect(offenders, offenders.join("\n  ")).toEqual([]);
  });
});

describe("useResource — one read, three phases", () => {
  it("starts pending, without having drawn anything", () => {
    const { result } = renderHook(() => useResource(() => new Promise<string>(() => undefined)));
    expect(result.current.phase).toBe("pending");
  });

  it("reaches ready with the value", async () => {
    const { result } = renderHook(() => useResource(() => Promise.resolve("estate")));
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    expect(result.current).toMatchObject({ phase: "ready", value: "estate" });
  });

  it("reaches failed with the thrown words, and retries back to ready", async () => {
    let attempts = 0;
    const load = () => {
      attempts += 1;
      return attempts === 1 ? Promise.reject(new Error("504")) : Promise.resolve("estate");
    };

    const { result } = renderHook(() => useResource(load));
    await waitFor(() => expect(result.current.phase).toBe("failed"));
    expect(result.current).toMatchObject({ phase: "failed", reason: "504" });

    act(() => {
      if (result.current.phase === "failed") result.current.retry();
    });
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    expect(attempts).toBe(2);
  });

  it("says something a person can read when the failure carries no words", async () => {
    const { result } = renderHook(() => useResource(() => Promise.reject(new Error(""))));
    await waitFor(() => expect(result.current.phase).toBe("failed"));
    expect(result.current).toMatchObject({ reason: UNANSWERED });
  });

  it("does not re-read on every render", async () => {
    /* Callers pass an inline arrow. Depending on it would put the surface in a
       fetch loop that presents as a slow network. */
    const load = vi.fn(() => Promise.resolve("estate"));
    const { result, rerender } = renderHook(() => useResource(load));
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    rerender();
    rerender();
    expect(load).toHaveBeenCalledOnce();
  });
});

/**
 * L4's other half: the boundary has to be **mounted**.
 *
 * The independent verification pass of this round found `SurfaceBoundary`
 * built, correct, tested — and reached by nothing. `grep` returned its own
 * definition and the barrel export, so a TypeError in any of the eighteen rooms
 * still took the whole tree down, which is exactly the failure its docstring
 * describes. A component that protects nothing passes every test written about
 * the component.
 *
 * These are source assertions rather than renders, and that is a deliberate
 * trade: mounting `Prototype` needs a session and mounting `LineApp` needs the
 * push state machine, so a render test here would mostly exercise scaffolding.
 * What they cannot prove — that the boundary *contains* a throw — is proven by
 * the behavioural tests above. What they do prove is the thing that was
 * actually wrong: that both entry points reach for it at all.
 */
describe("the boundary guards the real entry points", () => {
  const APP = path.resolve(__dirname, "..", "src");

  const sourceOf = (rel: string): string =>
    readFileSync(path.join(APP, rel), "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\{\/\*[\s\S]*?\*\/\}/g, "")
      .replace(/^\s*\/\/.*$/gm, "");

  it("wraps the estate's surface switch, inside the Shell", () => {
    const src = sourceOf("app/Prototype.tsx");
    expect(src).toMatch(/import\s*\{[^}]*SurfaceBoundary[^}]*\}\s*from\s*"\.\.\/lifecycle"/);

    // Inside the Shell, not around it: a room that throws must lose the room
    // and keep the rail, the palette and the way out.
    const shell = src.slice(src.indexOf("<Shell"), src.indexOf("</Shell>"));
    expect(shell, "the boundary sits outside <Shell>, so a throw takes the way out with it")
      .toContain("<SurfaceBoundary");
  });

  it("guards depth 0 separately, because there is no shell there to survive", () => {
    const src = sourceOf("app/Prototype.tsx");
    const stillAt = src.indexOf("<StillSurface");
    expect(stillAt).toBeGreaterThan(-1);
    // The nearest opening boundary before the Still surface must not be the
    // Shell's — depth 0 renders no Shell at all (D6 §2).
    expect(src.lastIndexOf("<SurfaceBoundary", stillAt)).toBeGreaterThan(-1);
  });

  it("guards the Line's tab body", () => {
    const src = sourceOf("line/LineApp.tsx");
    expect(src).toMatch(/import\s*\{[^}]*SurfaceBoundary[^}]*\}\s*from\s*"\.\.\/lifecycle"/);

    /* The Line has no palette, no depth ladder, and on an installed PWA no
       address bar — so a white screen there has no way out at all. */
    const swap = src.slice(src.indexOf("ln-swap"), src.indexOf("</main>"));
    expect(swap, "the Line's tab body is unguarded").toContain("<SurfaceBoundary");
  });

  it("passes a surface identity, so a latched error cannot follow you", () => {
    /* `componentDidUpdate` clears on a `surface` change. A boundary mounted
       with a constant string would latch: one broken room and every room after
       it shows the same failure. */
    let checked = 0;
    for (const rel of ["app/Prototype.tsx", "line/LineApp.tsx"]) {
      const src = sourceOf(rel);
      const mounts = [...src.matchAll(/<SurfaceBoundary\b([^>]*)>/g)];
      expect(mounts.length, `${rel} mounts no boundary`).toBeGreaterThan(0);

      for (const mount of mounts) {
        // noUncheckedIndexedAccess: a matched group is `string | undefined`.
        const props = mount[1] ?? "";
        checked += 1;
        /* Matched in BOTH forms on purpose. An earlier version of this test
           read only `surface={…}`, so mutating a mount to `surface="a room"`
           matched nothing and the loop passed over an empty set — a vacuous
           test that reported the property it was not checking. */
        const expression = /surface=\{([^}]+)\}/.exec(props);
        const literal = /surface=("[^"]*"|'[^']*')/.exec(props);

        expect(literal?.[1] ?? null,
          `${rel} pins the boundary to a constant name, so one broken room latches onto every room after it`)
          .toBeNull();
        expect(expression?.[1]?.trim(),
          `${rel} mounts a boundary with no surface identity at all`)
          .toBeTruthy();
      }
    }
    // The scan is worthless if it matched nothing.
    expect(checked).toBeGreaterThanOrEqual(3);
  });
});
