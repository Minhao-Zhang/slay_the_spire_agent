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
}: {
  mapData: MapVizData | null | undefined;
  onChoose?: (command: string) => void;
  bossAvailable: boolean;
  /** Metrics / replay: no choose clicks; boss orb disabled. */
  readOnly?: boolean;
  /** Draw a path through these map coordinates (e.g. from map_history). */
  visitedPath?: Array<{ x: number; y: number }>;
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
        className="min-h-[8rem] w-full rounded border border-slate-800 bg-slate-950/50"
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
          className={isNext ? "text-sky-400" : "text-slate-600"}
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
          strokeWidth={2}
          strokeDasharray="6 4"
          vectorEffect="non-scaling-stroke"
          className="text-emerald-500/90"
        />,
      );
    }
  }

  const bp = colW > 0 ? getPos(3, maxY + 1) : { x: 0, y: 0 };

  return (
    <div
      ref={containerRef}
      className="relative w-full min-h-0 rounded border border-slate-800 bg-slate-950/50"
    >
      {cw > 0 ? (
        <>
          <svg
            className="pointer-events-none absolute left-0 top-0 z-[1] w-full text-slate-600"
            height={totalH}
            width="100%"
            aria-hidden
          >
            {visitedLineEls}
            {lineEls}
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
              return (
                <button
                  key={`node-${ni}-${n.x}-${n.y}`}
                  type="button"
                  disabled={!canClick}
                  title={canClick ? `#${nIdx}` : undefined}
                  onClick={() => onChoose(`choose ${nIdx}`)}
                  className={
                    "absolute flex h-7 w-7 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 font-console text-xs font-bold transition " +
                    (isCur
                      ? "border-amber-400 bg-amber-600 text-white shadow-[0_0_12px_rgba(251,191,36,0.45)]"
                      : wasVisited
                        ? "cursor-default border-emerald-600/90 bg-emerald-950/80 text-emerald-200"
                        : canClick
                          ? "cursor-pointer border-sky-500 bg-slate-900 text-sky-300 hover:bg-sky-900/80"
                          : "cursor-default border-slate-600 bg-slate-900/90 text-slate-500")
                  }
                  style={{ left: p.x, top: p.y }}
                >
                  {n.symbol ?? "?"}
                </button>
              );
            })}
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
                  ? "cursor-pointer border-red-500 bg-red-950/80 text-red-300 hover:bg-red-900/90"
                  : "cursor-not-allowed border-slate-700 bg-slate-900 text-slate-600 opacity-60")
              }
              style={{ left: bp.x, top: bp.y }}
            >
              {"\u2620"}
            </button>
          </div>
        </>
      ) : null}
    </div>
  );
}
