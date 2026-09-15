import { useEffect, useState } from "react";

export type UiPreferences = {
  sidebarCollapsed: boolean;
  inspectorWidth: number;
  density: "comfortable" | "compact";
};

export const UI_PREFERENCES_STORAGE_KEY = "newsflow.ui-preferences.v1";

const defaults: UiPreferences = {
  sidebarCollapsed: false,
  inspectorWidth: 360,
  density: "comfortable",
};

function isUiPreferences(value: unknown): value is UiPreferences {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<UiPreferences>;
  return typeof candidate.sidebarCollapsed === "boolean"
    && typeof candidate.inspectorWidth === "number"
    && candidate.inspectorWidth >= 280
    && candidate.inspectorWidth <= 640
    && (candidate.density === "comfortable" || candidate.density === "compact");
}

export function loadUiPreferences(): UiPreferences {
  try {
    const stored = localStorage.getItem(UI_PREFERENCES_STORAGE_KEY);
    const parsed: unknown = stored ? JSON.parse(stored) : null;
    return isUiPreferences(parsed) ? parsed : defaults;
  } catch {
    return defaults;
  }
}

export function useUiPreferences(): [UiPreferences, React.Dispatch<React.SetStateAction<UiPreferences>>] {
  const [preferences, setPreferences] = useState<UiPreferences>(loadUiPreferences);
  useEffect(() => {
    localStorage.setItem(UI_PREFERENCES_STORAGE_KEY, JSON.stringify(preferences));
  }, [preferences]);
  return [preferences, setPreferences];
}
