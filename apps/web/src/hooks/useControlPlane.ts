import { useCallback, useEffect, useRef, useState } from "react";

import type {
  AgentSnapshotDTO,
  DebugSnapshotPayload,
  WsMessage,
} from "../types/viewModel";

function wsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws`;
}

export type SessionLogLine = {
  t: string;
  kind: string;
  msg: string;
  /** Present when identical consecutive lines (STATE) were merged; show as xN in the UI. */
  repeat?: number;
};

/** Logged ``*.ai.json`` next to a replay frame, mapped on the server to ``proposal`` / HITL. */
export type ReplayAiSidecarState =
  | null
  | { kind: "loading"; frame: string }
  | { kind: "missing"; frame: string }
  | {
      kind: "ok";
      frame: string;
      proposal: Record<string, unknown> | null;
      pending_approval: Record<string, unknown> | null;
    };

export function useControlPlane() {
  const [snapshot, setSnapshot] = useState<DebugSnapshotPayload | null>(null);
  const [connected, setConnected] = useState(false);
  const [logLines, setLogLines] = useState<SessionLogLine[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  /** While true, ignore WebSocket snapshots so replay frames are not overwritten by server broadcasts. */
  const replayActiveRef = useRef(false);

  const pushLog = useCallback((kind: string, msg: string) => {
    const t = new Date().toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
    setLogLines((prev) => {
      const base = prev.slice(-200);
      if (
        kind === "STATE" &&
        base.length > 0 &&
        base[base.length - 1].kind === "STATE" &&
        base[base.length - 1].msg === msg
      ) {
        const last = base[base.length - 1];
        const repeat = (last.repeat ?? 1) + 1;
        return [...base.slice(0, -1), { ...last, t, repeat }];
      }
      return [...base, { t, kind, msg }];
    });
  }, []);

  const applyPayload = useCallback(
    (p: DebugSnapshotPayload) => {
      setSnapshot(p);
      if (p.state_id) {
        pushLog("STATE", `state_id ${p.state_id}`);
      }
    },
    [pushLog],
  );

  const fetchSnapshot = useCallback(async () => {
    const r = await fetch("/api/debug/snapshot");
    if (!r.ok) return;
    const data = (await r.json()) as DebugSnapshotPayload;
    applyPayload(data);
  }, [applyPayload]);

  const postIngress = useCallback(
    async (body: Record<string, unknown>) => {
      const r = await fetch("/api/debug/ingress", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        pushLog("ERROR", JSON.stringify(err));
        return;
      }
      const data = (await r.json()) as DebugSnapshotPayload;
      applyPayload(data);
    },
    [applyPayload, pushLog],
  );

  const [replayRuns, setReplayRuns] = useState<string[]>([]);
  const [replayPickerRun, setReplayPickerRun] = useState("");
  const [replayRunName, setReplayRunName] = useState("");
  const [replayFiles, setReplayFiles] = useState<string[]>([]);
  const [replayIndex, setReplayIndex] = useState(0);
  const [replayBusy, setReplayBusy] = useState(false);
  const [replayAiSidecar, setReplayAiSidecar] =
    useState<ReplayAiSidecarState>(null);

  const loadReplayFrameAt = useCallback(
    async (run: string, files: string[], index: number) => {
      const n = files.length;
      if (!run || n === 0) return;
      const i = Math.max(0, Math.min(n - 1, index));
      const file = files[i];
      if (!file) return;
      replayActiveRef.current = true;
      setReplayAiSidecar({ kind: "loading", frame: file });
      const r = await fetch(
        `/api/runs/${encodeURIComponent(run)}/frames/${encodeURIComponent(file)}`,
      );
      if (!r.ok) {
        const t = await r.text();
        pushLog("ERROR", `Replay frame: ${t}`);
        setReplayAiSidecar(null);
        return;
      }
      const body = (await r.json()) as Record<string, unknown>;
      await postIngress(body);
      setReplayIndex(i);
      pushLog("REPLAY", `${run} · ${file} · ${i + 1}/${n}`);
      try {
        const sr = await fetch(
          `/api/runs/${encodeURIComponent(run)}/frames/${encodeURIComponent(file)}/ai_sidecar`,
        );
        if (!sr.ok) {
          setReplayAiSidecar({ kind: "missing", frame: file });
          return;
        }
        const sd = (await sr.json()) as {
          ok?: boolean;
          proposal?: Record<string, unknown> | null;
          pending_approval?: Record<string, unknown> | null;
        };
        if (sd.ok === true) {
          setReplayAiSidecar({
            kind: "ok",
            frame: file,
            proposal: sd.proposal ?? null,
            pending_approval: sd.pending_approval ?? null,
          });
        } else {
          setReplayAiSidecar({ kind: "missing", frame: file });
        }
      } catch {
        setReplayAiSidecar({ kind: "missing", frame: file });
      }
    },
    [postIngress, pushLog],
  );

  const clearReplaySelection = useCallback(() => {
    replayActiveRef.current = false;
    setReplayRunName("");
    setReplayFiles([]);
    setReplayIndex(0);
    setReplayAiSidecar(null);
    void fetchSnapshot();
  }, [fetchSnapshot]);

  const loadReplayRun = useCallback(
    async (run: string) => {
      const trimmed = run.trim();
      if (!trimmed) {
        return;
      }
      replayActiveRef.current = true;
      setReplayBusy(true);
      try {
        const r = await fetch(
          `/api/runs/${encodeURIComponent(trimmed)}/frames`,
        );
        if (!r.ok) {
          const t = await r.text();
          pushLog("ERROR", `Replay manifest: ${t}`);
          replayActiveRef.current = false;
          setReplayAiSidecar(null);
          return;
        }
        const body = (await r.json()) as { files?: string[]; detail?: string };
        const files = body.files ?? [];
        if (files.length === 0) {
          pushLog("SYSTEM", `Run ${trimmed} has no state frames.`);
          replayActiveRef.current = false;
          setReplayAiSidecar(null);
          return;
        }
        setReplayRunName(trimmed);
        setReplayFiles(files);
        await loadReplayFrameAt(trimmed, files, 0);
      } finally {
        setReplayBusy(false);
      }
    },
    [loadReplayFrameAt, pushLog],
  );

  const replaySeek = useCallback(
    (delta: number) => {
      if (!replayRunName || replayFiles.length === 0 || replayBusy) return;
      setReplayBusy(true);
      void loadReplayFrameAt(
        replayRunName,
        replayFiles,
        replayIndex + delta,
      ).finally(() => setReplayBusy(false));
    },
    [
      loadReplayFrameAt,
      replayBusy,
      replayFiles,
      replayIndex,
      replayRunName,
    ],
  );

  const queueManualCommand = useCallback(
    async (command: string) => {
      const r = await fetch("/api/debug/manual_command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        pushLog("ERROR", JSON.stringify(err));
        return;
      }
      pushLog("ACTION", `Queued for game: ${command}`);
    },
    [pushLog],
  );

  const resumeAgent = useCallback(
    async (
      kind: "approve" | "reject" | "edit",
      editCommand?: string,
    ) => {
      const body: Record<string, unknown> = { kind };
      if (kind === "edit" && editCommand != null) body.command = editCommand;
      const r = await fetch("/api/agent/resume", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        pushLog("ERROR", JSON.stringify(err));
        return;
      }
      const data = (await r.json()) as AgentSnapshotDTO;
      pushLog("SYSTEM", `Agent resume ${kind}: ${JSON.stringify(data)}`);
      void fetchSnapshot();
    },
    [fetchSnapshot, pushLog],
  );

  const setAgentMode = useCallback(
    async (mode: "manual" | "propose" | "auto") => {
      const r = await fetch("/api/ai/mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        pushLog("ERROR", JSON.stringify(err));
        return;
      }
      pushLog("SYSTEM", `Agent mode → ${mode}`);
      void fetchSnapshot();
    },
    [fetchSnapshot, pushLog],
  );

  const retryAgent = useCallback(async () => {
    const r = await fetch("/api/agent/retry", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      pushLog("ERROR", JSON.stringify(err));
      return;
    }
    const data = (await r.json()) as DebugSnapshotPayload;
    applyPayload(data);
    void fetchSnapshot();
    pushLog(
      "SYSTEM",
      "Agent retry: cleared stuck proposal on the server; the game process must run the model again on the next state update.",
    );
  }, [applyPayload, fetchSnapshot, pushLog]);

  useEffect(() => {
    void fetchSnapshot();
  }, [fetchSnapshot]);

  useEffect(() => {
    void (async () => {
      try {
        const r = await fetch("/api/runs");
        if (!r.ok) return;
        const body = (await r.json()) as { runs?: string[]; status?: string };
        if (body.status === "error") return;
        setReplayRuns(body.runs ?? []);
      } catch {
        /* ignore */
      }
    })();
  }, []);

  useEffect(() => {
    const ws = new WebSocket(wsUrl());
    wsRef.current = ws;
    ws.onopen = () => {
      setConnected(true);
      pushLog("SYSTEM", "WebSocket connected");
    };
    ws.onclose = () => {
      setConnected(false);
      pushLog("SYSTEM", "WebSocket disconnected");
    };
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(String(ev.data)) as WsMessage;
        if (msg.type === "snapshot" && msg.payload) {
          if (replayActiveRef.current) return;
          applyPayload(msg.payload);
        }
      } catch {
        /* ignore */
      }
    };
    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [applyPayload, pushLog]);

  return {
    snapshot,
    connected,
    logLines,
    fetchSnapshot,
    postIngress,
    queueManualCommand,
    setAgentMode,
    resumeAgent,
    retryAgent,
    pushLog,
    replayRuns,
    replayPickerRun,
    setReplayPickerRun,
    replayRunName,
    replayFiles,
    replayIndex,
    replayBusy,
    loadReplayRun,
    replaySeek,
    clearReplaySelection,
    replayAiSidecar,
  };
}
