import type { InputHTMLAttributes } from "react";

export function Switch({ label, onCheckedChange, ...props }: Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "onChange"> & { label: string; onCheckedChange(checked: boolean): void }) {
  return <label className="nf-switch"><span>{label}</span><input type="checkbox" role="switch" onChange={(event) => onCheckedChange(event.target.checked)} {...props} /><i aria-hidden="true" /></label>;
}
