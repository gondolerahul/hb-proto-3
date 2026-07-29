/**
 * DRIVER D9 — the Library (D6 §13). What these pin:
 *
 * - The influence sentence binds `questions_answered` (distinct
 *   queries) even when `retrievals` is bigger — the counter must match
 *   the sentence it prints.
 * - Staleness renders live with its reason; a fresh document shows no
 *   warning; NO contradiction section exists anywhere (nothing produces
 *   one yet).
 * - The viewer is the passage read — heading path and content, echoed.
 * - Absent provenance renders as an honest blank, never a checked box.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { DocumentOut } from "../src/api/library";
import { LibrarySurface, type LibraryLoaders } from "../src/app/LibrarySurface";

afterEach(cleanup);

function doc(id: string, overrides: Partial<DocumentOut> = {}): DocumentOut {
  return {
    id,
    filename: `${id}.pdf`,
    file_type: "pdf",
    upload_status: "completed",
    created_at: "2026-03-12T00:00:00",
    source_kind: "upload",
    source_uri: null,
    effective_from: "2026-04-01",
    staleness_state: "fresh",
    staleness_reason: null,
    superseded_by_id: null,
    memory_domain: null,
    ...overrides,
  };
}

const PRICING = doc("pricing-2026", {
  filename: "Pricing 2026.pdf",
  staleness_state: "superseded",
  staleness_reason: "superseded by Pricing 2026-Q3.pdf",
});
const LEGACY = doc("old-note", { source_kind: null, effective_from: null });

function harness(overrides: Partial<LibraryLoaders> = {}): {
  loaders: LibraryLoaders;
  echoes: string[];
} {
  const echoes: string[] = [];
  return {
    echoes,
    loaders: {
      documents: async () => [PRICING, LEGACY],
      influence: async () => ({
        document_id: "pricing-2026",
        window_days: 30,
        retrievals: 173,
        questions_answered: 40,
        peak_distinct_colleagues: 3,
        active_days: 12,
      }),
      passage: async () => ({
        chunks: [
          {
            chunk_index: 0,
            content: "Standard rate is ₹4,000/day.",
            heading_path: "Rates > Standard",
          },
        ],
      }),
      echo: async (echo) => {
        echoes.push(echo.sentence);
      },
      ...overrides,
    },
  };
}

async function open(h: ReturnType<typeof harness>): Promise<void> {
  render(<LibrarySurface loaders={h.loaders} />);
  await waitFor(() => {
    expect(screen.getByText(/Pricing 2026\.pdf/)).toBeDefined();
  });
  fireEvent.click(screen.getByText(/Pricing 2026\.pdf/));
  await waitFor(() => {
    expect(document.querySelector("[data-part='doc-pane']")).not.toBeNull();
  });
}

describe("the influence sentence", () => {
  it("binds questions_answered, never retrievals", async () => {
    const h = harness();
    await open(h);
    await waitFor(() => {
      expect(document.querySelector("[data-part='influence-sentence']")).not.toBeNull();
    });
    const sentence = document.querySelector("[data-part='influence-sentence']");
    expect(sentence?.textContent).toContain("40");
    expect(sentence?.textContent).not.toContain("173");
  });
});

describe("staleness and contradiction", () => {
  it("superseded renders with its reason; no contradiction section exists", async () => {
    const h = harness();
    await open(h);
    expect(screen.getByText(/SUPERSEDED — superseded by Pricing 2026-Q3/)).toBeDefined();
    expect(document.body.textContent).not.toContain("contradict");
  });

  it("absent provenance is an honest blank", async () => {
    const h = harness();
    render(<LibrarySurface loaders={h.loaders} />);
    await waitFor(() => {
      expect(screen.getByText(/old-note\.pdf/)).toBeDefined();
    });
    fireEvent.click(screen.getByText(/old-note\.pdf/));
    await waitFor(() => {
      expect(
        screen.getByText(/Uploaded before provenance existed/),
      ).toBeDefined();
    });
  });
});

describe("the viewer", () => {
  it("opens at the passage with its heading path, and echoes", async () => {
    const h = harness();
    await open(h);
    fireEvent.click(screen.getByText("▸ viewer"));
    await waitFor(() => {
      expect(screen.getByText(/Standard rate is/)).toBeDefined();
    });
    expect(screen.getByText("Rates > Standard")).toBeDefined();
    expect(h.echoes.some((s) => s.includes("at the first passage"))).toBe(true);
  });
});
