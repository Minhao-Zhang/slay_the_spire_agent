import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fmtIntEn, fmtNumEn } from "../lib/formatDisplayNumber";
import { SpireAgentNav } from "./SpireAgentNav";

const SLATE_AXIS = { stroke: "#64748b", fontSize: 11 };
const GRID = { stroke: "#334155", strokeDasharray: "3 3" };
const CHART_H = 220;
const CHART_MARGIN = { top: 8, right: 8, left: 4, bottom: 0 };

type ExperimentRunRow = {
  run: string;
  experiment_id?: string;
  experiment_tag?: string;
  max_floor?: number | null;
  victory?: boolean | null;
  deck_size_at_end?: number | null;
  ai_decisions?: number;
  total_tokens?: number;
  avg_latency_ms?: number | null;
};

type ExperimentGroup = {
  experiment_id: string;
  experiment_tag: string;
  experiment_tags?: Record<string, number>;
  run_count: number;
  completed_runs?: number;
  wins?: number;
  losses?: number;
  win_rate?: number | null;
  win_rate_wilson_95?: [number, number] | null;
  avg_max_floor?: number | null;
  avg_deck_size_at_end?: number | null;
  avg_tokens_per_run?: number | null;
  avg_latency_per_decision_ms?: number | null;
  card_reward_skip_rate?: number | null;
  potion_use_rate?: number | null;
  runs: ExperimentRunRow[];
};

type ExperimentsPayload = {
  ok: boolean;
  paired?: boolean;
  message?: string;
  logs_dir?: string;
  groups?: Record<string, ExperimentGroup>;
  runs?: ExperimentRunRow[];
};

function pct(x: number | null | undefined): string {
  if (x == null || Number.isNaN(x)) return "—";
  return `${fmtNumEn(x * 100, 1)}%`;
}

export function MultiRunMetricsPage() {
  const [data, setData] = useState<ExperimentsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string>("");
  const [pairA, setPairA] = useState("");
  const [pairB, setPairB] = useState("");
  const [pairedResult, setPairedResult] = useState<Record<
    string,
    unknown
  > | null>(null);
  const [pairLoading, setPairLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch("/api/experiments");
      const j = (await r.json()) as ExperimentsPayload;
      setData(j);
      if (!j.ok) {
        setError(j.message ?? "Request failed");
      } else if (j.groups) {
        const ids = Object.keys(j.groups).sort();
        setSelectedId((cur) => (cur && j.groups![cur] ? cur : ids[0] ?? ""));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const groups = data?.groups ?? {};
  const groupList = useMemo(
    () => Object.entries(groups).sort(([a], [b]) => a.localeCompare(b)),
    [groups],
  );

  const selectedGroup = selectedId ? groups[selectedId] : undefined;

  const chartRows = useMemo(() => {
    if (!selectedGroup?.runs?.length) return [];
    return [...selectedGroup.runs]
      .sort((a, b) => String(a.run).localeCompare(String(b.run)))
      .map((r, i) => ({
        idx: i + 1,
        floor:
          typeof r.max_floor === "number" && Number.isFinite(r.max_floor)
            ? r.max_floor
            : null,
        deck:
          typeof r.deck_size_at_end === "number" &&
          Number.isFinite(r.deck_size_at_end)
            ? r.deck_size_at_end
            : null,
        run: r.run,
      }));
  }, [selectedGroup]);

  const runPaired = async () => {
    const a = pairA.trim();
    const b = pairB.trim();
    if (!a || !b) return;
    setPairLoading(true);
    setPairedResult(null);
    try {
      const q = new URLSearchParams({ exp_a: a, exp_b: b });
      const r = await fetch(`/api/experiments?${q}`);
      const j = (await r.json()) as Record<string, unknown>;
      if (j.ok && j.comparison) {
        setPairedResult(j.comparison as Record<string, unknown>);
      } else {
        setPairedResult({ error: j.message ?? "paired request failed" });
      }
    } catch (e) {
      setPairedResult({
        error: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setPairLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-900 via-[#0a0d11] to-[#06080a] text-sm text-slate-300">
      <header className="border-b border-slate-700/80 bg-slate-950/50 px-4 py-3">
        <SpireAgentNav page="compare" runQuery="" />
        <p className="mt-2 max-w-3xl text-xs text-slate-500">
          Grouped by <code className="text-sky-400/90">experiment_id</code> from
          AI logs under <code className="text-slate-400">logs/games</code>.
        </p>
      </header>

      <main className="space-y-6 px-4 py-5">
        {loading ? (
          <p className="text-xs text-slate-500">Loading experiments…</p>
        ) : null}
        {error ? (
          <div
            className="rounded border border-amber-800/60 bg-amber-950/40 px-3 py-2 text-xs text-amber-100"
            role="alert"
          >
            {error}
          </div>
        ) : null}

        {data?.ok && groupList.length > 0 ? (
          <>
            <section className="overflow-x-auto rounded border border-slate-700/80 bg-slate-950/40">
              <table className="w-full min-w-[720px] border-collapse text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-700/80 text-slate-500">
                    <th className="px-3 py-2 font-semibold uppercase tracking-wide">
                      experiment_id
                    </th>
                    <th className="px-3 py-2 font-semibold uppercase tracking-wide">
                      tag
                    </th>
                    <th className="px-3 py-2 font-semibold uppercase tracking-wide">
                      runs
                    </th>
                    <th className="px-3 py-2 font-semibold uppercase tracking-wide">
                      win rate
                    </th>
                    <th className="px-3 py-2 font-semibold uppercase tracking-wide">
                      Wilson 95%
                    </th>
                    <th className="px-3 py-2 font-semibold uppercase tracking-wide">
                      avg floor
                    </th>
                    <th className="px-3 py-2 font-semibold uppercase tracking-wide">
                      avg deck
                    </th>
                    <th className="px-3 py-2 font-semibold uppercase tracking-wide">
                      tok/run
                    </th>
                    <th className="px-3 py-2 font-semibold uppercase tracking-wide">
                      lat/dec
                    </th>
                    <th className="px-3 py-2 font-semibold uppercase tracking-wide">
                      skip%
                    </th>
                    <th className="px-3 py-2 font-semibold uppercase tracking-wide">
                      potion%
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {groupList.map(([id, g]) => (
                    <tr
                      key={id}
                      className={
                        "cursor-pointer border-b border-slate-800/80 hover:bg-slate-900/60 " +
                        (selectedId === id ? "bg-sky-950/30" : "")
                      }
                      onClick={() => setSelectedId(id)}
                    >
                      <td className="px-3 py-2 font-mono text-[11px] text-sky-300">
                        {g.experiment_id}
                      </td>
                      <td className="px-3 py-2 text-slate-400">
                        {g.experiment_tag || "—"}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        {fmtIntEn(g.run_count)}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        {g.win_rate != null ? pct(g.win_rate) : "—"}
                      </td>
                      <td className="px-3 py-2 font-mono text-[10px] text-slate-500">
                        {g.win_rate_wilson_95
                          ? `${pct(g.win_rate_wilson_95[0])}–${pct(g.win_rate_wilson_95[1])}`
                          : "—"}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        {g.avg_max_floor != null
                          ? fmtNumEn(g.avg_max_floor, 1)
                          : "—"}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        {g.avg_deck_size_at_end != null
                          ? fmtNumEn(g.avg_deck_size_at_end, 1)
                          : "—"}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        {g.avg_tokens_per_run != null
                          ? fmtIntEn(Math.round(g.avg_tokens_per_run))
                          : "—"}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        {g.avg_latency_per_decision_ms != null
                          ? `${fmtNumEn(g.avg_latency_per_decision_ms, 0)}ms`
                          : "—"}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        {g.card_reward_skip_rate != null
                          ? pct(g.card_reward_skip_rate)
                          : "—"}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        {g.potion_use_rate != null
                          ? pct(g.potion_use_rate)
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            {selectedGroup ? (
              <section className="space-y-4">
                <h2 className="font-console text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Charts for{" "}
                  <span className="text-sky-400">{selectedGroup.experiment_id}</span>
                </h2>
                <div className="grid gap-6 lg:grid-cols-2">
                  <div className="rounded border border-slate-700/80 bg-slate-950/40 p-3">
                    <div className="mb-2 text-xs font-semibold text-slate-400">
                      Max floor by run index
                    </div>
                    <div style={{ height: CHART_H }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart
                          data={chartRows}
                          margin={CHART_MARGIN}
                        >
                          <CartesianGrid {...GRID} />
                          <XAxis
                            dataKey="idx"
                            tick={SLATE_AXIS}
                            label={{
                              value: "run #",
                              fill: "#64748b",
                              fontSize: 10,
                            }}
                          />
                          <YAxis tick={SLATE_AXIS} allowDecimals={false} />
                          <Tooltip
                            contentStyle={{
                              background: "#0f172a",
                              border: "1px solid #334155",
                              fontSize: 11,
                            }}
                            formatter={(v: unknown) =>
                              v == null || v === "" ? "—" : String(v)
                            }
                            labelFormatter={(_, payload) => {
                              const p = payload?.[0]?.payload as {
                                run?: string;
                              };
                              return p?.run ? `run: ${p.run}` : "";
                            }}
                          />
                          <Line
                            type="monotone"
                            dataKey="floor"
                            name="floor"
                            stroke="#38bdf8"
                            strokeWidth={2}
                            dot={{ r: 2 }}
                            connectNulls
                            isAnimationActive={false}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                  <div className="rounded border border-slate-700/80 bg-slate-950/40 p-3">
                    <div className="mb-2 text-xs font-semibold text-slate-400">
                      Deck size at end by run index
                    </div>
                    <div style={{ height: CHART_H }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={chartRows} margin={CHART_MARGIN}>
                          <CartesianGrid {...GRID} />
                          <XAxis dataKey="idx" tick={SLATE_AXIS} />
                          <YAxis tick={SLATE_AXIS} allowDecimals={false} />
                          <Tooltip
                            contentStyle={{
                              background: "#0f172a",
                              border: "1px solid #334155",
                              fontSize: 11,
                            }}
                            formatter={(v: unknown) =>
                              v == null || v === "" ? "—" : String(v)
                            }
                            labelFormatter={(_, payload) => {
                              const p = payload?.[0]?.payload as {
                                run?: string;
                              };
                              return p?.run ? `run: ${p.run}` : "";
                            }}
                          />
                          <Bar
                            dataKey="deck"
                            fill="#a78bfa"
                            isAnimationActive={false}
                            maxBarSize={28}
                          />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </div>
              </section>
            ) : null}

            <section className="rounded border border-slate-700/80 bg-slate-950/40 p-4">
              <h2 className="mb-3 font-console text-xs font-semibold uppercase tracking-wide text-slate-500">
                Paired comparison (same seed)
              </h2>
              <div className="flex flex-wrap items-end gap-3">
                <label className="flex flex-col gap-1 text-xs">
                  <span className="text-slate-500">experiment_id A</span>
                  <input
                    className="rounded border border-slate-600 bg-slate-900 px-2 py-1 font-mono text-xs text-slate-200"
                    value={pairA}
                    onChange={(e) => setPairA(e.target.value)}
                    placeholder="exp_a"
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs">
                  <span className="text-slate-500">experiment_id B</span>
                  <input
                    className="rounded border border-slate-600 bg-slate-900 px-2 py-1 font-mono text-xs text-slate-200"
                    value={pairB}
                    onChange={(e) => setPairB(e.target.value)}
                    placeholder="exp_b"
                  />
                </label>
                <button
                  type="button"
                  disabled={pairLoading || !pairA.trim() || !pairB.trim()}
                  onClick={() => void runPaired()}
                  className="rounded bg-sky-700 px-3 py-1.5 font-console text-xs font-semibold uppercase tracking-wide text-white hover:bg-sky-600 disabled:opacity-40"
                >
                  {pairLoading ? "…" : "Compare"}
                </button>
              </div>
              {pairedResult ? (
                <pre className="mt-3 max-h-80 overflow-auto rounded border border-slate-800 bg-slate-950 p-3 font-mono text-[10px] text-slate-400">
                  {JSON.stringify(pairedResult, null, 2)}
                </pre>
              ) : null}
            </section>
          </>
        ) : !loading && data?.ok && groupList.length === 0 ? (
          <p className="text-xs text-slate-500">
            No runs found under logs/games, or no AI sidecars with{" "}
            <code className="text-sky-400/90">experiment_id</code>.
          </p>
        ) : null}
      </main>
    </div>
  );
}
