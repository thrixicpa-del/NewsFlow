import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFileSync(path.join(root, relative), "utf8");
const fail = (message) => {
  process.stderr.write(`SECURITY_GATE=FAIL: ${message}\n`);
  process.exitCode = 1;
};
const requireSource = (source, fragment, name) => {
  if (!source.includes(fragment)) fail(`missing ${name}`);
};
function commandsFrom(source, declaration, terminator) {
  const start = source.indexOf(declaration);
  const end = source.indexOf(terminator, start);
  if (start < 0 || end < 0) {
    fail(`cannot parse ${declaration}`);
    return [];
  }
  return [...source.slice(start, end).matchAll(/"([a-z0-9-]+)"/g)].map((match) => match[1]);
}

const main = read("electron/main.ts");
const preload = read("electron/preload.cts");
const html = read("index.html");
const rendererCommands = commandsFrom(read("src/contracts/newsflowCommands.ts"), "export const NEWSFLOW_COMMANDS", "] as const");
const electronCommands = commandsFrom(read("electron/allowed-core-commands.ts"), "export const ALLOWED_CORE_COMMANDS", "]);\n");

requireSource(main, "contextIsolation: true", "context isolation");
requireSource(main, "nodeIntegration: false", "node integration disablement");
requireSource(main, "sandbox: true", "renderer sandbox");
requireSource(main, "assertTrustedIpcSender", "trusted IPC sender validation");
requireSource(main, "handleTrusted(", "trusted IPC wrapper");
requireSource(main, "assertAllowedCoreCommand", "core command allow-list enforcement");
requireSource(main, "setWindowOpenHandler", "new-window policy");
requireSource(main, "will-navigate", "navigation policy");
requireSource(main, "openApprovedPath", "approved filesystem-open capability");
requireSource(preload, "contextBridge.exposeInMainWorld", "narrow preload bridge");
requireSource(main, "preload.cjs", "sandbox-compatible CommonJS preload path");
requireSource(preload, "require('electron')", "sandbox-compatible Electron preload import");
if (/\bimport\s+.*from\s+['"]electron['"]/.test(preload)) fail("sandboxed preload cannot use Electron ESM imports");
const ipcHandleCount = [...main.matchAll(/\bipcMain\.handle\(/g)].length;
if (ipcHandleCount !== 1 || !main.includes("ipcMain.handle(channel,")) fail("unwrapped ipcMain.handle detected");
if (!/http-equiv=["']Content-Security-Policy["']/.test(html)) fail("Content-Security-Policy is missing");

const rendererSet = new Set(rendererCommands);
const electronSet = new Set(electronCommands);
if (rendererSet.size !== rendererCommands.length || electronSet.size !== electronCommands.length) fail("duplicate command in allow-list");
for (const command of rendererSet) if (!electronSet.has(command)) fail(`Electron allow-list misses ${command}`);
for (const command of electronSet) if (!rendererSet.has(command)) fail(`Electron allow-list has stale ${command}`);

if (!process.exitCode) process.stdout.write("SECURITY_GATE=PASS\n");
