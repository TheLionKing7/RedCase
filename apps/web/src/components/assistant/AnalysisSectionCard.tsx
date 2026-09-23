// AnalysisSectionCard — M1 assistant-tools renderer.
//
// A single presentational card that renders one analysis section (overview /
// arguments / law) returned by the assistant's drill-down tools
// (show_overview / show_arguments / show_similar_cases / show_law). It reflects
// `Analysis.output.sections[section]` on the wire mirror in lib/api/workbench.ts
// (no invented fields — addendum owner ruling 2). The card only renders data the
// analyser actually produced; a missing section renders an empty state rather than a
// guess (no fabrication in the UI).
//
// Layout: consistent rounded-xl card with a labelled header and a key/value list,
// following the Design System (subtle ring, slate base, focus/ring interaction).

import { FileText, Gavel, Layers, Scale } from "lucide-react";
import type { ReactNode } from "react";

export type AnalysisSectionKind =
  "overview" | "arguments" | "similar_cases" | "law";

const SECTION_META: Record<
  AnalysisSectionKind,
  { label: string; icon: ReactNode }
> = {
  overview: { label: "Overview", icon: <Layers className="h-4 w-4" /> },
  arguments: {
    label: "Arguments",
    icon: <FileText className="h-4 w-4" />,
  },
  similar_cases: {
    label: "Similar Cases",
    icon: <Scale className="h-4 w-4" />,
  },
  law: { label: "Law", icon: <Gavel className="h-4 w-4" /> },
};

/** Render a section value (string | array | object) into a compact prose list. */
function renderValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

interface Item {
  label?: string;
  value?: string;
}

interface AnalysisSectionCardProps {
  section: AnalysisSectionKind;
  data: unknown;
  className?: string;
}

export function AnalysisSectionCard({
  section,
  data,
  className = "",
}: AnalysisSectionCardProps) {
  const meta = SECTION_META[section];

  let items: Item[] = [];
  let empty = false;

  if (Array.isArray(data)) {
    items = data
      .map((entry) =>
        typeof entry === "string"
          ? { value: entry }
          : {
              label:
                (entry as { id?: string; clause?: string; argument?: string })
                  ?.clause ??
                (entry as { id?: string })?.id ??
                (entry as { argument?: string })?.argument,
              value: renderValue(entry),
            },
      )
      .slice(0, 6);
  } else if (data !== null && typeof data === "object") {
    items = Object.entries(data as Record<string, unknown>).map(([k, v]) => ({
      label: k,
      value: renderValue(v),
    }));
  } else if (data !== null && data !== undefined) {
    items = [{ value: renderValue(data) }];
  } else {
    empty = true;
  }
  empty = empty || items.length === 0;

  return (
    <div
      className={`rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition-all dark:border-slate-800 dark:bg-slate-900 ${className}`}
    >
      <div className="flex items-center gap-2 border-b border-slate-100 pb-2 dark:border-slate-800">
        {meta.icon}
        <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">
          {meta.label}
        </span>
      </div>
      {empty ? (
        <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">
          No {meta.label.toLowerCase()} recorded for this analysis.
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {items.map((it, i) => (
            <li key={i} className="text-sm">
              {it.label && (
                <div className="font-medium text-slate-700 dark:text-slate-300">
                  {it.label}
                </div>
              )}
              {it.value && (
                <div className="text-slate-600 dark:text-slate-400">
                  {it.value}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
