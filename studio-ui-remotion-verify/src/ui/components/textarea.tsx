import type { TextareaHTMLAttributes } from "react";

export function Textarea({ label, description, error, id, className = "", ...props }: TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; description?: string; error?: string }) {
  const controlId = id || `nf-textarea-${label.toLowerCase().replace(/[^a-zа-я0-9]+/gi, "-")}`;
  return <label className={`nf-field ${error ? "nf-field-error" : ""} ${className}`} htmlFor={controlId}><span>{label}</span><textarea id={controlId} {...props} />{description ? <small>{description}</small> : null}{error ? <small role="alert">{error}</small> : null}</label>;
}
