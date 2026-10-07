import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { CheckCircle2, ExternalLink, Loader2, XCircle, Cpu, Info } from 'lucide-react';
import { get } from '../lib/api';
import { secs } from '../lib/format';

export function useApi<T = any>(path: string | null, refreshMs = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    if (!path) return;
    try { setData(await get<T>(path)); setError(null); } catch (e: any) { setError(e.message); } finally { setLoading(false); }
  }, [path]);
  useEffect(() => {
    load();
    if (refreshMs > 0) { const t = setInterval(load, refreshMs); return () => clearInterval(t); }
  }, [load, refreshMs]);
  return { data, error, loading, reload: load };
}

export function Page({ title, section, subtitle, capability, children, actions }: {
  title: string; section?: string; subtitle?: string; capability?: string; children: ReactNode; actions?: ReactNode;
}) {
  return (
    <div className="p-8 max-w-[1400px] mx-auto space-y-6">
      <div className="flex items-start justify-between gap-6">
        <div>
          {section && <div className="text-xs font-semibold uppercase tracking-wider text-brand">{section}</div>}
          <h1 className="text-2xl font-semibold text-slate-900 mt-1">{title}</h1>
          {subtitle && <p className="text-slate-600 mt-1 max-w-3xl">{subtitle}</p>}
        </div>
        {actions && <div className="flex gap-2 shrink-0">{actions}</div>}
      </div>
      {capability && <Capability text={capability} />}
      {children}
    </div>
  );
}

export function Capability({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-700">
      <Cpu className="w-4 h-4 mt-0.5 text-brand shrink-0" />
      <div><span className="font-semibold text-slate-900">What's happening on Databricks: </span>{text}</div>
    </div>
  );
}

export function Card({ title, children, right, className = '' }: { title?: ReactNode; children: ReactNode; right?: ReactNode; className?: string }) {
  return (
    <section className={`bg-white rounded-xl border border-slate-200 shadow-sm ${className}`}>
      {title && (
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100">
          <h2 className="font-semibold text-slate-800 text-sm">{title}</h2>{right}
        </div>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Kpi({ label, value, sub, accent }: { label: string; value: ReactNode; sub?: ReactNode; accent?: boolean }) {
  return (
    <div className={`bg-white rounded-xl border p-4 shadow-sm ${accent ? 'border-brand/40' : 'border-slate-200'}`}>
      <div className="text-xs text-slate-500 uppercase tracking-wide">{label}</div>
      <div className={`text-2xl font-semibold mt-1 tabular ${accent ? 'text-brand' : 'text-slate-900'}`}>{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </div>
  );
}

const BADGE: Record<string, string> = {
  green: 'bg-emerald-50 text-emerald-700 border-emerald-200', red: 'bg-red-50 text-red-700 border-red-200',
  amber: 'bg-amber-50 text-amber-800 border-amber-200', blue: 'bg-sky-50 text-sky-700 border-sky-200',
  slate: 'bg-slate-100 text-slate-700 border-slate-200', brand: 'bg-orange-50 text-brand border-orange-200',
  violet: 'bg-violet-50 text-violet-700 border-violet-200',
};
export function Badge({ children, tone = 'slate' }: { children: ReactNode; tone?: keyof typeof BADGE | string }) {
  return <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs font-medium ${BADGE[tone] ?? BADGE.slate}`}>{children}</span>;
}

export function statusTone(s?: string | null) {
  if (!s) return 'slate';
  if (['APPROVED', 'SUCCESS', 'champion'].includes(s)) return 'green';
  if (['REJECTED', 'FAILED', 'INTERNAL_ERROR', 'TIMEDOUT', 'CANCELED'].includes(s)) return 'red';
  if (['PENDING', 'RUNNING', 'QUEUED', 'challenger', 'BLOCKED'].includes(s)) return 'amber';
  return 'slate';
}

export function Button({ children, onClick, variant = 'primary', disabled, busy, small }: {
  children: ReactNode; onClick?: () => void; variant?: 'primary' | 'secondary' | 'danger' | 'ghost'; disabled?: boolean; busy?: boolean; small?: boolean;
}) {
  const cls = {
    primary: 'bg-brand text-white hover:bg-[#e02e1b]', secondary: 'bg-white border border-slate-300 text-slate-800 hover:bg-slate-50',
    danger: 'bg-white border border-red-300 text-red-700 hover:bg-red-50', ghost: 'text-slate-600 hover:bg-slate-100',
  }[variant];
  return (
    <button onClick={onClick} disabled={disabled || busy}
      className={`inline-flex items-center gap-2 rounded-lg font-medium transition-colors disabled:opacity-50 ${small ? 'px-2.5 py-1 text-xs' : 'px-4 py-2 text-sm'} ${cls}`}>
      {busy && <Loader2 className="w-4 h-4 animate-spin" />}{children}
    </button>
  );
}

export function Empty({ text }: { text: string }) {
  return <div className="flex items-center gap-2 text-sm text-slate-500 py-6 justify-center"><Info className="w-4 h-4" />{text}</div>;
}

export function ErrorBox({ error }: { error?: string | null }) {
  if (!error) return null;
  return <div className="rounded-lg border border-red-200 bg-red-50 text-red-800 text-sm px-4 py-2">{error}</div>;
}

export type Col = { key: string; label: string; fmt?: (v: any, row: any) => ReactNode; align?: 'right' | 'left' };
export function Table({ rows, cols, max = 50, dense }: { rows: any[] | null | undefined; cols: Col[]; max?: number; dense?: boolean }) {
  if (!rows || rows.length === 0) return <Empty text="No rows yet." />;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-slate-500 uppercase tracking-wide border-b border-slate-200">
            {cols.map(c => <th key={c.key} className={`py-2 pr-4 font-medium ${c.align === 'right' ? 'text-right' : ''}`}>{c.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, max).map((r, i) => (
            <tr key={i} className="border-b border-slate-100 last:border-0 hover:bg-slate-50/60">
              {cols.map(c => (
                <td key={c.key} className={`${dense ? 'py-1' : 'py-2'} pr-4 tabular ${c.align === 'right' ? 'text-right' : ''}`}>
                  {c.fmt ? c.fmt(r[c.key], r) : (r[c.key] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Ext({ href, children }: { href?: string | null; children: ReactNode }) {
  if (!href) return <>{children}</>;
  return <a href={href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sky-700 hover:underline">{children}<ExternalLink className="w-3 h-3" /></a>;
}

/** Polls a job run until it terminates; shows state, task states and a deep link. */
export function RunTracker({ run, onDone, label }: { run: { run_id: number; run_url?: string } | null; onDone?: () => void; label?: string }) {
  const [st, setSt] = useState<any>(null);
  const doneRef = useRef(false);
  useEffect(() => {
    if (!run) return;
    doneRef.current = false; setSt(null);
    const tick = async () => {
      try {
        const s = await get(`/runs/${run.run_id}`); setSt(s);
        if (s.done && !doneRef.current) { doneRef.current = true; onDone?.(); }
      } catch { /* keep polling */ }
    };
    tick();
    const t = setInterval(() => { if (!doneRef.current) tick(); }, 5000);
    return () => clearInterval(t);
  }, [run?.run_id]);
  if (!run) return null;
  const result = st?.result_state, life = st?.life_cycle_state;
  const ok = result === 'SUCCESS', bad = result && result !== 'SUCCESS';
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm">
      {ok ? <CheckCircle2 className="w-4 h-4 text-emerald-600" /> : bad ? <XCircle className="w-4 h-4 text-red-600" /> : <Loader2 className="w-4 h-4 animate-spin text-amber-600" />}
      <span className="font-medium">{label ?? 'Job run'} #{run.run_id}</span>
      <Badge tone={statusTone(result ?? life)}>{result ?? life ?? 'SUBMITTED'}</Badge>
      {st?.duration_seconds != null && <span className="text-slate-500">{secs(st.duration_seconds)}</span>}
      {(st?.tasks ?? []).map((t: any) => <Badge key={t.task_key} tone={statusTone(t.state)}>{t.task_key}: {t.state ?? '…'}</Badge>)}
      <Ext href={st?.run_url ?? run.run_url}>open run</Ext>
    </div>
  );
}

export function Tabs({ tabs, value, onChange }: { tabs: string[]; value: string; onChange: (t: string) => void }) {
  return (
    <div className="flex gap-1 border-b border-slate-200">
      {tabs.map(t => (
        <button key={t} onClick={() => onChange(t)}
          className={`px-4 py-2 text-sm -mb-px border-b-2 ${value === t ? 'border-brand text-slate-900 font-medium' : 'border-transparent text-slate-500 hover:text-slate-800'}`}>{t}</button>
      ))}
    </div>
  );
}

export function Code({ children }: { children: string }) {
  return <pre className="bg-slate-900 text-slate-100 text-xs rounded-lg p-4 overflow-x-auto leading-relaxed"><code>{children}</code></pre>;
}
