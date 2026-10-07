import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Check, Send, Undo2, X } from 'lucide-react';
import { Page, Card, Badge, Button, Table, useApi, statusTone, ErrorBox, Ext } from '../components/ui';
import { Stat } from '../components/charts';
import { post } from '../lib/api';
import { n, ts } from '../lib/format';

function Delta({ a, b, lowerBetter = true, d = 0 }: { a?: number; b?: number; lowerBetter?: boolean; d?: number }) {
  if (a == null || b == null) return <>—</>;
  const diff = b - a, good = lowerBetter ? diff < 0 : diff > 0;
  return <span className={good ? 'text-emerald-700' : 'text-red-700'}>{diff > 0 ? '+' : ''}{n(diff, d)}</span>;
}

export default function Deployment() {
  const models = useApi<any[]>('/deployment/models', 15000);
  const cmp = useApi<any>('/deployment/compare?model=mortality_glm', 15000);
  const appr = useApi<any[]>('/deployment/approvals', 8000);
  const [rationale, setRationale] = useState('Adding salary band captures socio-economic mortality differences; AIC improves materially and A/E by salary band moves to ~1.00.');
  const [notes, setNotes] = useState('Reviewed relativities and A/E by segment. Approved for the Q3 valuation.');
  const [asChief, setAsChief] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const c = cmp.data ?? {};
  const cm = c.champion_meta?.metrics ?? {}, xm = c.challenger_meta?.metrics ?? {};
  const pending = (appr.data ?? []).filter(a => a.status === 'PENDING');
  const refresh = () => { models.reload(); cmp.reload(); appr.reload(); };
  const act = async (fn: () => Promise<any>, ok: string) => {
    setErr(null); setMsg(null);
    try { const r = await fn(); setMsg(r?.hint ?? ok); refresh(); } catch (e: any) { setErr(e.message); }
  };
  return (
    <Page section="5 · Model Deployment & Approval" title="Four-eyes approval: challenger → champion"
      subtitle="The actuary proposes, the chief actuary approves. Approval moves the Unity Catalog @champion alias, and that event re-runs the BEL projection automatically. No hand-copied parameter files."
      capability="Unity Catalog model registry (aliases @champion / @challenger / @previous_champion) · approval requests in a Delta table · model-update event fires the projection job · every step in the audit log">
      <ErrorBox error={err} />
      {msg && <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-900 flex items-center gap-3">{msg}
        <Link to="/orchestration" className="text-sky-700 hover:underline inline-flex items-center gap-1">watch the jobs<ArrowRight className="w-3 h-3" /></Link></div>}

      <div className="grid lg:grid-cols-3 gap-4">
        <Card title="Mortality model — champion vs challenger" className="lg:col-span-2">
          <div className="grid md:grid-cols-2 gap-6">
            <div>
              <div className="flex items-center gap-2 mb-2"><Badge tone="green">@champion v{c.champion ?? '—'}</Badge><span className="text-xs text-slate-500">{c.champion_meta?.params?.label}</span></div>
              <div className="flex items-center gap-2 mb-3"><Badge tone="amber">@challenger v{c.challenger ?? '—'}</Badge><span className="text-xs text-slate-500">{c.challenger_meta?.params?.label}</span></div>
              <table className="w-full text-sm tabular">
                <thead><tr className="text-xs text-slate-500 border-b"><th className="text-left py-1">Metric</th><th className="text-right">Champion</th><th className="text-right">Challenger</th><th className="text-right">Δ</th></tr></thead>
                <tbody>
                  {[['AIC', 'aic', true, 0], ['Deviance', 'deviance', true, 0], ['Pseudo R²', 'pseudo_r2', false, 3], ['Overall A/E', 'ae_overall', false, 3]].map(([l, k, lb, d]: any) => (
                    <tr key={k} className="border-b border-slate-100"><td className="py-1">{l}</td><td className="text-right">{n(cm[k], d)}</td><td className="text-right">{n(xm[k], d)}</td>
                      <td className="text-right">{k === 'ae_overall' ? '' : <Delta a={cm[k]} b={xm[k]} lowerBetter={lb} d={d} />}</td></tr>
                  ))}
                </tbody>
              </table>
              <div className="text-xs text-slate-500 mt-2">Trained on mart version {c.challenger_meta?.mart_table_version ?? '—'} · code {c.challenger_meta?.code_version ?? '—'}</div>
            </div>
            <div>
              <div className="text-xs font-semibold text-slate-600 uppercase mb-1">Relativities that changed</div>
              <Table dense max={14} rows={(c.relativities ?? []).filter((r: any) => r.champion == null || r.challenger == null || Math.abs(r.challenger - r.champion) > 0.005)} cols={[
                { key: 'factor', label: 'Factor' }, { key: 'level', label: 'Level' },
                { key: 'champion', label: 'Champion', align: 'right', fmt: v => v == null ? <span className="text-slate-400">n/a</span> : n(v, 3) },
                { key: 'challenger', label: 'Challenger', align: 'right', fmt: v => v == null ? <span className="text-slate-400">n/a</span> : n(v, 3) },
              ]} />
            </div>
          </div>
        </Card>
        <Card title="Propose challenger for approval">
          <textarea value={rationale} onChange={e => setRationale(e.target.value)} rows={5} className="w-full border border-slate-300 rounded-lg p-2 text-sm" />
          <div className="mt-3 flex items-center gap-2">
            <Button disabled={!c.challenger || c.challenger === c.champion || pending.length > 0}
              onClick={() => act(() => post('/deployment/propose', { model: 'mortality_glm', version: c.challenger, rationale }), 'Proposal submitted — waiting for the chief actuary.')}>
              <Send className="w-4 h-4" />Propose v{c.challenger ?? '—'}</Button>
            {c.challenger === c.champion && <span className="text-xs text-slate-500">challenger is already champion</span>}
          </div>
          <div className="text-xs text-slate-500 mt-3">Evidence (metrics, A/E) is snapshotted into the request so the decision is auditable later.</div>
        </Card>
      </div>

      <Card title="Pending approvals — chief actuary" right={<label className="text-xs flex items-center gap-2"><input type="checkbox" checked={asChief} onChange={e => setAsChief(e.target.checked)} />acting as Chief Actuary (demo)</label>}>
        {pending.length === 0 ? <div className="text-sm text-slate-500">Nothing waiting for approval.</div> : (
          <div className="space-y-3">
            <input value={notes} onChange={e => setNotes(e.target.value)} className="w-full border border-slate-300 rounded-lg px-3 py-1.5 text-sm" />
            {pending.map(p => (
              <div key={p.request_id} className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-200 bg-amber-50/50 p-3 text-sm">
                <Badge tone="amber">PENDING</Badge><b>{p.model_name} v{p.model_version}</b><span className="text-slate-500">replaces v{p.champion_version ?? '—'}</span>
                <span className="text-slate-600 flex-1">“{p.rationale}” — {p.proposed_by}, {ts(p.proposed_at)}</span>
                <Button small onClick={() => act(() => post(`/deployment/approvals/${p.request_id}/review`, { decision: 'APPROVED', notes, acting_as_chief_actuary: asChief }), 'Approved')}><Check className="w-3 h-3" />Approve → @champion</Button>
                <Button small variant="danger" onClick={() => act(() => post(`/deployment/approvals/${p.request_id}/review`, { decision: 'REJECTED', notes, acting_as_chief_actuary: asChief }), 'Rejected')}><X className="w-3 h-3" />Reject</Button>
              </div>
            ))}
          </div>
        )}
      </Card>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Registered models (Unity Catalog)">
          <div className="space-y-3">
            {(models.data ?? []).map(m => (
              <div key={m.key} className="border-b border-slate-100 pb-2 last:border-0">
                <div className="flex items-center gap-2 text-sm"><Ext href={m.url}><b>{m.label}</b></Ext>
                  {Object.entries(m.aliases ?? {}).map(([a, v]: any) => <Badge key={a} tone={statusTone(a)}>@{a} v{v}</Badge>)}</div>
                <div className="text-xs text-slate-500 mt-0.5">{m.versions.length} version(s) · {m.full_name}</div>
              </div>
            ))}
          </div>
          <div className="mt-3"><Button small variant="secondary" disabled={!c.previous_champion}
            onClick={() => act(() => post('/deployment/rollback', { model: 'mortality_glm', reason: 'Rollback from Workbench' }), 'Rolled back — projection will re-run.')}>
            <Undo2 className="w-3 h-3" />Roll back mortality to v{c.previous_champion ?? '—'}</Button></div>
        </Card>
        <Card title="Approval history">
          <Table dense rows={appr.data} cols={[
            { key: 'proposed_at', label: 'Proposed', fmt: ts }, { key: 'model_name', label: 'Model' }, { key: 'model_version', label: 'Ver.' },
            { key: 'status', label: 'Decision', fmt: v => <Badge tone={statusTone(v)}>{v}</Badge> },
            { key: 'proposed_by', label: 'Proposed by', fmt: v => <span className="text-xs">{v}</span> },
            { key: 'reviewed_by', label: 'Reviewed by', fmt: v => <span className="text-xs">{v ?? '—'}</span> },
          ]} />
          <Stat k="Four-eyes rule" v="reviewer ≠ proposer (enforced server-side)" />
        </Card>
      </div>
    </Page>
  );
}
