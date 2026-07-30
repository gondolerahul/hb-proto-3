/**
 * SUB T4 — the API client's laws.
 *
 * The one that matters is the storage pin: **no storage API appears
 * anywhere under src/** — the access token lives in memory and the refresh
 * token in an HttpOnly cookie this code cannot read, so an XSS on the app
 * that renders generated UI has nothing durable to steal (VP-01). The pin
 * covers all of src/, not just the client, because the failure mode is a
 * convenience cache added far from auth.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  csrfFromCookie,
  getAccessToken,
  logout,
  setAccessToken,
} from "../src/api/client";
import { parseManifestStream } from "../src/api/genui";

const appRoot = path.resolve(
  path.dirname(new URL(import.meta.url).pathname), "..");

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) out.push(...sourceFiles(full));
    else if (/\.(ts|tsx)$/.test(name) && !name.endsWith(".d.ts")) out.push(full);
  }
  return out;
}

describe("the storage pin (VP-01)", () => {
  it("no storage API anywhere under src/", () => {
    const offenders: string[] = [];
    for (const file of sourceFiles(path.join(appRoot, "src"))) {
      const text = readFileSync(file, "utf-8");
      if (/localStorage|sessionStorage|indexedDB/.test(text)) {
        offenders.push(path.relative(appRoot, file));
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe("the in-memory token", () => {
  it("sets, reads and clears without touching anything durable", () => {
    setAccessToken("abc");
    expect(getAccessToken()).toBe("abc");
    logout();
    expect(getAccessToken()).toBeNull();
  });
});

describe("csrfFromCookie", () => {
  it("finds the double-submit leg among other cookies", () => {
    expect(csrfFromCookie("a=1; csrf_token=xyz; b=2")).toBe("xyz");
    expect(csrfFromCookie("csrf_token=with=equals")).toBe("with=equals");
  });

  it("absence is null, never empty-string truthiness", () => {
    expect(csrfFromCookie("")).toBeNull();
    expect(csrfFromCookie("csrf_token=")).toBeNull();
    expect(csrfFromCookie("other=1")).toBeNull();
  });
});

describe("parseManifestStream", () => {
  const scaffold = JSON.stringify({
    part: "scaffold",
    manifest_version: 1,
    surface_id: "still",
    renderer: "S",
    plane: "live",
    depth: 0,
    density: "novice",
    layout: { kind: "stack", regions: ["r"] },
    components: [{ id: "c1", type: "primitive.pulse@1", region: "r" }],
    issued_at: "t",
    ttl_seconds: 120,
  });

  it("merges a well-formed two-part stream", () => {
    const fill = JSON.stringify({
      part: "fill",
      components: {
        c1: { props: { label: "p" }, bindings: [{ source: "estate.pulse" }] },
      },
    });
    const parsed = parseManifestStream(`${scaffold}\n${fill}\n`);
    expect(parsed.kind).toBe("ok");
    if (parsed.kind === "ok") {
      expect(parsed.manifest.components[0]?.props).toEqual({ label: "p" });
    }
  });

  it("rejects a stream that is not two parts", () => {
    expect(parseManifestStream(scaffold).kind).toBe("rejected");
    expect(parseManifestStream("").kind).toBe("rejected");
  });

  it("rejects non-JSON and mislabelled parts loudly", () => {
    expect(parseManifestStream(`${scaffold}\nnot json`).kind).toBe("rejected");
    expect(
      parseManifestStream(`${scaffold}\n${scaffold}`).kind,
    ).toBe("rejected");
  });
});
