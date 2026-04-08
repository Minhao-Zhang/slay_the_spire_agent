import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import type { JsonRecord, MetricsSummary } from "../lib/runMetricsDerive";

export type MetricsResponse =
  | {
      ok: true;
      run: string;
      records: JsonRecord[];
      parse_errors?: string[];
      summary?: MetricsSummary;
    }
  | {
      ok: false;
      run: string;
      reason: string;
      records: JsonRecord[];
      parse_errors?: string[];
    };

const METRICS_POLL_MS = 3000;
const RUNS_POLL_MS = 8000;

function fingerprintMetricsResponse(data: MetricsResponse): string {
  const recs = data.records ?? [];
  const tail = recs.length ? JSON.stringify(recs[recs.length - 1]) : "";
  const pe = JSON.stringify(data.parse_errors ?? []);
  if (data.ok) {
    return `ok|${recs.length}|${tail}|${pe}|${JSON.stringify(data.summary ?? null)}`;
  }
  return `err|${data.reason}|${recs.length}|${tail}|${pe}`;
}

function fingerprintRunsPayload(body: { runs?: string[] }): string {
  return JSON.stringify({ runs: body.runs ?? [] });
}

export function useRunMetricsData() {
  const [searchParams, setSearchParams] = useSearchParams();
  const run = searchParams.get("run")?.trim() ?? "";

  const setRun = useCallback(
    (value: string) => {
      const v = value.trim();
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (v) next.set("run", v);
          else next.delete("run");
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const [runs, setRuns] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [payload, setPayload] = useState<MetricsResponse | null>(null);
  const [frameCount, setFrameCount] = useState<number | null>(null);

  const lastMetricsFpRef = useRef<string | null>(null);
  const lastRunsFpRef = useRef<string | null>(null);
  const metricsRequestGen = useRef(0);
  const runRef = useRef(run);
  runRef.current = run;

  const fetchRunsList = useCallback(async (silent: boolean) => {
    try {
      const r = await fetch("/api/runs");
      if (!r.ok) return;
      const body = (await r.json()) as {
        runs?: string[];
        status?: string;
      };
      if (body.status === "error") return;
      const fp = fingerprintRunsPayload(body);
      if (silent && fp === lastRunsFpRef.current) return;
      lastRunsFpRef.current = fp;
      setRuns(body.runs ?? []);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    void fetchRunsList(false);
    const id = window.setInterval(() => {
      if (document.visibilityState === "hidden") return;
      void fetchRunsList(true);
    }, RUNS_POLL_MS);
    return () => window.clearInterval(id);
  }, [fetchRunsList]);

  const loadMetrics = useCallback(async (runName: string, silent: boolean) => {
    if (!runName) {
      lastMetricsFpRef.current = null;
      setPayload(null);
      setFrameCount(null);
      return;
    }
    const gen = ++metricsRequestGen.current;
    if (!silent) {
      setLoading(true);
      setPayload(null);
      setFrameCount(null);
      lastMetricsFpRef.current = null;
    }
    try {
      const q = "?summary=1";
      const mr = await fetch(
        `/api/runs/${encodeURIComponent(runName)}/metrics${q}`,
      );
      const raw: unknown = await mr.json().catch(() => null);
      let data: MetricsResponse;
      if (!mr.ok) {
        const detail =
          raw &&
          typeof raw === "object" &&
          "detail" in raw &&
          typeof (raw as { detail: unknown }).detail === "string"
            ? (raw as { detail: string }).detail
            : null;
        data = {
          ok: false,
          run: runName,
          reason: `http_${mr.status}`,
          records: [],
          parse_errors: detail ? [detail] : undefined,
        };
      } else if (
        raw &&
        typeof raw === "object" &&
        typeof (raw as { ok?: unknown }).ok === "boolean" &&
        Array.isArray((raw as { records?: unknown }).records)
      ) {
        data = raw as MetricsResponse;
      } else {
        data = {
          ok: false,
          run: runName,
          reason: "invalid_response",
          records: [],
        };
      }
      if (gen !== metricsRequestGen.current) return;

      const fp = fingerprintMetricsResponse(data);
      if (silent && fp === lastMetricsFpRef.current) {
        return;
      }
      lastMetricsFpRef.current = fp;
      setPayload(data);

      const fr = await fetch(
        `/api/runs/${encodeURIComponent(runName)}/frames`,
      );
      if (gen !== metricsRequestGen.current) return;
      if (fr.ok) {
        const fb = (await fr.json()) as { count?: number };
        const n = fb.count;
        if (typeof n === "number") {
          setFrameCount((prev) => (prev === n ? prev : n));
        }
      }
    } catch {
      if (gen !== metricsRequestGen.current) return;
      const errPayload: MetricsResponse = {
        ok: false,
        run: runName,
        reason: "fetch_error",
        records: [],
      };
      const fp = fingerprintMetricsResponse(errPayload);
      if (silent && fp === lastMetricsFpRef.current) return;
      lastMetricsFpRef.current = fp;
      setPayload(errPayload);
    } finally {
      if (gen === metricsRequestGen.current && !silent) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadMetrics(run, false);
  }, [run, loadMetrics]);

  /** Zip archives are not listed; clear stale `?run=…zip` bookmarks. */
  useEffect(() => {
    if (run.toLowerCase().endsWith(".zip")) {
      setRun("");
    }
  }, [run, setRun]);

  useEffect(() => {
    if (!run) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === "hidden") return;
      const name = runRef.current;
      if (!name) return;
      void loadMetrics(name, true);
    }, METRICS_POLL_MS);
    return () => window.clearInterval(id);
  }, [run, loadMetrics]);

  const records = payload?.records ?? [];
  const parseErrors = payload?.parse_errors ?? [];

  return {
    runs,
    run,
    setRun,
    loading,
    payload,
    frameCount,
    records,
    parseErrors,
  };
}
