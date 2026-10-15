import { useEffect, useRef } from "react";

const dirtyForms = new Set<symbol>();
export function hasUnsavedChanges() { return dirtyForms.size > 0; }
export function confirmNavigation() {
  return !hasUnsavedChanges() || window.confirm("Leave without saving? Your unsaved changes will be discarded.");
}
export function useUnsavedChanges(active: boolean) {
  const token = useRef(Symbol("unsaved form"));
  useEffect(() => {
    const id = token.current;
    if (!active) { dirtyForms.delete(id); return; }
    dirtyForms.add(id);
    const beforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault(); event.returnValue = "";
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => {
      dirtyForms.delete(id);
      window.removeEventListener("beforeunload", beforeUnload);
    };
  }, [active]);
}
