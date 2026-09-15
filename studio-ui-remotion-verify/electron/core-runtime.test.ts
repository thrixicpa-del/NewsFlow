import { existsSync, mkdtempSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { ensureTclRuntime } from "./core-runtime.js";

const roots: string[] = [];

afterEach(() => {
  // Test directories are deliberately left to the operating system's temp
  // cleanup; this avoids deleting anything outside the test-owned root.
  roots.length = 0;
});

describe("ensureTclRuntime", () => {
  it("restores missing Tcl data from the portable backup before core startup", () => {
    const root = mkdtempSync(path.join(tmpdir(), "newsflow-tcl-test-"));
    roots.push(root);
    const coreRoot = path.join(root, "core-bin");
    const backup = path.join(root, "core-tcl-data");
    mkdirSync(backup, { recursive: true });
    writeFileSync(path.join(backup, "init.tcl"), "package require Tcl");

    expect(ensureTclRuntime(coreRoot, backup)).toBe(true);
    const restored = path.join(coreRoot, "_internal", "_tcl_data", "init.tcl");
    expect(existsSync(restored)).toBe(true);
    expect(readFileSync(restored, "utf8")).toBe("package require Tcl");
  });
});
