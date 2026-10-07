import { useState } from 'react';
import { Page, Card, Kpi, Table, Button, RunTracker, useApi, Ext, ErrorBox } from '../components/ui';
import { Lines, VBars } from '../components/charts';
import { post } from '../lib/api';
import { eur, n, pct, secs, ts } from '../lib/format';

export default function Mart() {
  const { data, error, reload } = useApi<any>('/mart/summary');
  const [run, setRun] = useState<any>(null);
  const [scale, setScale] = useState(1);
  const t = data?.totals?.[0] ?? {};
  const ages = [...new Set((data?.by_age_sex ?? []).map((r: any) => r.age_band))] as string[];
  const rate = (s: string) => ages.map(a => (data?.by_age_sex ?? []).find((r: any) => r.age_band === a && r.sex === s)?.crude_rate_per_mille ?? 0);
  return (
    <Page section="2 · Experience Mart" title="One governed, GLM-ready experience mart"
      subtitle="Approved experience data joined to the policy master and aggregated to risk cells: exposure in life-years, deaths, disabilities, surrenders, paid-ups and expected deaths on the standard table."
      capability="Spark SQL on serverless (data parallelism) · Delta table with versions and time travel · Unity Catalog lineage and column comments · writing this table fires the table-update trigger on the assumption-model job"
      actions={<>
        <select value={scale} onChange={e => setScale(Number(e.target.value))} className="border border-slate-300 rounded-lg px-2 text-sm">
          <option value={1}>book × 1</option><option value={10}>book × 10 (benchmark)</option><option value={100}>book × 100 (benchmark)</option>
        </select>
        <Button onClick={async () => setRun(await post('/mart/rebuild', { scale_factor: scale }))}>Rebuild mart</Button>
      </>}>
      <ErrorBox error={error} />
      {run && <RunTracker run={run} label="Experience mart (job 02)" onDone={reload} />}
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-4">
        <Kpi label="Risk cells" value={n(t.cells)} /><Kpi label="Life-years" value={n(t.exposure)} />
        <Kpi label="Deaths" value={n(t.deaths)} /><Kpi label="Disabilities" value={n(t.disabilities)} />
        <Kpi label="Surrenders" value={n(t.surrenders)} /><Kpi label="Paid-ups" value={n(t.paid_ups)} />
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="A/E vs standard table, by calendar year">
          <Lines yMin={0.8} yFmt={v => v.toFixed(2)} xLabel="calendar year" series={[
            { name: 'A/E (standard table)', points: (data?.by_year ?? []).map((r: any) => [r.calendar_year, r.ae_std]) },
            { name: '1.00', points: (data?.by_year ?? []).map((r: any) => [r.calendar_year, 1]), color: '#FF3621', dashed: true },
          ]} />
          <div className="text-xs text-slate-500">A/E drifts below 1 over time — mortality improvement the standard table under-allows for.</div>
        </Card>
        <Card title="Crude mortality per mille, by age band and sex">
          <VBars cats={ages} yFmt={v => v.toFixed(0)} series={[{ name: 'Female', values: rate('F'), color: '#2E86AB' }, { name: 'Male', values: rate('M'), color: '#1B3139' }]} />
        </Card>
      </div>
      <Card title="By scheme">
        <Table rows={data?.by_scheme} cols={[
          { key: 'scheme', label: 'Scheme' }, { key: 'exposure', label: 'Life-years', align: 'right', fmt: v => n(v) },
          { key: 'deaths', label: 'Deaths', align: 'right', fmt: v => n(v) }, { key: 'ae_std', label: 'A/E std', align: 'right', fmt: v => n(v, 3) },
          { key: 'lapse_rate', label: 'Lapse rate', align: 'right', fmt: v => pct(v, 2) }, { key: 'disability_rate', label: 'Disability inc.', align: 'right', fmt: v => pct(v, 3) },
        ]} />
      </Card>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Delta history — every rebuild is a version" right={<Ext href={data?.links?.table}>open in Catalog Explorer</Ext>}>
          <Table dense rows={data?.history} cols={[
            { key: 'version', label: 'Version' }, { key: 'timestamp', label: 'When', fmt: ts }, { key: 'operation', label: 'Operation' },
            { key: 'rows', label: 'Rows', align: 'right', fmt: v => n(v) }, { key: 'userName', label: 'By', fmt: v => <span className="text-xs">{v}</span> },
          ]} />
          <div className="text-xs text-slate-500 mt-2">Any model can be re-fitted on the exact mart version it was trained on: <code>SELECT … FROM experience_mart VERSION AS OF n</code>. <Ext href={data?.links?.lineage}>lineage</Ext></div>
        </Card>
        <Card title="Model points for projection (in-force at valuation)">
          <Table dense rows={data?.model_points} cols={[
            { key: 'scheme', label: 'Scheme' }, { key: 'model_points', label: 'Model points', align: 'right', fmt: v => n(v) },
            { key: 'policies', label: 'Policies', align: 'right', fmt: v => n(v) }, { key: 'savings_eur', label: 'Savings', align: 'right', fmt: eur },
          ]} />
          {data?.benchmarks?.length ? (
            <div className="mt-3 text-sm"><b>Scale benchmark:</b> {data.benchmarks.map((b: any) => `×${b.scale_factor}: ${n(b.policy_years)} policy-years → ${n(b.cells)} cells in ${secs(b.seconds)}`).join(' · ')}</div>
          ) : null}
        </Card>
      </div>
      <Card title="Sample of the mart (largest cells)">
        <Table dense max={12} rows={data?.sample} cols={['calendar_year', 'age', 'sex', 'scheme', 'product_type', 'salary_band', 'region', 'duration_band'].map(k => ({ key: k, label: k.replace('_', ' ') }))
          .concat([{ key: 'exposure', label: 'exposure', fmt: (v: any) => n(v, 1) } as any, { key: 'deaths', label: 'deaths' } as any, { key: 'expected_deaths_std', label: 'expected (std)', fmt: (v: any) => n(v, 2) } as any])} />
      </Card>
    </Page>
  );
}
