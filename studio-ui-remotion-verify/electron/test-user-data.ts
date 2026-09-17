import path from "node:path";

type Environment = Record<string, string | undefined>;

function sameOrDescendant(candidate: string, parent: string): boolean {
  const normalizedCandidate = path.resolve(candidate).toLocaleLowerCase();
  const normalizedParent = path.resolve(parent).toLocaleLowerCase();
  const relative = path.relative(normalizedParent, normalizedCandidate);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

/**
 * Keep release acceptance's Electron profile next to, but distinct from, the
 * core's required test root.  A normal packaged launch returns null and keeps
 * the canonical production user-data location unchanged.
 */
export function isolatedElectronUserDataRoot(environment: Environment): string | null {
  if (environment.NEWSFLOW_TEST_MODE !== "1") return null;

  const configuredRoot = environment.NEWSFLOW_TEST_ROOT?.trim();
  if (!configuredRoot) {
    throw new Error("NEWSFLOW_TEST_ROOT is required for an isolated Electron test launch.");
  }

  const root = path.resolve(configuredRoot);
  const production = environment.NEWSFLOW_PRODUCTION_LOCALAPPDATA?.trim();
  const productionStorage = production ? path.join(path.resolve(production), "NewsFlow") : null;
  if (production && (root === path.resolve(production) || sameOrDescendant(root, productionStorage!))) {
    throw new Error("The isolated Electron test root must not be production LOCALAPPDATA.");
  }

  return path.join(root, "electron-user-data");
}

/** A test/RC window must never be visually mistaken for a production launch. */
export function environmentWindowTitle(environment: Environment): string {
  if (environment.NEWSFLOW_TEST_MODE !== "1") return "NewsFlow Studio";
  // Validate the explicit root before exposing the test identity to a window.
  isolatedElectronUserDataRoot(environment);
  return "NewsFlow Studio [TEST]";
}
