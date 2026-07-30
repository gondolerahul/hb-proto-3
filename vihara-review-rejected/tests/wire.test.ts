/**
 * SUB T7 — the cross-language wire golden: parse the REAL NDJSON the
 * backend's composer streams (captured by scripts/export_genui_fixtures.py,
 * kept honest by the backend's own gate test). If either end of the D4
 * contract drifts, one side's suite goes red in the same commit range.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { parseManifestStream } from "../src/api/genui";
import { assessManifest } from "../src/manifest/refusals";

const fixtures = path.join(
  path.dirname(new URL(import.meta.url).pathname), "fixtures");

function load(name: string): string {
  return readFileSync(path.join(fixtures, name), "utf-8");
}

const CASES = [
  ["still.ndjson", "still", "S"],
  ["terrace_sheet.ndjson", "terrace.sheet", "S"],
  ["terrace_world.ndjson", "terrace", "W"],
  ["district_p06.ndjson", "district.P06", "S"],
] as const;

describe("the backend's real wire output parses and renders", () => {
  for (const [file, surface, renderer] of CASES) {
    it(`${surface} (${renderer})`, () => {
      const parsed = parseManifestStream(load(file));
      expect(parsed.kind).toBe("ok");
      if (parsed.kind !== "ok") return;
      expect(parsed.manifest.surface_id).toBe(surface);
      expect(parsed.manifest.renderer).toBe(renderer);
      const assessment = assessManifest(parsed.manifest);
      expect(assessment.verdict).toBe("render");
      if (assessment.verdict === "render") {
        // Every component the backend composed resolves and renders —
        // no placeholders on our own composed surfaces.
        for (const disposition of assessment.dispositions) {
          expect(disposition.kind).toBe("render");
        }
      }
    });
  }

  it("the W terrace names its sheet, and the sheet fixture is that sheet (L9)", () => {
    const parsed = parseManifestStream(load("terrace_world.ndjson"));
    if (parsed.kind !== "ok") throw new Error("terrace must parse");
    expect(parsed.manifest.sheet_equivalent).toBe("terrace.sheet");
  });
});
