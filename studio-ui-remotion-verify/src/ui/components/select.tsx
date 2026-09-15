import type { SelectHTMLAttributes } from "react";

export type SelectOption = { value: string; label: string; disabled?: boolean };
export function Select({ label, options, id, className = "", ...props }: SelectHTMLAttributes<HTMLSelectElement> & { label: string; options: SelectOption[] }) {
  const controlId = id || `nf-select-${label.toLowerCase().replace(/[^a-zа-я0-9]+/gi, "-")}`;
  return <label className={`nf-field ${className}`} htmlFor={controlId}><span>{label}</span><select id={controlId} {...props}>{options.map((option) => <option key={option.value} value={option.value} disabled={option.disabled}>{option.label}</option>)}</select></label>;
}
