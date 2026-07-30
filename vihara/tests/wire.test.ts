import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { parseManifestStream } from "../src/api/genui";
import { assessManifest } from "../src/manifest/refusals";
import { resolve } from "../src/manifest/registry";
import { FillSchema, ScaffoldSchema } from "../src/manifest/schema";

/**
 * SUB T7 — the cross-language half of the wire gate.
 *
 * `tests/fixtures/*.ndjson` is not test data somebody typed: it is the exact
 * body `/ai/genui/manifest` streams, captured from the composer by
 * `backend/scripts/export_genui_fixtures.py`. The backend's own gate
 * (`tests/unit/test_genui_fixture_export.py`) pins the capture to the composer.
 * That gate alone only compares Python to a snapshot of Python — it goes green
 * on a composer change that no client can read. This file is the other end:
 * the SAME bytes through the SAME parser, schemas and registry the browser
 * runs. Drift on either side turns one of the two suites red inside the same
 * commit range, which is the only reason the fixtures are worth keeping.
 *
 * So the assertions here deliberately go through production code
 * (`parseManifestStream`, `assessManifest`, `resolve`) rather than
 * re-describing the format — a test that re-implements the parser proves the
 * test understands the wire, not that the app does.
 */
const FIXTURES = path.resolve(__dirname, "fixtures");

/** What `SURFACES` in the export script asks the composer for. Kept as data so
 *  the coverage check below can compare it against the directory. */
const CASES = [
  ["still.ndjson", "still", "S"],
  ["terrace_sheet.ndjson", "terrace.sheet", "S"],
  ["terrace_world.ndjson", "terrace", "W"],
  ["district_p06.ndjson", "district.P06", "S"],
] as const;

function load(name: string): string {
  return readFileSync(path.join(FIXTURES, name), "utf8");
}

/** The two NDJSON frames, unparsed by anything but JSON — so the schema
 *  assertions below are made against the raw wire, not against a merged
 *  object the client already normalised. */
function frames(name: string): [unknown, unknown] {
  const lines = load(name)
    .split("\n")
    .filter((line) => line.trim().length > 0);
  expect(lines, `${name} must be exactly two NDJSON frames`).toHaveLength(2);
  return [JSON.parse(lines[0]!), JSON.parse(lines[1]!)];
}

describe("the composer's real wire output, read by the client (SUB T7)", () => {
  it("covers every fixture the export script writes", () => {
    // A surface added to SURFACES lands here as a file nothing parses. Without
    // this the Python side could grow a surface the client has never read and
    // both suites would stay green.
    const onDisk = readdirSync(FIXTURES).filter((f) => f.endsWith(".ndjson")).sort();
    expect(onDisk).toEqual(CASES.map(([file]) => file).sort());
  });

  for (const [file, surface, renderer] of CASES) {
    describe(`${surface} (${renderer})`, () => {
      it("validates frame by frame against the wire schemas", () => {
        const [scaffold, fill] = frames(file);
        expect(ScaffoldSchema.safeParse(scaffold).success).toBe(true);
        expect(FillSchema.safeParse(fill).success).toBe(true);
      });

      it("parses, and carries the surface the exporter asked for", () => {
        const parsed = parseManifestStream(load(file));
        expect(parsed.kind, `${file}: ${parsed.kind === "rejected" ? parsed.reason : ""}`).toBe(
          "ok",
        );
        if (parsed.kind !== "ok") return;
        expect(parsed.manifest.surface_id).toBe(surface);
        expect(parsed.manifest.renderer).toBe(renderer);
        // Guards every "all of them render" assertion below from passing
        // vacuously on an empty composition.
        expect(parsed.manifest.components.length).toBeGreaterThan(0);
      });

      it("names only component types this client's registry resolves", () => {
        const parsed = parseManifestStream(load(file));
        if (parsed.kind !== "ok") throw new Error(`${file} must parse`);
        for (const component of parsed.manifest.components) {
          expect(
            resolve(component.type),
            `${component.type} is on the wire but not in the client registry`,
          ).toMatchObject({ kind: "ok" });
        }
      });

      it("survives the refusal ladder with no placeholders", () => {
        const parsed = parseManifestStream(load(file));
        if (parsed.kind !== "ok") throw new Error(`${file} must parse`);
        const assessment = assessManifest(parsed.manifest);
        expect(
          assessment.verdict,
          assessment.verdict === "reject" ? assessment.reason : "",
        ).toBe("render");
        if (assessment.verdict !== "render") return;
        // Placeholders are the honest answer to a component we cannot render,
        // but never on a surface we composed ourselves: one here means the two
        // ends disagree about a type, a prop or a binding source.
        for (const disposition of assessment.dispositions) {
          expect(
            disposition,
            disposition.kind === "placeholder" ? disposition.reason : "",
          ).toMatchObject({ kind: "render" });
        }
      });

      it("actually merges the fill frame into the scaffold", () => {
        // The scaffold frame carries no props or bindings — every one of them
        // arrives in the fill. If the merge silently no-opped, the ladder above
        // would still pass, so assert the second frame reached the components.
        const [, fillRaw] = frames(file);
        const fill = FillSchema.parse(fillRaw);
        const parsed = parseManifestStream(load(file));
        if (parsed.kind !== "ok") throw new Error(`${file} must parse`);
        const byId = new Map(parsed.manifest.components.map((c) => [c.id, c]));
        expect(Object.keys(fill.components).length).toBeGreaterThan(0);
        for (const [id, patch] of Object.entries(fill.components)) {
          const merged = byId.get(id);
          expect(merged, `fill names ${id}, which the scaffold never declared`).toBeDefined();
          if (patch.props !== undefined) expect(merged?.props).toEqual(patch.props);
          if (patch.bindings !== undefined) expect(merged?.bindings).toEqual(patch.bindings);
        }
      });
    });
  }

  it("has the W terrace name its sheet, and ships that sheet as a fixture (L9)", () => {
    // L9: a world surface must always offer a sheet equivalent. The client
    // refuses a W manifest without one, so the composer naming a sheet it does
    // not compose would be a dead end the ladder cannot see.
    const parsed = parseManifestStream(load("terrace_world.ndjson"));
    if (parsed.kind !== "ok") throw new Error("terrace must parse");
    expect(parsed.manifest.sheet_equivalent).toBe("terrace.sheet");

    const sheet = parseManifestStream(load("terrace_sheet.ndjson"));
    if (sheet.kind !== "ok") throw new Error("the sheet must parse");
    expect(sheet.manifest.surface_id).toBe(parsed.manifest.sheet_equivalent);
    expect(sheet.manifest.renderer).toBe("S");
  });
});
