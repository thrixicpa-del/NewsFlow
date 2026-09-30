import { createRequire } from "node:module";
import { extname, basename } from "node:path";
import { open, stat } from "node:fs/promises";

export type ReadyScenarioText = { title: string; text: string };

type ZipEntry = {
  path: string;
  type: "File" | "Directory";
  uncompressedSize?: number;
  stream: () => AsyncIterable<Uint8Array>;
};

type ZipDirectory = { files: ZipEntry[] };

const require = createRequire(import.meta.url);
const unzipper = require("unzipper") as {
  Open: { file: (path: string) => Promise<ZipDirectory> };
};

const TEXT_EXTENSIONS = new Set([".txt", ".md", ".markdown"]);
const MAX_TEXT_BYTES = 1_000_000;
const MAX_ARCHIVE_BYTES = 20_000_000;
const MAX_ARCHIVE_ENTRIES = 100;
const MAX_ARCHIVE_TEXT_BYTES = 10_000_000;
const BINARY_CONTROL = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]/;

function isTextFile(name: string): boolean {
  return TEXT_EXTENSIONS.has(extname(name).toLowerCase());
}

function titleFor(name: string): string {
  return basename(name, extname(name)).trim();
}

function assertSafeArchivePath(name: string): void {
  const normalized = name.replace(/\\/g, "/");
  if (
    !normalized ||
    normalized.startsWith("/") ||
    /^[A-Za-z]:\//.test(normalized) ||
    normalized.split("/").some((part) => part === "..")
  ) {
    throw new Error("Архив содержит небезопасный путь к файлу сценария.");
  }
}

function decodeScenarioText(contents: Buffer, name: string): string {
  let text: string;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(contents);
  } catch {
    throw new Error(`Файл «${name}» должен быть строго в кодировке UTF-8.`);
  }
  if (BINARY_CONTROL.test(text)) {
    throw new Error(`Файл «${name}» содержит служебные бинарные символы.`);
  }
  return text.trim();
}

async function readLimitedText(path: string, limit = MAX_TEXT_BYTES): Promise<string> {
  const metadata = await stat(path);
  if (metadata.size > limit) {
    throw new Error(`Файл «${basename(path)}» больше 1 МБ. Разделите его на несколько TXT.`);
  }
  const handle = await open(path, "r");
  try {
    const contents = Buffer.allocUnsafe(limit + 1);
    const { bytesRead } = await handle.read(contents, 0, contents.length, 0);
    if (bytesRead > limit) {
      throw new Error(`Файл «${basename(path)}» больше 1 МБ. Разделите его на несколько TXT.`);
    }
    return decodeScenarioText(contents.subarray(0, bytesRead), basename(path));
  } finally {
    await handle.close();
  }
}

async function readZipEntry(entry: ZipEntry): Promise<Buffer> {
  const declaredSize = entry.uncompressedSize;
  if (typeof declaredSize === "number" && declaredSize > MAX_TEXT_BYTES) {
    throw new Error(`Файл «${entry.path}» в архиве больше 1 МБ. Разделите его на несколько TXT.`);
  }
  const chunks: Buffer[] = [];
  let length = 0;
  for await (const chunk of entry.stream()) {
    length += chunk.length;
    if (length > MAX_TEXT_BYTES) {
      throw new Error(`Файл «${entry.path}» в архиве больше 1 МБ. Разделите его на несколько TXT.`);
    }
    chunks.push(Buffer.from(chunk));
  }
  return Buffer.concat(chunks, length);
}

async function readZip(path: string): Promise<ReadyScenarioText[]> {
  const archive = await stat(path);
  if (archive.size > MAX_ARCHIVE_BYTES) {
    throw new Error(`Архив «${basename(path)}» больше 20 МБ.`);
  }
  let directory: ZipDirectory;
  try {
    directory = await unzipper.Open.file(path);
  } catch {
    throw new Error(`Не удалось прочитать ZIP-архив «${basename(path)}».`);
  }
  if (directory.files.length > MAX_ARCHIVE_ENTRIES) {
    throw new Error(`В архиве «${basename(path)}» больше ${MAX_ARCHIVE_ENTRIES} файлов.`);
  }

  const scenarios: ReadyScenarioText[] = [];
  let totalTextBytes = 0;
  for (const entry of directory.files) {
    assertSafeArchivePath(entry.path);
    if (entry.type !== "File" || !isTextFile(entry.path)) continue;
    const contents = await readZipEntry(entry);
    totalTextBytes += contents.length;
    if (totalTextBytes > MAX_ARCHIVE_TEXT_BYTES) {
      throw new Error(`Текстовые сценарии в архиве «${basename(path)}» больше 10 МБ.`);
    }
    const title = titleFor(entry.path);
    const text = decodeScenarioText(contents, entry.path);
    if (title && text) scenarios.push({ title, text });
  }
  return scenarios;
}

/** Read selected local ready-script files without extracting archive paths. */
export async function readReadyScenarioFiles(paths: string[]): Promise<ReadyScenarioText[]> {
  const scenarios: ReadyScenarioText[] = [];
  for (const path of paths) {
    const extension = extname(path).toLowerCase();
    if (extension === ".zip") {
      scenarios.push(...await readZip(path));
      continue;
    }
    if (!isTextFile(path)) {
      throw new Error("Можно выбрать только TXT, Markdown или ZIP со сценариями.");
    }
    const title = titleFor(path);
    const text = await readLimitedText(path);
    if (title && text) scenarios.push({ title, text });
  }
  return scenarios;
}
