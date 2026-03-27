import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useHistoryExplorer } from "../hooks/useHistoryExplorer";

function formatTs(row: unknown): string {
  const o = row as Record<string, unknown>;
  const s = o.ts_logical ?? o.created_at ?? "";
  return String(s);
}

export function HistoryExplorerPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initial = searchParams.get("thread_id")?.trim() ?? "";
  const {
    threads,
    selectedThreadId,
    setSelectedThreadId,
    events,
    checkpoints,
    detail,
    error,
    refreshThreads,
    loadCheckpointDetail,
  } = useHistoryExplorer(initial);

  const mergedTimeline = useMemo(() => {
    const evRows = events.map((e, i) => ({
      kind: "event" as const,
      key: `e-${i}-${e.step_seq ?? i}`,
      sort: Number(e.ts_logical ?? 0) || i,
      label: `trace ${e.step_kind ?? "?"}`,
      sub: String(e.state_id ?? ""),
      payload: e,
    }));
    const cpRows = checkpoints.map((c, i) => ({
      kind: "checkpoint" as const,
      key: `c-${c.checkpoint_id ?? i}`,
      sort:
        c.created_at != null
          ? new Date(String(c.created_at)).getTime()
          : 1e15 + i,
      label: `cp ${String(c.checkpoint_id ?? "").slice(0, 8)}…`,
      sub: String(c.state_id ?? ""),
      payload: c,
    }));
    return [...evRows, ...cpRows].sort((a, b) => b.sort - a.sort);
  }, [events, checkpoints]);

  return (
    <div className="flex h-screen flex-col bg-zinc-950 text-zinc-100">
      <header className="flex items-center justify-between border-b border-zinc-800 px-4 py-2">
        <div className="flex items-center gap-3">
          <Link
            to="/"
            className="text-sm text-sky-400 hover:text-sky-300"
          >
            Monitor
          </Link>
          <h1 className="text-sm font-semibold tracking-wide text-zinc-300">
            History Explorer
          </h1>
        </div>
        <button
          type="button"
          onClick={() => void refreshThreads()}
          className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs hover:bg-zinc-800"
        >
          Refresh threads
        </button>
      </header>
      {error ? (
        <div className="bg-rose-950 px-4 py-2 text-sm text-rose-200">{error}</div>
      ) : null}
      <div className="flex min-h-0 flex-1">
        <aside className="w-56 shrink-0 overflow-y-auto border-r border-zinc-800 p-2">
          <div className="mb-2 text-xs font-medium uppercase text-zinc-500">
            Threads
          </div>
          <select
            className="mb-2 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs"
            value={selectedThreadId}
            onChange={(e) => {
              const v = e.target.value;
              setSelectedThreadId(v);
              setSearchParams(v ? { thread_id: v } : {});
            }}
          >
            <option value="">—</option>
            {threads.map((t) => (
              <option key={t.thread_id} value={t.thread_id}>
                {t.thread_id} ({t.event_count})
              </option>
            ))}
          </select>
          <ul className="space-y-1 text-xs">
            {threads.map((t) => (
              <li key={t.thread_id}>
                <button
                  type="button"
                  className={`w-full truncate rounded px-2 py-1 text-left hover:bg-zinc-900 ${selectedThreadId === t.thread_id ? "bg-zinc-800" : ""}`}
                  onClick={() => {
                    setSelectedThreadId(t.thread_id);
                    setSearchParams({ thread_id: t.thread_id });
                  }}
                >
                  {t.thread_id}
                </button>
              </li>
            ))}
          </ul>
        </aside>
        <section className="min-w-0 flex-1 overflow-y-auto border-r border-zinc-800 p-2">
          <div className="mb-2 text-xs font-medium uppercase text-zinc-500">
            Timeline
          </div>
          <ul className="space-y-1 text-xs">
            {mergedTimeline.map((row) => (
              <li key={row.key}>
                <button
                  type="button"
                  className={`w-full rounded border border-transparent px-2 py-1 text-left hover:border-zinc-700 hover:bg-zinc-900 ${row.kind === "checkpoint" ? "" : "opacity-90"}`}
                  onClick={() => {
                    if (row.kind === "checkpoint" && selectedThreadId) {
                      const c = row.payload as Record<string, unknown>;
                      void loadCheckpointDetail(
                        selectedThreadId,
                        c.checkpoint_id != null ? String(c.checkpoint_id) : null,
                        c.checkpoint_ns != null ? String(c.checkpoint_ns) : "",
                      );
                    }
                  }}
                >
                  <span className="text-zinc-400">{formatTs(row.payload)}</span>{" "}
                  <span className="text-zinc-200">{row.label}</span>
                  <span className="block truncate text-zinc-500">{row.sub}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
        <section className="flex w-[42%] min-w-[280px] flex-col overflow-hidden">
          <div className="shrink-0 border-b border-zinc-800 px-2 py-2 text-xs font-medium uppercase text-zinc-500">
            Checkpoint state
          </div>
          <pre className="min-h-0 flex-1 overflow-auto p-2 text-[11px] leading-relaxed text-emerald-100">
            {detail
              ? JSON.stringify(detail.checkpoint, null, 2)
              : "// Select a checkpoint row to load ``values`` (safe allowlist)."}
          </pre>
        </section>
      </div>
    </div>
  );
}
