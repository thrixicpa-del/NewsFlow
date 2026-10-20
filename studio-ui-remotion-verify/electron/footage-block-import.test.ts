import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import * as textReader from "./strict-text-file.js";

const folders: string[] = [];
const fixture = (bytes: Buffer) => {
  const folder = mkdtempSync(join(tmpdir(), "newsflow-footage-txt-"));
  folders.push(folder);
  const file = join(folder, "blocks.txt");
  writeFileSync(file, bytes);
  return file;
};
afterEach(() => {
  for (const folder of folders.splice(0))
    rmSync(folder, { recursive: true, force: true });
});

describe("Footage block TXT native transport", () => {
  it("preserves every UTF8 pair, BOM and line endings for a file beyond the prompt limit", () => {
    const text = "Тема\r\n\r\nБлок футажей ✨\r\n\r\n".repeat(30_000);
    const file = fixture(Buffer.from("\ufeff" + text, "utf8"));
    expect(textReader.readStrictUtf8FootageBlockText(file)).toBe(text);
  });
  it("rejects malformed UTF8 and binary controls with actionable errors", () => {
    expect(() =>
      textReader.readStrictUtf8FootageBlockText(
        fixture(Buffer.from([0xc3, 0x28])),
      ),
    ).toThrow("UTF-8");
    expect(() =>
      textReader.readStrictUtf8FootageBlockText(
        fixture(Buffer.from("Тема\0блок")),
      ),
    ).toThrow("управляющие символы");
  });
  it("wires the strict reader through one trusted single TXT picker", () => {
    const main = readFileSync(
      resolve(process.cwd(), "electron/main.ts"),
      "utf8",
    );
    const preload = readFileSync(
      resolve(process.cwd(), "electron/preload.cts"),
      "utf8",
    );
    const handler = main.match(
      /handleTrusted\('newsflow:choose-footage-block-pairs',[\s\S]*?\n\}\);/,
    )?.[0];
    expect(handler).toContain("properties: ['openFile']");
    expect(handler).toContain("extensions: ['txt']");
    expect(handler).toContain("readStrictUtf8FootageBlockText(file)");
    expect(preload).toContain(
      "chooseFootageBlockPairs: () => ipcRenderer.invoke('newsflow:choose-footage-block-pairs')",
    );
  });
});
