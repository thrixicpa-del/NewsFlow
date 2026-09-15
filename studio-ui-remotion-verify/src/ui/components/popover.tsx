import type { ReactNode } from "react";

export function Popover({ label, children }: { label: string; children: ReactNode }) {
  return <details className="nf-popover"><summary>{label}</summary><div>{children}</div></details>;
}
