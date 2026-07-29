/**
 * DRIVER D1 — the Tray (D6 §4). What these pin, rule by rule:
 *
 * 1. The certified block is BYTE-IDENTICAL in the tray and in a manifest
 *    surface — both render through the one shared dispatch.
 * 2. The countdown is quiet — a plain timer, no alarm class to seize on.
 * 3. A path with no cost shows NO cost line — no placeholder, no dash.
 * 4. The certified-act flow: a `step_up_required` refusal becomes the
 *    ceremony; the action retries WHOLE, exactly once; a second refusal
 *    shows the server's reason and does not loop; an ordinary failure is
 *    never claimed by the ceremony.
 *
 * Plus the L10 contract: every path echoes — approve, decline, and asking.
 */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { EchoInput } from "../src/api/genui";
import type { Tray } from "../src/api/trays";
import { TraySurface, type TrayLoaders } from "../src/app/TraySurface";
import { formatSlaSentence } from "../src/components/primitive/SlaCountdown";
import { assessManifest } from "../src/manifest/refusals";
import type { WireScaffold } from "../src/manifest/schema";
import type { StreamEvent } from "../src/estate/live";
import { RenderManifest } from "../src/renderers/RenderManifest";

afterEach(cleanup);

const CERTIFIED_PROPS = {
  approval_id: "00000000-0000-0000-0000-000000000001",
  checkpoint_key: "before_outbound_payout_above_band",
  summary: "a payout of consequence",
  amount: 84200,
  currency: null,
  tier: "T2",
};

const PAYMENT_TRAY: Tray = {
  tray_id: "t-1",
  approval_id: "00000000-0000-0000-0000-000000000001",
  checkpoint_key: "before_outbound_payout_above_band",
  what_happened: {
    sentence: "Kulkarni Traders crossed 60 days overdue on KT-2291.",
    object: null,
  },
  recommendation: null,
  paths: [
    {
      key: "approve",
      label: "Approve",
      consequence: "the payout proceeds.",
      cost: { amount: 84200, currency: null, basis: "the amount itself" },
    },
    {
      key: "decline",
      label: "Decline",
      consequence: "the payout does not happen.",
      cost: null,
    },
  ],
  certified: {
    component: "certified.payment@1",
    tier: "T2",
    props: CERTIFIED_PROPS,
    manifest_hash: "sha256:fixture",
  },
  sla: { seconds_left: 12400, on_timeout: "auto_deny" },
  prepared_by: { entity_id: "e-1", name: "Meera" },
};

const REFUSAL_ERROR = {
  response: {
    status: 403,
    data: {
      detail: {
        error: "step_up_required",
        tier: "T2",
        why: "payments need a passkey",
        reason: "step up to T2 first",
        current_level: 1,
        required_level: 2,
        needs_step_up: true,
        needs_oob: false,
        locked: false,
        command_ref: "approval:00000000-0000-0000-0000-000000000001",
        command_summary: "a payout of consequence",
      },
    },
  },
};

interface Harness {
  loaders: TrayLoaders;
  echoes: EchoInput[];
  responds: { id: string; decision: string }[];
  fireStream: (event: StreamEvent) => void;
}

function harness({
  lists,
  respond,
  totpOk = true,
}: {
  lists: Tray[][];
  respond?: () => Promise<void>;
  totpOk?: boolean;
}): Harness {
  const echoes: EchoInput[] = [];
  const responds: { id: string; decision: string }[] = [];
  let handler: ((event: StreamEvent) => void) | null = null;
  let call = 0;
  const loaders: TrayLoaders = {
    trays: async () => lists[Math.min(call++, lists.length - 1)] ?? [],
    respond: async (id, decision) => {
      responds.push({ id, decision });
      if (respond !== undefined) await respond();
    },
    echo: async (echo) => {
      echoes.push(echo);
    },
    stream: (onEvent) => {
      handler = onEvent;
      return () => undefined;
    },
    ceremony: {
      passkey: async () => ({ ok: true }),
      totp: async () => ({ ok: totpOk, reason: totpOk ? undefined : "wrong code" }),
    },
  };
  return {
    loaders,
    echoes,
    responds,
    fireStream: (event) => handler?.(event),
  };
}

async function renderTrays(h: Harness): Promise<void> {
  render(<TraySurface loaders={h.loaders} />);
  await waitFor(() => {
    expect(document.querySelector("[data-part='tray']")).not.toBeNull();
  });
}

describe("rule 1 — the certified block is byte-identical across contexts", () => {
  it("tray block === manifest block, same dispatch, same DOM", async () => {
    const h = harness({ lists: [[PAYMENT_TRAY]] });
    await renderTrays(h);
    const inTray = document.querySelector("[data-part='certified']");
    expect(inTray).not.toBeNull();
    const trayHtml = (inTray as HTMLElement).outerHTML;
    cleanup();

    const scaffold: WireScaffold = {
      part: "scaffold",
      manifest_version: 1,
      surface_id: "some-sheet",
      renderer: "S",
      plane: "live",
      depth: 2,
      density: "novice",
      layout: { kind: "stack", regions: ["body"] },
      components: [
        {
          id: "c9",
          type: "certified.payment@1",
          region: "body",
          props: CERTIFIED_PROPS,
        },
      ],
      issued_at: "t",
      ttl_seconds: 60,
    };
    render(
      <RenderManifest manifest={scaffold} assessment={assessManifest(scaffold)} />,
    );
    const inSheet = document.querySelector("[data-part='certified']");
    expect((inSheet as HTMLElement).outerHTML).toBe(trayHtml);
  });

  it("a certified block that fails the registry renders a refusal, not a lookalike", async () => {
    const poisoned: Tray = {
      ...PAYMENT_TRAY,
      certified: {
        ...PAYMENT_TRAY.certified,
        props: { ...CERTIFIED_PROPS, injected: "<script>" },
      },
    };
    const h = harness({ lists: [[poisoned]] });
    await renderTrays(h);
    expect(document.querySelector("[data-part='uncertifiable']")).not.toBeNull();
    expect(document.querySelector("[data-part='certified']")).toBeNull();
  });
});

describe("rule 2 — the countdown is quiet", () => {
  it("formats as a plain sentence at every band", () => {
    expect(formatSlaSentence(12400, "auto_deny")).toBe("3h 26m left");
    expect(formatSlaSentence(1560, null)).toBe("26m left");
    expect(formatSlaSentence(30, null)).toBe("under a minute left");
    expect(formatSlaSentence(0, "auto_deny")).toBe(
      "past its window — it will decline itself",
    );
    expect(formatSlaSentence(-5, null)).toBe("past its window");
  });

  it("renders as a timer with the quiet class and nothing else", async () => {
    const h = harness({ lists: [[PAYMENT_TRAY]] });
    await renderTrays(h);
    const timer = document.querySelector("[data-part='sla-countdown']");
    expect(timer).not.toBeNull();
    expect((timer as HTMLElement).className).toBe("vh-sla");
    expect((timer as HTMLElement).getAttribute("role")).toBe("timer");
  });

  it("composes no countdown at all when the checkpoint has no SLA", async () => {
    const noSla: Tray = {
      ...PAYMENT_TRAY,
      sla: { seconds_left: null, on_timeout: null },
    };
    const h = harness({ lists: [[noSla]] });
    await renderTrays(h);
    expect(document.querySelector("[data-part='sla-countdown']")).toBeNull();
  });
});

describe("rule 3 — a path with no cost shows no cost line", () => {
  it("costed path shows amount and basis; null-cost path shows nothing", async () => {
    const h = harness({ lists: [[PAYMENT_TRAY]] });
    await renderTrays(h);
    const approve = document.querySelector("[data-path='approve']");
    const decline = document.querySelector("[data-path='decline']");
    expect(approve?.querySelector("[data-part='path-cost']")).not.toBeNull();
    expect(approve?.textContent).toContain("the amount itself");
    expect(decline?.querySelector("[data-part='path-cost']")).toBeNull();
    expect(decline?.textContent).not.toContain("—");
  });
});

describe("the recommendation is honest about absence", () => {
  it("null recommendation renders no recommendation region", async () => {
    const h = harness({ lists: [[PAYMENT_TRAY]] });
    await renderTrays(h);
    expect(document.querySelector("[data-part='recommendation']")).toBeNull();
  });

  it("a present recommendation renders, why expanded at novice density", async () => {
    const advised: Tray = {
      ...PAYMENT_TRAY,
      recommendation: {
        sentence: "I'd send the firm reminder we agreed.",
        why: "their last call promised payment by Friday",
      },
    };
    const h = harness({ lists: [[advised]] });
    await renderTrays(h);
    const region = document.querySelector("[data-part='recommendation']");
    expect(region).not.toBeNull();
    expect(region?.querySelector("details")?.open).toBe(true);
  });
});

describe("rule 4 — the certified act flow", () => {
  it("approve → refusal → ceremony → retry whole, echo, tray settles", async () => {
    let first = true;
    const h = harness({
      lists: [[PAYMENT_TRAY]],
      respond: async () => {
        if (first) {
          first = false;
          throw REFUSAL_ERROR;
        }
      },
    });
    await renderTrays(h);

    fireEvent.click(screen.getByText("approve"));
    await waitFor(() => {
      expect(document.querySelector("[data-part='ceremony']")).not.toBeNull();
    });

    fireEvent.change(screen.getByLabelText(/one-time code/), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByText("verify"));

    await waitFor(() => {
      expect(document.querySelector("[data-part='tray']")).toBeNull();
    });
    expect(h.responds).toHaveLength(2);
    expect(h.responds[1]).toEqual({
      id: PAYMENT_TRAY.approval_id,
      decision: "APPROVED",
    });
    expect(h.echoes.map((echo) => echo.sentence)).toContain(
      "approved: a payout of consequence",
    );
  });

  it("refused again after the ceremony: the server's reason, no loop", async () => {
    const h = harness({
      lists: [[PAYMENT_TRAY]],
      respond: async () => {
        throw REFUSAL_ERROR;
      },
    });
    await renderTrays(h);

    fireEvent.click(screen.getByText("approve"));
    await waitFor(() => {
      expect(document.querySelector("[data-part='ceremony']")).not.toBeNull();
    });
    fireEvent.change(screen.getByLabelText(/one-time code/), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByText("verify"));

    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toBe("step up to T2 first");
    });
    expect(document.querySelector("[data-part='ceremony']")).toBeNull();
    expect(document.querySelector("[data-part='tray']")).not.toBeNull();
  });

  it("an ordinary failure is never claimed by the ceremony", async () => {
    const h = harness({
      lists: [[PAYMENT_TRAY]],
      respond: async () => {
        throw { response: { status: 500, data: {} } };
      },
    });
    await renderTrays(h);
    fireEvent.click(screen.getByText("decline"));
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toBe(
        "That could not be completed.",
      );
    });
    expect(document.querySelector("[data-part='ceremony']")).toBeNull();
  });

  it("decline echoes too", async () => {
    const h = harness({ lists: [[PAYMENT_TRAY]] });
    await renderTrays(h);
    fireEvent.click(screen.getByText("decline"));
    await waitFor(() => {
      expect(h.echoes.map((echo) => echo.sentence)).toContain(
        "declined: a payout of consequence",
      );
    });
    expect(h.responds[0]?.decision).toBe("REJECTED");
  });
});

describe("asking is a path and it echoes (L10)", () => {
  it("talk-to-me emits its echo and says honestly when she can answer", async () => {
    const h = harness({ lists: [[PAYMENT_TRAY]] });
    await renderTrays(h);
    fireEvent.click(screen.getByText("talk to me about it"));
    await waitFor(() => {
      expect(h.echoes.map((echo) => echo.sentence)).toContain(
        "asked about: a payout of consequence",
      );
    });
    expect(document.querySelector("[data-part='ask-honesty']")).not.toBeNull();
  });
});

describe("the live wire", () => {
  it("a delivered tray refetches the list — the read is the truth", async () => {
    const h = harness({ lists: [[], [PAYMENT_TRAY]] });
    render(<TraySurface loaders={h.loaders} />);
    await waitFor(() => {
      expect(document.querySelector("[data-part='trays-empty']")).not.toBeNull();
    });
    h.fireStream({ type: "tray.delivered", payload: {} });
    await waitFor(() => {
      expect(document.querySelector("[data-part='tray']")).not.toBeNull();
    });
  });

  it("an empty tray list says nothing needs you", async () => {
    const h = harness({ lists: [[]] });
    render(<TraySurface loaders={h.loaders} />);
    await waitFor(() => {
      expect(screen.getByText("Nothing needs you.")).toBeDefined();
    });
  });
});
