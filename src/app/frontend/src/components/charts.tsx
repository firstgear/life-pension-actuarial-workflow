/** Lightweight inline-SVG charts (no chart library). */
import type { ReactNode } from 'react';

export const PALETTE = ['#1B3139', '#FF3621', '#2E86AB', '#00A972', '#F2A900', '#8E44AD', '#7F8C8D', '#C0392B'];

const niceMax = (v: number) => {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  return Math.ceil(v / p) * p;
};

/** Horizontal bars, optional CI whiskers and a reference line (e.g. relativity = 1). */
export function HBar({ data, fmt = (v: number) => v.toFixed(2), refLine, height, color = PALETTE[0], labelWidth = 170 }: {
  data: { label: string; value: number; lo?: number; hi?: number; tone?: string; title?: string }[];
  fmt?: (v: number) => string; refLine?: number; height?: number; color?: string; labelWidth?: number;
}) {
  if (!data.length) return null;
  const W = 640, row = 24, H = height ?? data.length * row + 24, x0 = labelWidth, x1 = W - 60;
  const vmax = niceMax(Math.max(...data.map(d => Math.max(d.hi ?? d.value, d.value)), refLine ?? 0));
  const vmin = Math.min(0, ...data.map(d => d.lo ?? d.value));
  const sx = (v: number) => x0 + ((v - vmin) / (vmax - vmin)) * (x1 - x0);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img">
      {data.map((d, i) => {
        const y = 8 + i * row;
        return (
          <g key={i}>
            {d.title && <title>{d.title}</title>}
            <text x={x0 - 8} y={y + 12} textAnchor="end" className="fill-slate-600" fontSize="11">{d.label}</text>
            <rect x={sx(Math.min(0, d.value))} y={y + 3} width={Math.abs(sx(d.value) - sx(0))} height={row - 9} rx="2" fill={d.tone ?? color} opacity="0.85" />
            {d.lo !== undefined && d.hi !== undefined && (
              <g stroke="#0f172a" strokeWidth="1.2">
                <line x1={sx(d.lo)} x2={sx(d.hi)} y1={y + row / 2 - 1} y2={y + row / 2 - 1} />
                <line x1={sx(d.lo)} x2={sx(d.lo)} y1={y + 6} y2={y + row - 8} />
                <line x1={sx(d.hi)} x2={sx(d.hi)} y1={y + 6} y2={y + row - 8} />
              </g>
            )}
            <text x={Math.max(sx(d.value), sx(d.hi ?? d.value)) + 6} y={y + 12} fontSize="11" className="fill-slate-800 tabular">{fmt(d.value)}</text>
          </g>
        );
      })}
      {refLine !== undefined && <line x1={sx(refLine)} x2={sx(refLine)} y1={2} y2={H - 14} stroke="#FF3621" strokeDasharray="4 3" />}
    </svg>
  );
}

type Series = { name: string; points: [number, number][]; color?: string; dashed?: boolean };

/** Multi-series line chart over a numeric x axis. */
export function Lines({ series, xLabel, yFmt = (v: number) => v.toFixed(2), height = 260, yMin, step }: {
  series: Series[]; xLabel?: string; yFmt?: (v: number) => string; height?: number; yMin?: number; step?: boolean;
}) {
  const pts = series.flatMap(s => s.points);
  if (!pts.length) return null;
  const W = 680, H = height, L = 64, R = 16, T = 12, B = 34;
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const xmin = Math.min(...xs), xmax = Math.max(...xs);
  const ylo = yMin ?? Math.min(0, ...ys), yhi = Math.max(...ys) * 1.05 || 1;
  const sx = (x: number) => L + ((x - xmin) / (xmax - xmin || 1)) * (W - L - R);
  const sy = (y: number) => T + (1 - (y - ylo) / (yhi - ylo || 1)) * (H - T - B);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map(f => ylo + f * (yhi - ylo));
  const path = (p: [number, number][]) => p.map((q, i) => {
    if (!step || i === 0) return `${i ? 'L' : 'M'}${sx(q[0])},${sy(q[1])}`;
    return `H${sx(q[0])}V${sy(q[1])}`;
  }).join('');
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        {ticks.map((t, i) => (
          <g key={i}><line x1={L} x2={W - R} y1={sy(t)} y2={sy(t)} stroke="#e2e8f0" />
            <text x={L - 6} y={sy(t) + 4} textAnchor="end" fontSize="10" className="fill-slate-500">{yFmt(t)}</text></g>
        ))}
        {[xmin, (xmin + xmax) / 2, xmax].map((x, i) => (
          <text key={i} x={sx(x)} y={H - 16} textAnchor="middle" fontSize="10" className="fill-slate-500">{Math.round(x)}</text>
        ))}
        {xLabel && <text x={(L + W - R) / 2} y={H - 2} textAnchor="middle" fontSize="10" className="fill-slate-500">{xLabel}</text>}
        {series.map((s, i) => (
          <path key={s.name} d={path([...s.points].sort((a, b) => a[0] - b[0]))} fill="none" stroke={s.color ?? PALETTE[i % PALETTE.length]}
            strokeWidth="2" strokeDasharray={s.dashed ? '5 4' : undefined} />
        ))}
      </svg>
      <Legend items={series.map((s, i) => ({ name: s.name, color: s.color ?? PALETTE[i % PALETTE.length] }))} />
    </div>
  );
}

export function Legend({ items }: { items: { name: string; color: string }[] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1 text-xs text-slate-600">
      {items.map(it => <span key={it.name} className="inline-flex items-center gap-1.5"><span className="w-3 h-1.5 rounded" style={{ background: it.color }} />{it.name}</span>)}
    </div>
  );
}

/** Percentile fan chart (p05-p95 and p25-p75 bands + median). */
export function Fan({ rows, yFmt = (v: number) => `${(v * 100).toFixed(1)}%`, xLabel }: {
  rows: { x: number; p05: number; p25: number; p50: number; p75: number; p95: number }[]; yFmt?: (v: number) => string; xLabel?: string;
}) {
  if (!rows.length) return null;
  const W = 680, H = 240, L = 56, R = 12, T = 10, B = 30;
  const xmin = rows[0].x, xmax = rows[rows.length - 1].x;
  const ylo = Math.min(...rows.map(r => r.p05)), yhi = Math.max(...rows.map(r => r.p95));
  const sx = (x: number) => L + ((x - xmin) / (xmax - xmin || 1)) * (W - L - R);
  const sy = (y: number) => T + (1 - (y - ylo) / (yhi - ylo || 1)) * (H - T - B);
  const band = (a: keyof typeof rows[0], b: keyof typeof rows[0]) =>
    rows.map((r, i) => `${i ? 'L' : 'M'}${sx(r.x)},${sy(r[a] as number)}`).join('') +
    [...rows].reverse().map(r => `L${sx(r.x)},${sy(r[b] as number)}`).join('') + 'Z';
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      {[ylo, (ylo + yhi) / 2, yhi].map((t, i) => (
        <g key={i}><line x1={L} x2={W - R} y1={sy(t)} y2={sy(t)} stroke="#e2e8f0" />
          <text x={L - 6} y={sy(t) + 4} textAnchor="end" fontSize="10" className="fill-slate-500">{yFmt(t)}</text></g>
      ))}
      <path d={band('p05', 'p95')} fill="#2E86AB" opacity="0.15" />
      <path d={band('p25', 'p75')} fill="#2E86AB" opacity="0.3" />
      <path d={rows.map((r, i) => `${i ? 'L' : 'M'}${sx(r.x)},${sy(r.p50)}`).join('')} fill="none" stroke="#1B3139" strokeWidth="2" />
      {[xmin, xmax].map((x, i) => <text key={i} x={sx(x)} y={H - 12} textAnchor="middle" fontSize="10" className="fill-slate-500">{x}</text>)}
      {xLabel && <text x={(L + W) / 2} y={H - 2} textAnchor="middle" fontSize="10" className="fill-slate-500">{xLabel}</text>}
    </svg>
  );
}

/** Vertical histogram with optional marker lines (e.g. mean, 99.5%). */
export function Histogram({ bins, markers = [], xFmt = (v: number) => v.toFixed(0) }: {
  bins: { mid: number; n: number }[]; markers?: { x: number; label: string; color?: string }[]; xFmt?: (v: number) => string;
}) {
  if (!bins.length) return null;
  const W = 680, H = 220, L = 30, R = 10, T = 18, B = 28;
  const xmin = Math.min(...bins.map(b => b.mid)), xmax = Math.max(...bins.map(b => b.mid));
  const span = xmax - xmin || 1, bw = (W - L - R) / bins.length;
  const nmax = Math.max(...bins.map(b => b.n));
  const sx = (x: number) => L + ((x - xmin) / span) * (W - L - R - bw) + bw / 2;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      {bins.map((b, i) => {
        const h = (b.n / nmax) * (H - T - B);
        return <rect key={i} x={sx(b.mid) - bw / 2 + 1} y={H - B - h} width={bw - 2} height={h} fill="#1B3139" opacity="0.75" />;
      })}
      {markers.map(m => (
        <g key={m.label}>
          <line x1={sx(m.x)} x2={sx(m.x)} y1={T - 6} y2={H - B} stroke={m.color ?? '#FF3621'} strokeDasharray="4 3" strokeWidth="1.5" />
          <text x={sx(m.x) + 4} y={T} fontSize="10" fill={m.color ?? '#FF3621'}>{m.label}</text>
        </g>
      ))}
      {[xmin, (xmin + xmax) / 2, xmax].map((x, i) => <text key={i} x={sx(x)} y={H - 10} textAnchor="middle" fontSize="10" className="fill-slate-500">{xFmt(x)}</text>)}
    </svg>
  );
}

/** Vertical grouped bars for a few categories. */
export function VBars({ cats, series, yFmt = (v: number) => v.toFixed(0), height = 220 }: {
  cats: string[]; series: { name: string; values: number[]; color?: string }[]; yFmt?: (v: number) => string; height?: number;
}) {
  if (!cats.length) return null;
  const W = 680, H = height, L = 56, R = 10, T = 10, B = 40;
  const all = series.flatMap(s => s.values);
  const ymax = niceMax(Math.max(...all, 0)), ymin = Math.min(0, ...all);
  const sy = (y: number) => T + (1 - (y - ymin) / (ymax - ymin || 1)) * (H - T - B);
  const gw = (W - L - R) / cats.length, bw = (gw * 0.75) / series.length;
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        {[ymin, (ymin + ymax) / 2, ymax].map((t, i) => (
          <g key={i}><line x1={L} x2={W - R} y1={sy(t)} y2={sy(t)} stroke="#e2e8f0" />
            <text x={L - 6} y={sy(t) + 4} textAnchor="end" fontSize="10" className="fill-slate-500">{yFmt(t)}</text></g>
        ))}
        {cats.map((c, ci) => (
          <g key={c}>
            {series.map((s, si) => {
              const v = s.values[ci] ?? 0, x = L + ci * gw + gw * 0.125 + si * bw;
              return <rect key={s.name} x={x} y={Math.min(sy(v), sy(0))} width={bw - 2} height={Math.abs(sy(v) - sy(0))}
                fill={s.color ?? PALETTE[si % PALETTE.length]} opacity="0.85" />;
            })}
            <text x={L + ci * gw + gw / 2} y={H - 24} textAnchor="middle" fontSize="10" className="fill-slate-600">{c}</text>
          </g>
        ))}
      </svg>
      {series.length > 1 && <Legend items={series.map((s, i) => ({ name: s.name, color: s.color ?? PALETTE[i % PALETTE.length] }))} />}
    </div>
  );
}

export function Stat({ k, v }: { k: string; v: ReactNode }) {
  return <div className="flex justify-between gap-4 py-1 text-sm border-b border-slate-100 last:border-0"><span className="text-slate-500">{k}</span><span className="font-medium tabular">{v}</span></div>;
}
