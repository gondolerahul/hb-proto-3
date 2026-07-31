import { readFileSync } from "node:fs";
import path from "node:path";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * R-4 part W wired `TraySurface` to `GET /ai/genui/trays`, and the Thread reads
 * the same endpoint for the act its step-up bar stands under — so both halves
 * of the Line paint a scaffold first and their content on the next tick, and
 * every assertion below waits for hydration rather than reading synchronously.
 *
 * The mock is **stateful on purpose.** `respondToApproval` takes the tray off
 * the pending list exactly as the server does, because that is now the only
 * thing that can make the bar go: the Thread settles by re-reading what is
 * still waiting, never by matching a string in the echo. A mock that went on
 * serving an answered tray would let a relay that re-reads nothing pass on the
 * blank moment while the read is in flight. `reads` is counted so a test can
 * say the second read happened rather than infer it from a render.
 */
const wire = vi.hoisted(() => ({ answered: false, reads: 0 }));

beforeEach(() => {
  wire.answered = false;
  wire.reads = 0;
});

vi.mock("../src/api/trays", async (importOriginal) => {
  const { TRAY: cards } = await import("../src/fixtures/estate");
  const card = cards.find((c) => c.kind === "certified")!;
  const composed = {
    tray_id: card.id,
    approval_id: card.id,
    checkpoint_key: "before_outbound_payout_above_band",
    what_happened: { sentence: card.because, object: null },
    recommendation: null,
    paths: card.paths.map((p, i) => ({
      key: i === 0 ? "approve" : "decline",
      label: p.label,
      consequence: i === 0 ? `${card.title} proceeds.` : `${card.title} does not happen.`,
      cost: null,
    })),
    certified: {
      component: "certified.payment@1",
      tier: "T2",
      props: {
        approval_id: card.id,
        checkpoint_key: "before_outbound_payout_above_band",
        summary: card.title,
        amount: 184000,
        currency: null,
        tier: "T2",
      },
      manifest_hash: "sha256:8f2c1a440b7e4d519a632c8e5f0a7b1988f0c1de2b4a7690",
    },
    sla: { seconds_left: 2040, on_timeout: "AUTO_DENY" },
    prepared_by: { entity_id: card.raisedById, name: card.raisedBy },
  };
  return {
    ...(await importOriginal<Record<string, unknown>>()),
    fetchTrayList: () => {
      wire.reads += 1;
      return Promise.resolve(wire.answered ? [] : [composed]);
    },
    respondToApproval: () => {
      wire.answered = true;
      return Promise.resolve();
    },
  };
});

/**
 * The other three reads the Line makes, mocked the same way and for the same
 * reason: every one of them is a network call now, so a surface that used to
 * render synchronously out of a module paints a scaffold first.
 *
 * The morning is composed **from the fixture the desk was designed against**,
 * field for field onto the wire's snake_case, so the assertions below still name
 * the same story — three unvoiced cards, `tts_failed`, her sentences joined —
 * rather than a second story written to suit the test.
 *
 * The estate is deliberately *not* the fixture. The Desk's readings are the
 * projection's own plinth now, and the two states this file exists to keep apart
 * — a counted zero and no reading at all — are `value: 0, measurable: true`
 * against `value: null, measurable: false` on that plinth. Writing them here is
 * what makes them checkable; the fixture cannot produce a `PlinthKpi`.
 */
vi.mock("../src/api/line", async (importOriginal) => {
  const { MORNING } = await import("../src/fixtures/morning");
  return {
    ...(await importOriginal<Record<string, unknown>>()),
    fetchMorningStory: () =>
      Promise.resolve({
        story_date: MORNING.storyDate,
        generated_at: MORNING.generatedAt,
        degraded_reason: MORNING.degradedReason,
        cards: MORNING.cards.map((card) => ({
          entity_id: card.entityId,
          name: card.name,
          district: card.district,
          sentences: card.sentences,
          waiting: card.waiting,
          audio:
            card.audio === null
              ? null
              : { mime: card.audio.mime, data_b64: card.audio.dataB64 },
        })),
      }),
  };
});

/** Her side of the thread, as `/ai/pragya/history` sends it: a role, the words
 *  and a naive-UTC stamp. Oldest first, which is the order the endpoint returns
 *  and the opposite of the order the surface reads. */
vi.mock("../src/api/pragya", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchThreadHistory: () =>
    Promise.resolve([
      {
        role: "user",
        content: "Has Kanwal Trading answered yet?",
        at: "2026-07-30T09:12:04.113000",
      },
      {
        role: "pragya",
        content:
          "Not yet — two reminders have gone out and neither was answered. Anjali has drafted the third and it is waiting on you above.",
        at: "2026-07-30T09:12:31.402000",
      },
    ]),
}));

const desk = vi.hoisted(() => ({
  live: null as unknown,
  preferences: {} as Record<string, unknown>,
  history: { from: "2026-07-25", to: "2026-07-30", series: [] as unknown[] },
}));

vi.mock("../src/estate/useLiveEstate", () => ({
  useLiveEstate: () => desk.live,
}));
vi.mock("../src/api/study", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchPreferences: () => Promise.resolve(desk.preferences),
  writePreference: () => Promise.resolve(),
}));
vi.mock("../src/api/gallery", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchKpiHistory: () => Promise.resolve(desk.history),
}));

import type { EstateSnapshot, PlinthKpi } from "../src/api/estate";
import { TRAY } from "../src/fixtures/estate";
import { MORNING } from "../src/fixtures/morning";
import { MorningStorySurface, UNVOICED } from "../src/line/MorningStorySurface";
import { PocketDesk } from "../src/line/PocketDesk";
import { ThreadSurface } from "../src/line/ThreadSurface";
import { TraySurface } from "../src/surfaces/TraySurface";

/** The three plinth entries this file's two Desk rules are about. */
const NO_READING: PlinthKpi = {
  kpi_key: "kpi.close_days",
  display_name: "Days to close the books",
  value: null,
  measurable: false,
  unit: "days",
};
const COUNTED_ZERO: PlinthKpi = {
  kpi_key: "kpi.unreconciled",
  display_name: "Unreconciled invoices",
  value: 0,
  measurable: true,
  unit: "count",
};
const A_READING: PlinthKpi = {
  kpi_key: "kpi.dso",
  display_name: "Days sales outstanding",
  value: 38,
  measurable: true,
  unit: "days",
};

function estateWith(plinth: PlinthKpi[]): EstateSnapshot {
  return {
    estate: {
      loop_id: "loop-1",
      pulse: { beat_at: "2026-07-30T21:00:00", healthy: true },
      local_time: "2026-07-30T21:00:00+05:30",
      phase: "night",
      standing: "active",
    },
    quarters: [{ code: "finance", name: "Finance", districts: ["P08"] }],
    districts: [
      {
        process_code: "P08",
        name: "Collections",
        quarter: "finance",
        colleagues: [],
        kpi: { plinth },
        treasury: null,
        weather: { state: "clear", icon: null, sentence: null },
        traffic: { in_1h: 0, out_1h: 0, parked: 0 },
      },
    ],
    gatehouses: [],
    bridges: [],
    halls: [],
    monuments: [],
    beacons: [],
    glasshouse: { open_scenarios: 0, last_run_at: null },
    gallery: { versions: 0, terminated: 0 },
    as_of: "2026-07-30T21:00:00",
  };
}

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

  it("renders the Tray subtree the desk renders, to the byte", async () => {
    const desk = render(<TraySurface onEcho={vi.fn()} />);
    /* Hydrated, not scaffolded: two scaffolds are byte-equal for free, which
       would make this assertion pass without comparing any of the Tray's real
       markup. Settled on the scaffold being GONE rather than on `.tr-list`
       appearing — the scaffold draws ghost cards inside a `.tr-list` of its
       own, so that condition was satisfied by the very state it meant to skip. */
    await waitFor(() =>
      expect(desk.container.querySelector('[data-lifecycle="scaffold"]')).toBeNull(),
    );
    const atTheDesk = desk.container.querySelector(".tr")?.outerHTML;
    expect(atTheDesk).toBeDefined();
    cleanup();

    const line = render(<ThreadSurface onEcho={vi.fn()} />);
    await waitFor(() =>
      expect(line.container.querySelector('[data-lifecycle="scaffold"]')).toBeNull(),
    );
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
  /**
   * The bar's act comes off the wire, and the assertion is that it is the act
   * *on the screen* — the same string the mounted card prints as its ask, not a
   * second copy that can be edited into naming something else. Reading the
   * fixture here would re-create exactly the defect this replaced: the bar named
   * `fixtures/estate`'s certified card while the Tray beside it rendered the
   * tenant's own trays, so on real data the ceremony named an act that was not
   * among the cards it stood under.
   */
  it("names the act on the screen above it, read off the same wire the Tray reads", async () => {
    const { container } = render(<ThreadSurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".th-step")).not.toBeNull());

    const onTheCard = container.querySelector(".tr-ask")?.textContent;
    expect(onTheCard).toBe(CERTIFIED.title);
    expect(container.querySelector(".th-step-cmd")?.textContent).toBe(onTheCard);

    // And no command reference. `GET /ai/genui/trays` carries none — the server
    // mints one when it refuses and the ceremony prints that one — so a ref
    // here could only have been composed on the client, which is the thing that
    // lets one command's confirmation authorise another.
    expect(container.querySelector(".th-step-ref")).toBeNull();
    expect(container.querySelector(".th-step")?.textContent).not.toMatch(/cmd_|approval:/);
  });

  /**
   * The bar must not stand under an act that is already done — a ceremony
   * offered for a settled command is the clearest way to teach someone that the
   * ceremony is decorative.
   *
   * Driven through the real Tray, which it could not be while the Thread
   * decided "settled" from the echo *sentence*: the fixture-era Tray emitted
   * `"Release the payment · HITL-8841"` and part W's emits §8's form ("approved
   * Meera's run"), carrying the id on `action_ref.params.subject` where an id
   * belongs, so the substring match this test used to satisfy could only be met
   * by a stand-in. The Thread re-reads the pending list instead, which is what
   * `ThreadSurface.tsx` always said R-4 would do, and the whole path — button,
   * gate, response, re-read — is exercised here rather than mocked past.
   */
  it("goes when the command it stands under is settled", async () => {
    const { container } = render(<ThreadSurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".th-step")).not.toBeNull());

    const gold = CERTIFIED.paths.find((p) => p.rank === "certified")!;
    const button = [...container.querySelectorAll("button.tr-path")].find((b) =>
      b.textContent?.includes(gold.label),
    );
    expect(button, `no path button for "${gold.label}"`).toBeDefined();
    fireEvent.click(button as HTMLElement);

    // The Tray marks the card answered, which proves the response went through
    // and the echo fired; the bar goes because the re-read comes back without
    // the act, not because a sentence was inspected.
    await waitFor(() => expect(container.querySelector(".tr-card-settled")).not.toBeNull());
    await waitFor(() =>
      expect(
        container.querySelector(".th-step"),
        "a ceremony left standing under an act that is already done",
      ).toBeNull(),
    );
    expect(wire.answered).toBe(true);
  });

  /**
   * The other half of the same rule, and the one that fails a relay which
   * settles on the echo rather than on the estate.
   *
   * The stand-in emits a sentence carrying the act's id — precisely what the old
   * `msg.includes(certified.id)` matched — and answers nothing. The act is still
   * waiting, so the bar must come back. A Thread that reads prose for facts
   * leaves it down for good.
   */
  it("stands again when the echo answered nothing", async () => {
    vi.resetModules();
    vi.doMock("../src/surfaces/TraySurface", () => ({
      TraySurface: ({ onEcho }: { onEcho: (msg: string) => void }) => (
        <button onClick={() => onEcho(`approved ${CERTIFIED.id}`)}>echo only</button>
      ),
    }));

    try {
      const { ThreadSurface: Fresh } = await import("../src/line/ThreadSurface");
      const { container } = render(<Fresh onEcho={vi.fn()} />);
      await waitFor(() => expect(container.querySelector(".th-step")).not.toBeNull());

      const before = wire.reads;
      fireEvent.click(container.querySelector("button") as HTMLElement);

      // It asked the estate again rather than reasoning about the sentence …
      await waitFor(() => expect(wire.reads).toBeGreaterThan(before));
      // … and the estate still has the act, so the ceremony still stands.
      await waitFor(() => expect(container.querySelector(".th-step")).not.toBeNull());
      expect(wire.answered).toBe(false);
    } finally {
      cleanup();
      vi.doUnmock("../src/surfaces/TraySurface");
      vi.resetModules();
    }
  });

  it("says in words, not only in colour, whether this browser can raise it", async () => {
    // jsdom has no PublicKeyCredential, so this render takes the honest gap
    // branch — which is the branch §7.4 exists for and the one nobody looks at.
    // The composed tray is T2, the tier that wants a passkey; a T3 act asks a
    // second channel instead and this capability is not the one to report.
    const { container } = render(<ThreadSurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".th-step")).not.toBeNull());
    const state = container.querySelector(".th-step-state");

    expect(state?.textContent).toBe("this phone cannot ask");
    expect(container.querySelector(".th-step .m-lamp")?.getAttribute("data-negative")).toBe("true");
  });
});

/**
 * The bar against trays the fixtures have never heard of.
 *
 * The mock at the top of this file composes its tray *from* the certified
 * fixture card, which is what keeps the rest of the suite legible — and it means
 * a Thread that read the fixture and a Thread that reads the wire are
 * indistinguishable to those tests. These three feed it something the fixture
 * cannot produce, which is the only way to hold the three rules the wired bar
 * runs on.
 */
function aTray(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    tray_id: "TR-1",
    approval_id: "6f1c9a3e-4d21-4a77-9f0e-2b8c5d13a940",
    checkpoint_key: "before_strategy_adoption",
    what_happened: { sentence: "The band was reached.", object: null },
    recommendation: null,
    paths: [
      { key: "approve", label: "Adopt it", consequence: "It is adopted.", cost: null },
      { key: "decline", label: "Leave it", consequence: "Nothing changes.", cost: null },
    ],
    certified: {
      component: "certified.approval@1",
      tier: "T2",
      props: {
        approval_id: "6f1c9a3e-4d21-4a77-9f0e-2b8c5d13a940",
        checkpoint_key: "before_strategy_adoption",
        summary: "Adopt the revised collections stance",
        tier: "T2",
      },
      manifest_hash: "sha256:0c41f7b2ae9d3155c6b80f24e7a91d3355ef0c8b4471aa02",
    },
    sla: { seconds_left: 900, on_timeout: "AUTO_DENY" },
    prepared_by: { entity_id: "AGT-052", name: "Devika" },
    ...over,
  };
}

async function withTrays(
  list: Record<string, unknown>[],
  body: (container: HTMLElement) => Promise<void>,
): Promise<void> {
  vi.resetModules();
  vi.doMock("../src/api/trays", () => ({
    fetchTrayList: () => Promise.resolve(list),
    respondToApproval: () => Promise.resolve(),
  }));
  try {
    const { ThreadSurface: Fresh } = await import("../src/line/ThreadSurface");
    const { container } = render(<Fresh onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".tr-list")).not.toBeNull());
    await body(container);
  } finally {
    cleanup();
    vi.doUnmock("../src/api/trays");
    vi.resetModules();
  }
}

describe("the step-up bar reads the estate, not the fixtures", () => {
  it("names the act the wire sent, and asks for the factor that act's tier wants", async () => {
    const t3 = aTray({
      certified: {
        component: "certified.approval@1",
        tier: "T3",
        props: {
          approval_id: "6f1c9a3e-4d21-4a77-9f0e-2b8c5d13a940",
          checkpoint_key: "before_strategy_adoption",
          summary: "Close the Bhagwati dispute at the agreed figure",
          tier: "T3",
        },
        manifest_hash: "sha256:0c41f7b2ae9d3155c6b80f24e7a91d3355ef0c8b4471aa02",
      },
    });

    await withTrays([t3], async (container) => {
      const bar = container.querySelector(".th-step");
      expect(bar).not.toBeNull();
      expect(container.querySelector(".th-step-cmd")?.textContent).toBe(
        "Close the Bhagwati dispute at the agreed figure",
      );
      // The act the fixture would have named is nowhere near this screen.
      expect(bar!.textContent).not.toContain(CERTIFIED.title);

      /* T3 goes to `StepUpCeremony`'s second-channel leg: a code issued to
         another registered channel and typed back. Reporting this browser's
         passkey support there would answer a question the act never asked, on
         the one surface whose subject is which factor is about to be wanted. */
      expect(container.querySelector(".th-step-state")?.textContent).toBe(
        "a second channel is asked",
      );
      expect(
        container.querySelector(".th-step .m-lamp")?.getAttribute("data-negative"),
        "a T3 act was marked unavailable because jsdom has no passkey",
      ).toBeNull();
      expect(bar!.textContent).not.toContain("cannot");
    });
  });

  it("stands under no act at all where the tier asks for nothing", async () => {
    /* T1 wants a BOUND session and no ceremony (`TIER_REQUIRES`), so nothing
       will stop and ask. A bar over it would promise a ceremony that never
       fires, and an owner who learns one promise is empty has learnt the wrong
       thing about all of them. */
    const t1 = aTray({
      certified: {
        component: "certified.approval@1",
        tier: "T1",
        props: {
          approval_id: "6f1c9a3e-4d21-4a77-9f0e-2b8c5d13a940",
          checkpoint_key: "before_strategy_adoption",
          summary: "Send the revised note",
          tier: "T1",
        },
        manifest_hash: "sha256:0c41f7b2ae9d3155c6b80f24e7a91d3355ef0c8b4471aa02",
      },
    });

    await withTrays([t1], async (container) => {
      expect(container.querySelector(".tr-ask")?.textContent).toBe("Send the revised note");
      expect(container.querySelector(".th-step")).toBeNull();
    });
  });

  it("binds to nothing rather than to one of two acts waiting", async () => {
    /* Every tray carries a certified block now, so "the certified card" no
       longer picks one out. The bar names one act and says "the gold path
       above"; with two on screen there is no such path, and binding to the
       first is the confusion the ceremony's own reference exists to prevent.
       Each card goes on saying what taking *it* will ask for. */
    const second = aTray({
      tray_id: "TR-2",
      approval_id: "b2d84c17-0e35-4c69-8a1f-77c0e9d4b213",
      certified: {
        component: "certified.payment@1",
        tier: "T2",
        props: {
          approval_id: "b2d84c17-0e35-4c69-8a1f-77c0e9d4b213",
          checkpoint_key: "before_outbound_payout_above_band",
          summary: "Release the second instalment",
          amount: 92000,
          currency: null,
          tier: "T2",
        },
        manifest_hash: "sha256:0c41f7b2ae9d3155c6b80f24e7a91d3355ef0c8b4471aa02",
      },
    });

    await withTrays([aTray(), second], async (container) => {
      expect(container.querySelectorAll("article.tr-card")).toHaveLength(2);
      expect(
        container.querySelector(".th-step"),
        "a bar bound to one of two acts, under a gold path that is not the only one",
      ).toBeNull();
      // The per-card promise is still made, once for each act.
      expect(container.querySelectorAll(".tr-cert-note").length).toBeGreaterThan(0);
    });
  });
});

/**
 * The day, after R-4 part W.
 *
 * The two tests that stood here were about a `narrative.story-card` — a title, a
 * template, and a figure in a well that had to render as **nothing** when its
 * binding produced none. That card is gone, and so is the voice note beside it:
 * `/ai/pragya/history` carries a role, the words of the turn and a timestamp,
 * and nothing that could fill either shape. §7.1 says a binding that produced
 * nothing renders nothing, and the surface applied it to the whole composition
 * rather than to one field of it.
 *
 * So the rule those tests held is held here instead, and more strictly: the day
 * may print the words and the clock the seam actually sends, and **no figure of
 * any kind**. A story card cannot regress into existence without failing this,
 * and neither can a figure composed out of a paragraph.
 */
describe("the Thread's own content", () => {
  it("draws the turns the seam sent, and composes no figure for any of them", async () => {
    const { container } = render(<ThreadSurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelectorAll(".th-note")).toHaveLength(2));

    const day = container.querySelector(".th-turns")!;

    // Newest first — the endpoint returns conversation order and the phone is
    // opened to catch up, not to re-read.
    const prose = [...day.querySelectorAll(".th-prose")].map((p) => p.textContent);
    expect(prose[0]).toContain("Anjali has drafted the third");
    expect(prose[1]).toBe("Has Kanwal Trading answered yet?");

    // None of the shapes the seam cannot answer.
    expect(day.querySelector(".th-card")).toBeNull();
    expect(day.querySelector(".th-fig")).toBeNull();
    expect(day.querySelector(".th-voice")).toBeNull();

    /* Her prose is the server's, to the character. This is the assertion that
       catches a figure composed *into* a turn rather than drawn beside it —
       a template with a number substituted in, or a "—" put where one was
       expected. The forbidden-glyph scan cannot be run over the text itself,
       because an em-dash inside a sentence she wrote is punctuation and not a
       number-shaped hole; equality catches both cases and mistakes neither. */
    expect(prose[0]).toBe(
      "Not yet — two reminders have gone out and neither was answered. Anjali has drafted the third and it is waiting on you above.",
    );

    // The chrome the surface composes around them holds no figure of any kind.
    const composed =
      (day.querySelector("#th-earlier")?.textContent ?? "") +
      (day.querySelector(".th-turns-note")?.textContent ?? "") +
      [...day.querySelectorAll(".th-when")].map((w) => w.textContent).join("");
    expect(composed).not.toMatch(/[₹$€£]/);
    for (const forbidden of ["—", "–", "n/a", "N/A", "unknown", "not available"]) {
      expect(composed).not.toContain(forbidden);
    }
  });

  it("tells her turns from yours, in a word and not only in a rule", async () => {
    /* L3 is that no colleague can write to you, not that you cannot write. The
       history is the conversation, so both speakers arrive — and which of them
       said a thing is carried by the eyebrow, because a hairline alone is
       colour-by-another-name (§4). */
    const { container } = render(<ThreadSurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelectorAll(".th-note")).toHaveLength(2));

    const notes = [...container.querySelectorAll(".th-note")];
    expect(notes[0]!.querySelector(".t-eyebrow")?.textContent).toBe("PRAGYA");
    expect(notes[0]!.hasAttribute("data-yours")).toBe(false);
    expect(notes[1]!.querySelector(".t-eyebrow")?.textContent).toBe("YOU");
    expect(notes[1]!.hasAttribute("data-yours")).toBe(true);
  });

  it("puts one heading at the top of its outline, and it is the Tray's", async () => {
    const { container } = render(<ThreadSurface onEcho={vi.fn()} />);
    // The Tray's `<h1>` arrives with its data (D7 §3.1) — the scaffold is
    // structure, and a heading with nothing in it would be a claim.
    await waitFor(() => expect(container.querySelectorAll("h1")).toHaveLength(1));

    const headings = [...container.querySelectorAll("h1")];
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
  it("renders the reason in place of the voice, and no player, for an unvoiced card", async () => {
    const { container } = render(<MorningStorySurface onEcho={vi.fn()} />);
    await waitFor(() =>
      expect(container.querySelector('[data-lifecycle="scaffold"]')).toBeNull(),
    );

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

  it("names the degradation the job actually reported, never a generic apology", async () => {
    const { container } = render(<MorningStorySurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".mo-unvoiced")).not.toBeNull());
    const stated = container.querySelector(".mo-unvoiced")!.textContent ?? "";

    // The morning's reason is `tts_failed`; the copy must be that reason's own
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

/** Comments stripped — the surface explains the absence rule in prose, and a
 *  scan that cannot tell the explanation from a violation of it is a scan that
 *  punishes writing the reason down. */
const PD_TSX = readFileSync(path.join(SRC, "line", "PocketDesk.tsx"), "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/^\s*\/\/.*$/gm, "");

/** Render the Desk over one plinth, with `pinned` kept in `surface.line_pins`,
 *  and wait for it to hydrate. */
async function desking(plinth: PlinthKpi[], pinned: string[]): Promise<HTMLElement> {
  desk.live = { phase: "ready", estate: estateWith(plinth), wire: { status: "live" } };
  desk.preferences = { "surface.line_pins": { value: pinned } };
  const { container } = render(<PocketDesk onEcho={vi.fn()} />);
  await waitFor(() =>
    expect(container.querySelector('[data-lifecycle="scaffold"]')).toBeNull(),
  );
  return container;
}

describe("the Pocket Desk never invents a reading", () => {
  it("renders no figure at all where the plinth has no reading yet", async () => {
    /* `estate.py` puts every KPI definition on a district's plinth whether or
       not a snapshot has ever been taken for it, so this is the *primary* state
       of a young tenant's Desk rather than an edge of it. */
    const container = await desking(
      [NO_READING, A_READING],
      [NO_READING.kpi_key],
    );
    const card = [...container.querySelectorAll(".pd-card")].find(
      (c) => c.querySelector(".pd-card-title")?.textContent === NO_READING.display_name,
    )!;
    expect(card, "the absent reading did not render a card at all").toBeDefined();

    // Not 0, not a dash, not "unknown", not a unit on its own.
    expect(card.querySelector(".pd-figure")).toBeNull();
    expect(card.querySelector(".pd-unit")).toBeNull();

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

  it("keeps a counted zero and an absent reading visibly different", async () => {
    /* One plinth, both states, one render — because the failure this guards
       against is not "zero renders wrong" but "null and zero render alike", and
       that can only be seen with the two side by side. `value: 0,
       measurable: true` against `value: null, measurable: false` is exactly the
       distinction `estate.py` is careful to keep on the wire. */
    const container = await desking(
      [COUNTED_ZERO, NO_READING],
      [COUNTED_ZERO.kpi_key, NO_READING.kpi_key],
    );

    const cards = [...container.querySelectorAll(".pd-card")];
    const zero = cards.find(
      (c) => c.querySelector(".pd-card-title")?.textContent === COUNTED_ZERO.display_name,
    )!;
    const absent = cards.find(
      (c) => c.querySelector(".pd-card-title")?.textContent === NO_READING.display_name,
    )!;

    // A measured zero IS a reading and prints. This is the assertion that stops
    // "render nothing for a null" from being over-applied into "render nothing
    // for a falsy" — which would erase a real, and often good, result.
    //
    // Asserted on the figure element rather than on the card's `textContent`:
    // a card concatenates without separators, so a text scan cannot tell a
    // rendered zero from a zero inside a neighbouring word.
    const figure = zero.querySelector(".pd-figure");
    expect(figure, "the counted zero rendered no figure element at all").not.toBeNull();
    expect(figure!.textContent?.trim()).toBe("0");
    expect(zero.querySelector(".pd-absent")).toBeNull();

    // And the two are not the same card twice.
    expect(absent.querySelector(".pd-figure")).toBeNull();
    expect(absent.querySelector(".pd-absent")).not.toBeNull();
  });

  it("prints a counted zero on the shelf too, where there is no card to explain it", async () => {
    /* The shelf drops the figure entirely for a reading that does not exist —
       "no dash holding a place open for a number that is not there" — and the
       same closing of the column would erase a real zero if the test were on
       truthiness rather than on the null. */
    const container = await desking([COUNTED_ZERO, NO_READING], []);

    const rows = [...container.querySelectorAll(".pd-shelf-row")];
    const zero = rows.find((r) =>
      r.textContent?.includes(COUNTED_ZERO.display_name),
    )!;
    const absent = rows.find((r) =>
      r.textContent?.includes(NO_READING.display_name),
    )!;

    expect(zero.querySelector(".pd-shelf-figure")?.textContent?.trim()).toBe("0");
    expect(absent.querySelector(".pd-shelf-figure")).toBeNull();
  });
});
