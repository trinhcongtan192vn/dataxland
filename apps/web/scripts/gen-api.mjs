// Sinh kiểu TypeScript từ OpenAPI của services/api (spec 05 §10). Chạy: pnpm --filter web gen:api
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "../../..");
const out = resolve(here, "../lib/api");
mkdirSync(out, { recursive: true });

const json = execFileSync("uv", ["run", "python", "scripts/dump_openapi.py"], {
  cwd: resolve(repo, "services/api"),
  env: { ...process.env, PYTHONUTF8: "1", DX_REPO_ROOT: repo },
  encoding: "utf-8",
  maxBuffer: 64 * 1024 * 1024,
});
writeFileSync(resolve(out, "openapi.json"), json);
execFileSync("npx", ["openapi-typescript", resolve(out, "openapi.json"), "-o", resolve(out, "schema.d.ts")], {
  cwd: resolve(here, ".."),
  stdio: "inherit",
  shell: process.platform === "win32",
});
