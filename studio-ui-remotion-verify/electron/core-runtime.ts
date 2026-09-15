import { cpSync, existsSync, mkdirSync } from "node:fs";
import path from "node:path";

/**
 * Some Windows portable extractors lose PyInstaller's underscore-prefixed
 * Tcl directory.  Restore it from a separately packaged backup before the
 * Python core is ever spawned.  Returns true only when a repair was made.
 */
export function ensureTclRuntime(coreRoot: string, backupTclData: string): boolean {
  const target = path.join(coreRoot, "_internal", "_tcl_data");
  if (existsSync(target) || !existsSync(backupTclData)) return false;
  mkdirSync(path.dirname(target), { recursive: true });
  cpSync(backupTclData, target, { recursive: true, force: false });
  return true;
}
