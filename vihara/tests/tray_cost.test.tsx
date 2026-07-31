import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Tray, TrayCost } from "../src/api/trays";
import { TraySurface } from "../src/surfaces/TraySurface";

/**
 * D5 §4.1: `paths[].cost` is the field the contract argued hardest about, and
 * the rendering rule is that a **null cost renders as nothing at all** — never
 * "₹0", never "—", never "cost unknown". On a payment card an invented zero is
 * the worst available bug, so it is held by a test rather than by a convention.
 *
 * R-4 part W moved this off the fixture and onto the wire, and the wire made
 * the rule harder rather than easier in three ways this file now pins:
 *
 * 1. **`cost` is an object, not a string.** `{amount, currency, basis}`. The
 *    check is on the object being `null`, never on its truthiness — because
 *    `amount: 0` is a *real observation*. `genui/cost.py` is explicit: "an
 *    approved run that spent nothing afterwards **is** an observation, at
 *    zero", so a `cost?.amount &&` guard would suppress a measured zero and
 *    print a null one. The two mistakes are opposite and both are §7.1.
 * 2. **`currency` is null in both of the composer's branches.** The platform
 *    does not stamp a currency on a bare amount, so nothing may print one —
 *    and, per §7.4, the absence is *said* rather than left to be assumed. A
 *    bare figure in a rupee-shaped app is read as rupees whether or not anyone
 *    said so; `certified.payment` already ships this exact sentence.
 * 3. **The estimator is real and frequently silent.** It floors at five
 *    observations per `(company, checkpoint)` and the dev DB has zero
 *    approvals, so the null branch is the common case in every demo — which is
 *    precisely why it must not be the untested one.
 *
 * The surface is fed through a mocked `api/trays`: the fixture is no longer
 * imported by the Tray, and a test that reached for it would be testing a
 * module the surface has stopped reading.
 */

const wire = vi.hoisted(() => ({ trays: [] as unknown[] }));

vi.mock("../src/api/trays", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchTrayList: () => Promise.resolve(wire.trays),
  respondToApproval: () => Promise.resolve(),
}));

afterEach(() => {
  cleanup();
  wire.trays = [];
});

/**
 * One composed tray, in `genui/trays.py`'s own shape. Deliberately awkward
 * content (§7.5): a co-operative whose name wraps, an amount with a fractional
 * part the wire really sends, and no currency anywhere — because that is what
 * the composer emits, not a tidy case.
 */
function tray(overrides: {
  id: string;
  approveCost: TrayCost | null;
  amount?: number;
}): Tray {
  return {
    tray_id: overrides.id,
    approval_id: overrides.id,
    checkpoint_key: "before_outbound_payout_above_band",
    what_happened: {
      sentence:
        "Invoice INV-4471 matched the goods receipt and the purchase order; terms are net 30 and today is day 30.",
      object: { kind: "run", id: "run-1", label: "Meera's run" },
    },
    recommendation: null,
    paths: [
      {
        key: "approve",
        label: "Approve",
        consequence:
          "Releasing the balance on the Coromandel Garments & Furnishing Co-operative order proceeds.",
        cost: overrides.approveCost,
      },
      {
        key: "decline",
        label: "Decline",
        consequence: "It does not happen; the run continues without it.",
        cost: null,
      },
    ],
    certified: {
      component: overrides.amount === undefined ? "certified.approval@1" : "certified.payment@1",
      tier: "T2",
      props: {
        approval_id: overrides.id,
        checkpoint_key: "before_outbound_payout_above_band",
        summary: "Release the balance on the Coromandel Garments & Furnishing Co-operative order.",
        ...(overrides.amount === undefined
          ? {}
          : { amount: overrides.amount, currency: null }),
        tier: "T2",
      },
      manifest_hash: "sha256:8f2c1a440b7e4d519a632c8e5f0a7b1988f0c1de2b4a7690",
    },
    sla: { seconds_left: 2460, on_timeout: "AUTO_DENY" },
    prepared_by: { entity_id: "1d9b3e70-5a12-4c88-bf04-6e21d3a95c77", name: "Meera" },
  };
}

async function mount() {
  const view = render(<TraySurface onEcho={vi.fn()} />);
  /* Scaffold first, words second (D7 §3.1) — every assertion below is about
     the hydrated surface.

     Settle on the scaffold being GONE, not on `.tr-list` being present: the
     scaffold draws its ghost cards inside a `.tr-list` too, so waiting for that
     class matched the loading state this helper exists to wait past. It passed
     whenever the first paint happened to be slow enough and failed under load,
     which is what made it read as a flake rather than as a wrong condition.
     `data-lifecycle="scaffold"` is on `Scaffold` itself and cannot collide. */
  await waitFor(() =>
    expect(view.container.querySelector('[data-lifecycle="scaffold"]')).toBeNull(),
  );
  return view;
}

function pathButton(container: HTMLElement, label: string): HTMLElement | undefined {
  return [...container.querySelectorAll("button.tr-path")].find((button) =>
    button.textContent?.includes(label),
  ) as HTMLElement | undefined;
}

describe("the tray's cost line", () => {
  it("renders a cost when the endpoint gives one", async () => {
    wire.trays = [
      tray({
        id: "a1",
        amount: 184000,
        approveCost: { amount: 184000, currency: null, basis: "the amount itself" },
      }),
    ];
    const { container } = await mount();

    // Scoped to the path button: the same figure also appears in the facts
    // well, so an unscoped query matches twice and proves nothing about the
    // button. Grouped by hand — never `toLocaleString`, which would regroup the
    // figure the owner is about to release according to the machine's locale.
    const button = pathButton(container, "Approve");
    expect(button).toBeDefined();
    expect(button!.querySelector(".tr-path-cost")?.textContent).toBe("184,000");
  });

  it("renders nothing at all when the cost is null", async () => {
    wire.trays = [tray({ id: "a1", approveCost: null })];
    const { container } = await mount();

    const button = pathButton(container, "Decline");
    expect(button, 'no button for path "Decline"').toBeDefined();

    // No cost element inside it...
    expect(button!.querySelector(".tr-path-cost")).toBeNull();
    // ...and none of the shapes an invented cost would take.
    expect(button!.textContent).toBe("Decline");
    for (const forbidden of ["₹0", "—", "-", "0.00", "unknown", "n/a", "N/A"]) {
      expect(button!.textContent).not.toContain(forbidden);
    }
  });

  /**
   * The inverse trap, and the one a careful author gets wrong. `cost.amount`
   * of zero is a measurement — five approved runs that spent nothing after the
   * decision — and suppressing it would report "we do not know" about
   * something the estate does know.
   */
  it("renders a measured zero, because zero is an observation and null is not", async () => {
    wire.trays = [
      tray({
        id: "a1",
        approveCost: {
          amount: 0,
          currency: null,
          basis: "observed: median platform spend across 7 similar decisions",
        },
      }),
    ];
    const { container } = await mount();

    const button = pathButton(container, "Approve");
    expect(button!.querySelector(".tr-path-cost")?.textContent).toBe("0");
    // And the denominator is carried, so a person can weigh the number.
    expect(container.textContent).toContain("across 7 similar decisions");
  });

  it("never prints a currency symbol on a path whose cost has none", async () => {
    wire.trays = [
      tray({
        id: "a1",
        amount: 184000,
        approveCost: { amount: 184000, currency: null, basis: "the amount itself" },
      }),
      tray({ id: "a2", approveCost: null }),
    ];
    const { container } = await mount();

    for (const button of container.querySelectorAll("button.tr-path")) {
      expect(button.textContent).not.toMatch(/[₹$€£]/);
    }
    // The absence is said, not left to be assumed (§7.4) — the same sentence
    // `certified.payment` ships, for the same reason.
    expect(container.textContent).toContain("The currency was not stated on this approval.");
  });

  it("prints the currency the endpoint states, when it states one", async () => {
    wire.trays = [
      tray({
        id: "a1",
        approveCost: { amount: 842000.5, currency: "INR", basis: "the amount itself" },
      }),
    ];
    const { container } = await mount();

    const button = pathButton(container, "Approve");
    // 842000.5 → "842,000.5" on every machine. Not padded to two decimals:
    // that would be a digit the wire never sent.
    expect(button!.querySelector(".tr-path-cost")?.textContent).toBe("INR 842,000.5");
    expect(button!.textContent).not.toContain("842,000.50");
  });

  it("invents no figure anywhere on an empty tray", async () => {
    wire.trays = [];
    const { container } = render(<TraySurface onEcho={vi.fn()} />);
    await waitFor(() =>
      expect(container.textContent).toContain("without needing you"),
    );

    expect(container.querySelector(".tr-head-meta")).toBeNull();
    /* `Math.max()` of nothing is `-Infinity` and `Math.min()` of nothing is
       `Infinity`; "soonest Infinitym" is a number nobody measured, which §7.1
       forbids more strictly than it forbids a blank. An em dash is *prose* in
       the empty copy, so the dash this rule is about is checked as a standalone
       value rather than as a substring of a sentence. */
    for (const forbidden of ["₹0", "Infinity", "NaN", "0 of 0"]) {
      expect(container.textContent).not.toContain(forbidden);
    }
    for (const node of container.querySelectorAll("*")) {
      expect(node.textContent?.trim()).not.toBe("—");
    }
  });

  /**
   * The other half of §7.1 on this surface: a path the approval endpoint
   * cannot answer gets no control at all, rather than a control that guesses.
   * `POST /ai/approvals/{id}/respond` takes APPROVED or REJECTED and nothing
   * else, so a third path key is a rendered gap.
   */
  it("draws no control for a path the endpoint has no answer for", async () => {
    const base = tray({ id: "a1", approveCost: null });
    wire.trays = [
      {
        ...base,
        paths: [
          ...base.paths,
          { key: "escalate", label: "Send it upstairs", consequence: "Someone else decides.", cost: null },
        ],
      },
    ];
    const { container } = await mount();

    expect(pathButton(container, "Send it upstairs")).toBeUndefined();
    expect(container.textContent).toContain("approve and decline, and nothing else");
  });

  /**
   * The closed-set guard, from the surface's side. `RunnableCertifiedType` is
   * eight named acts; a tray whose certified block is none of them cannot be
   * routed, because choosing a gate for it would be this client deciding which
   * ceremony an unknown act deserves. So the card draws no control at all and
   * names the block it could not place.
   */
  it("takes no act at all for a certified block it has no gate for", async () => {
    const base = tray({ id: "a1", approveCost: null });
    wire.trays = [
      { ...base, certified: { ...base.certified, component: "certified.mystery@1" } },
    ];
    const { container } = await mount();

    expect(container.querySelectorAll("button.tr-path")).toHaveLength(0);
    expect(container.textContent).toContain("certified.mystery@1");
    expect(container.textContent).toContain("cannot take any of these paths");
  });
});

describe("the tray's certified act", () => {
  it("routes a step-up refusal into the ceremony rather than an error", async () => {
    const trays = await import("../src/api/trays");
    vi.spyOn(trays, "respondToApproval").mockRejectedValueOnce({
      response: {
        status: 403,
        data: {
          detail: {
            error: "step_up_required",
            tier: "T2",
            why: "a payout above the auto-release band is a T2 act",
            reason: "T2 needs ELEVATED, session holds BOUND",
            needs_step_up: true,
            needs_oob: false,
            locked: false,
            command_ref: "approval:a1",
            command_summary: "a payout approval for 184,000",
            current_level: "BOUND",
            required_level: "ELEVATED",
          },
        },
      },
    });

    wire.trays = [tray({ id: "a1", amount: 184000, approveCost: null })];
    const { container } = await mount();

    fireEvent.click(pathButton(container, "Approve")!);

    // The 403 is the ceremony's entry point (C3), never a failure notice.
    await waitFor(() =>
      expect(container.ownerDocument.querySelector('[role="dialog"]')).not.toBeNull(),
    );
    expect(container.querySelector(".tr-problem")).toBeNull();
    expect(container.querySelector(".tr-card-settled")).toBeNull();
  });

  it("settles the card only when the server took the act", async () => {
    wire.trays = [tray({ id: "a1", amount: 184000, approveCost: null })];
    const { container } = await mount();

    fireEvent.click(pathButton(container, "Approve")!);
    await waitFor(() => expect(container.querySelector(".tr-card-settled")).not.toBeNull());
    expect(container.querySelector(".tr-title")?.textContent).toBe("Nothing needs you.");
  });
});
