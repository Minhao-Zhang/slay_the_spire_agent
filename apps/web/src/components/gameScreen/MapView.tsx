import {
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type MapChild = { x: number; y: number };

export type MapNode = {
  x: number;
  y: number;
  symbol?: string;
  children?: MapChild[];
};

export type MapVizData = {
  nodes: MapNode[];
  current_node?: { x: number; y: number } | null;
  next_nodes?: { x: number; y: number }[];
  boss_available?: boolean;
};

/** Minimum grid span so boss column (x=3) and typical acts fit. */
const MIN_GRID_MAX_X = 6;
const ROW_H = 78;

/** Aligns with `map_analysis._SYMBOL_TO_BUCKET` (CommunicationMod single-char symbols). */
type MapRoomBucket =
  | "monster"
  | "elite"
  | "rest"
  | "shop"
  | "event"
  | "treasure"
  | "unknown";

function bucketForSymbol(symbol: string | undefined): MapRoomBucket {
  const ch = (symbol?.trim() || "?")[0] ?? "?";
  switch (ch) {
    case "M":
      return "monster";
    case "E":
      return "elite";
    case "R":
      return "rest";
    case "$":
      return "shop";
    case "?":
      return "event";
    case "T":
      return "treasure";
    default:
      return "unknown";
  }
}

/** Bucket fills — jewel tones on parchment map (borders align with theme accents). */
const BUCKET_STYLE: Record<
  MapRoomBucket,
  { bg: string; border: string; fg: string }
> = {
  monster: { bg: "rgb(248 160 160 / 0.55)", border: "#b91c1c", fg: "#14110c" },
  elite: { bg: "rgb(245 200 120 / 0.55)", border: "#9a6d00", fg: "#14110c" },
  rest: { bg: "rgb(130 220 180 / 0.5)", border: "#059669", fg: "#14110c" },
  shop: { bg: "rgb(150 190 255 / 0.5)", border: "#2563eb", fg: "#14110c" },
  event: { bg: "rgb(190 170 248 / 0.48)", border: "#5b21b6", fg: "#14110c" },
  treasure: { bg: "rgb(230 200 120 / 0.52)", border: "#7a5500", fg: "#14110c" },
  unknown: { bg: "rgb(175 168 152 / 0.65)", border: "#6b5e4e", fg: "#14110c" },
};

function nodeKey(x: number, y: number): string {
  return `${x},${y}`;
}

function buildKnownNodeSet(nodes: MapNode[]): Set<string> {
  return new Set(nodes.map((n) => nodeKey(n.x, n.y)));
}

/** Undirected adjacency: edge exists in either direction along `children` links. */
function buildUndirectedEdgeSet(nodes: MapNode[]): Set<string> {
  const edges = new Set<string>();
  const order = (x1: number, y1: number, x2: number, y2: number) => {
    const a = nodeKey(x1, y1);
    const b = nodeKey(x2, y2);
    return a < b ? `${a}|${b}` : `${b}|${a}`;
  };
  for (const n of nodes) {
    for (const c of n.children ?? []) {
      edges.add(order(n.x, n.y, c.x, c.y));
    }
  }
  return edges;
}

function areAdjacentOnMap(
  edgeSet: Set<string>,
  a: { x: number; y: number },
  b: { x: number; y: number },
): boolean {
  const k1 = nodeKey(a.x, a.y);
  const k2 = nodeKey(b.x, b.y);
  const und = k1 < k2 ? `${k1}|${k2}` : `${k2}|${k1}`;
  return edgeSet.has(und);
}

/** Drop off-graph points, NaN, and consecutive duplicates (log noise / act bleed). */
function sanitizeVisitedPath(
  path: Array<{ x: number; y: number }> | undefined,
  known: Set<string>,
): Array<{ x: number; y: number }> {
  if (!path?.length) return [];
  const out: Array<{ x: number; y: number }> = [];
  for (const p of path) {
    const xi = Math.round(Number(p.x));
    const yi = Math.round(Number(p.y));
    if (!Number.isFinite(xi) || !Number.isFinite(yi)) continue;
    const k = nodeKey(xi, yi);
    if (!known.has(k)) continue;
    const last = out[out.length - 1];
    if (last && last.x === xi && last.y === yi) continue;
    out.push({ x: xi, y: yi });
  }
  return out;
}

/** Dashboard-style map view (dark theme). */
export function MapView({
  mapData,
  onChoose = () => {},
  bossAvailable,
  readOnly = false,
  visitedPath,
  /** Hide synthetic boss orb (e.g. run map analytics — boss shown in page chrome). */
  hideBossNode = false,
}: {
  mapData: MapVizData | null | undefined;
  onChoose?: (command: string) => void;
  bossAvailable: boolean;
  /** Metrics / replay: no choose clicks; boss orb disabled. */
  readOnly?: boolean;
  /** Draw a path through these map coordinates (e.g. from map_history). */
  visitedPath?: Array<{ x: number; y: number }>;
  hideBossNode?: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [cw, setCw] = useState(0);

  const measure = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    setCw(el.clientWidth);
  }, []);

  useLayoutEffect(() => {
    measure();
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => measure());
    ro.observe(el);
    return () => ro.disconnect();
  }, [measure]);

  const nodes = mapData?.nodes;
  if (!nodes?.length) {
    return (
      <div
        ref={containerRef}
        className="min-h-[8rem] w-full rounded border border-spire-border-muted bg-spire-inset/50"
      />
    );
  }

  let maxY = 0;
  let maxX = 0;
  nodes.forEach((n) => {
    if (n.y > maxY) maxY = n.y;
    if (n.x > maxX) maxX = n.x;
  });
  const gridMaxX = Math.max(MIN_GRID_MAX_X, maxX);
  const colSpan = gridMaxX + 1 + 0.75;
  const colW = cw > 0 ? cw / colSpan : 0;
  const totalH = (maxY + 2) * ROW_H;
  const getPos = (x: number, y: number) => ({
    x: (x + 0.5) * colW,
    y: totalH - (y + 1) * ROW_H,
  });

  const knownNodes = buildKnownNodeSet(nodes);
  const edgeSet = buildUndirectedEdgeSet(nodes);
  const safeVisited = sanitizeVisitedPath(visitedPath, knownNodes);

  const current = mapData?.current_node;
  const next = readOnly ? [] : (mapData?.next_nodes ?? []);
  const visitedSet = new Set(safeVisited.map((p) => nodeKey(p.x, p.y)));

  const lineEls: ReactNode[] = [];
  nodes.forEach((n) => {
    if (colW <= 0) return;
    const p = getPos(n.x, n.y);
    (n.children ?? []).forEach((c) => {
      const ck = nodeKey(c.x, c.y);
      // Drop synthetic edges to the boss orb / off-graph targets (not real room nodes).
      if (!knownNodes.has(ck)) return;
      const ep = getPos(c.x, c.y);
      const isNext =
        current != null &&
        n.x === current.x &&
        n.y === current.y &&
        next.some((nx) => nx.x === c.x && nx.y === c.y);
      lineEls.push(
        <line
          key={`${n.x},${n.y}-${c.x},${c.y}`}
          x1={p.x}
          y1={p.y}
          x2={ep.x}
          y2={ep.y}
          stroke="currentColor"
          strokeWidth={isNext ? 2 : 1}
          strokeDasharray={isNext ? undefined : "4 3"}
          vectorEffect="non-scaling-stroke"
          className={isNext ? "text-spire-accent" : "text-spire-faint"}
        />,
      );
    });
  });

  const visitedLineEls: ReactNode[] = [];
  if (colW > 0 && safeVisited.length > 1) {
    for (let i = 0; i < safeVisited.length - 1; i++) {
      const a = safeVisited[i];
      const b = safeVisited[i + 1];
      if (!areAdjacentOnMap(edgeSet, a, b)) continue;
      const p0 = getPos(a.x, a.y);
      const p1 = getPos(b.x, b.y);
      if (
        !Number.isFinite(p0.x) ||
        !Number.isFinite(p0.y) ||
        !Number.isFinite(p1.x) ||
        !Number.isFinite(p1.y)
      ) {
        continue;
      }
      visitedLineEls.push(
        <line
          key={`v-${a.x},${a.y}-${b.x},${b.y}-${i}`}
          x1={p0.x}
          y1={p0.y}
          x2={p1.x}
          y2={p1.y}
          stroke="currentColor"
          strokeWidth={2.5}
          vectorEffect="non-scaling-stroke"
          className="text-spire-success/90"
        />,
      );
    }
  }

  const bp = colW > 0 ? getPos(3, maxY + 1) : { x: 0, y: 0 };

  return (
    <div
      ref={containerRef}
      className="relative w-full min-h-0 rounded border border-spire-border-muted bg-spire-inset/50"
    >
      {cw > 0 ? (
        <>
          <svg
            className="pointer-events-none absolute left-0 top-0 z-[1] w-full text-spire-faint"
            height={totalH}
            width="100%"
            aria-hidden
          >
            {lineEls}
            {visitedLineEls}
          </svg>
          <div
            className="relative z-[2]"
            style={{ height: totalH, minHeight: totalH }}
          >
            {nodes.map((n, ni) => {
              const p = getPos(n.x, n.y);
              const isCur =
                current != null && n.x === current.x && n.y === current.y;
              const wasVisited = visitedSet.has(`${n.x},${n.y}`);
              const nIdx = next.findIndex(
                (nx) => nx.x === n.x && nx.y === n.y,
              );
              const canClick = !readOnly && nIdx !== -1;
              const bucket = bucketForSymbol(n.symbol);
              const pal = BUCKET_STYLE[bucket];
              const readOnlyTip =
                readOnly && (n.symbol === "?" || n.symbol === undefined)
                  ? "? — event room in mod data, or missing symbol on this frame"
                  : readOnly
                    ? `${n.symbol ?? "?"} (${bucket})`
                    : undefined;
              return (
                <button
                  key={`node-${ni}-${n.x}-${n.y}`}
                  type="button"
                  disabled={!canClick}
                  title={
                    canClick
                      ? `#${nIdx}`
                      : readOnlyTip ?? (wasVisited ? "Visited" : undefined)
                  }
                  onClick={() => onChoose(`choose ${nIdx}`)}
                  className={
                    "absolute flex h-7 w-7 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 font-console text-xs font-bold transition " +
                    (isCur
                      ? "z-[3] border-spire-warning bg-spire-warning text-spire-primary shadow-[0_0_12px_color-mix(in_srgb,var(--warning)_45%,transparent)]"
                      : canClick
                        ? "cursor-pointer border-spire-accent bg-spire-canvas text-spire-accent hover:bg-spire-tab-active/90"
                        : wasVisited
                          ? "cursor-default ring-2 ring-spire-success/55 ring-offset-2 ring-offset-spire-canvas"
                          : "cursor-default")
                  }
                  style={
                    isCur || canClick
                      ? { left: p.x, top: p.y }
                      : {
                          left: p.x,
                          top: p.y,
                          backgroundColor: pal.bg,
                          borderColor: pal.border,
                          color: pal.fg,
                        }
                  }
                >
                  {n.symbol ?? "?"}
                </button>
              );
            })}
            {!hideBossNode ? (
            <button
              type="button"
              disabled={readOnly || !bossAvailable}
              title={
                readOnly
                  ? undefined
                  : bossAvailable
                    ? "choose boss"
                    : undefined
              }
              onClick={() => onChoose("choose boss")}
              className={
                "absolute flex h-[52px] w-[52px] -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 font-console text-xl font-bold transition " +
                (bossAvailable
                  ? "cursor-pointer border-spire-danger bg-spire-danger/20 text-spire-danger hover:bg-spire-danger/28"
                  : "cursor-not-allowed border-spire-border-subtle bg-spire-canvas text-spire-faint opacity-60")
              }
              style={{ left: bp.x, top: bp.y }}
            >
              {"\u2620"}
            </button>
            ) : null}
          </div>
        </>
      ) : null}
    </div>
  );
}
