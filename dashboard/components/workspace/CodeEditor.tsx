"use client";

import { useRef } from "react";
import { highlightLine } from "@/lib/highlight";

const FONT = "font-mono text-[13px] leading-[20px]";

/** A small C/C++ editor: a transparent <textarea> (the real, accessible
 *  input) laid over a syntax-highlighted copy of the same text. */
export function CodeEditor({
  value,
  onChange,
  readOnly = false,
  height = 380,
  label,
  placeholder,
}: {
  value: string;
  onChange?: (v: string) => void;
  readOnly?: boolean;
  height?: number;
  label: string;
  placeholder?: string;
}) {
  const layer = useRef<HTMLDivElement>(null);
  const gutter = useRef<HTMLDivElement>(null);
  const rows = value.split("\n");

  function sync(el: HTMLTextAreaElement) {
    const t = `translate(${-el.scrollLeft}px, ${-el.scrollTop}px)`;
    if (layer.current) layer.current.style.transform = t;
    if (gutter.current) gutter.current.style.transform = `translateY(${-el.scrollTop}px)`;
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (readOnly || e.key !== "Tab" || e.shiftKey) return;
    e.preventDefault(); // keep Tab for indentation; Esc then Tab still leaves the field
    const el = e.currentTarget;
    const { selectionStart: s, selectionEnd: end } = el;
    onChange?.(value.slice(0, s) + "    " + value.slice(end));
    requestAnimationFrame(() => el.setSelectionRange(s + 4, s + 4));
  }

  const digits = String(rows.length).length;
  const gutterWidth = `${Math.max(digits, 2) + 1.4}ch`;

  return (
    <div className="relative overflow-hidden rounded-[8px] border border-rule bg-sunken focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/25" style={{ height }}>
      <div className="pointer-events-none absolute inset-y-0 left-0 overflow-hidden border-r border-rule bg-surface/60" style={{ width: gutterWidth }} aria-hidden>
        <div ref={gutter} className={`py-3 pr-2 text-right text-faint ${FONT}`}>
          {rows.map((_, i) => <div key={i}>{i + 1}</div>)}
        </div>
      </div>
      <div className="absolute inset-y-0 right-0 overflow-hidden" style={{ left: gutterWidth }} aria-hidden>
        <div ref={layer} className={`min-w-full whitespace-pre px-3 py-3 text-ink ${FONT}`}>
          {rows.map((r, i) => <div key={i}>{highlightLine(r)}</div>)}
        </div>
      </div>
      <textarea
        aria-label={label}
        value={value}
        readOnly={readOnly}
        placeholder={placeholder}
        spellCheck={false}
        autoCapitalize="off"
        autoCorrect="off"
        wrap="off"
        onChange={(e) => onChange?.(e.target.value)}
        onScroll={(e) => sync(e.currentTarget)}
        onKeyDown={onKeyDown}
        className={`absolute inset-y-0 right-0 resize-none whitespace-pre border-0 bg-transparent px-3 py-3 text-transparent caret-ink outline-none selection:bg-accent/25 placeholder:text-faint ${FONT}`}
        style={{ left: gutterWidth, overflow: "auto", tabSize: 4 }}
      />
    </div>
  );
}

/** Read-only code with line numbers; changed lines are tinted. Scroll is
 *  reported so two panes can be kept in step. */
export function CodePane({
  title,
  code,
  tint,
  tone,
  height = 460,
  onScroll,
  scrollRef,
}: {
  title: string;
  code: string;
  tint?: Set<number>;
  tone?: "add" | "del";
  height?: number;
  onScroll?: (el: HTMLDivElement) => void;
  scrollRef?: React.Ref<HTMLDivElement>;
}) {
  const rows = code.split("\n");
  return (
    <div className="min-w-0 overflow-hidden rounded-[8px] border border-rule">
      <div className="border-b border-rule bg-surface px-3 py-2 text-[12.5px] font-semibold text-ink">{title}</div>
      <div ref={scrollRef} onScroll={(e) => onScroll?.(e.currentTarget)} className="overflow-auto bg-sunken" style={{ height }} tabIndex={0} aria-label={title}>
        <table className={`w-full border-collapse ${FONT}`}>
          <tbody>
            {rows.map((line, i) => (
              <tr key={i} className={tint?.has(i) ? (tone === "add" ? "bg-accent-soft" : "bg-bad-soft") : undefined}>
                <td className="w-[1%] select-none whitespace-nowrap px-2 text-right text-faint">{i + 1}</td>
                <td className="whitespace-pre pr-4">{highlightLine(line)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
