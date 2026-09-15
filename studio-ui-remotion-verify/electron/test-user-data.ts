import path from "node:path";

type Environment = Record<string, string | undefined>;

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
  if (production && root === path.resolve(production)) {
    throw new Error("The isolated Electron test root must not be production LOCALAPPDATA.");
  }

  return path.join(root, "electron-user-data");
}
