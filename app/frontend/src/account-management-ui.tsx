import type { ReactNode } from "react";
import { Notice } from "./ui";
export function AccountNotice({ children }: { children: ReactNode }) {
  return (
    <div role="status" aria-live="polite">
      <Notice>{children}</Notice>
    </div>
  );
}
