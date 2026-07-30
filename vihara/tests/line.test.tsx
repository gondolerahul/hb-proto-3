import { readFileSync } from "node:fs";
import path from "node:path";
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TRAY } from "../src/fixtures/estate";
import { MORNING } from "../src/fixtures/morning";
import { READINGS, type DeskDial } from "../src/fixtures/pocket";
import { STEP_UP, THREAD } from "../src/fixtures/thread";
import { MorningStorySurface, UNVOICED } from "../src/line/MorningStorySurface";
import { PocketDesk } from "../src/line/PocketDesk";
import { ThreadSurface } from "../src/line/ThreadSurface";
import { TraySurface } from "../src/surfaces/TraySurface";

/**
 * R-3c C4 — the Line's load-bearing invariant.
 *
 * **The Thread's certified section is `TraySurface`. The component, mounted.**
 * If it were a phone-shaped reimplementation, a certified act would be *drawn*
 * in the place it is read and *approved* somewhere else, and the step-up bar
 * beside it would be a picture of a security control. That is the exact class
 * of defect that makes a control decorative, so it is held here rather than by
 * convention.
 *
 * Four assertions, because a copy defeats any one of them alone:
 *
 *  1. **Module identity.** Stand a fake in for `src/surfaces/TraySurface` and
 *     the Thread renders the fake. A reimplementation would not notice.
 *  2. **Structural identity.** The `.tr` subtree the Line renders is byte-equal
 *     to the one the desk renders — so a `compact` prop, or one extra wrapper
 *     class, or any *drifting* fork fails. Note what this one does **not**
 *     catch: a byte-perfect copy emits byte-identical markup and passes here.
 *     That is what 1 and 3 are for, and it is why the suite needs all four —
 *     mutation-tested, not assumed.
 *  3. **The source imports it and holds none of its markup.**
 *  4. **`thread.css` may only give it geometry.** This is the one that erodes
 *     quietly: nobody forks the component, someone just makes the gold "sit
 *     better on the phone", and the two surfaces stop showing the same act.
 *
 * The rest of the file holds the Thread's own content rules — the §7.1 absence
 * that must render as nothing, and the ceremony that must name the act it
 * authorises and no other.
 */

const SRC = path.resolve(__dirname, "..", "src");

/** Comments stripped: the prose in this surface names the Tray's own classes on
 *  purpose, and a source scan that cannot tell a citation from an implementation
 *  is a scan that punishes explaining yourself. */
const THREAD_TSX = readFileSync(path.join(SRC, "line", "ThreadSurface.tsx"), "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/^\s*\/\/.*$/gm, "");

/** Comments stripped, and at-rule wrappers flattened: `@media (…) {` opens a
 *  brace the rule scan below would otherwise mistake for a selector's, which
 *  would let a colour change hide from this file by being written inside a
 *  breakpoint. Dropping the opener leaves the rules it contained at top level
 *  and one orphan `}` the scan ignores. */
const THREAD_CSS = readFileSync(path.join(SRC, "line", "thread.css"), "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/@(?:media|supports|container|layer)[^{]*\{/g, "");

/** The one certified card in the tray — the act the ceremony is bound to. */
const CERTIFIED = TRAY.find((c) => c.kind === "certified")!;

afterEach(cleanup);

describe("the Thread's certified section is the Tray itself", () => {
  it("resolves to the estate's TraySurface module, not to something shaped like it", async () => {
    vi.resetModules();
    vi.doMock("../src/surfaces/TraySurface", () => ({
      TraySurface: ({ onEcho }: { onEcho: (msg: string) => void }) => (
        <button data-testid="stood-in-for-the-tray" onClick={() => onEcho("stood in")}>
          the module
        </button>
      ),
    }));

    try {
      const { ThreadSurface: Fresh } = await import("../src/line/ThreadSurface");
      const onEcho = vi.fn();
      const { container } = render(<Fresh onEcho={onEcho} />);

      const standIn = container.querySelector("[data-testid='stood-in-for-the-tray']");
      expect(
        standIn,
        "the Thread's certified block did not come from src/surfaces/TraySurface",
      ).not.toBeNull();

      // And the echo bus runs through it — the same prop the desk passes, so an
      // act taken on the phone reaches L10 by the same path it does at the desk.
      fireEvent.click(standIn as HTMLElement);
      expect(onEcho).toHaveBeenCalledWith("stood in");
    } finally {
      cleanup();
      vi.doUnmock("../src/surfaces/TraySurface");
      vi.resetModules();
    }
  });

  it("renders the Tray subtree the desk renders, to the byte", () => {
    const desk = render(<TraySurface onEcho={vi.fn()} />);
    const atTheDesk = desk.container.querySelector(".tr")?.outerHTML;
    expect(atTheDesk).toBeDefined();
    cleanup();

    const line = render(<ThreadSurface onEcho={vi.fn()} />);
    const onTheLine = line.container.querySelector(".tr")?.outerHTML;

    expect(
      onTheLine,
      "the Line's tray markup diverged from the desk's — a copy, a variant, or an extra prop",
    ).toBe(atTheDesk);
  });

  it("imports the Tray and holds none of its markup", () => {
    expect(THREAD_TSX).toMatch(
      /import\s*\{\s*TraySurface\s*\}\s*from\s*"\.\.\/surfaces\/TraySurface"/,
    );

    // A reimplementation has to write these itself; a mount cannot.
    for (const own of ["tr-card", "tr-ask", "tr-because", "tr-facts", "tr-path", "tr-raiser"]) {
      expect(THREAD_TSX, `ThreadSurface.tsx draws the Tray's own "${own}"`).not.toContain(own);
    }
  });

  it("lets thread.css give the Tray geometry and nothing else", () => {
    /* Geometry is what a 390px column legitimately owes a surface written for a
       1600px desk: the room it stands in, and the 44px touch floor. Colour, type
       and material are what "the same act, drawn the same way" means, so they are
       not on this list — and the failure message names the property, because the
       next person to reach for one will have a good reason and should be made to
       take it to tray.css instead. */
    const GEOMETRY = new Set([
      "display",
      "flex",
      "flex-direction",
      "flex-wrap",
      "align-items",
      "align-self",
      "justify-content",
      "gap",
      "row-gap",
      "column-gap",
      "grid-template-columns",
      "place-items",
      "width",
      "min-width",
      "max-width",
      "height",
      "min-height",
      "max-height",
      "overflow",
      "overflow-x",
      "overflow-y",
      "padding",
      "padding-top",
      "padding-right",
      "padding-bottom",
      "padding-left",
      "margin",
      "margin-top",
      "margin-right",
      "margin-bottom",
      "margin-left",
      "margin-inline",
    ]);

    const reaching: string[] = [];
    for (const block of THREAD_CSS.split("}")) {
      const brace = block.indexOf("{");
      if (brace === -1) continue;
      const selector = block.slice(0, brace).trim();
      if (!/\.tr(-|\b)/.test(selector)) continue;
      reaching.push(selector);

      for (const declaration of block.slice(brace + 1).split(";")) {
        const property = declaration.split(":")[0]?.trim();
        if (property === undefined || property === "") continue;
        expect(
          GEOMETRY.has(property),
          `thread.css sets "${property}" on "${selector}" — that is how the Line stops showing the same act as the desk`,
        ).toBe(true);
      }
    }

    // The scan is worthless if it matched nothing.
    expect(reaching.length).toBeGreaterThan(0);
  });
});

describe("the step-up bar", () => {
  it("names the act it authorises, read off the tray card rather than copied", () => {
    const { container } = render(<ThreadSurface onEcho={vi.fn()} />);

    expect(container.querySelector(".th-step-cmd")?.textContent).toBe(CERTIFIED.title);
    expect(container.querySelector(".th-step-ref")?.textContent).toBe(
      STEP_UP[CERTIFIED.id]!.commandRef,
    );
  });

  it("goes when the command it stands under is settled", () => {
    const { container } = render(<ThreadSurface onEcho={vi.fn()} />);
    expect(container.querySelector(".th-step")).not.toBeNull();

    const goldPath = CERTIFIED.paths.find((p) => p.rank === "certified")!;
    const button = [...container.querySelectorAll("button.tr-path")].find((b) =>
      b.textContent?.includes(goldPath.label),
    );
    expect(button, `no path button for "${goldPath.label}"`).toBeDefined();
    fireEvent.click(button as HTMLElement);

    expect(
      container.querySelector(".th-step"),
      "a ceremony left standing under an act that is already done",
    ).toBeNull();
  });

  it("says in words, not only in colour, whether this browser can raise it", () => {
    // jsdom has no PublicKeyCredential, so this render takes the honest gap
    // branch — which is the branch §7.4 exists for and the one nobody looks at.
    const { container } = render(<ThreadSurface onEcho={vi.fn()} />);
    const state = container.querySelector(".th-step-state");

    expect(state?.textContent).toBe("this phone cannot ask");
    expect(container.querySelector(".th-step .m-lamp")?.getAttribute("data-negative")).toBe("true");
  });
});

describe("the Thread's own content", () => {
  it("renders nothing at all for a story whose figure is absent", () => {
    const absent = THREAD.find((t) => t.kind === "story" && t.figure === null);
    expect(absent, "the fixture no longer carries a story with no figure").toBeDefined();

    const { container } = render(<ThreadSurface onEcho={vi.fn()} />);
    const card = [...container.querySelectorAll("article.th-card")].find(
      (c) => c.querySelector(".th-card-title")?.textContent === (absent as { title: string }).title,
    );
    expect(card).toBeDefined();

    // No figure element, and none of the shapes an invented figure would take.
    expect(card!.querySelector(".th-fig")).toBeNull();
    expect(card!.querySelector(".th-fig-val")).toBeNull();
    expect(card!.textContent).not.toMatch(/[₹$€£]/);
    for (const forbidden of ["—", "–", "n/a", "N/A", "unknown", "not available"]) {
      expect(card!.textContent).not.toContain(forbidden);
    }
  });

  it("still draws the figure where the binding produced one", () => {
    const withFigure = THREAD.find((t) => t.kind === "story" && t.figure !== null) as {
      title: string;
      figure: { value: string };
    };

    const { container } = render(<ThreadSurface onEcho={vi.fn()} />);
    const card = [...container.querySelectorAll("article.th-card")].find(
      (c) => c.querySelector(".th-card-title")?.textContent === withFigure.title,
    );

    expect(card!.querySelector(".th-fig-val")?.textContent).toBe(withFigure.figure.value);
  });

  it("puts one heading at the top of its outline, and it is the Tray's", () => {
    const { container } = render(<ThreadSurface onEcho={vi.fn()} />);
    const headings = [...container.querySelectorAll("h1")];

    expect(headings).toHaveLength(1);
    expect(headings[0]!.className).toContain("tr-title");
  });
});

/**
 * R-3c — the §7.1 absence rule on the other two Line surfaces.
 *
 * The Thread's half of this is above. These two suites exist because the
 * independent verification pass found the rule *correct in the render* on the
 * Morning Story and the Pocket Desk and *held by nothing* — the surfaces do the
 * right thing today and a regression would ship silently.
 *
 * `tests/tray_cost.test.tsx` is the precedent and the reason: a null that
 * renders as a number is the worst available bug in this product, so every
 * surface that can receive one owes a test, not a careful author.
 */

describe("the Morning Story degrades to text, and says why", () => {
  it("renders the reason in place of the voice, and no player, for an unvoiced card", () => {
    const { container } = render(<MorningStorySurface onEcho={vi.fn()} />);

    const unvoiced = MORNING.cards.filter((c) => c.audio === null);
    expect(unvoiced.length).toBeGreaterThan(0);

    const reasons = [...container.querySelectorAll(".mo-unvoiced")];
    expect(reasons).toHaveLength(unvoiced.length);

    // The reason is stated, not implied by an absence.
    for (const node of reasons) {
      expect(node.textContent?.trim()).not.toBe("");
    }

    // A degraded card offers no player at all — not a disabled one. A control
    // that cannot do its job must be absent, or the user taps it and learns
    // nothing about why nothing happened.
    expect(container.querySelectorAll(".mo-listen")).toHaveLength(
      MORNING.cards.length - unvoiced.length,
    );
    expect(container.querySelectorAll("button.mo-listen[disabled]")).toHaveLength(0);
  });

  it("names the degradation the job actually reported, never a generic apology", () => {
    const { container } = render(<MorningStorySurface onEcho={vi.fn()} />);
    const stated = container.querySelector(".mo-unvoiced")!.textContent ?? "";

    // The fixture's reason is `tts_failed`; the copy must be that reason's own
    // sentence rather than one that would fit any of the four.
    expect(MORNING.degradedReason).not.toBeNull();
    const others = (["wallet", "not_configured", "not_generated"] as const).filter(
      (r) => r !== MORNING.degradedReason,
    );
    const sentences = new Set(others.map((r) => UNVOICED[r]));
    expect(sentences.has(stated)).toBe(false);
    expect(stated).toBe(UNVOICED[MORNING.degradedReason!]);
  });
});

const DIALS = READINGS.filter((r): r is DeskDial => r.kind === "dial");

/** Comments stripped — the surface explains the absence rule in prose, and a
 *  scan that cannot tell the explanation from a violation of it is a scan that
 *  punishes writing the reason down. */
const PD_TSX = readFileSync(path.join(SRC, "line", "PocketDesk.tsx"), "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/^\s*\/\/.*$/gm, "");

describe("the Pocket Desk never invents a reading", () => {
  it("renders no figure at all where the series has no point yet", () => {
    // Narrowed to dials: only a dial carries `title`, and the young-series case
    // this rule exists for is a KPI with no point yet. `find` alone does not
    // narrow a union, so the guard is explicit.
    const absent = DIALS.find((r) => r.current === null);
    expect(absent, "no dial in the fixture exercises the absent-reading path").toBeDefined();

    const { container } = render(<PocketDesk onEcho={vi.fn()} />);
    const card = [...container.querySelectorAll(".pd-card")].find(
      (c) => c.querySelector(".pd-card-title")?.textContent === absent!.title,
    )!;

    // Not 0, not a dash, not "unknown", not a unit on its own.
    expect(card.querySelector(".pd-figure")).toBeNull();
    expect(card.querySelector(".pd-meter")).toBeNull();

    const absence = card.querySelector(".pd-absent");
    expect(absence).not.toBeNull();
    expect(absence!.textContent).not.toMatch(/(^|\s)(0|—|-|n\/a|unknown)(\s|$)/i);
  });

  it("routes every null reading to an absence, on the figure path as well as the dial", () => {
    /* The behavioural test above covers the dial, because the dial is the only
       kind the fixture currently has a null for. Mutation-testing it proved the
       gap: replacing the *figure* branch's `<Absent/>` with a dash passed every
       test in this file.

       So the rule is also asserted at the source. Both null branches must reach
       `<Absent>` — or, on the shelf, render literally nothing — and neither may
       fall back to a glyph. It is a weaker instrument than a render, and it is
       the strongest one available until a figure with no aggregate exists to
       render. */
    const sites = [...PD_TSX.matchAll(/current === null/g)];
    expect(
      sites.length,
      "the null-reading scan matched nothing — PocketDesk stopped guarding, or the guard was renamed",
    ).toBeGreaterThanOrEqual(3);

    for (const site of sites) {
      const after = PD_TSX.slice(site.index!, site.index! + 160);
      expect(
        /<Absent|\?\s*null|return null/.test(after),
        `a "current === null" branch in PocketDesk.tsx does not reach <Absent> or render nothing:\n${after.split("\n").slice(0, 3).join("\n")}`,
      ).toBe(true);
      // The thing the rule exists to forbid, stated as itself.
      expect(
        /["'>](\s*)(0|—|–|-|N\/A|n\/a|unknown)(\s*)["'<]/.test(after),
        "a null reading fell back to a glyph — §7.1 forbids 0, a dash and \"unknown\" alike",
      ).toBe(false);
    }
  });

  it("keeps a counted zero and an absent reading visibly different", () => {
    const zero = DIALS.find((r) => r.current !== null && r.current.value === 0);
    expect(zero, "no dial in the fixture exercises the counted-zero path").toBeDefined();

    const { container } = render(<PocketDesk onEcho={vi.fn()} />);
    const card = [...container.querySelectorAll(".pd-card, .pd-shelf-row")].find(
      (c) => c.textContent?.includes(zero!.title),
    )!;

    // A measured zero IS a reading and prints. This is the assertion that stops
    // "render nothing for a null" from being over-applied into "render nothing
    // for a falsy" — which would erase a real, and often good, result.
    //
    // Asserted on the figure element rather than on the row's `textContent`:
    // the row concatenates without separators ("…Compliance0Pin"), so a text
    // scan cannot tell a rendered zero from a zero inside a neighbouring word.
    const figure = card.querySelector(".pd-shelf-figure, .pd-figure");
    expect(figure, "the counted zero rendered no figure element at all").not.toBeNull();
    expect(figure!.textContent?.trim()).toBe("0");
    expect(card.querySelector(".pd-absent")).toBeNull();
  });
});
