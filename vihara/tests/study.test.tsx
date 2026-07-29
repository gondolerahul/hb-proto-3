/**
 * DRIVER D12 — the Study (D6 §15a, VP-03). What these pin:
 *
 * - Passkey enrolment lives here: enrolling echoes; zero passkeys is an
 *   honest warning (certified acts will keep asking); removal is plain.
 * - Density stated-vs-learned: the switch writes the preference and the
 *   learned state shows beside it.
 * - Dunning is explicable: read-only renders the ladder in words —
 *   the one surface where quiet must not read as calm.
 * - notify.* toggles write to the existing store, no new namespace.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { StudySurface, type StudyLoaders } from "../src/app/StudySurface";

afterEach(cleanup);

function harness(overrides: Partial<StudyLoaders> = {}): {
  loaders: StudyLoaders;
  echoes: string[];
  writes: { key: string; value: unknown }[];
} {
  const echoes: string[] = [];
  const writes: { key: string; value: unknown }[] = [];
  return {
    echoes,
    writes,
    loaders: {
      me: async () => ({
        id: "u1",
        email: "rahul@northwind.co",
        full_name: "Rahul",
        company_id: "c1",
        role: "admin",
      }),
      passkeys: async () => [
        {
          id: "pk-1",
          label: "MacBook Touch ID",
          created_at: "2026-03-12T00:00:00",
          last_used_at: null,
        },
      ],
      enroll: async () => undefined,
      removePasskey: async () => undefined,
      preferences: async () => ({
        "density.default": { value: "novice", learned: true },
        "notify.push_enabled": { value: true },
      }),
      write: async (key, value) => {
        writes.push({ key, value });
      },
      balance: async () => ({ balance: 4200 }),
      subscription: async () => ({ tier: "growth", subscription_status: "current" }),
      echo: async (echo) => {
        echoes.push(echo.sentence);
      },
      passkeySupported: () => true,
      ...overrides,
    },
  };
}

async function open(h: ReturnType<typeof harness>): Promise<void> {
  render(<StudySurface loaders={h.loaders} />);
  await waitFor(() => {
    expect(document.querySelector("[data-part='study']")).not.toBeNull();
  });
}

describe("security", () => {
  it("lists passkeys, enrolment echoes", async () => {
    const h = harness();
    await open(h);
    await waitFor(() => {
      expect(screen.getByText("MacBook Touch ID")).toBeDefined();
    });
    fireEvent.click(screen.getByText("add a passkey"));
    await waitFor(() => {
      expect(h.echoes).toContain("added a passkey");
    });
  });

  it("zero passkeys is an honest warning, not a blank", async () => {
    const h = harness({ passkeys: async () => [] });
    await open(h);
    await waitFor(() => {
      expect(document.querySelector("[data-part='no-passkeys']")).not.toBeNull();
    });
    expect(screen.getByText(/certified acts will keep asking/)).toBeDefined();
  });
});

describe("density", () => {
  it("stating a density writes the preference and shows the learned note", async () => {
    const h = harness();
    await open(h);
    await waitFor(() => {
      expect(document.querySelector("[data-part='density-learned']")).not.toBeNull();
    });
    fireEvent.click(screen.getByLabelText("operator"));
    await waitFor(() => {
      expect(h.writes).toContainEqual({
        key: "density.default",
        value: "operator",
      });
    });
    expect(h.echoes).toContain("set density to operator");
  });
});

describe("notifications", () => {
  it("toggles write notify.* — the store that already exists", async () => {
    const h = harness();
    await open(h);
    await waitFor(() => {
      expect(screen.getByText("morning story")).toBeDefined();
    });
    fireEvent.click(screen.getByText("morning story"));
    await waitFor(() => {
      expect(h.writes.some((w) => w.key === "notify.morning_story")).toBe(true);
    });
  });
});

describe("billing", () => {
  it("a current subscription shows the wallet plainly", async () => {
    const h = harness();
    await open(h);
    await waitFor(() => {
      expect(screen.getByText("4200")).toBeDefined();
    });
    expect(document.querySelector("[data-part='dunning-explained']")).toBeNull();
  });

  it("read-only explains why the estate went quiet", async () => {
    const h = harness({
      subscription: async () => ({ tier: "solo", subscription_status: "read_only" }),
    });
    await open(h);
    await waitFor(() => {
      expect(document.querySelector("[data-part='dunning-explained']")).not.toBeNull();
    });
    expect(screen.getByText(/parked, not dropped/)).toBeDefined();
  });
});
