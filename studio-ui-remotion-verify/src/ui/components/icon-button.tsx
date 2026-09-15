import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Button } from "./button";

export function IconButton({ label, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; children: ReactNode }) {
  return <Button size="icon" variant="ghost" aria-label={label} title={label} {...props}>{children}</Button>;
}
