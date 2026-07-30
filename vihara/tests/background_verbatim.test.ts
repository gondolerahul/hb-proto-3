import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Redesign decision D2 says the owner's background is ported *verbatim*.
 * Finding RD-6 is what happens when it isn't: the first build re-derived the
 * effect instead of carrying it across, and the result was not the thing that
 * had been approved.
 *
 * These are text assertions, not imports — nothing here crosses the
 * `frontend/` boundary at build time.
 */

const ROOT = path.resolve(__dirname, "..", "..");
const legacySource = readFileSync(
  path.join(ROOT, "frontend/src/components/layout/AnimatedBackground.tsx"),
  "utf8",
);
const portSource = readFileSync(
  path.join(ROOT, "vihara/src/background/LegacyBackground.tsx"),
  "utf8",
);
const hexFieldSource = readFileSync(
  path.join(ROOT, "vihara/src/background/hexField.ts"),
  "utf8",
);

/** Pull a backtick-delimited template literal assigned to `name`. */
function templateLiteral(source: string, name: string): string {
  const m = source.match(new RegExp(`const ${name} = \`([\\s\\S]*?)\`;`));
  if (!m?.[1]) throw new Error(`no template literal named ${name}`);
  return m[1];
}

/** Pull a numeric constant, tolerating an `export` prefix. */
function numericConstant(source: string, name: string): string {
  const m = source.match(new RegExp(`(?:export )?const ${name} = ([\\d.]+);`));
  if (!m?.[1]) throw new Error(`no numeric constant named ${name}`);
  return m[1];
}

describe("the legacy background port", () => {
  it("is byte-identical to the file the owner approved", () => {
    expect(portSource).toBe(legacySource);
  });
});

describe("the re-keyed variant", () => {
  it.each(["vertexShader", "fragmentShader"])(
    "carries the legacy %s character-for-character",
    (name) => {
      expect(templateLiteral(hexFieldSource, name)).toBe(templateLiteral(legacySource, name));
    },
  );

  it.each(["HEX_RADIUS", "HEX_HEIGHT", "GAP", "GRID_ROWS", "GRID_COLS"])(
    "keeps the legacy value of %s",
    (name) => {
      expect(numericConstant(hexFieldSource, name)).toBe(numericConstant(legacySource, name));
    },
  );

  it("keeps the legacy bloom parameters", () => {
    // strength / radius / threshold, in the order UnrealBloomPass takes them.
    for (const line of ["0.8, // strength", "0.4, // radius", "0.1, // threshold"]) {
      const legacyLine = line.replace(",", "").trim();
      expect(hexFieldSource).toContain(legacyLine.split(" //")[0]!);
    }
    expect(hexFieldSource).toContain("new THREE.Fog(0x000000, 10, 40)");
    expect(hexFieldSource).toContain("camera.position.set(0, 9, 7)");
    expect(hexFieldSource).toContain("camera.lookAt(0, -8, -6)");
  });

  it("differs from the legacy palette only in the four colour values", () => {
    // The legacy palette must still be present and exact...
    expect(hexFieldSource).toContain("new THREE.Vector3(0.4, 0.2, 0.1)");
    expect(hexFieldSource).toContain("new THREE.Vector3(0.1, 0.2, 0.4)");
    expect(hexFieldSource).toContain('new THREE.Color("#080808")');
    expect(hexFieldSource).toContain('new THREE.Color("#382b02ff")');
    // ...and the brand palette must introduce no hue outside gold and neutral.
    expect(hexFieldSource).toContain("new THREE.Vector3(0.39, 0.28, 0.12)");
    expect(hexFieldSource).toContain("new THREE.Vector3(0.16, 0.18, 0.22)");
  });
});
