"use client";

import { useState } from "react";

export function PageHeader({ title, description, eyebrow = "Market AI", children }: {
  title: string; description: string; eyebrow?: string; children?: React.ReactNode;
}) {
  return <header className="page-header"><div className="min-w-0"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="page-description">{description}</p></div>{children && <div className="flex shrink-0 flex-wrap gap-2">{children}</div>}</header>;
}

export function Guide({ title = "Comment utiliser cette page", children }: { title?: string; children: React.ReactNode }) {
  return <details className="guide-panel"><summary>{title}</summary><div className="mt-3 space-y-3 text-sm leading-6 text-slate-400">{children}</div></details>;
}

export function SectionSwitch({ value, onChange, options, label }: {
  value: string; onChange: (value: string) => void; options: Array<{ value: string; label: string }>; label: string;
}) {
  return <div className="section-switch" role="group" aria-label={label}>{options.map(o => <button type="button" key={o.value}
    aria-pressed={o.value === value} onClick={() => onChange(o.value)} className={o.value === value ? "is-active" : ""}>{o.label}</button>)}</div>;
}

export function Pagination({ page, pageSize, total, hasNext, busy = false, onChange, label = "résultats", targetId }: {
  page: number; pageSize: number; total?: number; hasNext?: boolean; busy?: boolean;
  onChange: (page: number) => void; label?: string; targetId?: string;
}) {
  const pages = total === undefined ? null : Math.max(1, Math.ceil(total / pageSize));
  const next = pages === null ? Boolean(hasNext) : page + 1 < pages;
  const multiplePages = pages === null ? page > 0 || next : pages > 1;
  if (total === undefined && !multiplePages) return null;
  function change(nextPage: number) {
    onChange(nextPage);
    if (targetId) document.getElementById(targetId)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  return <nav aria-label={`Pagination : ${label}`} className="pagination">
    <p aria-live="polite">{total === 0 ? "Aucun résultat" : total !== undefined ? `${page * pageSize + 1}–${Math.min((page + 1) * pageSize, total)} sur ${total} ${label}` : `Page ${page + 1}`}<span className="sr-only">{pages ? ` · Page ${page + 1} sur ${pages}` : ""}</span></p>
    {multiplePages && <div className="flex items-center gap-2"><button type="button" disabled={busy || page === 0} onClick={() => change(page - 1)} aria-controls={targetId} aria-label={`Page précédente : ${label}`}>← <span>Précédent</span></button>
      <span className="page-number" aria-hidden="true">{page + 1}{pages ? ` / ${pages}` : ""}</span>
      <button type="button" disabled={busy || !next} onClick={() => change(page + 1)} aria-controls={targetId} aria-label={`Page suivante : ${label}`}><span>Suivant</span> →</button></div>}
  </nav>;
}

export function usePagination<T>(items: T[], pageSize = 10, resetKey = "") {
  const [state, setState] = useState({ page: 0, key: resetKey });
  if (state.key !== resetKey) setState({ page: 0, key: resetKey });
  const page = Math.min(state.key === resetKey ? state.page : 0, Math.max(0, Math.ceil(items.length / pageSize) - 1));
  return { page, pageSize, total: items.length, items: items.slice(page * pageSize, (page + 1) * pageSize),
    onChange: (next: number) => setState({ page: Math.max(0, next), key: resetKey }) };
}
