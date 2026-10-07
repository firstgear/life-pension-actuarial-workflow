import { useEffect, useState } from 'react';
import { Play } from 'lucide-react';
import { Page, Card, Kpi, Table, Button, RunTracker, useApi, Badge, ErrorBox } from '../components/ui';
import { HBar, Lines, PALETTE } from '../components/charts';
import { get, post } from '../lib/api';
import { eur, n, pct, secs, ts } from '../lib/format';

function Slider({ label, value, set, min, max, step, fmt }: any) {
  return (
    <label className="block text-sm">
      <div className="flex justify-between"><span>{label}</span><span className="font-medium tabular">{fmt(value)}</span></div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={e => set(Number(e.target.value))} className="w-full accent-[#FF3621]" />
    </label>
  );
}

export default function Projection() {
  const runs = useApi<any[]>('/projection/runs', 15000);
  const [sel, setSel] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [dr, setDr] = useState(0.025), [mm, setMm] = useState(1.0), [lm, setLm] = useState(1.0);
  const [label, setLabel] = useState('What-if');
  const [run, setRun] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const list = runs.data ?? [];
  const cur = list.find(r => r.projection_run_id === sel) ?? list[0];
  const base = list.find(r => r.scenario_label?.startsWith('Base') && r.model_version === cur?.model_version) ?? list[list.length - 1];
  useEffect(() => { if (cur) get(`/projection/runs/${cur.projection_run_id}`).then(setDetail).catch(() => setDetail(null)); }, [cur?.projection_run_id]);
  const schemes = [...new Set((detail?.cashflows ?? []).map((r: any) => r.scheme))] as string[];
  const go = async () => {
    setErr(null);
    try { setRun(await post('/projection/run', { discount_rate: dr, mortality_mult: mm, lapse_mult: lm, scenario_label: label })); } catch (e: any) { setErr(e.message); }
  };
  return (
    <Page section="6 · Projection Engine" title="Best-estimate liability — re-projected when the champion changes"
      subtitle="80 years of cash flows per model point: mortality from the champion GLM, lapse from the experience, annuities from retirement age, disability and health claims, expenses. Discounted to a best-estimate liability."
      capability="Job fired by the @champion change (model-update event) · loads the model from the UC registry · vectorised NumPy kernel fanned out with Spark mapInPandas · results and cash flows in Delta">
      <ErrorBox error={err} />
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <Kpi label="Total BEL (selected run)" value={eur(cur?.total_bel_eur)} sub={cur?.scenario_label} accent />
        <Kpi label="vs base" value={cur && base ? pct(cur.total_bel_eur / base.total_bel_eur - 1, 2) : '—'} sub={base ? `base ${eur(base.total_bel_eur)}` : undefined} />
        <Kpi label="Mortality model" value={cur ? `v${cur.model_version}` : '—'} sub="@champion at run time" />
        <Kpi label="Model points" value={n(cur?.model_points)} sub={`projected in ${secs(cur?.seconds)}`} />
        <Kpi label="Triggered by" value={<span className="text-base">{cur?.requested_by ?? '—'}</span>} sub={ts(cur?.run_ts)} />
      </div>
      <div className="grid lg:grid-cols-3 gap-4">
        <Card title="Net liability cash flows by scheme (undiscounted)" className="lg:col-span-2">
          <Lines yFmt={v => eur(v).replace(' EUR', '')} xLabel="calendar year" series={schemes.map((s, i) => ({
            name: s, color: PALETTE[i], points: (detail?.cashflows ?? []).filter((r: any) => r.scheme === s).map((r: any) => [r.calendar_year, r.net_cashflow_eur]) }))} />
        </Card>
        <Card title="What-if — re-run the projection job">
          <div className="space-y-3">
            <Slider label="Discount rate" value={dr} set={setDr} min={0.005} max={0.05} step={0.0025} fmt={(v: number) => pct(v, 2)} />
            <Slider label="Mortality multiplier" value={mm} set={setMm} min={0.7} max={1.3} step={0.05} fmt={(v: number) => `× ${v.toFixed(2)}`} />
            <Slider label="Lapse multiplier" value={lm} set={setLm} min={0.5} max={1.5} step={0.1} fmt={(v: number) => `× ${v.toFixed(1)}`} />
            <input value={label} onChange={e => setLabel(e.target.value)} className="w-full border border-slate-300 rounded-lg px-3 py-1.5 text-sm" />
            <Button onClick={go}><Play className="w-4 h-4" />Run projection</Button>
          </div>
          {run && <div className="mt-3"><RunTracker run={run} label="BEL projection (job 05)" onDone={runs.reload} /></div>}
        </Card>
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="BEL by scheme (selected run)">
          <HBar labelWidth={150} fmt={v => eur(v)} data={Object.entries(cur?.bel_by_scheme ?? {}).map(([k, v]: any) => ({ label: k, value: v, tone: v < 0 ? '#00A972' : '#1B3139' }))} />
          <div className="text-xs text-slate-500 mt-1">Negative BEL = future premiums exceed expected claims (risk products).</div>
        </Card>
        <Card title="Largest segments">
          <Table dense max={10} rows={detail?.by_segment} cols={[
            { key: 'scheme', label: 'Scheme' }, { key: 'sex', label: 'Sex' }, { key: 'policies', label: 'Policies', align: 'right', fmt: v => n(v) },
            { key: 'bel_eur', label: 'BEL', align: 'right', fmt: eur }, { key: 'duration', label: 'Duration (y)', align: 'right', fmt: v => n(v, 1) },
          ]} />
        </Card>
      </div>
      <Card title="Projection runs — click to select">
        <Table dense rows={list.map(r => ({ ...r, _sel: r.projection_run_id === cur?.projection_run_id }))} cols={[
          { key: 'run_ts', label: 'When', fmt: (v, r) => <button className="text-sky-700 hover:underline" onClick={() => setSel(r.projection_run_id)}>{ts(v)}</button> },
          { key: 'scenario_label', label: 'Scenario', fmt: (v, r) => <>{v} {r._sel && <Badge tone="brand">selected</Badge>}</> },
          { key: 'model_version', label: 'Mortality v.' }, { key: 'discount_rate', label: 'Disc.', align: 'right', fmt: v => pct(v, 2) },
          { key: 'mortality_mult', label: 'Mort ×', align: 'right', fmt: v => n(v, 2) }, { key: 'lapse_mult', label: 'Lapse ×', align: 'right', fmt: v => n(v, 1) },
          { key: 'total_bel_eur', label: 'BEL', align: 'right', fmt: eur }, { key: 'requested_by', label: 'Trigger', fmt: v => <span className="text-xs">{v}</span> },
        ]} />
      </Card>
    </Page>
  );
}
