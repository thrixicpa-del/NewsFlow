import type { ReactNode } from "react";

export function Sidebar({ brand, status, children, collapsed = false, onToggle }: { brand: ReactNode; status: ReactNode; children: ReactNode; collapsed?: boolean; onToggle?: () => void }) {
  const toggleLabel = collapsed ? "Развернуть навигацию" : "Свернуть навигацию";
  return <div className="nf-sidebar" data-collapsed={collapsed || undefined}><div className="nf-sidebar-brand">{brand}</div>{onToggle ? <button className="nf-sidebar-toggle" type="button" aria-label={toggleLabel} aria-expanded={!collapsed} onClick={onToggle}>{collapsed ? "»" : "«"}</button> : null}<nav className="nf-sidebar-nav" aria-label="Разделы NewsFlow">{children}</nav><div className="nf-sidebar-status"><i aria-hidden="true" />{status}</div></div>;
}
