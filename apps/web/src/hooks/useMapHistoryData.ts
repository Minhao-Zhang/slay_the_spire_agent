import { useCallback, useEffect, useRef, useState } from "react";

import type { MapNode } from "../components/gameScreen/MapView";

export type MapHistoryAct = {
  act: number;
  nodes: MapNode[];
  visited_path: Array<{ x: number; y: number; symbol?: string }>;
  boss_name?: string | null;
};

export type MapHistoryResponse =
  | { ok: true; run: string; acts: MapHistoryAct[] }
  | { ok: false; run: string; reason: string; acts: MapHistoryAct[] };

const MAP_POLL_MS = 5000;

function fingerprintMapHistory(data: MapHistoryResponse): string {
  if (!data.ok) {
    return `err|${data.reason}|${data.run}`;
  }
  const acts = data.acts ?? [];
  const parts = acts.map((a) => {
    const plen = a.visited_path?.length ?? 0;
    const last =
      plen > 0
        ? `${a.visited_path[plen - 1].x},${a.visited_path[plen - 1].y}`
        : "";
    return `${a.act}|${a.nodes?.length ?? 0}|${plen}|${last}`;
  });
  return `ok|${data.run}|${parts.join(";")}`;
}

export function useMapHistoryData(run: string, isZip: boolean) {
  const [payload, setPayload] = useState<MapHistoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const lastFpRef = useRef<string | null>(null);
  const reqGen = useRef(0);

  useEffect(() => {
    if (!run || isZip) {
      lastFpRef.current = null;
      setPayload(null);
      setLoading(false);
    }
  }, [run, isZip]);

  const load = useCallback(async (silent: boolean) => {
    if (!run || isZip) {
      lastFpRef.current = null;
      setPayload(null);
      return;
    }
    const gen = ++reqGen.current;
    if (!silent) {
      setLoading(true);
      setPayload(null);
      lastFpRef.current = null;
    }
    try {
      const r = await fetch(
        `/api/runs/${encodeURIComponent(run)}/map_history`,
      );
      const data = (await r.json()) as MapHistoryResponse;
      if (gen !== reqGen.current) return;
      const fp = fingerprintMapHistory(data);
      if (silent && fp === lastFpRef.current) return;
      lastFpRef.current = fp;
      setPayload(data);
    } catch {
      if (gen !== reqGen.current) return;
      const err: MapHistoryResponse = {
        ok: false,
        run,
        reason: "fetch_error",
        acts: [],
      };
      const fp = fingerprintMapHistory(err);
      if (silent && fp === lastFpRef.current) return;
      lastFpRef.current = fp;
      setPayload(err);
    } finally {
      if (gen === reqGen.current && !silent) {
        setLoading(false);
      }
    }
  }, [run, isZip]);

  useEffect(() => {
    void load(false);
  }, [load]);

  useEffect(() => {
    if (!run || isZip) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === "hidden") return;
      void load(true);
    }, MAP_POLL_MS);
    return () => window.clearInterval(id);
  }, [run, isZip, load]);

  const errorLabel =
    payload && !payload.ok
      ? payload.reason === "zip_archive"
        ? "Map history unavailable for zip archives."
        : payload.reason === "fetch_error"
          ? "Could not load map history."
          : `Map: ${payload.reason}`
      : null;

  return { payload, loading, errorLabel, reload: () => void load(false) };
}
