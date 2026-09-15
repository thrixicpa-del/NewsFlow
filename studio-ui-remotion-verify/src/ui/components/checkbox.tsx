import type { InputHTMLAttributes } from "react";

export function Checkbox({ label, onCheckedChange, ...props }: Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "onChange"> & { label: string; onCheckedChange(checked: boolean): void }) {
  return <label className="nf-check"><input type="checkbox" onChange={(event) => onCheckedChange(event.target.checked)} {...props} /><span>{label}</span></label>;
}
