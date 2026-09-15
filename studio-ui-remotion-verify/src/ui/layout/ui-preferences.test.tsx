import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { UI_PREFERENCES_STORAGE_KEY, useUiPreferences } from "./ui-preferences";

function PreferenceProbe() {
  const [preferences, setPreferences] = useUiPreferences();
  return <>
    <output aria-label="sidebar state">{String(preferences.sidebarCollapsed)}</output>
    <button onClick={() => setPreferences((current) => ({ ...current, sidebarCollapsed: true, inspectorWidth: 420 }))}>Изменить layout</button>
  </>;
}

describe("useUiPreferences", () => {
  beforeEach(() => localStorage.clear());

  it("persists layout-only preferences under a dedicated versioned key", () => {
    render(<PreferenceProbe />);
    fireEvent.click(screen.getByRole("button", { name: "Изменить layout" }));

    expect(screen.getByLabelText("sidebar state").textContent).toBe("true");
    expect(JSON.parse(localStorage.getItem(UI_PREFERENCES_STORAGE_KEY) || "{}")).toMatchObject({
      sidebarCollapsed: true,
      inspectorWidth: 420,
    });
    expect(Object.keys(localStorage)).toEqual([UI_PREFERENCES_STORAGE_KEY]);
  });

  it("rejects malformed layout values without reading or changing business state", () => {
    localStorage.setItem(UI_PREFERENCES_STORAGE_KEY, JSON.stringify({ sidebarCollapsed: "yes", inspectorWidth: -1 }));
    render(<PreferenceProbe />);

    expect(screen.getByLabelText("sidebar state").textContent).toBe("false");
    expect(localStorage.getItem("newsflow-settings")).toBeNull();
  });
});
