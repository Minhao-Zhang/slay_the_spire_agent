import { useEffect, useMemo, useState } from "react";

import { useMapHistoryData } from "../hooks/useMapHistoryData";
import { useRunMetricsData } from "../hooks/useRunMetricsData";
import { fmtIntEn } from "../lib/formatDisplayNumber";
import { MapView, type MapNode, type MapVizData } from "./gameScreen/MapView";
import { RunMetricsRunBar } from "./RunMetricsRunBar";

function asMapNodes(raw: unknown): MapNode[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (n) =>
      n &&
      typeof n === "object" &&
      typeof (n as MapNode).x === "number" &&
      typeof (n as MapNode).y === "number",
  ) as MapNode[];
}

export function RunMapPage() {
  const {
    runs,
    run,
    setRun,
    loading: metricsLoading,
    frameCount,
  } = useRunMetricsData();

  const { payload: mapPayload, loading: mapLoading, errorLabel } =
    useMapHistoryData(run);

  const acts = useMemo(() => {
    if (!mapPayload?.ok) return [];
    return mapPayload.acts.map((a) => ({
      act: a.act,
      nodes: asMapNodes(a.nodes),
      visited_path: (a.visited_path ?? []).map((p) => ({
        x: p.x,
        y: p.y,
        symbol: p.symbol,
      })),
      boss_name: a.boss_name ?? null,
    }));
  }, [mapPayload]);

  const [actTab, setActTab] = useState(0);
  useEffect(() => {
    setActTab(0);
  }, [run, acts.length]);

  const safeTab = acts.length ? Math.min(actTab, acts.length - 1) : 0;
  const current = acts[safeTab];

  const mapViz: MapVizData | null = useMemo(() => {
    if (!current?.nodes?.length) return null;
    const path = current.visited_path;
    const last = path.length ? path[path.length - 1] : null;
    return {
      nodes: current.nodes,
      current_node: last ? { x: last.x, y: last.y } : null,
      next_nodes: [],
      boss_available: false,
    };
  }, [current]);

  return (
    <div className="metrics-page-bg min-h-screen text-sm text-[var(--text-primary)]">
      <RunMetricsRunBar
        runs={runs}
        run={run}
        onRunChange={setRun}
        loading={metricsLoading}
        frameCount={frameCount}
        metricsReason={null}
        variant="map"
        mapLoading={mapLoading}
        mapError={errorLabel}
      />

      <main className="space-y-4 px-4 py-5">
        {!run ? (
          <p className="text-sm text-spire-label">Select a run to view maps.</p>
        ) : null}

        {run && !mapLoading && mapPayload && !mapPayload.ok ? (
          <p className="text-sm text-spire-warning/90">
            {mapPayload.reason === "read_error"
              ? "Could not read run directory for map history."
              : `Map history unavailable (${mapPayload.reason}).`}
          </p>
        ) : null}

        {run && mapPayload?.ok && acts.length === 0 && !mapLoading ? (
          <p className="text-sm text-spire-label">
            No map data in captured frames yet.
          </p>
        ) : null}

        {acts.length > 0 ? (
          <>
            <div className="flex flex-wrap gap-2 border-b border-spire-border-subtle/80 pb-3">
              {acts.map((a, i) => (
                <button
                  key={a.act}
                  type="button"
                  onClick={() => setActTab(i)}
                  className={
                    "rounded border px-3 py-1.5 font-console text-xs font-semibold uppercase tracking-wide transition " +
                    (safeTab === i
                      ? "border-spire-accent bg-spire-live-surface text-spire-primary"
                      : "border-spire-border-subtle bg-spire-inset/50 text-spire-muted hover:border-spire-border-strong")
                  }
                >
                  Act {fmtIntEn(a.act)}
                  {a.boss_name ? (
                    <span className="ml-1 font-normal text-spire-label">
                      ({a.boss_name})
                    </span>
                  ) : null}
                </button>
              ))}
            </div>
            {current ? (
              <div className="space-y-2">
                {current.boss_name ? (
                  <div className="rounded border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-panel)_55%,transparent)] px-3 py-2 font-console text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                    Boss:{" "}
                    <span className="normal-case tracking-normal text-[var(--text-primary)]">
                      {current.boss_name}
                    </span>
                  </div>
                ) : null}
                <div className="min-h-[24rem] rounded border border-spire-border-subtle/80 bg-spire-inset/30 p-2">
                  <MapView
                    mapData={mapViz}
                    bossAvailable={false}
                    readOnly
                    hideBossNode
                    visitedPath={current.visited_path}
                  />
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-2 text-[13px] text-spire-label">
                  <span className="font-console font-semibold uppercase tracking-wide text-spire-muted">
                    Legend
                  </span>
                  {(
                    [
                      ["M", "Monster"],
                      ["E", "Elite"],
                      ["R", "Rest"],
                      ["$", "Shop"],
                      ["?", "Event / missing"],
                      ["T", "Treasure"],
                    ] as const
                  ).map(([sym, label]) => (
                    <span key={sym} className="tabular-nums">
                      <span className="font-mono text-spire-primary">{sym}</span>{" "}
                      {label}
                    </span>
                  ))}
                </div>
                <p className="text-[13px] text-spire-label">
                  Visited steps: {fmtIntEn(current.visited_path.length)} · Nodes:{" "}
                  {fmtIntEn(current.nodes.length)}
                </p>
              </div>
            ) : null}
          </>
        ) : null}
      </main>
    </div>
  );
}
