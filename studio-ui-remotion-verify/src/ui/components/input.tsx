import type { InputHTMLAttributes } from "react";

export function Input({ label, description, error, id, className = "", ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string; description?: string; error?: string }) {
  const controlId = id || `nf-input-${label.toLowerCase().replace(/[^a-zа-я0-9]+/gi, "-")}`;
  return <label className={`nf-field ${error ? "nf-field-error" : ""} ${className}`} htmlFor={controlId}><span>{label}</span><input id={controlId} {...props} />{description ? <small>{description}</small> : null}{error ? <small role="alert">{error}</small> : null}</label>;
}
