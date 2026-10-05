import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const mainSource = readFileSync(resolve(process.cwd(), "electron/main.ts"), "utf8");

describe("Core response transport", () => {
  it("streams Core JSON to a disposable file instead of imposing a stdout maxBuffer", () => {
    expect(mainSource).toContain("createWriteStream(responsePath");
    expect(mainSource).toContain("child.stdout.pipe(responseStream)");
    expect(mainSource).toContain("stdio: ['ignore', 'pipe', 'pipe']");
    expect(mainSource).not.toContain("maxBuffer:");
    expect(mainSource).not.toContain("execFile(");
  });

  it("keeps only bounded stderr diagnostics while parsing the complete response file", () => {
    expect(mainSource).toContain("stderr.length < 4096");
    expect(mainSource).toContain("JSON.parse(readFileSync(responsePath, 'utf8'))");
  });
});
