import type { ReactNode } from "react";

export function Toolbar({ label, children, className = "" }: { label?: string; children: ReactNode; className?: string }) {
  return <div className={`nf-toolbar ${className}`} aria-label={label}>{children}</div>;
}
