/**
 * Generate the typed API surface from the exported backend contract
 * (D1 §5). The export itself comes from the backend:
 *   cd backend && poetry run python scripts/export_openapi.py
 * then here:
 *   npm run gen:api
 * Both artifacts are checked in; the backend unit test
 * test_openapi_export.py is the gate that catches drift.
 */
import { execFileSync } from "node:child_process";
import path from "node:path";

const here = path.dirname(new URL(import.meta.url).pathname);
const source = path.join(here, "..", "src", "api", "openapi.json");
const target = path.join(here, "..", "src", "api", "schema.d.ts");

execFileSync(
  path.join(here, "..", "node_modules", ".bin", "openapi-typescript"),
  [source, "-o", target],
  { stdio: "inherit" },
);
