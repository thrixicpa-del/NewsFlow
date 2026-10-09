import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { stripTypeScriptTypes } from "node:module";
import { runInNewContext } from "node:vm";
import { describe, expect, it, vi } from "vitest";

// Execute the real scheduler without importing Electron or touching providers.
const source = readFileSync(resolve(process.cwd(), "electron/main.ts"), "utf8");
const scheduler = stripTypeScriptTypes(source.slice(
  source.indexOf("let fastGenResumeRunning = false;"), source.indexOf("function createWindow()"),
));

async function run(settings?: { rateAutoResume?: boolean; generationPaused?: boolean }) {
  const callCore = vi.fn(async (_name: string, _payload?: Record<string, unknown>) => ({ coverSettings: settings,
    covers: [{ status: "Ожидает лимит FastGen", rate_limit_wait_until: "2026-01-01T00:00:00Z" }] }));
  class MinuteOne extends Date { getMinutes() { return 1; } }
  const resume = runInNewContext(scheduler + "\nresumeFastGenAtHourlyReset;", { callCore, Date: MinuteOne });
  await resume();
  if (callCore.mock.calls.some(([name]) => name === "resume-cover-generation")) {
    expect(callCore).toHaveBeenCalledWith("resume-cover-generation", { automatic: true });
  }
  return callCore.mock.calls.map((args) => args[0]);
}

describe("hourly cover resume respects operator settings", () => {
  it("does not resume when auto-resume is disabled", async () => {
    expect(await run({ rateAutoResume: false })).toEqual(["snapshot"]);
  });
  it("does not override a manual generation pause", async () => {
    expect(await run({ rateAutoResume: true, generationPaused: true })).toEqual(["snapshot"]);
  });
  it("does not infer paid permission from missing settings", async () => {
    expect(await run()).toEqual(["snapshot"]);
  });
  it("retains the enabled auto-resume route", async () => {
    expect(await run({ rateAutoResume: true, generationPaused: false }))
      .toEqual(["snapshot", "refresh-fastgen", "resume-cover-generation"]);
  });
});
