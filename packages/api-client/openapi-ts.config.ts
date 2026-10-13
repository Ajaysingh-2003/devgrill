import { defineConfig } from "@hey-api/openapi-ts";

// Input is written by `uv run python -m devgrill_api.openapi_export` (see root `pnpm gen:api`).
// Output is generated: never edit src/gen by hand. CI fails if regeneration produces a diff.
export default defineConfig({
  input: "./openapi.json",
  output: "src/gen",
  plugins: ["@hey-api/client-fetch", "@hey-api/typescript", "@hey-api/sdk"],
});
