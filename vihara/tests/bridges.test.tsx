/**
 * DRIVER D11 — the Bridges & Gates board (D6 §14). What these pin:
 *
 * - A bridge without an expiry date says "unknown — not checked", never
 *   implies health.
 * - Binding is the certified act: refusal → ceremony → retry whole →
 *   bound and echoed.
 * - A sync.conflict renders as a dispute keeping the losing delta —
 *   master-wins stated, nothing lost, nothing re-fought.
 * - Gates with no read endpoints render honest absences.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type {
  CatalogConnector,
  ConnectorBinding,
  SyncConflict,
} from "../src/api/bridges";
import { BridgesSurface, type BridgesLoaders } from "../src/app/BridgesSurface";

afterEach(cleanup);

const ZOHO: CatalogConnector = {
  connector_id: "zoho_books",
  domain: "accounting",
  display_name: "Zoho Books",
  backend: "MCP_SERVER",
  auth: "api_key",
  masters: ["Invoice", "Payment"],
  bindable: true,
};

const BOUND: ConnectorBinding = {
  connector_id: "zoho_books",
  status: "active",
  credentials_expire_at: null,
};

const CONFLICT: SyncConflict = {
  signal_id: "sig-1",
  def_name: "Invoice",
  record_id: "rec-1",
  losing_delta: { total: 90000 },
  connector: "zoho_books",
  created_at: "2026-07-29T00:00:00",
};

const REFUSAL_ERROR = {
  response: {
    status: 403,
    data: {
      detail: {
        error: "step_up_required",
        tier: "T2",
        why: "credentials need a ceremony",
        reason: "step up to T2 first",
        needs_step_up: true,
        needs_oob: false,
        locked: false,
        command_ref: "connector-bind:zoho_books",
        command_summary: "connecting zoho_books",
      },
    },
  },
};

function harness(overrides: Partial<BridgesLoaders> = {}): {
  loaders: BridgesLoaders;
  echoes: string[];
  bound: string[];
} {
  const echoes: string[] = [];
  const bound: string[] = [];
  return {
    echoes,
    bound,
    loaders: {
      catalog: async () => [ZOHO],
      bindings: async () => [],
      bind: async (connectorId) => {
        bound.push(connectorId);
        return BOUND;
      },
      social: async () => [{ id: "g1", platform: "linkedin", status: "active" }],
      conflicts: async () => [CONFLICT],
      echo: async (echo) => {
        echoes.push(echo.sentence);
      },
      ceremony: {
        passkey: async () => ({ ok: true }),
        totp: async () => ({ ok: true }),
      },
      ...overrides,
    },
  };
}

describe("the bridges board", () => {
  it("an expiry-less bound bridge says unknown, never implies checked", async () => {
    const h = harness({ bindings: async () => [BOUND] });
    render(<BridgesSurface loaders={h.loaders} />);
    await waitFor(() => {
      expect(document.querySelector("[data-part='expiry-unknown']")).not.toBeNull();
    });
    expect(screen.getByText(/not checked, not implied/)).toBeDefined();
  });

  it("binding meets the ceremony, retries whole, echoes", async () => {
    let refused = false;
    const h = harness();
    const realBind = h.loaders.bind;
    h.loaders.bind = async (connectorId, credentials) => {
      if (!refused) {
        refused = true;
        throw REFUSAL_ERROR;
      }
      return realBind(connectorId, credentials);
    };
    render(<BridgesSurface loaders={h.loaders} />);
    await waitFor(() => {
      expect(screen.getByText(/connect… T2/)).toBeDefined();
    });
    fireEvent.click(screen.getByText(/connect… T2/));
    fireEvent.change(screen.getByLabelText(/Zoho Books credential/), {
      target: { value: "secret" },
    });
    fireEvent.click(screen.getByText("bind"));
    await waitFor(() => {
      expect(document.querySelector("[data-part='ceremony']")).not.toBeNull();
    });
    fireEvent.change(screen.getByLabelText(/one-time code/), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByText("verify"));
    await waitFor(() => {
      expect(h.bound).toEqual(["zoho_books"]);
    });
    expect(h.echoes).toContain("connected Zoho Books");
  });

  it("a sync.conflict is a dispute that keeps the losing delta", async () => {
    const h = harness();
    render(<BridgesSurface loaders={h.loaders} />);
    await waitFor(() => {
      expect(document.querySelector("[data-part='dispute']")).not.toBeNull();
    });
    expect(screen.getByText(/the master \(zoho_books\) won/)).toBeDefined();
    expect(document.body.textContent).toContain('{"total":90000}');
  });

  it("gates list what is connected and say what cannot be read yet", async () => {
    const h = harness();
    render(<BridgesSurface loaders={h.loaders} />);
    await waitFor(() => {
      expect(document.querySelector("[data-part='gate']")).not.toBeNull();
    });
    expect(screen.getByText("linkedin")).toBeDefined();
    expect(document.querySelector("[data-part='gates-absences']")).not.toBeNull();
  });
});
