import path from "node:path";
import { describe, expect, it } from "vitest";
import { environmentWindowTitle, isolatedElectronUserDataRoot } from "./test-user-data.js";

describe("isolated Electron user-data root", () => {
  it("uses a dedicated child of the explicit test root", () => {
    const root = path.resolve("C:/temp/newsflow-release-acceptance");

    expect(isolatedElectronUserDataRoot({
      NEWSFLOW_TEST_MODE: "1",
      NEWSFLOW_TEST_ROOT: root,
      NEWSFLOW_PRODUCTION_LOCALAPPDATA: path.resolve("C:/Users/borov/AppData/Local"),
    })).toBe(path.join(root, "electron-user-data"));
  });

  it("rejects test mode without an explicit isolated root", () => {
    expect(() => isolatedElectronUserDataRoot({ NEWSFLOW_TEST_MODE: "1" }))
      .toThrow("NEWSFLOW_TEST_ROOT");
  });

  it("rejects a test root that points at production local app data", () => {
    const production = path.resolve("C:/Users/borov/AppData/Local");

    expect(() => isolatedElectronUserDataRoot({
      NEWSFLOW_TEST_MODE: "1",
      NEWSFLOW_TEST_ROOT: production,
      NEWSFLOW_PRODUCTION_LOCALAPPDATA: production,
    })).toThrow("production");
  });

  it("rejects a test root inside the canonical production NewsFlow folder", () => {
    const production = path.resolve("C:/Users/borov/AppData/Local");

    expect(() => isolatedElectronUserDataRoot({
      NEWSFLOW_TEST_MODE: "1",
      NEWSFLOW_TEST_ROOT: path.join(production, "NewsFlow", "nested-test"),
      NEWSFLOW_PRODUCTION_LOCALAPPDATA: production,
    })).toThrow("production");
  });

  it("marks a validated test launch in the native window title", () => {
    expect(environmentWindowTitle({
      NEWSFLOW_TEST_MODE: "1",
      NEWSFLOW_TEST_ROOT: path.resolve("D:/NewsFlow-RC/disposable/phase-4"),
      NEWSFLOW_PRODUCTION_LOCALAPPDATA: path.resolve("C:/Users/borov/AppData/Local"),
    })).toBe("NewsFlow Studio [TEST]");
  });

  it("keeps the production title for a normal launch", () => {
    expect(environmentWindowTitle({})).toBe("NewsFlow Studio");
  });
});
