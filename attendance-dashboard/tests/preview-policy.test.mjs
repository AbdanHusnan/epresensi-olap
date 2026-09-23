import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/lib/auth/preview-policy.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } });
const { allowLocalPreview } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);
const env = { NODE_ENV: "development", DASHBOARD_LOCAL_PREVIEW: "true", APP_ORIGIN: "http://127.0.0.1:3002" };
const origin = env.APP_ORIGIN;
const host = "127.0.0.1:3002";

test("explicit development preview permits matching loopback origin", () => {
  assert.equal(allowLocalPreview(env, origin, host), true);
});
test("production and test never enable preview", () => {
  for (const NODE_ENV of ["production", "test", undefined]) assert.equal(allowLocalPreview({ ...env, NODE_ENV }, origin, host), false);
});
test("preview must be explicitly enabled", () => {
  for (const DASHBOARD_LOCAL_PREVIEW of [undefined, "false", "1"]) assert.equal(allowLocalPreview({ ...env, DASHBOARD_LOCAL_PREVIEW }, origin, host), false);
});
test("missing, foreign, and mismatched origins or hosts are rejected", () => {
  for (const value of [null, "http://evil.example", "http://localhost:3002"]) assert.equal(allowLocalPreview(env, value, host), false);
  for (const value of [null, "evil.example", "127.0.0.1:3003"]) assert.equal(allowLocalPreview(env, origin, value), false);
});
test("non-loopback and malformed configured origins are rejected", () => {
  for (const value of ["http://dashboard.example", "http://127.0.0.1:3002/path", "invalid", "http://127.0.0.1.evil.example"]) {
    assert.equal(allowLocalPreview({ ...env, APP_ORIGIN: value }, value, value.replace("http://", "")), false);
  }
});
