import type { ReactNode } from "react";

export function DropdownMenu({ label, children }: { label: string; children: ReactNode }) {
  return <details className="nf-dropdown"><summary aria-label={label}>{label}</summary><div role="menu">{children}</div></details>;
}
