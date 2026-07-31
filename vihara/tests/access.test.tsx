import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PreSession } from "../src/app/PreSession";
import { Prototype } from "../src/app/Prototype";
import { ancestorsOf, parseRoute, pathOf, SURFACES, surfaceOf } from "../src/app/routes";
import { Palette, type PaletteItem } from "../src/shell/Palette";

/**
 * R-4 parts A and N — the door, and the way around.
 *
 * Four properties are held here because each of them is invisible when broken:
 *
 *  1. **VP-01's storage rule.** `api/client.ts` claims in prose that no storage
 *     API appears under `src/`. Nothing checked it. An access token in
 *     `localStorage` looks and behaves identically to one in a module variable
 *     right up until an XSS on the app that renders generated UI, so it is
 *     checked by a scan rather than by everyone remembering.
 *
 *  2. **The password-reset absence is rendered.** A future edit that "finishes"
 *     the login screen by adding a Forgot-password link would ship a control
 *     that goes nowhere, which is the exact failure DESIGN_CONTRACT §7.4 names.
 *
 *  3. **A failed refresh is a logged-out state.** The regression this guards is
 *     the error cascade: a cold visitor treated as a fault.
 *
 *  4. **Every surface is reachable without `PrototypeNav`.** The scaffold is
 *     deleted, so the palette is now the only enumeration of the estate; a
 *     surface that falls out of it becomes unreachable in a way nothing else
 *     would notice — which is the same failure R-3c §1 describes, where a sweep
 *     agreed with whatever it found while three surfaces were missing.
 */

const SRC = path.resolve(__dirname, "..", "src");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) return walk(full);
    return /\.(ts|tsx)$/.test(full) ? [full] : [];
  });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

beforeEach(() => {
  window.history.replaceState(null, "", "/");
});

/* jsdom ships no `matchMedia`, and `background/tier.ts` asks it whether the
   visitor wants less motion before it decides anything else. Answering "no" is
   what puts the probe on its normal path; it then finds no WebGL2 and settles on
   tier C, so nothing three-shaped is ever imported here. */
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

/* jsdom's `getContext` throws "not implemented" into the virtual console on
   every mount. `probeTier` catches it and answers C either way, so the only
   thing the throw changes is whether the gate's output is readable. */
HTMLCanvasElement.prototype.getContext = (() =>
  null) as unknown as typeof HTMLCanvasElement.prototype.getContext;

/* ========================================================== VP-01, mechanised */

describe("nothing durable to steal (VP-01)", () => {
  it("names no storage API anywhere under src/", () => {
    const offenders: string[] = [];
    for (const file of walk(SRC)) {
      const body = readFileSync(file, "utf8");
      for (const api of ["localStorage", "sessionStorage", "indexedDB", "openDatabase"]) {
        // Word-bounded, so `sessionStorageIsBanned` in a comment is not a hit and
        // `window.localStorage` is.
        if (new RegExp(`\\b${api}\\b`).test(body)) {
          offenders.push(`${path.relative(SRC, file)} → ${api}`);
        }
      }
    }
    expect(offenders, offenders.join("\n")).toEqual([]);
  });
});

/* ================================================================ the routes */

describe("surface identity as a URL (N2)", () => {
  it("round-trips every surface", () => {
    for (const s of SURFACES) {
      const route = { surface: s.id, subject: null };
      expect(parseRoute(pathOf(route))).toEqual(route);
    }
  });

  it("carries a subject only where the platform has one to name", () => {
    expect(parseRoute("/tray/tr-2026-07-31-4")).toEqual({
      surface: "tray",
      subject: "tr-2026-07-31-4",
    });
    expect(pathOf({ surface: "district", subject: "P08" })).toBe("/district/P08");
    // The Study names no subject, so a trailing segment is dropped rather than
    // half-honoured.
    expect(parseRoute("/study/anything")).toEqual({ surface: "study", subject: null });
  });

  it("resolves an unrecognised path to the front door rather than to nothing", () => {
    expect(parseRoute("/no-such-room")).toEqual({ surface: "still", subject: null });
    expect(parseRoute("")).toEqual({ surface: "still", subject: null });
  });

  it("gives every surface a ladder that ends at the root (N3)", () => {
    for (const s of SURFACES) {
      const chain = ancestorsOf({ surface: s.id, subject: null });
      if (s.id === "still") {
        expect(chain).toEqual([]);
        continue;
      }
      expect(chain[0]?.surface, `${s.id} does not rise to the root`).toBe("still");
      // No surface may be its own ancestor, or the seeded stack never ends.
      const seen = chain.map((r) => r.surface);
      expect(new Set(seen).size, `${s.id} has a cycle above it`).toBe(seen.length);
      expect(seen).not.toContain(s.id);
      // Depth never decreases on the way down, so Back never descends. Equal is
      // allowed — rooms open onto rooms, and D6's ladder has only four rungs.
      const depths = [...chain.map((r) => surfaceOf(r.surface).depth), s.depth];
      for (let i = 1; i < depths.length; i++) {
        expect(depths[i]!, `${s.id} rung ${i}`).toBeGreaterThanOrEqual(depths[i - 1]!);
      }
    }
  });
});

/* ============================================================== pre-session */

describe("pre-session (A1)", () => {
  it("says the password reset does not exist, and offers no link to it", () => {
    const { container, getByText } = render(<PreSession onEntered={vi.fn()} />);
    expect(getByText(/no password-reset endpoint/i)).toBeDefined();
    // Not one link on the screen — the gap is a sentence, never a control.
    expect(container.querySelectorAll("a").length).toBe(0);
    expect(container.textContent).not.toMatch(/send you a reset|reset link|email me a link/i);
  });

  it("stays conventional — no world, no depth ladder, no glass", () => {
    const { container } = render(<PreSession onEntered={vi.fn()} />);
    expect(container.querySelector(".sh-dial")).toBeNull();
    expect(container.querySelector(".m-glass")).toBeNull();
    expect(container.querySelector("canvas")).toBeNull();
  });

  it("asks for a name only when an estate is being opened", () => {
    const { getByText, queryByText } = render(<PreSession onEntered={vi.fn()} />);
    expect(queryByText("Your name")).toBeNull();
    fireEvent.click(getByText(/New here\?/));
    expect(getByText("Your name")).toBeDefined();
  });

  it("does not say 'wrong password' when the server never answered", async () => {
    const client = await import("../src/api/client");
    vi.spyOn(client, "login").mockRejectedValue(new Error("Network Error"));

    const { container, getByText, findByRole } = render(<PreSession onEntered={vi.fn()} />);
    fireEvent.change(container.querySelector('input[type="email"]')!, {
      target: { value: "owner@example.com" },
    });
    fireEvent.change(container.querySelector('input[type="password"]')!, {
      target: { value: "hunter2" },
    });
    fireEvent.click(getByText("Enter"));

    const alert = await findByRole("alert");
    expect(alert.textContent).toMatch(/did not answer/i);
    expect(alert.textContent).not.toMatch(/did not match/i);
  });

  it("says so, and only so, when the rate limiter refuses", async () => {
    const client = await import("../src/api/client");
    vi.spyOn(client, "login").mockRejectedValue({ response: { status: 429 } });

    const { container, getByText, findByRole } = render(<PreSession onEntered={vi.fn()} />);
    fireEvent.change(container.querySelector('input[type="email"]')!, {
      target: { value: "owner@example.com" },
    });
    fireEvent.change(container.querySelector('input[type="password"]')!, {
      target: { value: "hunter2" },
    });
    fireEvent.click(getByText("Enter"));

    expect((await findByRole("alert")).textContent).toMatch(/too many attempts/i);
  });
});

/* ================================================================ the gate */

describe("the session gate (A2, A4)", () => {
  it("renders the login screen when the refresh fails, and calls it no error", async () => {
    vi.resetModules();
    vi.doMock("../src/api/client", () => ({
      refreshAccessToken: () => Promise.resolve(false),
      getAccessToken: () => null,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
    }));
    /* The destination is a prop now, not an import to stand in for: the Line
       goes through this same gate and must not drag the estate's surfaces into
       its bundle. A child rendered here would mean the gate let a cold visitor
       past. */
    const { Session } = await import("../src/app/Session");
    const { container, findByText } = render(
      <Session>
        <div>ESTATE-MOUNTED</div>
      </Session>,
    );
    await findByText(/ENTER THE ESTATE/);

    expect(container.textContent).not.toMatch(/error|failed|something went wrong/i);
    expect(container.textContent).not.toContain("ESTATE-MOUNTED");
    vi.doUnmock("../src/api/client");
  });

  it("renders the estate when the refresh succeeds", async () => {
    vi.resetModules();
    vi.doMock("../src/api/client", () => ({
      refreshAccessToken: () => Promise.resolve(true),
      getAccessToken: () => "at",
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
    }));
    const { Session } = await import("../src/app/Session");
    const { findByText } = render(
      <Session>
        <div>ESTATE-MOUNTED</div>
      </Session>,
    );
    expect(await findByText("ESTATE-MOUNTED")).toBeDefined();
    vi.doUnmock("../src/api/client");
  });

  it("gates the Line's entry too, not only the estate's", async () => {
    /* The defect this closes: `line/main.tsx` mounted `LineApp` unconditionally,
       so the Line's default tab fired its reads with no access token. Every unit
       test passed — they mock the API — and the first live sweep found a 401
       storm on The Line · Morning. Asserted at the source, because mounting the
       real entry would `createRoot` into the document. */
    const entry = readFileSync(path.join(SRC, "line", "main.tsx"), "utf8");
    expect(entry).toMatch(/import\s*\{\s*Session\s*\}\s*from\s*"\.\.\/app\/Session"/);
    expect(entry).toMatch(/<Session[\s>]/);
    // And it must not reach the estate through the door it shares with it.
    expect(entry).not.toContain("Prototype");
  });
});

/* ============================================================== the palette */

const ITEMS: PaletteItem[] = [
  { id: "still", label: "Still surface", note: "the front door", group: "Still", href: "/" },
  { id: "tray", label: "The Tray", note: "what is waiting", group: "Rooms", href: "/tray" },
  {
    id: "undercroft",
    label: "The Undercroft",
    note: "the machinery",
    group: "Undercroft",
    href: "/undercroft",
    aka: "manifest flags",
  },
];

describe("the navigator (N1)", () => {
  it("filters on words it never prints", () => {
    const { container, getByLabelText } = render(
      <Palette items={ITEMS} onGo={vi.fn()} onClose={vi.fn()} />,
    );
    fireEvent.change(getByLabelText("Filter surfaces"), { target: { value: "flags" } });
    const rows = [...container.querySelectorAll(".pl-opt")];
    expect(rows.length).toBe(1);
    expect(rows[0]!.textContent).toContain("The Undercroft");
    expect(rows[0]!.textContent).not.toContain("flags");
  });

  it("says so when nothing matches, rather than showing an empty box", () => {
    const { container, getByLabelText } = render(
      <Palette items={ITEMS} onGo={vi.fn()} onClose={vi.fn()} />,
    );
    fireEvent.change(getByLabelText("Filter surfaces"), { target: { value: "zzz" } });
    expect(container.querySelectorAll(".pl-opt").length).toBe(0);
    expect(container.querySelector(".pl-none")?.textContent).toMatch(/Nothing in the estate/);
  });

  it("moves with the arrows and goes on Enter", () => {
    const onGo = vi.fn();
    const onClose = vi.fn();
    const { getByLabelText } = render(
      <Palette items={ITEMS} onGo={onGo} onClose={onClose} />,
    );
    const input = getByLabelText("Filter surfaces");
    expect(input.getAttribute("aria-activedescendant")).toBe("pl-opt-still");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(input.getAttribute("aria-activedescendant")).toBe("pl-opt-tray");
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onGo).toHaveBeenCalledWith(expect.objectContaining({ id: "tray" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("wraps at both ends rather than dead-ending", () => {
    const { getByLabelText } = render(<Palette items={ITEMS} onGo={vi.fn()} onClose={vi.fn()} />);
    const input = getByLabelText("Filter surfaces");
    fireEvent.keyDown(input, { key: "ArrowUp" });
    expect(input.getAttribute("aria-activedescendant")).toBe("pl-opt-undercroft");
  });

  it("traps Tab and closes on Escape", () => {
    const onClose = vi.fn();
    const { getByLabelText } = render(<Palette items={ITEMS} onGo={vi.fn()} onClose={onClose} />);
    const input = getByLabelText("Filter surfaces");
    // `fireEvent` returns false when the handler called preventDefault.
    expect(fireEvent.keyDown(input, { key: "Tab" })).toBe(false);
    fireEvent.keyDown(input, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("takes focus on open and gives it back on close", () => {
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();

    const { getByLabelText, unmount } = render(
      <Palette items={ITEMS} onGo={vi.fn()} onClose={vi.fn()} />,
    );
    expect(document.activeElement).toBe(getByLabelText("Filter surfaces"));
    unmount();
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });
});

/* ================================================ the estate, end to end */

describe("every surface is reachable without PrototypeNav (N1, N4)", () => {
  it("lists all fifteen surfaces plus the Line, and nothing else", async () => {
    const { container } = render(<Prototype />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });

    await waitFor(() => expect(container.querySelector(".pl")).not.toBeNull());
    const rows = [...container.querySelectorAll(".pl-opt")];
    expect(rows.length).toBe(SURFACES.length + 1);

    const hrefs = rows.map((r) => r.getAttribute("href"));
    for (const s of SURFACES) {
      expect(hrefs, `${s.id} is not in the palette`).toContain(
        pathOf({ surface: s.id, subject: null }),
      );
    }
    expect(hrefs).toContain("/line.html");
  });

  it("opens at depth 0, where the old scaffold was the only way out", () => {
    const { container } = render(<Prototype />);
    expect(container.querySelector(".sh")).toBeNull();
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    expect(container.querySelector(".pl")).not.toBeNull();
  });

  it("puts the surface in the address bar and seeds the ladder under it", async () => {
    window.history.replaceState(null, "", "/tray");
    render(<Prototype />);
    // Root, terrace, tray — so Back rises out of a notification's deep link
    // instead of leaving the product (N3).
    await waitFor(() => expect(window.location.pathname).toBe("/tray"));
    window.history.back();
    await waitFor(() => expect(window.location.pathname).toBe("/terrace"));
    window.history.back();
    await waitFor(() => expect(window.location.pathname).toBe("/"));
  });

  it("navigates from the palette and pushes the URL", async () => {
    const { container } = render(<Prototype />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    await waitFor(() => expect(container.querySelector(".pl")).not.toBeNull());

    const row = [...container.querySelectorAll<HTMLAnchorElement>(".pl-opt")].find(
      (a) => a.getAttribute("href") === "/terrace",
    );
    expect(row).toBeDefined();
    fireEvent.click(row!);

    await waitFor(() => expect(window.location.pathname).toBe("/terrace"));
    expect(container.querySelector(".pl")).toBeNull();
    expect(container.querySelector(".sh")).not.toBeNull();
  });

  it("has no review scaffold left to fall back on", () => {
    // The prose may name what was deleted; the code may not reference it.
    const body = readFileSync(path.join(SRC, "app", "Prototype.tsx"), "utf8");
    expect(body).not.toMatch(/<PrototypeNav|function PrototypeNav/);
    expect(body).not.toMatch(/from "\.\.\/boards/);
    expect(() => statSync(path.join(SRC, "boards"))).toThrow();
    for (const file of walk(SRC)) {
      expect(readFileSync(file, "utf8"), file).not.toMatch(/from ".*boards\//);
    }
  });
});
