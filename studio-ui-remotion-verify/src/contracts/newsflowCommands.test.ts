import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { NEWSFLOW_COMMANDS } from "./newsflowCommands";

describe("NewsFlow renderer command contract", () => {
  it("registers every critical Light production path", () => {
    expect(NEWSFLOW_COMMANDS).toContain("save-settings");
    expect(NEWSFLOW_COMMANDS).toContain("generate-ideas");
    expect(NEWSFLOW_COMMANDS).toContain("generate-scenarios");
    expect(NEWSFLOW_COMMANDS).toContain("generate-voice-queue");
    expect(NEWSFLOW_COMMANDS).toContain("generate-voice-range");
    expect(NEWSFLOW_COMMANDS).toContain("generate-covers");
    expect(NEWSFLOW_COMMANDS).toContain("run-montage-queue");
    expect(NEWSFLOW_COMMANDS).toContain("generate-seo");
    expect(NEWSFLOW_COMMANDS).toContain("generate-tags");
    expect(NEWSFLOW_COMMANDS).toContain("confirm-publication-v2-distribution");
  });

  it("does not permit an unregistered renderer command", () => {
    expect(NEWSFLOW_COMMANDS).not.toContain("not-a-newsflow-command");
  });

  it("keeps the preload, Electron IPC and Python bridge command boundary wired", () => {
    const preload = readFileSync(resolve(process.cwd(), "electron/preload.mts"), "utf8");
    const main = readFileSync(resolve(process.cwd(), "electron/main.ts"), "utf8");
    const bridge = readFileSync(resolve(process.cwd(), "../scriptor/bridge.py"), "utf8");

    expect(preload).toContain("newsflow:command");
    expect(main).toContain("ipcMain.handle('newsflow:command'");
    for (const command of ["generate-ideas", "generate-scenarios", "generate-covers", "run-montage-queue"]) {
      expect(bridge).toContain(`command == "${command}"`);
    }
  });

  it("keeps the voice-range action aligned with the current bridge payload", () => {
    const contract = readFileSync(resolve(process.cwd(), "src/contracts/newsflowCommands.ts"), "utf8");
    const bridge = readFileSync(resolve(process.cwd(), "../scriptor/bridge.py"), "utf8");

    expect(contract).toContain('"generate-voice-range": { rangeId?: string; force?: boolean }');
    expect(bridge).toContain('range_id = str(payload.get("rangeId") or "").strip()');
  });

  it("keeps queue-all voice generation on its current dedicated handler", () => {
    const bridge = readFileSync(resolve(process.cwd(), "../scriptor/bridge.py"), "utf8");
    const registry = readFileSync(resolve(process.cwd(), "../scriptor/command_contract.py"), "utf8");

    expect(bridge).toContain('command == "generate-voice-queue"');
    expect(registry).toContain('"generate-voice-queue": CommandRegistration("generate_voice_queue"');
  });
});
