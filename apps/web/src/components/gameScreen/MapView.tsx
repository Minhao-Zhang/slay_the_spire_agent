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

const MAX_COL = 6;
const ROW_H = 70;

/** Port of ``renderFullMap`` from ``src/ui/templates/index.html`` (dark theme). */
export function MapView({
  mapData,
  onChoose,
  bossAvailable,
}: {
  mapData: MapVizData | null | undefined;
  onChoose: (command: string) => void;
  bossAvailable: boolean;
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
  nodes.forEach((n) => {
    if (n.y > maxY) maxY = n.y;
  });
  const colW = cw > 0 ? cw / (MAX_COL + 1) : 0;
  const totalH = (maxY + 2) * ROW_H;
  const getPos = (x: number, y: number) => ({
    x: (x + 0.5) * colW,
    y: totalH - (y + 1) * ROW_H,
  });

  const current = mapData?.current_node;
  const next = mapData?.next_nodes ?? [];

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
              const nIdx = next.findIndex(
                (nx) => nx.x === n.x && nx.y === n.y,
              );
              const canClick = nIdx !== -1;
              return (
                <button
                  key={`node-${ni}-${n.x}-${n.y}`}
                  type="button"
                  disabled={!canClick}
                  title={canClick ? `choose ${nIdx}` : undefined}
                  onClick={() => onChoose(`choose ${nIdx}`)}
                  className={
                    "absolute flex h-7 w-7 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 font-console text-xs font-bold transition " +
                    (isCur
                      ? "border-amber-400 bg-amber-600 text-white shadow-[0_0_12px_rgba(251,191,36,0.45)]"
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
              disabled={!bossAvailable}
              title={bossAvailable ? "choose boss" : undefined}
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
