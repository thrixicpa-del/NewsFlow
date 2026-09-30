import { deflateRawSync } from "node:zlib";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { readReadyScenarioFiles } from "./scenario-import.js";

function storedZip(entries: Array<{ name: string; text: string }>): Buffer {
  const chunks: Buffer[] = [];
  const central: Buffer[] = [];
  let offset = 0;
  for (const entry of entries) {
    const name = Buffer.from(entry.name, "utf8");
    const input = Buffer.from(entry.text, "utf8");
    const data = deflateRawSync(input);
    const header = Buffer.alloc(30);
    header.writeUInt32LE(0x04034b50, 0);
    header.writeUInt16LE(20, 4);
    header.writeUInt16LE(0, 6);
    header.writeUInt16LE(8, 8);
    header.writeUInt32LE(0, 14);
    header.writeUInt32LE(data.length, 18);
    header.writeUInt32LE(input.length, 22);
    header.writeUInt16LE(name.length, 26);
    header.writeUInt16LE(0, 28);
    const local = Buffer.concat([header, name, data]);
    chunks.push(local);

    const directory = Buffer.alloc(46);
    directory.writeUInt32LE(0x02014b50, 0);
    directory.writeUInt16LE(20, 4);
    directory.writeUInt16LE(20, 6);
    directory.writeUInt16LE(0, 8);
    directory.writeUInt16LE(8, 10);
    directory.writeUInt32LE(0, 16);
    directory.writeUInt32LE(data.length, 20);
    directory.writeUInt32LE(input.length, 24);
    directory.writeUInt16LE(name.length, 28);
    directory.writeUInt16LE(0, 30);
    directory.writeUInt16LE(0, 32);
    directory.writeUInt16LE(0, 34);
    directory.writeUInt16LE(0, 36);
    directory.writeUInt32LE(0, 38);
    directory.writeUInt32LE(offset, 42);
    central.push(Buffer.concat([directory, name]));
    offset += local.length;
  }
  const centralData = Buffer.concat(central);
  const trailer = Buffer.alloc(22);
  trailer.writeUInt32LE(0x06054b50, 0);
  trailer.writeUInt16LE(entries.length, 8);
  trailer.writeUInt16LE(entries.length, 10);
  trailer.writeUInt32LE(centralData.length, 12);
  trailer.writeUInt32LE(offset, 16);
  return Buffer.concat([...chunks, centralData, trailer]);
}

describe("readReadyScenarioFiles", () => {
  it("imports multiple text files and ZIP entries with filename titles", async () => {
    const root = await mkdtemp(join(tmpdir(), "newsflow-ready-scenarios-"));
    try {
      const txt = join(root, "Первый сюжет.txt");
      const zip = join(root, "пакет.zip");
      await writeFile(txt, "Текст первого сценария", "utf8");
      await writeFile(zip, storedZip([
        { name: "nested/Второй сюжет.md", text: "Текст второго сценария" },
        { name: "ignored.jpg", text: "не сценарий" },
      ]));

      await expect(readReadyScenarioFiles([txt, zip])).resolves.toEqual([
        { title: "Первый сюжет", text: "Текст первого сценария" },
        { title: "Второй сюжет", text: "Текст второго сценария" },
      ]);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  it("rejects unsafe archive paths instead of importing them", async () => {
    const root = await mkdtemp(join(tmpdir(), "newsflow-ready-scenarios-"));
    try {
      const zip = join(root, "unsafe.zip");
      await writeFile(zip, storedZip([{ name: "../outside.txt", text: "Нельзя импортировать" }]));

      await expect(readReadyScenarioFiles([zip])).rejects.toThrow("небезопасный путь");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});
