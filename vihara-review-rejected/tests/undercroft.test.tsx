/**
 * DRIVER D10 — the Undercroft (D6 §15). What these pin:
 *
 * - Operator density regardless of the learned value — stamped on the
 *   surface itself.
 * - The manifest inspector answers "why did she show me that": surface,
 *   verdict, component count, cache age off the log the API client
 *   keeps — including a REJECTED manifest, which is precisely the one
 *   the owner will ask about.
 * - Every drill echoes; the two endpoint-less panels are honest
 *   absences, not empty registers.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { parseManifestStream } from "../src/api/genui";
import {
  UndercroftSurface,
  type UndercroftLoaders,
} from "../src/app/UndercroftSurface";

afterEach(cleanup);

const NOW = new Date("2026-07-29T10:00:30Z");

function harness(): { loaders: UndercroftLoaders; echoes: string[] } {
  const echoes: string[] = [];
  return {
    echoes,
    loaders: {
      signals: async () => [
        { id: "s1", type: "email.inbound", status: "completed" },
      ],
      triggers: async () => [{ id: "t1", type_pattern: "email.*" }],
      envelope: async () => ({ envelope_usd: 30 }),
      executions: async () => [
        {
          id: "run-12345678",
          entity_id: "e1",
          status: "COMPLETED",
          total_cost_usd: 0,
          execution_time_ms: null,
          error_message: null,
          started_at: null,
          completed_at: null,
          created_at: "2026-07-29T09:00:00",
        },
      ],
      trace: async () => ({ steps: ["gate"] }),
      defs: async () => [],
      routing: async () => [],
      manifestLog: () => [
        {
          surface: "still",
          renderer: "S",
          density: "novice",
          verdict: "render" as const,
          issued_at: "2026-07-29T10:00:00Z",
          ttl_seconds: 120,
          manifest_version: 1,
          component_count: 2,
          fetched_at: "2026-07-29T10:00:00Z",
        },
        {
          surface: "district.P08",
          renderer: "S",
          density: "novice",
          verdict: "reject" as const,
          reason: "certified.approval: injected prop",
          fetched_at: "2026-07-29T10:00:10Z",
        },
      ],
      echo: async (echo) => {
        echoes.push(echo.sentence);
      },
    },
  };
}

describe("the undercroft", () => {
  it("is operator density by decree and every drill echoes", async () => {
    const h = harness();
    render(<UndercroftSurface loaders={h.loaders} now={() => NOW} />);
    await waitFor(() => {
      expect(document.querySelector("[data-part='undercroft']")).not.toBeNull();
    });
    expect(
      document
        .querySelector("[data-part='undercroft']")
        ?.getAttribute("data-density"),
    ).toBe("operator");
    fireEvent.click(screen.getByText("envelope"));
    await waitFor(() => {
      expect(h.echoes).toContain("drilled into the envelope register");
    });
  });

  it("the manifest inspector shows verdicts and cache age — rejections included", async () => {
    const h = harness();
    render(<UndercroftSurface loaders={h.loaders} now={() => NOW} />);
    fireEvent.click(screen.getByText("manifests"));
    await waitFor(() => {
      expect(document.querySelector("[data-part='manifest-inspector']")).not.toBeNull();
    });
    const verdicts = [...document.querySelectorAll("[data-part='manifest-verdict']")]
      .map((cell) => cell.textContent);
    expect(verdicts).toContain("render");
    expect(verdicts).toContain("reject");
    // Cache age: fetched at 10:00:00, now 10:00:30 → 30s.
    expect(screen.getByText("30s")).toBeDefined();
  });

  it("runs drill to the trace", async () => {
    const h = harness();
    render(<UndercroftSurface loaders={h.loaders} now={() => NOW} />);
    fireEvent.click(screen.getByText("runs"));
    await waitFor(() => {
      expect(document.querySelector("[data-part='runs-register']")).not.toBeNull();
    });
    fireEvent.click(screen.getByText("trace"));
    await waitFor(() => {
      expect(document.body.textContent).toContain('"gate"');
    });
  });

  it("endpoint-less panels are honest absences", async () => {
    const h = harness();
    render(<UndercroftSurface loaders={h.loaders} now={() => NOW} />);
    await waitFor(() => {
      expect(
        document.querySelector("[data-part='undercroft-absences']"),
      ).not.toBeNull();
    });
  });
});

describe("the API client's manifest log", () => {
  it("records what the wire could not even parse", () => {
    const parsed = parseManifestStream("not json at all");
    expect(parsed.kind).toBe("rejected");
  });
});
