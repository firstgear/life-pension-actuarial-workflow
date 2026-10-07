export const n = (v: any, d = 0) =>
  v === null || v === undefined || v === '' || Number.isNaN(Number(v)) ? '—'
    : Number(v).toLocaleString('en-GB', { minimumFractionDigits: d, maximumFractionDigits: d });

export const eur = (v: any) => {
  if (v === null || v === undefined) return '—';
  const x = Number(v), a = Math.abs(x);
  if (a >= 1e9) return `${(x / 1e9).toFixed(2)} bn EUR`;
  if (a >= 1e6) return `${(x / 1e6).toFixed(1)} m EUR`;
  if (a >= 1e3) return `${(x / 1e3).toFixed(0)} k EUR`;
  return `${x.toFixed(0)} EUR`;
};

export const pct = (v: any, d = 1) => (v === null || v === undefined ? '—' : `${(Number(v) * 100).toFixed(d)}%`);

export const ts = (v: any) => {
  if (!v) return '—';
  const d = typeof v === 'number' ? new Date(v) : new Date(String(v).replace(' ', 'T'));
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' });
};

export const secs = (v: any) => {
  if (v === null || v === undefined) return '—';
  const s = Number(v);
  if (s < 60) return `${s.toFixed(1)} s`;
  if (s < 3600) return `${(s / 60).toFixed(1)} min`;
  return `${(s / 3600).toFixed(1)} h`;
};
