import { fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "./AppShell";
import { Sidebar } from "./Sidebar";

const shellStyles = readFileSync(resolve(process.cwd(), "src/ui/layout/app-shell.css"), "utf8");
const responsiveStyles = readFileSync(resolve(process.cwd(), "src/ui/layout/app-shell-responsive.css"), "utf8");
const rendererEntry = readFileSync(resolve(process.cwd(), "src/main.tsx"), "utf8");

describe("AppShell", () => {
  it("keeps navigation and active content in caller-owned runtime state", () => {
    const onNavigate = vi.fn();
    render(<AppShell sidebar={<Sidebar brand="NEWSFLOW" status="Система готова"><button onClick={() => onNavigate("ideas")}>Идеи</button></Sidebar>} header={<h1>Центр управления</h1>}><section aria-label="Активная страница">Dashboard content</section></AppShell>);

    fireEvent.click(screen.getByRole("button", { name: "Идеи" }));
    expect(onNavigate).toHaveBeenCalledWith("ideas");
    expect(screen.getByLabelText("Активная страница")).not.toBeNull();
  });

  it("supports a persisted compact navigation rail without changing caller-owned navigation", () => {
    const onToggle = vi.fn();
    render(<AppShell sidebarCollapsed sidebar={<Sidebar brand="NEWSFLOW" status="Готово" collapsed onToggle={onToggle}><button>Идеи</button></Sidebar>}><section>Workspace</section></AppShell>);

    expect(document.querySelector(".nf-app-shell")?.classList.contains("nf-app-shell-collapsed")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Развернуть навигацию" }));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("mounts an optional caller-owned context inspector with its saved width", () => {
    render(<AppShell sidebar="Navigation" inspector={<section aria-label="Контекстный инспектор">Task context</section>} inspectorWidth={420}><section>Workspace</section></AppShell>);

    expect(screen.getByLabelText("Контекстный инспектор")).not.toBeNull();
    expect(document.querySelector(".nf-app-shell")?.getAttribute("style")).toContain("--nf-inspector-width: 420px");
  });

  it("applies caller-owned compact density without touching navigation state", () => {
    render(<AppShell sidebar="Navigation" density="compact"><section>Workspace</section></AppShell>);
    expect(document.querySelector(".nf-app-shell")?.classList.contains("nf-density-compact")).toBe(true);
  });

  it("does not retain the legacy desktop minimum width that prevents the workstation shell from becoming narrow", () => {
    expect(responsiveStyles).toContain("body{min-width:0}");
    expect(responsiveStyles).toContain("main.nf-main{grid-column:auto;padding:0}");
    expect(responsiveStyles).toContain(".nf-editorial-workspace .split-ideas{grid-template-columns:minmax(0,1fr)}");
    expect(responsiveStyles).toContain(".nf-sidebar-nav{display:flex;overflow-x:auto;grid-column:1/-1");
    expect(responsiveStyles).toContain(".nf-editorial-workspace>.publication-target-widget{grid-template-columns:minmax(0,1fr)}");
    expect(responsiveStyles).toContain(".nf-ideas .custom-topic-entry{flex-direction:column;align-items:stretch}");
    expect(responsiveStyles).toContain(".nf-ideas .custom-topic-entry{min-width:0;width:100%}");
    expect(shellStyles).toContain("@media(max-width:900px){.nf-app-shell");
    expect(rendererEntry.indexOf("import './ui/styles.css';")).toBeLessThan(rendererEntry.indexOf("import './ui/layout/app-shell-responsive.css';"));
  });

  it("keeps the Topics action rail usable at phone-width workstation windows", () => {
    expect(responsiveStyles).toContain("@media(max-width:600px)");
    expect(responsiveStyles).toContain(".nf-ideas>.nf-toolbar{align-items:stretch}");
    expect(responsiveStyles).toContain(".nf-ideas>.nf-toolbar>.nf-button{width:100%;justify-content:center}");
  });

  it("contains legacy production forms inside the actual workspace width beside the inspector", () => {
    expect(shellStyles).toContain(".nf-main{min-width:0;container-type:inline-size}");
    expect(responsiveStyles).toContain("@container (max-width:920px)");
    expect(responsiveStyles).toContain(".nf-footage .form-row,.nf-cutter .form-row{flex-wrap:wrap}");
    expect(responsiveStyles).toContain(".voice-provider-readiness+.split{grid-template-columns:minmax(0,1fr)}");
  });
});
