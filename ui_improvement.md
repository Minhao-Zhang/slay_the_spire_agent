# UI improvement notes

This document covers **Monitor** (`/`), **Run metrics** (`/metrics`), **Run map** (`/metrics/map`), and a **strategic case for rewriting** large frontend surfaces to shed technical and visual debt. The product assumption for the operator UI is **desktop-first** and **high information density** where noted.

**Product decision — Compare runs:** **Remove the compare surface entirely** — route **`/metrics/compare`**, **`MultiRunMetricsPage`**, and **nav links** (e.g. in `SpireAgentNav`). Multi-run analytics are **not ready**; the single-run metrics and operator story should harden first. Reintroduce a compare experience only with an explicit product spec and API backing (do not keep a half-maintained page in the shell).

**Reference screenshot (Monitor):** [`docs/images/dashboard_screenshot.png`](docs/images/dashboard_screenshot.png) (also embedded in the README).

---

## Ground truth (verified in repo)

Use this table when scoping work; refresh line counts after large refactors (`wc -l` on the paths below).

| Topic | Location / value |
|--------|------------------|
| **Routes** | [`apps/web/src/App.tsx`](apps/web/src/App.tsx): `/` → `MonitorDashboard`; `/metrics` → `RunMetricsPage`; `/metrics/map` → `RunMapPage`; `/metrics/debug` → redirect to `/metrics`. **`/metrics/compare` exists today but is scheduled for removal** (see product decision above). |
| **Dev server** | [`apps/web/vite.config.ts`](apps/web/vite.config.ts): port **5173** (`strictPort: true`); proxies **`/api`** and **`/ws`** to `http://127.0.0.1:8000`. Files in [`apps/web/public/`](apps/web/public/) are served at the site root (theme sampler: `/theme-preview.html`). |
| **Large UI modules** | [`RunMetricsPage.tsx`](apps/web/src/components/RunMetricsPage.tsx) (~1970 LOC); [`MonitorDashboard.tsx`](apps/web/src/components/MonitorDashboard.tsx) (~1902 LOC). [`MultiRunMetricsPage.tsx`](apps/web/src/components/MultiRunMetricsPage.tsx) (~429 LOC) — **delete with compare sunset**. |
| **Metrics derivation** | [`runMetricsDerive.ts`](apps/web/src/lib/runMetricsDerive.ts) (~602 LOC) — keep as the numerical core when splitting pages. |
| **Theme as implemented** | [`apps/web/src/index.css`](apps/web/src/index.css): semantic `:root` tokens (**Option G — Spire parchment**, [`ui_improvement.md`](ui_improvement.md) table + [`theme-preview.html`](apps/web/public/theme-preview.html) `.g`). `body` uses `var(--bg-canvas)` (`#16100c`); `.metrics-page-bg` = `#1f1812` → `#16100c` like `.g .swatches`. **`--chart-*`** tuned for the same palette (gold / relic violet / sage / blood). **Monitor / GameScreen** still mix many Tailwind `slate-*` / `sky-*` literals — those pockets stay cooler until migrated to tokens. |
| **Typography roles (target)** | **Sora** (`font-console`): chrome, section titles, controls. **JetBrains Mono** (`font-telemetry`): numeric HUD, timestamps, code-y readouts. Document scale in one place (e.g. `text-xs` caps strip + `tabular-nums` for KPIs) when tokens land. |
| **Metrics polling** | [`useRunMetricsData.ts`](apps/web/src/hooks/useRunMetricsData.ts): `METRICS_POLL_MS = 3000`; run list poll **8000** ms; polling skips when `document.visibilityState === "hidden"`; `fingerprintMetricsResponse` avoids React churn when the tail of `records` is unchanged. |
| **Snapshot payload (TS)** | [`DebugSnapshotPayload`](apps/web/src/types/viewModel.ts): `live_ingress`, optional `ingress_age_seconds` (server rounds to 0.1s). JSDoc on `live_ingress` references **`DASHBOARD_MAX_INGRESS_AGE_SECONDS`** — same env as [`src/ui/dashboard.py`](src/ui/dashboard.py) / [`.env.example`](.env.example) (default **90**). |
| **Game → dashboard today** | [`src/main.py`](src/main.py) sends `notify_dashboard("/update_state", {"state": state, "meta": {"state_id": state_id}})` only. When a session starts, `session.game_dir` is set under `logs/games/<basename>` but that basename is **not** on the wire — the **Live run on Metrics** section proposes adding it for Follow-live UX. |

### Design principles (short)

- **One spine:** Prefer a **default** palette + semantic tokens (`--accent-primary`, `--chart-hp`, …) before debating alternates; use the sampler to **tune**, not to postpone shipping tokens.
- **State clarity:** Never collapse **WebSocket health** and **ingress freshness** into one word on the header (see Monitor pill section).
- **Phased rewrite:** Split **data hook → chart primitives → layout** in vertical slices; avoid a single “big bang” unless resourced for it (see **Target architecture**).
- **Motion:** Keep `isAnimationActive={false}` on heavy Recharts paths (already the norm in `RunMetricsPage.tsx`); add **page-level** feedback (section stagger, KPI emphasis on run change) and honor **`prefers-reduced-motion`**.
- **Accessibility:** Tooltips alone are insufficient for WCAG intent; pair hover detail with **visible summaries**, **keyboard-focusable** controls for tabs/toggles, and chart colors that remain distinguishable **without** hue alone (thickness/pattern where feasible).

---

## Global color theme — directions (frontend redesign)

*Goal: one coherent system across Monitor, Metrics, and Map. Typography: **Sora + JetBrains Mono**. **Revision:** earlier options (amber / phosphor green / ember orange) were retired; below are **three new** directions — lunar, brass, tide pool — so you can compare fresh palettes in the sampler.*

### Option D — **“Lunar telemetry”**

**Tone:** Quiet **moonlight on ink** — sci-fi observatory, not “blue admin panel.” Primary chrome avoids warm orange and avoids CRT green.

| Role | Example | Notes |
|------|---------|--------|
| Canvas | `#0a0b10` | Blue-black ink. |
| Surface | `#12141f`, borders `#2a3148` | Cool raised panels. |
| Primary accent | `#9eb0ff` → hover `#b8c4ff` | **Rim light** — nav, live emphasis, links (periwinkle, not sky-400 clone). |
| Text | `#e4e6f0` primary, `#8b91a8` muted | |
| Success | `#7d9b8c` | Muted sage — “feed OK” without competing with rim light. |
| Danger | `#c97b84` | Dusty rose-red — HP / errors, soft not alarm red. |
| AI / traces | `#b8a9d9` | Muted **lilac** for model rail second accent. |

**Differentiation:** Reads **calm and precise**; chart lines can use a **desaturated spectrum** anchored in blue-violet + sage so metrics don’t turn rainbow.

---

### Option E — **“Brass gate”**

**Tone:** **Warm vault + metal** — stately industrial (museum plaque, ship’s bridge). Hero accent is **brass**, not orange-amber or coral.

| Role | Example | Notes |
|------|---------|--------|
| Canvas | `#100e0b` | Warm near-black. |
| Surface | `#1a1712`, borders `#4a3f2e` | Brown-bronze frame. |
| Primary accent | `#c9a43a` brass, hover `#d4b356` | CTAs, active tab, “live” emphasis. |
| Text | `#eae6dc` cream, `#9a9488` labels | |
| Success | `#6d8f7a` | Deep sage. |
| Danger | `#b85c5c` | Muted wine-red. |
| AI | `#8b7cb8` | Dusty **royal** violet — sparingly. |

**Differentiation:** **Gold-adjacent** without looking like “warning yellow”; pairs well with map room colors as **secondary** rings (keep brass for chrome only).

---

### Option F — **“Tide pool”**

**Tone:** **Deep water + sea-glass** — maritime instrument panel; fresh, not tropical neon.

| Role | Example | Notes |
|------|---------|--------|
| Canvas | `#0c1012` | Blue-green void. |
| Surface | `#141c20`, borders `#2a3d42` | Teal-slate panels. |
| Primary accent | `#5eb8a8` sea-glass | Live, links, primary actions — **mint-teal**, not emerald terminal. |
| Secondary data | `#7eb3d0` | Cool **harbor** blue for chart series / secondary emphasis. |
| Text | `#e2ecec` mist, `#7d8f94` muted | |
| Warning | `#d4a574` | Sand / rope — stale feed, not harsh amber. |
| Danger | `#d67b7b` | Soft coral-red. |

**Differentiation:** Coherent **cool ecosystem**; brass and orange from previous rounds are gone; still readable for long sessions.

---

### Semantic tokens (all options)

Define **roles** in CSS, not scattered hex:

- `--bg-canvas`, `--bg-panel`, `--border-subtle`, `--border-strong`
- `--text-primary`, `--text-muted`, `--text-label`
- `--accent-primary`, `--accent-secondary`, `--danger`, `--success`, `--warning`
- `--chart-*` + map room buckets (saturation capped)

### Recommendation (this revision)

**Practical default for the repo:** implement **semantic tokens once** in [`index.css`](apps/web/src/index.css) + chart usage, then choose **D** (calm night ops), **E** (warm industrial), or **G** (game-adjacent) as the first shipped palette. **F** fits if the team wants cool maritime without “default blue admin.” The sampler is for **side-by-side approval**, not an indefinite design phase.

| If you prioritize… | Start with |
|--------------------|------------|
| Long sessions, minimal visual noise | **D — Lunar telemetry** |
| Warm operator metal, closer to current slate/brass hints | **E — Brass gate** |
| Strong StS affinity without copying art | **G — Spire parchment** |
| Cool teal ecosystem (non-generic SaaS blue) | **F — Tide pool** |

If you want to **evoke the game itself**, read **“Slay the Spire–inspired”** below — that is separate from D/E/F (warmer, more “parchment + gold”).

---

### Slay the Spire — what theme does the game use? (lookup summary)

**Official sources:** The [Mega Crit press kit](https://www.megacrit.com/press-kits/slay-the-spire/) and [screenshot gallery](https://www.megacrit.com/press-kits/slay-the-spire/#images) show the real UI but **do not publish a color spec or hex palette**. There is no public “brand token” sheet like a corporate design system.

**What players and UI galleries consistently show** (in-game, not mods):

| Element | Visual language (qualitative) |
|--------|-------------------------------|
| **Panels / cards** | **Parchment / aged paper** — warm tan, cream, brown edges; hand-drawn **ornate borders** on cards and many overlays. |
| **Highlights** | **Gold / warm yellow** for selection, emphasis, and key UI chrome (deckbuilder “pick this” energy). |
| **Threat** | **Blood / brick red** for enemy HP, damage, danger states. |
| **Player / safety** | **Greens** for block, some buffs, “safe” feedback (context-dependent). |
| **Special / rare** | **Purple / violet** accents on relics and some special UI (not the dominant chrome color). |
| **Backgrounds** | **Dark, atmospheric** scene art behind UI — color shifts by act; UI panels stay **warm** on top. |

Third-party UI archives (e.g. [Interface In Game — Slay the Spire](https://interfaceingame.com/games/slay-the-spire/)) catalog menus, map, combat, overlays — same **parchment + gold + red threat** reading.

### Can our web app “match” that?

**Yes in spirit; not as a 1:1 copy.**

- **Feasible:** A **“Spire parchment”** dark theme: warm brown canvas, parchment-tinted panels, **gold** primary accent, **blood red** danger, muted **violet** for AI/special — dense dashboard stays readable without game textures.
- **Not feasible / not advisable:** Lifting **Mega Crit art assets**, card frames, or logo treatment without permission; pretending **hex values are “official”** — they aren’t published.
- **Already closest in this doc:** **Option E (Brass gate)** is brass-on-warm-dark; to go **full Spire**, push further toward **parchment panel beige**, slightly **redder** danger, and reserve **purple** for “relic / rare” AI emphasis (see table below).

### Option G — **“Spire parchment”** (game-inspired, web-safe)

Use as a **starting point**; tune against real screenshots side by side.

| Role | Example hex | Notes |
|------|-------------|--------|
| Canvas | `#16100c` | Deep coffee / void behind panels (like dark scene under UI). |
| Panel | `#2a2319` | Warm “paper shadow”; border `#4a3f32` ink edge. |
| Parchment highlight | `#3d3428` | Raised strip / card chrome. |
| Text | `#f0e6d8` cream, `#a69b8c` muted | |
| **Gold** (primary accent) | `#d4a84b` | Nav active, live, CTAs — **card-highlight** energy, not neon. |
| **Blood** (danger / enemy) | `#c44b4b` | HP, errors — slightly more **red** than Option E’s wine. |
| **Sage** (OK / block-adjacent) | `#6d8c72` | Success / feed OK — keeps Spire “green safety” without terminal green. |
| **Relic violet** (AI / rare) | `#8b7eae` | Second accent — AI rail, special traces. |

**Typography:** Keep **Sora + JetBrains Mono**; the **game** uses a fantasy hand-drawn titling look — you could later add a **display font** for page titles only (license permitting), but it’s optional.

### See the colors (no hex reading required)

- **Local sampler:** `http://localhost:5173/theme-preview.html` → `apps/web/public/theme-preview.html` (shows **D / E / F / G** swatches + mini mock; **G** = Spire parchment for approval).
- **Game reference (visual):** [Mega Crit — Slay the Spire press screenshots](https://www.megacrit.com/press-kits/slay-the-spire/#images); [Interface In Game — STS UI gallery](https://interfaceingame.com/games/slay-the-spire/).
- **External palette tools:** [Coolors](https://coolors.co/), [Happy Hues](https://www.happyhues.co/), [Adobe Color](https://color.adobe.com/create/color-wheel).

**Sampler:** Option **G** is included on `theme-preview.html` for side-by-side approval.

---

## Why a full logic / structure rewrite is worth it

The web app’s two heaviest screens — `MonitorDashboard.tsx` and `RunMetricsPage.tsx` — are each on the order of **~1.9k lines** in a single module. That is not just a maintenance annoyance; it **actively blocks** consistent design and reliable behavior.

### Symptoms of debt

| Area | What happens today | Why it hurts |
|------|-------------------|--------------|
| **Single-file components** | Dozens of helpers, subcomponents, and JSX branches live beside orchestration logic. | Hard to review, test, or reuse; every change risks regressions in an unrelated panel. |
| **Duplication** | Chart margins, axis styles, tooltip chrome, and patterns repeat across metrics code paths (historically also `MultiRunMetricsPage`, **being removed**). | Visual drift; fixing a tooltip or theme requires many edits. |
| **Derivation + UI coupled** | `RunMetricsPage` holds long `useMemo` chains next to hundreds of lines of Recharts JSX. | Impossible to snapshot-test charts from pure data; hard to swap chart library or layout without touching math. |
| **Tooltip / chart sprawl** | Metrics alone defines **many** near-identical tooltip wrappers (`TooltipFloorStateHp`, `TooltipStateHp`, …). | Boilerplate explosion; no shared “telemetry tooltip” primitive. |

### Target architecture (directional)

A rewrite should **separate concerns**, not just split files for cosmetics:

1. **Data layer:** `useRunMetricsModel(run)` (or similar) returns **typed view models** — series ready for charts, KPI values, parse warnings — built on existing `runMetricsDerive.ts`.
2. **Chart layer:** Small declarative **chart definitions** (data key, color token, tooltip builder) mapped to a **single** `TelemetryLineChart` / `TelemetryBarChart` wrapper so margins, grid, and animation policy live in one place.
3. **Layout layer:** Route shells (`MonitorLayout`, `MetricsLayout`) own chrome; pages compose **named regions** (e.g. `KpiStrip`, `ChartSection`, `AiRail`).
4. **Design tokens:** CSS variables for **semantic series colors** (e.g. `--chart-hp`, `--chart-gold`, `--chart-tokens-in`) instead of scattered hex literals.

This aligns the codebase with how operators actually think: **state → derived metrics → presentation**, and it makes a **visual redesign** of metrics feasible without a week-long merge conflict.

### Phased delivery (suggested)

To reduce merge risk on ~2k-line files:

1. **Phase A — No visual redesign:** Extract `useRunMetricsModel` (or rename `useRunMetricsData` + move derivations) with the same JSX; add tests against view-model outputs.
2. **Phase B — Primitives:** Introduce `TelemetryChartPanel` + one shared tooltip; migrate **one** chart family (e.g. progression) to prove the pattern, then batch the rest.
3. **Phase C — Layout:** Hero strip + tabs/accordions + performance wins (tab unmount). *(Multi-run chart sharing is **out of scope** until compare is re-spec’d.)*
4. **Phase D — Theme:** Replace Tailwind hex literals in charts with `--chart-*` tokens tied to the chosen palette (D/E/F/G).

---

## Run metrics page (`/metrics`) — design flaws

*Lens: product is an **internal telemetry console** for an AI Spire agent; audience is **you and power users** on desktop. The Monitor page already commits to an **industrial / operator** tone (Sora + JetBrains Mono, dark slate, fused readouts). Run metrics should feel like the **same product**, not a generic analytics template.*

### 1. Weak product identity (“any dashboard”)

The metrics view reads as **default Recharts + Tailwind**: slate grid, small uppercase `h2` labels, identical `ChartCard` tiles, `isAnimationActive={false}` everywhere. Functionally fine; **emotionally and mnemonically flat**. Nothing signals “Spire Agent telemetry” the way the Monitor’s deck bar and AI rail do.

**Gap vs. a deliberate aesthetic:** no unifying motif (e.g. act-boundary treatment as a **designed** system, run “tape” metaphor, or shared **chassis** around charts). The page could be from any Grafana clone.

### 2. Flat information hierarchy

Sections (**Progression**, **AI decisions**, histograms, pie, bar charts) use the **same typographic weight** and rhythm. On first open, **everything competes** — there is no clear “start here” story (e.g. run outcome + token cost + one progression sparkline vs. detail charts below).

The **Event level / Floor level** control is critical to mental model but sits in a **small resolution bar** easy to overlook relative to the KPI grid and first chart row.

### 3. Color as decoration, not semantics

Line colors vary per chart (`#f87171`, `#38bdf8`, `#c084fc`, …) without a **documented semantic map**. HP-red and gold-amber are intuitive; other hues feel **arbitrary**. Pie slices use a **rainbow** (`PIE_COLORS`) that does not encode meaning (e.g. status severity). That increases cognitive load when scanning many charts.

A stronger approach: **fixed role → token** mapping (damage / economy / deck / AI input / AI output / latency) reused across Monitor and metrics.

### 4. Visual repetition and wallpaper effect

`lg:grid-cols-2` repeats **the same card geometry** dozens of times. On a wide monitor, users see **two columns of same-height charts** scrolling forever — **no focal composition**, no “hero” summary chart, no **density toggle** (compact vs. inspector).

### 5. Motion and feedback

Charts disable animation globally. That may be intentional for performance on huge series, but the result is a **static wall**. If animation stays off, other **high-impact** feedback (section mount stagger, KPI count-up on run change, act divider emphasis) could restore a sense of **alive instrumentation** without janky Recharts redraws.

### 6. Tooltip UX debt (design + code)

Tooltips are dense and useful but **inconsistent shells** (some `font-mono`, some `max-w-sm`, duplicated `FloorLevelTooltipHeader` patterns). Many small tooltip components should be **one parameterized telemetry tooltip** with slots — better **accessibility** (contrast, focus) and **visual consistency**.

### 7. Accessibility and non-chart readers

Heavy reliance on **hover tooltips** and **line charts without textual summaries** makes quick extraction of values harder for some users. A rewrite could add **optional table export** or **summary lines** under key charts without dumbing down the default view.

### 8. Alignment with Monitor

Monitor uses **inset chassis**, **uppercase micro-labels**, and **fused controls**. Metrics uses **flat bordered cards** and a **lighter** chrome. Users switching routes feel a **context switch**; shared **layout primitives** and **tokenized chart chrome** would unify the app.

### Design directions (metrics-specific)

- **Tier content:** Top = **run headline** (class, outcome, score) + **3–4 hero KPIs** + **one** combined or summary chart; fold detailed grids behind **tabs** or **“All charts”** expansion.
- **Semantic palette:** Lock **6–8** `--chart-*` tokens; document in CSS or a tiny `chartTheme.ts`.
- **Act boundaries:** Treat act dividers as a **designed language** (not only `ReferenceLine`) — label bands, subtle background stripes, or section labels.
- **Same fonts, same density language:** Reuse Monitor’s label styles for section headers and card strips.
- **Optional motion:** Stagger section visibility on run change; keep chart animation off if needed.

---

## Run metrics — information inventory (nothing lost in a redesign)

The redesigned page should still expose **everything** the current `RunMetricsPage` does. Inventory for acceptance testing:

| Area | Content |
|------|---------|
| **Chrome** | `RunMetricsRunBar`: nav links, run `<select>`, loading state, frame count, NDJSON row count (when available), metrics error reason. |
| **Alerts** | Parse warnings banner (first N messages + overflow count). |
| **Resolution** | Toggle **Event level** vs **Floor level** (controls progression + AI chart x-axes and aggregations). |
| **KPI strip (×8)** | Character (class · ascension), non-cached input tokens, cache-read tokens, output tokens, run outcome, final score, latency mean/median (s), levels reached (act/floor). Tooltips / titles that explain token accounting must be preserved. |
| **Progression** | **Event:** combined HP & max HP, gold, floor, legal actions, enemy HP sum, hand size, deck size, relic count (line charts vs `event_index`). **Floor:** mean HP, mean max HP, mean gold, mean legal, mean enemy HP, mean hand size, min deck, min relics (vs floor + act dividers). |
| **AI decisions** | **Event:** input (k/call), output (k/call), total (k/call), latency (s/call), estimated throughput (clipped chart + tooltip explaining basis). **Floor:** per-floor input/output/total (k), cumulative total (k) area, mean latency (s/floor). Rich tooltips: `decision_id`, status, model, experiment, strategist flag, timestamps where present. |
| **Distributions** | AI status **pie**, input token **histogram**, latency **histogram** (ms). Empty states when no AI rows. |

Any redesign must keep **parity** on the above (or explicitly document removed metrics with owner approval). Optional **additions** (export CSV, copy series summary) do not replace rows in this table.

---

## Run metrics — proposed redesign (hierarchy + layout)

Goal: **same data**, **clearer story**, **same operator aesthetic** as Monitor (chassis, labels, semantic color), **less wallpaper**.

### 1. Run header band (always visible)

Single row (or two tight rows) under `RunMetricsRunBar`:

- **Left:** run name (from query), **character**, **outcome** + **score** (badges or compact type).
- **Center:** **resolution control** (Event | Floor) as a **prominent segmented control** — same visual weight as Monitor’s mode bar, not a small pill.
- **Right:** **token + latency KPIs** (3–4 numbers with labels) or a condensed duplicate of the most critical KPIs so experts don’t scroll to see cost.

Optional: **act progress** mini-indicator (e.g. highest floor reached) when space allows.

### 2. Hero “run health” strip

One **wide** chart or **small multiples** that answer: “How did this run progress?” without opening every line chart.

- **Default:** dual-axis or small-multiple **sparkline row** — e.g. HP, gold, floor index — **same x-resolution** as the current mode (event vs floor).  
- **Alternative:** single **faceted** SVG or one Recharts `ComposedChart` with normalized series (only if legends and tooltips stay clear).

This does **not** remove the detailed progression charts; it **summarizes** them for first glance.

### 3. Tabbed or accordioned detail (preserve all charts)

Use **tabs** aligned to mental model (names indicative):

| Tab | Contents |
|-----|----------|
| **Progression** | All current progression line charts (event/floor sets), same grid as today or **collapsible groups** (Economy: gold; Combat: HP, enemies, legal; Deck: hand, deck, relics). |
| **AI cost & latency** | All token/latency/TPS + floor cumulative + floor latency charts. |
| **Distributions** | Pie + both histograms. |

**Accordion** variant: same three groups, all collapsed by default except the tab/group the user last opened (persist in `sessionStorage`).

**Why tabs help design and performance:** only **one panel’s** chart tree is mounted at a time (see performance section). Users who need “everything at once” get a **“Expand all”** or **“Compact / Inspector”** density toggle that restores multi-column layout for power users.

### 4. Visual system

- **ChartCard** → **TelemetryChartPanel**: same **strip header** pattern as Monitor’s `osdPanelStrip` (label + optional Copy / “Data” popover).
- **Semantic colors** from CSS variables; **act boundaries** as background bands or labeled reference regions, not only vertical lines.
- **KPI tiles** reuse Monitor HUD label/value scale (`text-[10px]` caps + tabular nums) for cross-route consistency.

### 5. Discoverability of “hidden” detail

- **Table / export:** optional second view for a series (“View as table”) for accessibility and for copying numbers without hover.
- **Chart subtitle** line: e.g. “Event index 0–N” or “Floors with samples: …” so context is visible without tooltip.

---

## Run metrics — performance strategy

Today the page runs **many `useMemo` derivations** in one component and mounts **dozens of `ResponsiveContainer` + Recharts** instances when data exists. Polling (`METRICS_POLL_MS = 3000` in `useRunMetricsData`) can refresh records while a run is open, so the UI must stay smooth under **repeated updates**.

### Principles

1. **O(n) work off the hot path:** keep heavy aggregation in **`runMetricsDerive`** (or a dedicated `buildRunMetricsModel`) and **memoize on `records` reference + mode** (`event`/`floor`). Avoid recomputing on unrelated state (open tooltips, selected tab).
2. **Mount less SVG:** Prefer **tabs with unmounted inactive panels** so Recharts only renders **one group** of charts. That is the largest win for initial interaction and memory on long runs.
3. **Defer off-screen work:** For a single long-scroll layout (if you keep it), use **`content-visibility: auto`** on chart panels and/or **Intersection Observer** to mount a chart only when it enters the viewport (with a lightweight placeholder). Combine with a small root margin so charts pre-mount just before scroll.
4. **Stable props for memoized children:** Wrap chart panels in **`React.memo`**. Pass **primitive or stable references** (pre-built data arrays from the model hook). Avoid **inline `content={() => …}`** tooltip renderers that close over fresh closures every parent render; use a **shared tooltip** with `payload` only, or `useCallback` with stable deps.
5. **Polling discipline:** When `document.visibilityState === 'hidden'`, polling already skips in places; ensure **derivation does not run twice** on identical payloads — `fingerprintMetricsResponse` helps; the model hook should **short-circuit** if `records` fingerprint unchanged.
6. **Large series:** If `event_index` length exceeds a threshold (e.g. 8k–15k points), **downsample for display** (stride, min/max bucketing per pixel column, or LTTB) while keeping **KPIs and histograms** on full data where cheap. Document the cap in UI (“display decimated for speed”).
7. **Recharts settings:** Keep **`isAnimationActive={false}`** on heavy charts. Avoid unnecessary **`dot`** on long lines. Prefer **`connectNulls`** only where semantically needed.
8. **Optional `requestIdleCallback`:** For very large `records`, defer non-critical derivations (e.g. histogram bins) to the next idle slice so first paint shows KPIs + hero chart first.
9. **Optional Web Worker:** If profiling shows derive time > ~50–100ms on typical files, move **`deriveStateRows` / `deriveAiRows` / floor aggs** to a worker; main thread receives immutable model snapshot. Only needed if NDJSON grows large.

### Success criteria (manual + CI-friendly)

- Switching runs clears and repaints without **multi-second** main-thread freeze on representative logs (define a max record count fixture).
- With **three tabs**, inactive tabs contribute **no Recharts** instances (verify in React DevTools / component count).
- Polling updates do **not** cause full-page jank: scrolling and tab switches stay responsive.

---

# Monitor page

The sections below focus on **`MonitorDashboard`** only.

---

## Current layout (anatomy)

1. **Top header:** `SpireAgentNav`, live/offline pill, replay strip (run picker, frame controls).
2. **HUD row:** seed, class, floor, HP, gold, energy, turn, keys, deck, potions, orbs (Defect).
3. **Main grid:**
   - **Left sidebar (~9rem):** relics stack, player powers stack.
   - **Center (`main`, flex-1):**
     - **Top:** either `GameScreenPanel` (non-combat screens) or split **Enemies** (~`flex-[0.68]`) | **Hand** (~`flex-[1.32]`).
     - **Middle:** **Valid actions** strip (fixed height, `max-h-[28vh]`).
     - **Bottom band** (`~min(38vh, 30rem)`): **LLM user prompt** (grows) | **Session log** (width-capped: `min(26vw, 22rem)`, `min-w-[15rem]`, `max-w-[24rem]`).
   - **Right rail:** AI control, status, HITL, model output. Current sizing: `w-[min(32rem,40vw)]` with **`min-w-[26rem]`** so controls and output never collapse too far.

---

## Right rail width

### Problem

`min-w-[26rem]` (~416px) prioritizes the AI column over the combat tables when the window is tiled or moderately wide. Game state (hand/enemy tables) shrinks first.

### Direction

- **Keep a minimum width** so **AI control** (mode bar, retry, auto-start, approval block) and **model output** remain usable without horizontal scrolling inside the rail.
- That minimum does **not** have to stay at `26rem`; it can be **tuned** (e.g. a smaller floor that still fits the mode strip and primary buttons) once tested on target resolutions.
- **Optional enhancement:** a **user-resizable** split between center and rail (with persistence in `localStorage`) so operators can widen the rail when reading long traces without committing to a global large minimum.

---

## Session log — why it often feels unhelpful

The log is **browser-only** (`useControlPlane`), not a full game/mod trace.

### What gets logged

| Kind     | Typical content | Utility |
|----------|-----------------|--------|
| `STATE`  | `state_id …` on every snapshot | **High noise** during live WS updates; game state is already visible; state mismatch is also surfaced in the AI status card when relevant. |
| `SYSTEM` | WebSocket connect/disconnect, mode changes, copy confirmations, retry text, replay warnings, **raw JSON** on agent resume | Mixed: some lines are useful, **JSON blobs are unreadable** in a narrow column. |
| `ERROR`  | Failed API responses (often JSON) | Often **duplicates** errors already shown in the AI rail. |
| `REPLAY` | Run / file / frame index | **Useful** for replay workflow. |
| `ACTION` | Queued manual commands | **Useful** for operator actions. |

### Layout problem

The session log sits in the **bottom band beside the LLM user prompt**—premium horizontal space. It behaves like a **narrow sliver**: three columns per row (time | kind | message), competing with the prompt operators actually read end-to-end.

### Possible directions

1. **Full width to prompt:** Remove the log column; surface only high-signal events (disconnect, replay load, queued command) as **toasts** or a **one-line status** near replay/header.
2. **Filtered “operator log”:** Default to `ACTION` + `REPLAY` + critical `SYSTEM`/`ERROR`; hide or toggle **`STATE`** and verbose JSON.
3. **Off the golden path:** Collapsible footer, drawer, or modal (“Session / debug log”) so default view is combat + prompt + AI rail.
4. **Keep log but widen:** If retained inline, give it a **larger share** or **stack below** the prompt on wide screens so it is readable when needed.

Implementation choices should be driven by whether the primary use is **day-to-day play** (minimize noise) or **debugging** (keep raw stream, but not in the prompt’s lane).

---

## Center column — unused space

### Observation

The center often shows **empty horizontal or vertical space** even though the overall UI is dense. Common causes in the current structure:

1. **Flex ratios vs. content:** Enemies and hand use fixed flex weights (`0.68` / `1.32`). When enemy count is low, the **Enemies** column still reserves a fraction of width; the hand table may not expand to use perceived “slack” in a visually balanced way.
2. **Tables don’t stretch:** `CardTable` and enemy cards are **content-width biased** inside scroll regions; large viewports can leave **gutter** beside the table instead of wider columns (e.g. **Text** for card rules).
3. **Bottom band:** The prompt uses `flex-1`, but the session log’s **`max-w-[24rem]`** caps the right part of the band; depending on viewport, the prompt may stop growing while a **visual gap** remains—or the log feels disproportionately small relative to the band height.
4. **Valid actions:** A **short** action list in a tall strip leaves **vertical** dead zone within that strip (by design there is `max-h-[28vh]`).

### Improvement ideas (center-focused)

- **Hand table:** Allow **Name / Text** columns to use remaining width (`min-width: 0`, `width: 100%` on text column, optional **max width none** on description) so long card text uses horizontal space instead of only vertical scroll.
- **Enemies column:** When `monsters.length === 0`, consider **collapsing** or **narrowing** the enemies pane and giving more width to hand (or to a single “non-combat” message) so space isn’t reserved for an empty panel.
- **Dynamic split:** Replace fixed `0.68` / `1.32` with a **resizable split** between enemies and hand, or compute ratio from **presence of enemies** (e.g. more width to hand on map/event screens if enemies panel is empty).
- **Game screen (`GameScreenPanel`):** For MAP / reward layouts, ensure **max-width** constraints don’t leave a dead column; center content or let map **scale** to available width (within readability limits).
- **Valid actions:** If vertical slack is distracting, reduce strip **max-height** when action count is low, or use a **dense grid** that grows only as needed (still cap for huge action lists).

These changes respect **desktop + density** while making **pixels work** for readable card text and combat context.

---

## Monitor top bar — “Live / Offline” pill: code verification

### Claim (accurate)

Operator clarity requires **two independent channels**, but the UI **collapses** them into one word on the pill.

| Channel | Meaning | Source in code |
|--------|---------|----------------|
| **1. Dashboard link** | Browser tab has an open **WebSocket** to the dashboard server (snapshots can arrive). | `useControlPlane` → `connected` (`ws.onopen` / `onclose`). |
| **2. Game ingress** | The **game / CommunicationMod / debug paste** has touched dashboard ingress **recently** (within `DASHBOARD_MAX_INGRESS_AGE_SECONDS`, default 90s). | Snapshot `live_ingress` from `_build_react_snapshot_payload()` → `_ingress_is_live()` in `src/ui/dashboard.py` (compares monotonic clock to last ingress). |

**What the pill actually shows:** only channel **2**. In `MonitorDashboard.tsx`, `gameFeedLive = snapshot?.live_ingress === true` drives the **green “Live”** vs **red “Offline”** label and ping animation. Channel **1** is **not** shown on the pill.

**What the tooltip does when the pill is “Offline”:** it branches on `connected` — if WebSocket is down → *“Dashboard WebSocket disconnected.”*; else → *“No fresh game state (game stopped or stale).”* So the **truth is available on hover**, but the **visible word “Offline”** is the same for “dashboard unreachable” and “dashboard fine, game quiet” — that is **misleading** without reading the tooltip.

**Server-side note:** `_ingress_is_live()` returns **false** if `_last_ingress_body is None` — there is no “live with no body.” The odd case is the reverse: **body present** but `_last_ingress_monotonic is None` (should be rare) → the function returns **true** without an age comparison. Normal path: both set, freshness checked against `DASHBOARD_MAX_INGRESS_AGE_SECONDS` (min clamp10s in code).

### Plan: show the two channels differently (no implementation in this doc)

Prefer **never** using one word for both failures. Options (pick one in implementation):

1. **Two compact pills:** e.g. **Dash** (WS) · **Feed** (ingress) with separate colors; tooltips spell out each.  
2. **Single composite label:** e.g. `Dash OK · Feed stale` / `Dash down` / `Dash OK · Feed live` — still dense for the header.  
3. **Icon + text:** socket glyph vs antenna glyph; aria-label includes both sentences.

**Replay:** when a replay run is loaded, the pill semantics should either **ignore** ingress for “game feed” or show a third state **Replay** so users don’t think the red Offline pill means the WebSocket is dead.

After this change, the amber **“No live game feed”** banner (`live_ingress === false`) remains the right place for **stale-feed narrative**; it should align wording with the new **Feed** indicator, not duplicate a conflicting “Offline” story.

---

## Live run on Metrics, LIVE vs archive, and syncing with Monitor

### How it works today (gap)

| Surface | What the UI implies | Run identity |
|--------|---------------------|--------------|
| **Monitor** (`/`) | **Pill:** “Live” = ingress fresh only (`live_ingress`). **Tooltip** when not live distinguishes WS vs stale feed. WS health is **not** on the pill. Optional **`ingress_age_seconds`** on the payload can back “stale” copy without extra round-trips. | **Not exposed** in `DebugSnapshotPayload` — no `logs/games/<run>` basename on the wire. |
| **Run metrics** (`/metrics`) | No feed/WS indicators today; polling log files only. | **Explicit** `?run=`; unrelated to active writing session unless user guesses. |

So metrics is always **“a log-backed view of a directory”**, not **“the run the game is writing right now”**, unless the user guesses the correct folder name. There is **no** automatic coupling to the monitor’s live session.

### Backend prerequisite (required for real “follow live”)

The game process already creates `session.game_dir` under `logs/games/<basename>` when logging starts (`src/main.py`). That basename is **not** included in `POST /update_state` today (only `state_id` in `meta`).

**Proposal:** whenever a session has a resolved log directory, include in dashboard state (and in `_build_react_snapshot_payload()`):

- `active_log_run: string | null` — **directory basename only** (same string used by `/api/runs/{run_name}/metrics`), validated safe.
- Optionally `logging_enabled: boolean` if useful for empty states.

The dashboard can update `active_log_run` whenever it processes `update_state` (game process must pass basename in `meta`, or the dashboard reads it from a small side channel — **simplest is adding `meta.log_run` or `meta.active_log_run`** from `main.py` alongside `state_id`).

Without this field, the frontend **cannot** truthfully label “this is the live run” or auto-select metrics.

### Recommended UX model: two explicit modes + situation matrix

**Modes**

1. **Follow live** (toggle or default-on for power users)  
   - Metrics needs the **same snapshot fields as Monitor** for `active_log_run`, `live_ingress`, and (once added) does **not** conflate them with the metrics file poll.  
   - When `follow=1` and `active_log_run` is non-null, keep `?run=` aligned with that basename (replace state, shareable URL).  
   - **Metrics poll** of `/api/runs/.../metrics` remains the **NDJSON tail** — orthogonal to “Feed live” on the monitor (file may lag ingress by a tick).  
   - Edge: **between runs** (`active_log_run` null, or new game not started): show **empty / “No active log run”** in Follow mode instead of a stale previous `?run=`.

2. **Pinned run**  
   - User selects a run from the dropdown → set `follow=0` (or omit). Never auto-change `?run=` until user re-enables Follow.  
   - If **Feed** is live and pinned run ≠ `active_log_run`, show an explicit **“Viewing a different run than the live session”** banner (not just a subtle badge).

**Situation matrix (planning — drives copy and banner priority)**

| Dash (WS) | Feed (`live_ingress`) | Metrics mode | Pinned `?run=` vs `active_log_run` | Plan: primary message |
|-----------|------------------------|--------------|-------------------------------------|------------------------|
| Down | *any* | *any* | *any* | **Dashboard disconnected** — snapshots/metrics context may be stale; do not imply game state. |
| Up | Live | Follow | match | **Live session · metrics tailing this run** — ideal. |
| Up | Live | Follow | no `active_log_run` yet | **Live feed · no log folder yet** (title / main menu). |
| Up | Live | Pinned | mismatch | **Live feed · pinned historical run** — warn; offer “Jump to live run”. |
| Up | Stale | Follow | match | **Feed stale** (game paused or threshold) — metrics may still reflect last written lines; align with dual-channel Feed pill. |
| Up | Stale | Pinned | *any* | **Offline feed · archive** — normal for post-mortem; no alarm if intentional. |

**Replay (Monitor):** When replay controls a frame, **Feed** indicator should reflect **replay vs live ingress** (plan: third state or subtitle) so “Offline” is not read as “WS broken.”

This avoids **silent surprises** and aligns Metrics **modes** with the same **two-channel** vocabulary as the Monitor header.

### Clear LIVE vs cached / historical (UI)

Use **orthogonal** signals (do not fold into one “Live” word):

| Signal | Source | Use |
|--------|--------|-----|
| **Dashboard link** | WebSocket `connected` | Tab can receive pushes; distinct from game sending data. |
| **Feed / ingress** | `live_ingress` | Game (or debug paste) recently updated ingress — **this is what today’s green pill encodes alone**. |
| **Run is the active log target** | `selectedRun === active_log_run` (non-empty) | Metrics charts match the directory the process **writes** (once `active_log_run` exists). |
| **Metrics file tail** | Metrics API / row count / optional `last_modified` | NDJSON growing vs stuck; independent of a single ingress tick. |

**Badge suggestions (example copy):**

- **Live run · updating** — `live_ingress` && follow (or match active) && `selectedRun === active_log_run`.  
- **Live feed · viewing other run** — `live_ingress` but user **pinned** a different `?run=` (warn: not the active session).  
- **Offline / archive** — `!live_ingress`: clarify “Log archive — no live game feed” even if charts have data.  
- **Stale feed** — reuse Monitor’s amber banner pattern when `live_ingress === false` and link to metrics with caveat.

Honest labeling matters because “live metrics” is still **file polling**; sub-second lag and OS buffer flush can occur — optional **“Last metrics fetch: … · rows: N”** in the run bar reduces confusion.

### Keeping Monitor and Metrics “in sync”

**Canonical state:** `?run=` + `follow=` query params are enough for **bookmarking and share**.

**Cross-page navigation:**

- Add **“Metrics (this run)”** on Monitor when `active_log_run` is known: `Link` to `/metrics?run=…&follow=1`.  
- On Metrics, **“Open monitor”** already exists via nav; when following live, no extra param needed on `/`.

**Shared client state (optional):** a thin `OperatorSessionProvider` that holds `active_log_run`, `live_ingress`, and `followRun` reduces duplicate snapshot polling if both routes mount; otherwise Metrics can **poll snapshot every N seconds** (larger N than metrics file poll if needed) **only while the tab is visible** — tune to avoid triple polling (runs list + metrics + snapshot).

**Replay mode on Monitor:** when replay is active, `active_log_run` for “live” should either **exclude** replay or metrics should show **“Replay — metrics for loaded run if you select it”** so mental model stays clean.

### Is this a good design choice?

**Yes, with boundaries.**

- **Pros:** One mental model — “the run directory the game is writing” is the default metrics target; operators stop hunting dropdowns; LIVE vs archive becomes **legible**; URL stays shareable.  
- **Cons / mitigations:**  
  - **Must not** overwrite a deliberate historical selection without an obvious **Pinned** state.  
  - **Requires backend** exposure of `active_log_run`; without it, only UX polish (badges guessing from heuristics) is possible.  
  - Metrics remain **NDJSON-backed**; label as **live tail**, not pixel-synced to Monitor frames.

**Avoid:** auto-switching metrics to a **new** run when a new game starts **without** a visible toast and without resetting chart axis context — users may think charts corrupted; a one-line **“New run: &lt;basename&gt; — charts reset”** (when follow is on) is enough.

### Implementation checklist (engineering)

- [ ] **Monitor header:** replace single **Live/Offline** pill with **two-channel** (or composite) indicator per plan above; **replay** state must not imply WS failure.  
- [ ] `main.py`: add basename to `notify_dashboard` `meta` when `session.game_dir` is set (or equivalent).  
- [ ] `dashboard.py`: persist `active_log_run` on ingress; include in `_build_react_snapshot_payload()`.  
- [ ] `viewModel.ts`: extend `DebugSnapshotPayload`.  
- [ ] `useRunMetricsData` (or successor): `follow` param + snapshot subscription; derive `run` when follow on; disable follow on manual select; implement **situation matrix** banners.  
- [ ] `RunMetricsRunBar` / layout: **Follow live** toggle, **pinned vs live run** warning, optional link **Jump to live run**; align wording with Monitor feed/dash indicators.  
- [ ] Tests: snapshot shape + metrics URL behavior + indicator combinations (WS up/down × ingress live/stale).

---

## Run map page (`/metrics/map`) — verified behavior & planned visuals

*No implementation in this doc — design verification and alignment with product owner choices.*

### How map data is produced (logs → API → UI)

1. **`GET /api/runs/{run}/map_history`** (`src/ui/dashboard.py` → `_build_map_history_for_run_dir`) scans frame `*.json` in the run directory.
2. For each frame, it reads `game_state.map` (list of nodes) and, on **MAP** screens, appends **`current_node`** positions to **`visited_path`** (with `symbol` only if `current_node.symbol` is a **string** — otherwise the path point has coordinates but no symbol key).
3. **`boss_name`** comes from `game_state.act_boss` when present.
4. **`MapView`** (`apps/web/src/components/gameScreen/MapView.tsx`) renders nodes from that graph; **`RunMapPage`** passes **`readOnly`**, **`boss_available: false`**, and builds **`mapViz.current_node`** as the **last** visited path point for highlighting.

### Claim: “`?` on nodes is expected” — **verified, with nuance**

| Source | Behavior |
|--------|----------|
| **UI** | `MapView` displays `{n.symbol ?? "?"}`. Any node **without** a `symbol` field shows **`?`**. |
| **Agent / analysis** | `src/agent/map_analysis.py` documents CommunicationMod **`game["map"]`** nodes with `symbol`. **`_sym_char`** uses `node.get("symbol", "?")` and normalizes empty/missing to **`?`**. |
| **Symbol vocabulary** | `_SYMBOL_TO_BUCKET` maps **`?` → `"event"`**. So **`?` is not only a fallback**: in this codebase it is the **canonical single-character label for event rooms**, same as **M/E/R/$/T** for other types. |
| **Visited path** | Path points may omit `symbol` when the mod did not supply a string on that frame; the **node** at that coordinate might still have a symbol on the graph. |

**Conclusion:** Seeing **`?`** is **expected** for (a) **event** rooms per mod convention, and (b) **missing/empty** symbol data on a **node**. The UI cannot distinguish “real event” vs “data hole” without inspecting raw frames or showing coordinates in a tooltip. Documenting that in UI copy or devtools is optional.

### Claim: color by room type — **aligned with existing semantics**

`map_analysis.py` already classifies CommunicationMod symbols into buckets: **monster (M), elite (E), rest (R), shop ($), event (?), treasure (T)**. A **muted, semantic palette** (one hue family per bucket, restrained saturation) would match backend/agent language and stay readable on the dark operator theme — **good design direction**; avoid neon rainbow.

### Claim: boss should not be a node — **reasonable; verify Monitor interaction**

**Current implementation:** `MapView` draws a **synthetic boss control** at grid position **`(3, maxY+1)`** (skull glyph), separate from the `nodes` list. **`RunMapPage`** disables boss interaction (`boss_available: false`, `readOnly`), but the **orb can still appear** as visual noise.

**Data:** Each act already exposes **`boss_name`** from logs; act tabs on `RunMapPage` can show **`(boss_name)`** next to the act label.

**Product direction (accepted in plan):** Treat the act boss as **context**, not a graph vertex: e.g. a **top bar** (or panel strip) **“Boss: &lt;name&gt;”** instead of rendering the skull node on the **map analytics** page. That matches the idea that routes **converge toward** the boss layer without needing a fake coordinate.

**Caveat — Monitor (`/`) live MAP:** When the player can **Challenge Boss**, the product still needs an **affordance** (`choose boss`). That can be a **bar button** (“Challenge boss”) rather than the floating orb — same design language as the map page; document when implementing so HITL is not lost.

### File references (map)

- Map graph + visited path from logs: `src/ui/dashboard.py` (`_build_map_history_for_run_dir`, `get_run_map_history`)
- Symbol buckets / CommunicationMod contract: `src/agent/map_analysis.py` (`_SYMBOL_TO_BUCKET`, `_sym_char`)
- Map UI: `apps/web/src/components/gameScreen/MapView.tsx`, `apps/web/src/components/RunMapPage.tsx`

### Checklist (map visuals — future implementation)

- [ ] **Node colors** by symbol bucket; keep palette restrained; legend for M/E/R/$/?/T (+ unknown).  
- [ ] **Boss:** strip or bar with **`boss_name`** on run map page; remove or replace synthetic skull **node** on read-only view; reconcile **Monitor** boss action (bar vs orb).  
- [ ] Optional: tooltip clarifies **`?`** = event *or* missing symbol (coordinates from data).

---

## Summary checklist

**Monitor**

- [ ] **Top bar:** split **dashboard link** vs **game ingress** (stop using one “Offline” for both); handle **replay** as its own state.  
- [ ] Tune **right rail** minimum width (keep controls visible; consider < `26rem` or resizable split).
- [ ] Rework **session log**: relocate, filter, or collapse; reduce `STATE` noise and JSON-in-log.
- [ ] Improve **center** use of space: hand/enemy split, table column growth, empty-state column width.
- [ ] Optional: **persisted** layout (rail width, splitters) for operator workflows.

**Compare runs — remove**

- [ ] Drop **`/metrics/compare`** route from `App.tsx` and **delete** [`MultiRunMetricsPage.tsx`](apps/web/src/components/MultiRunMetricsPage.tsx) (no orphaned imports).
- [ ] Remove **Compare runs** from [`SpireAgentNav`](apps/web/src/components/SpireAgentNav.tsx) (`SpireNavPage` type, labels, `Link`).
- [ ] Grep the web app for `compare` / `/metrics/compare` and clean **docs or README** links if any.

**Metrics & codebase**

- [ ] **Split** `RunMetricsPage` into hooks + chart registry + layout sections; align with `runMetricsDerive.ts`.
- [ ] Introduce **shared chart / tooltip primitives** inside the **single-run** metrics stack (no compare page to share with yet).
- [ ] **Tier** metrics UI (hero vs. detail); **tabs or accordions** for chart families; verify against **information inventory** (parity checklist).
- [ ] **Semantic chart colors** (CSS variables) shared with Monitor where it makes sense.
- [ ] **Performance:** tab-unmounting (or lazy-mount), stable memoized chart props, polling + derive short-circuit, optional display downsampling for huge `event_index` series; measure against success criteria in doc.
- [ ] **Live / sync:** expose `active_log_run` in snapshot; metrics **Follow live** vs **Pinned run**; LIVE / archive badges; Monitor link to `/metrics?run=…&follow=1` (see dedicated section above).

**Run map (`/metrics/map`)**

- [ ] Semantic **node colors** + legend; **boss** as header/strip (not synthetic node); **Monitor** boss affordance without relying on skull orb (see Run map section above).

**Global theme**

- [ ] Choose **D / E / F** or **G (Spire parchment)** — see “Slay the Spire–inspired” in this doc; implement **`@theme` / CSS variables** in `index.css` + replace scattered Tailwind hex in charts/map; document semantic token list.

---

## File references

- Routes: `apps/web/src/App.tsx`
- Vite proxy + dev port: `apps/web/vite.config.ts`
- Global fonts + base theme: `apps/web/src/index.css`
- Monitor layout (pill: `gameFeedLive`, `title` tooltip vs `connected`): `apps/web/src/components/MonitorDashboard.tsx`
- Session log + WebSocket `connected`: `apps/web/src/hooks/useControlPlane.ts`
- Run metrics (monolith today): `apps/web/src/components/RunMetricsPage.tsx`
- Metrics fetch + polling: `apps/web/src/hooks/useRunMetricsData.ts`
- Metrics derivation (keep / extend): `apps/web/src/lib/runMetricsDerive.ts`
- Compare runs (**remove**): `apps/web/src/components/MultiRunMetricsPage.tsx`, nav in `apps/web/src/components/SpireAgentNav.tsx`, route in `apps/web/src/App.tsx`
- TS snapshot types: `apps/web/src/types/viewModel.ts` (`DebugSnapshotPayload`)
- Theme sampler (static): `apps/web/public/theme-preview.html`
- Snapshot payload builder (extend for `active_log_run`): `src/ui/dashboard.py` (`_build_react_snapshot_payload`, `_ingress_is_live`)
- Game session / log dir basename: `src/main.py` (`session.game_dir`, `build_game_dir_name`, `notify_dashboard` `/update_state` meta)
