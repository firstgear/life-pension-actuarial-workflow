import { useState } from 'react';
import { Upload, Check, X } from 'lucide-react';
import { Page, Card, Badge, Button, Table, RunTracker, useApi, statusTone, ErrorBox, Ext } from '../components/ui';
import { HBar } from '../components/charts';
import { post } from '../lib/api';
import { n, ts, pct } from '../lib/format';

export default function Ingestion() {
  const ex = useApi<any[]>('/ingestion/extracts', 10000);
  const dq = useApi<any>('/ingestion/quality', 20000);
  const land = useApi<any>('/ingestion/landing', 10000);
  const [drop, setDrop] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [notes, setNotes] = useState('Reconciled to the quarter-end policy count; A/E within tolerance.');
  const [martRun, setMartRun] = useState<any>(null);

  const doDrop = async () => {
    setBusy(true); setErr(null);
    try { setDrop(await post('/ingestion/drop-extract')); land.reload(); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const decide = async (id: string, decision: string) => {
    setErr(null);
    try { const r = await post(`/ingestion/extracts/${id}/decision`, { decision, notes }); setMartRun(r.run); ex.reload(); }
    catch (e: any) { setErr(e.message); }
  };
  const rules = dq.data?.by_rule ?? [];
  return (
    <Page section="1 · Data Ingestion" title="policy admin extracts — land, validate, approve"
      subtitle="Quarterly experience extracts (exposure and decrements per policy-year) land in a Unity Catalog volume. Bad rows are quarantined, never silently lost, and an actuary approves the extract before it can influence an assumption."
      capability="Job started from the app (file-arrival trigger in production) · UC volume · Lakeflow Declarative Pipeline (Auto Loader, serverless) with data-quality expectations · human-in-the-loop approval in a Delta table · audit log"
      actions={<Button onClick={doDrop} busy={busy}><Upload className="w-4 h-4" />Drop new policy admin extract (2026 Q1–Q3)</Button>}>
      <ErrorBox error={err} />
      {drop && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          Landed <b>{drop.path.split('/').pop()}</b> ({n(drop.bytes / 1e6, 1)} MB). {drop.hint} <Ext href={drop.volume_url}>view volume</Ext>
          {drop.run && <div className="mt-2"><RunTracker run={drop.run} label="Extract ingest + DQ pipeline (job 01)" onDone={() => { ex.reload(); dq.reload(); }} /></div>}
        </div>
      )}
      <div className="grid lg:grid-cols-3 gap-4">
        <Card title="Landing zone — /Volumes/…/extract_landing/incoming" className="lg:col-span-2">
          <Table dense rows={land.data?.incoming} cols={[
            { key: 'name', label: 'File' }, { key: 'size', label: 'Size', align: 'right', fmt: v => `${n(v / 1e6, 1)} MB` },
            { key: 'modified', label: 'Arrived', fmt: ts },
          ]} />
        </Card>
        <Card title="DQ rules — rows quarantined">
          {rules.length ? (
            <HBar fmt={v => n(v)} labelWidth={140} data={['policy_id_present', 'exposure_in_range', 'age_plausible'].map(r => ({
              label: r, value: rules.reduce((s: number, x: any) => s + (x[r] ?? 0), 0), tone: '#FF3621' }))} />
          ) : <div className="text-sm text-slate-500">No quarantined rows yet.</div>}
          <div className="text-xs text-slate-500 mt-2">Expectations: policy id present · 0 &lt; exposure ≤ 1 · age 15–115 · events binary.</div>
        </Card>
      </div>

      <Card title="Extracts awaiting / after review" right={<span className="text-xs text-slate-500">only APPROVED extracts enter the experience mart</span>}>
        <div className="mb-3 flex items-center gap-2 text-sm">
          <span className="text-slate-500">Reviewer notes:</span>
          <input value={notes} onChange={e => setNotes(e.target.value)} className="flex-1 border border-slate-300 rounded-lg px-3 py-1.5 text-sm" />
        </div>
        <Table rows={ex.data} cols={[
          { key: 'source_file', label: 'Extract', fmt: v => <span className="text-xs font-mono">{v}</span> },
          { key: 'extract_period', label: 'Period' },
          { key: 'rows_received', label: 'Rows', align: 'right', fmt: v => n(v) },
          { key: 'rows_quarantined', label: 'Quarantined', align: 'right', fmt: v => <span className={v ? 'text-red-700 font-medium' : ''}>{n(v)}</span> },
          { key: 'deaths', label: 'Deaths', align: 'right', fmt: v => n(v) },
          { key: 'crude_mortality', label: 'Crude q', align: 'right', fmt: v => pct(v, 2) },
          { key: 'ae_vs_champion', label: 'A/E vs champion', align: 'right', fmt: v => v == null ? '—' : <span className={Math.abs(v - 1) > 0.05 ? 'text-amber-700 font-medium' : ''}>{Number(v).toFixed(3)}</span> },
          { key: 'status', label: 'Status', fmt: v => <Badge tone={statusTone(v)}>{v}</Badge> },
          { key: 'reviewed_by', label: 'Reviewed by', fmt: (v, r) => v ? <span className="text-xs">{v}<br /><span className="text-slate-400">{ts(r.reviewed_at)}</span></span> : '—' },
          { key: 'extract_id', label: '', fmt: (id, r) => r.status === 'PENDING' ? (
            <div className="flex gap-1">
              <Button small onClick={() => decide(id, 'APPROVED')}><Check className="w-3 h-3" />Approve</Button>
              <Button small variant="danger" onClick={() => decide(id, 'REJECTED')}><X className="w-3 h-3" />Reject</Button>
            </div>) : null },
        ]} />
        {martRun && <div className="mt-3"><RunTracker run={martRun} label="Experience mart rebuild (job 02)" /></div>}
      </Card>

      <Card title="Quarantine — sample of rejected rows">
        <Table dense max={12} rows={dq.data?.sample} cols={[
          { key: 'source_file', label: 'File', fmt: v => <span className="text-xs font-mono">{v}</span> }, { key: 'policy_id', label: 'Policy', fmt: v => v ?? <Badge tone="red">NULL</Badge> },
          { key: 'calendar_year', label: 'Year' }, { key: 'age', label: 'Age', fmt: v => v > 115 ? <Badge tone="red">{v}</Badge> : v },
          { key: 'exposure_years', label: 'Exposure', fmt: v => v <= 0 ? <Badge tone="red">{v}</Badge> : v }, { key: 'death', label: 'Death' },
        ]} />
      </Card>
    </Page>
  );
}
