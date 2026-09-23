import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("workstation visual capture contract", () => {
  it("measures route navigation before waiting for screenshot animation settling", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );
    const settle = captureScript.indexOf("await waitForVisualSettle(window);");
    const navigationMeasurement = captureScript.indexOf(
      "const navigationMs = performance.now() - navigationStartedAt;",
    );

    expect(settle).toBeGreaterThan(-1);
    expect(navigationMeasurement).toBeGreaterThan(-1);
    expect(navigationMeasurement).toBeLessThan(settle);
  });

  it("waits for two identical compositor frames before comparing a visual baseline", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );

    expect(captureScript).toContain("async function captureStablePage(window)");
    expect(captureScript).toContain("let stableFrames = 0;");
    expect(captureScript).toContain("pixelDifference(currentImage.toBitmap(), previousImage.toBitmap()) === 0");
    expect(captureScript).toContain("const currentPng = await captureStablePage(window);");
  });

  it("can render the current OAuth handoff UI only through a disposable local adapter", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );

    expect(captureScript).toContain("async function installVisualOauthAdapter(window)");
    expect(captureScript).toContain("visual-oauth-waiting");
    expect(captureScript).toContain("startYoutubeOAuthHandoff");
  });

  it("reports the pixel bounds when a visual baseline fails", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );

    expect(captureScript).toContain("function pixelDifferenceDetails(left, right, width)");
    expect(captureScript).toContain("bounds ${details.bounds}");
  });

  it("cleans up disposable visual resources before selecting the process exit code", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );
    const destroyWindow = captureScript.indexOf("if (!window.isDestroyed()) window.destroy();");
    const awaitStop = captureScript.indexOf("await stopDisposableVite(vite);");
    const terminalHandler = captureScript.indexOf("void captureBaselines().then(");

    expect(destroyWindow).toBeGreaterThan(-1);
    expect(awaitStop).toBeGreaterThan(destroyWindow);
    expect(terminalHandler).toBeGreaterThan(awaitStop);
    expect(captureScript.slice(destroyWindow, terminalHandler)).not.toContain("app.exit(");
  });

  it("keeps Electron alive after closing the disposable window until the terminal handler selects an exit code", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );

    const preventAutomaticExit = captureScript.indexOf('app.on("window-all-closed", (event) => event.preventDefault());');
    const terminalHandler = captureScript.indexOf("void captureBaselines().then(");

    expect(preventAutomaticExit).toBeGreaterThan(-1);
    expect(preventAutomaticExit).toBeLessThan(terminalHandler);
  });

  it("waits for the disposable Vite process tree before terminating visual capture", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );
    const stopVite = captureScript.indexOf("async function stopDisposableVite(vite)");
    const awaitStop = captureScript.indexOf("await stopDisposableVite(vite);");

    expect(stopVite).toBeGreaterThan(-1);
    expect(awaitStop).toBeGreaterThan(stopVite);
    expect(captureScript).toContain('taskkill.exe');
  });

  it("returns a failing Electron exit code when visual capture rejects", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );
    const terminalHandler = captureScript.indexOf("void captureBaselines().then(");
    const successExit = captureScript.indexOf("() => app.exit(0)", terminalHandler);
    const errorLog = captureScript.indexOf("console.error(error);", successExit);
    const failureExit = captureScript.indexOf("app.exit(1);", errorLog);

    expect(terminalHandler).toBeGreaterThan(-1);
    expect(successExit).toBeGreaterThan(terminalHandler);
    expect(errorLog).toBeGreaterThan(successExit);
    expect(failureExit).toBeGreaterThan(errorLog);
  });

  it("clears disposable renderer preferences before loading each visual case", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );
    const clearPreferences = captureScript.indexOf("localStorage.clear()");
    const loadCase = captureScript.indexOf("await window.loadURL(url.href);");

    expect(clearPreferences).toBeGreaterThan(-1);
    expect(clearPreferences).toBeLessThan(loadCase);
  });

  it("includes the active SEO and Tags production desks in the isolated visual matrix", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );

    expect(captureScript).toContain('{ id: "seo-empty"');
    expect(captureScript).toContain('{ id: "tags-empty"');
  });

  it("covers ready metadata artifacts independently from empty-state workspaces", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );

    expect(captureScript).toContain('{ id: "seo-ready", fixture: "metadata-ready"');
    expect(captureScript).toContain('{ id: "tags-ready", fixture: "metadata-ready"');
  });

  it("covers every remaining active workstation route on disposable empty state", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );
    const requiredCases = [
      "scenarios-empty",
      "templates-empty",
      "agents-empty",
      "cover-gallery-empty",
      "media-empty",
      "footage-empty",
      "cutter-empty",
      "voice-profiles-empty",
      "audio-empty",
      "outputs-empty",
      "sessions-empty",
    ];

    for (const caseId of requiredCases) expect(captureScript).toContain(`id: "${caseId}"`);
  });

  it("loads approved baselines from versioned test assets while keeping captures disposable", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );

    expect(captureScript).toContain('"tests", "visual-baselines", "approved"');
    expect(captureScript).toContain('".artifacts", "workstation-visual-baselines"');
  });

});
