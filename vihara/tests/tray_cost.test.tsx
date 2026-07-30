import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TraySurface } from "../src/surfaces/TraySurface";
import { TRAY } from "../src/fixtures/estate";

/**
 * D5 §4.1: `paths[].cost` is `null` on the tray endpoint until DRIVER's
 * estimator exists, and the contract admits that absence honestly rather than
 * inventing a number.
 *
 * The rendering rule is that a null cost renders as **nothing at all** — never
 * "₹0", never "—", never "cost unknown". On a payment card an invented zero is
 * the worst available bug, so it is held by a test rather than by a convention.
 */
describe("the tray's cost line", () => {
  it("renders a cost when the endpoint gives one", () => {
    const { container } = render(<TraySurface onEcho={vi.fn()} />);
    // The first card is open by default and its certified path carries a cost.
    // Scoped to the path button: the same figure also appears in the facts well,
    // so an unscoped query matches twice and proves nothing about the button.
    const withCost = TRAY[0]!.paths.find((p) => p.cost !== null)!;
    const button = [...container.querySelectorAll("button.tr-path")].find((b) =>
      b.textContent?.includes(withCost.label),
    );
    expect(button).toBeDefined();
    expect(button!.querySelector(".tr-path-cost")?.textContent).toBe(withCost.cost);
  });

  it("renders nothing at all when the cost is null", () => {
    const { container } = render(<TraySurface onEcho={vi.fn()} />);
    const nullCostPath = TRAY[0]!.paths.find((p) => p.cost === null)!;

    const button = [...container.querySelectorAll("button.tr-path")].find((b) =>
      b.textContent?.includes(nullCostPath.label),
    );
    expect(button, `no button for path "${nullCostPath.label}"`).toBeDefined();

    // No cost element inside it...
    expect(button!.querySelector(".tr-path-cost")).toBeNull();
    // ...and none of the shapes an invented cost would take.
    expect(button!.textContent).toBe(nullCostPath.label);
    for (const forbidden of ["₹0", "—", "-", "0.00", "unknown", "n/a", "N/A"]) {
      expect(button!.textContent).not.toContain(forbidden);
    }
  });

  it("never prints a currency symbol on a path whose cost is null", () => {
    const { container } = render(<TraySurface onEcho={vi.fn()} />);
    for (const card of TRAY) {
      for (const path of card.paths) {
        if (path.cost !== null) continue;
        const button = [...container.querySelectorAll("button.tr-path")].find((b) =>
          b.textContent?.includes(path.label),
        );
        if (!button) continue; // card not open in this render
        expect(button.textContent).not.toMatch(/[₹$€£]/);
      }
    }
  });
});
