// Regenerate the typed API surface from the exported backend contract.
//
// No backend has to be running: the contract is a checked-in file. The
// producer is on the other side —
//   cd backend && poetry run python scripts/export_openapi.py
// writes src/api/openapi.json here, and backend
// tests/unit/test_openapi_export.py fails when that export drifts from the
// live app. So the chain is: backend route change -> red backend test ->
// re-export -> `npm run gen:api` -> both artifacts committed together.
//
//   npm run gen:api
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = path.join(here, "..", "src", "api", "openapi.json");
const target = path.join(here, "..", "src", "api", "schema.d.ts");

execFileSync(
  path.join(here, "..", "node_modules", ".bin", "openapi-typescript"),
  [source, "-o", target],
  { stdio: "inherit" },
);
