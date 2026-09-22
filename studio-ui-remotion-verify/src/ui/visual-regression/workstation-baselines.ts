import type { VisualFixtureName } from "./visual-fixtures";

export type WorkstationBaselineCase = {
  id: string;
  page: string;
  dataRoot: "disposable";
  fixture?: VisualFixtureName;
  inspectorTask?: string;
  viewport?: { width: number; height: number };
};

export const workstationBaselineCases: WorkstationBaselineCase[] = [
  { id: "dashboard-empty", page: "dashboard", dataRoot: "disposable" },
  { id: "topics-empty", page: "ideas", dataRoot: "disposable" },
  { id: "topics-narrow", page: "ideas", dataRoot: "disposable", viewport: { width: 390, height: 844 } },
  { id: "scripts-empty", page: "scripts", dataRoot: "disposable" },
  { id: "covers-empty", page: "covers", dataRoot: "disposable" },
  { id: "covers-failed", page: "covers", dataRoot: "disposable", fixture: "task-states" },
  { id: "covers-84", page: "covers", dataRoot: "disposable", fixture: "covers-84" },
  { id: "covers-inspector", page: "covers", dataRoot: "disposable", fixture: "covers-84" },
  { id: "covers-configuration", page: "covers", dataRoot: "disposable" },
  { id: "voice-empty", page: "voice", dataRoot: "disposable" },
  { id: "voice-waiting", page: "voice", dataRoot: "disposable", fixture: "task-states" },
  { id: "voice-84", page: "voice", dataRoot: "disposable", fixture: "voice-84" },
  { id: "audio-inspector", page: "audio", dataRoot: "disposable", fixture: "voice-84" },
  { id: "voice-provider-readiness", page: "voices", dataRoot: "disposable" },
  { id: "montage-empty", page: "editor", dataRoot: "disposable" },
  { id: "montage-ready", page: "editor", dataRoot: "disposable", fixture: "task-states" },
  { id: "montage-84", page: "editor", dataRoot: "disposable", fixture: "montage-84" },
  { id: "montage-inspector", page: "editor", dataRoot: "disposable", fixture: "montage-84" },
  { id: "montage-configuration", page: "editor", dataRoot: "disposable" },
  { id: "publication-empty", page: "publication", dataRoot: "disposable" },
  { id: "publication-paused", page: "publication", dataRoot: "disposable", fixture: "task-states" },
  { id: "publication-84", page: "publication", dataRoot: "disposable", fixture: "publication-84" },
  { id: "publication-narrow", page: "publication", dataRoot: "disposable", fixture: "publication-84", viewport: { width: 390, height: 844 } },
  { id: "publication-day-plan", page: "publication", dataRoot: "disposable", fixture: "publication-84" },
  { id: "publication-queue-ads", page: "publication", dataRoot: "disposable", fixture: "publication-84" },
  { id: "publication-receipt", page: "publication", dataRoot: "disposable", fixture: "publication-receipt" },
  { id: "analytics-oauth-waiting", page: "analytics", dataRoot: "disposable", fixture: "analytics-oauth-waiting" },
  { id: "sidebar-collapsed", page: "dashboard", dataRoot: "disposable" },
  { id: "knowledge-empty", page: "knowledge", dataRoot: "disposable" },
  { id: "keys-discard-dialog", page: "keys", dataRoot: "disposable" },
  { id: "task-states-inspector", page: "dashboard", dataRoot: "disposable", fixture: "task-states", inspectorTask: "Озвучка ожидает провайдера" },
];
