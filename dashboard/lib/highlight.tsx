import { Fragment, ReactNode } from "react";

// A deliberately small C/C++ highlighter: comments, strings, preprocessor,
// keywords, types, numbers. Enough to read code comfortably; no dependency.
const KEYWORDS = new Set(
  "if else for while do return break continue switch case default goto sizeof static const volatile extern inline restrict typedef struct union enum register auto new delete template typename class namespace using public private protected virtual operator".split(" "),
);
const TYPES = new Set(
  "int long short char float double void unsigned signed size_t bool uint8_t uint16_t uint32_t uint64_t int8_t int16_t int32_t int64_t FILE".split(" "),
);
const TOKEN = /(\/\/.*$|\/\*.*?\*\/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|^\s*#\s*\w+|\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?[uUlLfF]*\b|\b[A-Za-z_]\w*\b)/g;

export function highlightLine(line: string): ReactNode {
  const out: ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  TOKEN.lastIndex = 0;
  while ((m = TOKEN.exec(line))) {
    if (m.index > last) out.push(line.slice(last, m.index));
    const t = m[0];
    let cls = "";
    if (t.startsWith("//") || t.startsWith("/*")) cls = "text-faint italic";
    else if (t.startsWith('"') || t.startsWith("'")) cls = "text-warn";
    else if (/^\s*#/.test(t)) cls = "text-info";
    else if (/^\d/.test(t)) cls = "text-accent";
    else if (KEYWORDS.has(t)) cls = "text-info font-medium";
    else if (TYPES.has(t)) cls = "text-[rgb(var(--lane-profiler))]";
    out.push(cls ? <span key={m.index} className={cls}>{t}</span> : <Fragment key={m.index}>{t}</Fragment>);
    last = m.index + t.length;
    if (t.length === 0) TOKEN.lastIndex++;
  }
  if (last < line.length) out.push(line.slice(last));
  return out.length ? out : " ";
}
