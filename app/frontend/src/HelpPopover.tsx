import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { CircleHelp } from "lucide-react";
import "./help-popover.css";

export default function HelpPopover({ label, children }: { label: string; children: ReactNode }) {
  const id = useId();
  const button = useRef<HTMLButtonElement>(null), tip = useRef<HTMLSpanElement>(null);
  const [open, setOpen] = useState(false), [pinned, setPinned] = useState(false);
  const [position, setPosition] = useState({left: 16, top: 16});
  const dismissed = useRef(false), timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  function show() { clearTimeout(timer.current); if (!dismissed.current) setOpen(true); }
  function close() { clearTimeout(timer.current); setOpen(false); setPinned(false); }
  function leave() {
    dismissed.current = false;
    if (!pinned) timer.current = setTimeout(() => {
      if (document.activeElement !== button.current) setOpen(false);
    }, 140);
  }
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const a = button.current?.getBoundingClientRect(), b = tip.current?.getBoundingClientRect();
      if (!a || !b) return;
      setPosition({left: Math.max(16, Math.min(a.right - b.width, window.innerWidth - b.width - 16)),
        top: a.bottom + b.height + 8 > window.innerHeight ? Math.max(12, a.top - b.height - 8) : a.bottom + 8});
    };
    place(); window.addEventListener("resize", place); window.addEventListener("scroll", place, true);
    return () => { window.removeEventListener("resize", place); window.removeEventListener("scroll", place, true); };
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const escape = (e: KeyboardEvent) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); dismissed.current = true; close(); } };
    const outside = (e: Event) => { if (!button.current?.contains(e.target as Node) && !tip.current?.contains(e.target as Node)) close(); };
    document.addEventListener("keydown", escape, true); document.addEventListener("pointerdown", outside); document.addEventListener("focusin", outside);
    return () => { document.removeEventListener("keydown", escape, true); document.removeEventListener("pointerdown", outside); document.removeEventListener("focusin", outside); };
  }, [open]);
  useEffect(() => () => clearTimeout(timer.current), []);
  return <span className="help-trigger-wrap">
    <button ref={button} type="button" className="help-trigger" aria-label={label}
      aria-expanded={open} aria-describedby={open ? id : undefined}
      onPointerEnter={show} onPointerLeave={leave} onFocus={() => { dismissed.current = false; show(); }}
      onBlur={() => { dismissed.current = false; if (!pinned) close(); }}
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); dismissed.current = false; if (pinned) close(); else {setPinned(true);setOpen(true);} }}>
      <CircleHelp size={16} aria-hidden="true" />
    </button>
    {open && createPortal(<span id={id} ref={tip} className="help-tooltip" role="tooltip" style={position}
      onPointerEnter={() => clearTimeout(timer.current)} onPointerLeave={leave}>{children}</span>, document.body)}
  </span>;
}
