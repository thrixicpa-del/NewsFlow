import type { CSSProperties, ReactNode } from "react";
import "./app-shell.css";

export function AppShell({ sidebar, header, notice, taskCenter, inspector, inspectorWidth = 360, density = "comfortable", children, sidebarCollapsed = false }: { sidebar: ReactNode; header?: ReactNode; notice?: ReactNode; taskCenter?: ReactNode; inspector?: ReactNode; inspectorWidth?: number; density?: "comfortable" | "compact"; children: ReactNode; sidebarCollapsed?: boolean }) {
  const className = `nf-app-shell${sidebarCollapsed ? " nf-app-shell-collapsed" : ""}${inspector ? " nf-app-shell-with-inspector" : ""}${density === "compact" ? " nf-density-compact" : ""}`;
  const style = { "--nf-inspector-width": `${inspectorWidth}px` } as CSSProperties;
  return <div className={className} style={style}><aside className="nf-sidebar-slot">{sidebar}</aside><main className="nf-main"><div className="nf-main-inner">{header}{notice}{taskCenter}{children}</div></main>{inspector ? <aside className="nf-context-inspector-slot">{inspector}</aside> : null}</div>;
}
