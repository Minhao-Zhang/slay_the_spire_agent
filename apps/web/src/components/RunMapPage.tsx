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
    archived,
    run,
    setRun,
    loading: metricsLoading,
    frameCount,
  } = useRunMetricsData();

  const isZip = run.toLowerCase().endsWith(".zip");
  const { payload: mapPayload, loading: mapLoading, errorLabel } =
    useMapHistoryData(run, isZip);

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
    <div className="min-h-screen bg-gradient-to-b from-slate-900 via-[#0a0d11] to-[#06080a] text-sm text-slate-300">
      <RunMetricsRunBar
        runs={runs}
        archived={archived}
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
          <p className="text-sm text-slate-500">Select a run to view maps.</p>
        ) : null}

        {isZip ? (
          <p className="text-sm text-slate-500">
            Map history is not available for zip archives.
          </p>
        ) : null}

        {run && !isZip && !mapLoading && mapPayload && !mapPayload.ok ? (
          <p className="text-sm text-amber-400/90">
            {mapPayload.reason === "read_error"
              ? "Could not read run directory for map history."
              : `Map history unavailable (${mapPayload.reason}).`}
          </p>
        ) : null}

        {run && !isZip && mapPayload?.ok && acts.length === 0 && !mapLoading ? (
          <p className="text-sm text-slate-500">
            No map data in captured frames yet.
          </p>
        ) : null}

        {acts.length > 0 ? (
          <>
            <div className="flex flex-wrap gap-2 border-b border-slate-700/80 pb-3">
              {acts.map((a, i) => (
                <button
                  key={a.act}
                  type="button"
                  onClick={() => setActTab(i)}
                  className={
                    "rounded border px-3 py-1.5 font-console text-xs font-semibold uppercase tracking-wide transition " +
                    (safeTab === i
                      ? "border-sky-600 bg-sky-950/60 text-sky-200"
                      : "border-slate-700 bg-slate-950/50 text-slate-400 hover:border-slate-600")
                  }
                >
                  Act {fmtIntEn(a.act)}
                  {a.boss_name ? (
                    <span className="ml-1 font-normal text-slate-500">
                      ({a.boss_name})
                    </span>
                  ) : null}
                </button>
              ))}
            </div>
            {current ? (
              <div className="space-y-2">
                <div className="min-h-[24rem] rounded border border-slate-700/80 bg-slate-950/30 p-2">
                  <MapView
                    mapData={mapViz}
                    bossAvailable={false}
                    readOnly
                    visitedPath={current.visited_path}
                  />
                </div>
                <p className="text-[11px] text-slate-500">
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
