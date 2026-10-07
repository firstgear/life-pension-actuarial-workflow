import { useState } from 'react';
import { Play } from 'lucide-react';
import { Page, Card, Kpi, Table, Tabs, Button, RunTracker, useApi, Code, ErrorBox } from '../components/ui';
import { HBar } from '../components/charts';
import { post } from '../lib/api';
import { n, secs, ts } from '../lib/format';

const PRESETS: Record<string, string> = {
  'scheme × sex × product × region × period': 'scheme,sex,product_type,region,period',
  'scheme × sex × salary × sector': 'scheme,sex,salary_band,employer_sector',
  'scheme × sex × product × duration × period': 'scheme,sex,product_type,duration_band,period',
};

const RAY = `# Same kernel, fanned out as Ray tasks (Ray-on-Spark, spot workers) — notebook 04b
from ray.util.spark import setup_ray_cluster
setup_ray_cluster(min_worker_nodes=2, max_worker_nodes=16)

@ray.remote(num_cpus=1)
def fit(seg_key, cells, replicate):
    return fit_segment_gompertz(cells, rng_seed=None if replicate == 0 else 1000 + replicate)

groups  = {k: ray.put(g) for k, g in mart_pdf.groupby(seg_cols)}       # Spark reads the governed mart
futures = [fit.remote(k, ref, r) for k, ref in groups.items() for r in range(n_boot + 1)]
results = ray.get(futures)                                              # back to Delta via Spark`;

const SPARK = `# What job 04 runs on serverless — plain statsmodels inside Spark applyInPandas
def fit_group(pdf):
    rep = int(pdf.replicate.iloc[0])
    return pd.DataFrame([{**segment_key(pdf), "replicate": rep,
                          **fit_segment_gompertz(pdf, rng_seed=None if rep == 0 else 1000 + rep)}])

(mart.groupBy(*seg_cols, "age").agg(sum("exposure"), sum("deaths"))
     .crossJoin(spark.range(n_boot + 1).withColumnRenamed("id", "replicate"))
     .groupBy(*seg_cols, "replicate").applyInPandas(fit_group, schema)
     .write.saveAsTable("factory_results"))`;

const SHORT: Record<string, string> = {
  COMPANY_PENSION: 'Company', PRIVATE_PENSION: 'Private', LIFE_ANNUITY: 'Annuity', DISABILITY_COVER: 'Disability',
  HEALTH_COVER: 'Health', AVERAGE_RATE: 'Avg-rate', MARKET_RATE: 'Unit-linked', CAPITAL: 'Capital', NORTH: 'North',
  SOUTH: 'South', EAST: 'East', WEST: 'West',
};
const shortSegment = (seg: string) => String(seg).split(' · ').map(p => SHORT[p] ?? p).join(' · ');

export default function Factory() {
  const { data, reload } = useApi<any>('/factory/runs', 15000);
  const [boot, setBoot] = useState(50);
  const [preset, setPreset] = useState(Object.keys(PRESETS)[0]);
  const [run, setRun] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState('Spark (running today)');
  const last = data?.runs?.[0];
  const segs = (data?.segments ?? []).filter((s: any) => s.converged && s.mu65_p975 != null);
  const shown = [...segs.slice(0, 12), ...segs.slice(-12)];
  const start = async () => {
    setErr(null);
    try { setRun(await post('/factory/run', { n_bootstrap: boot, segment_by: PRESETS[preset] })); } catch (e: any) { setErr(e.message); }
  };
  return (
    <Page section="4 · Model Factory" title="Thousands of GLMs in parallel — the overnight run in minutes"
      subtitle="One Gompertz-Poisson GLM per segment × bootstrap replicate. Each fit is small and independent, so the job is embarrassingly parallel. The statistics stay plain statsmodels; Databricks only fans them out."
      capability="Spark applyInPandas on serverless (parallel Python per group) · the same kernel runs as Ray tasks on a spot cluster (illustrative) · results to Delta, run metadata in factory_runs">
      <ErrorBox error={err} />
      <Card title="Launch a factory run">
        <div className="flex flex-wrap items-end gap-4">
          <label className="text-sm">Segmentation<br />
            <select value={preset} onChange={e => setPreset(e.target.value)} className="mt-1 border border-slate-300 rounded-lg px-2 py-1.5 text-sm">
              {Object.keys(PRESETS).map(p => <option key={p}>{p}</option>)}
            </select></label>
          <label className="text-sm">Bootstrap replicates per segment<br />
            <select value={boot} onChange={e => setBoot(Number(e.target.value))} className="mt-1 border border-slate-300 rounded-lg px-2 py-1.5 text-sm">
              {[5, 10, 25, 50, 100].map(b => <option key={b} value={b}>{b}</option>)}
            </select></label>
          <Button onClick={start}><Play className="w-4 h-4" />Run model factory</Button>
          <span className="text-xs text-slate-500">~200 segments × (replicates + 1) fits</span>
        </div>
        {run && <div className="mt-3"><RunTracker run={run} label="Model factory (job 04)" onDone={reload} /></div>}
        {!run && data?.active?.length ? <div className="mt-3 text-sm text-amber-700">A factory run is in progress (#{data.active[0].run_id}).</div> : null}
      </Card>
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <Kpi label="GLM fits (last run)" value={n(last?.n_fits)} sub={last ? `${n(last.n_segments)} segments × ${n(last.n_bootstrap + 1)}` : 'run job 04'} />
        <Kpi label="Parallel wall-clock" value={secs(last?.parallel_seconds)} sub={last?.engine} accent />
        <Kpi label="Sequential (one after another)" value={secs(last?.sequential_seconds_est)} sub="timed sample, extrapolated" />
        <Kpi label="Speed-up" value={last ? `× ${n(last.speedup, 1)}` : '—'} sub="grows with the workload — serverless scales out" accent />
        <Kpi label="Converged" value={last ? `${n(last.converged)} / ${n(last.n_fits)}` : '—'} sub="sparse segments reported, not failed" />
      </div>
      <Card title="Mortality at 65 relative to the book — bootstrap 95% intervals (heaviest and lightest segments)">
        <HBar refLine={1} labelWidth={250} fmt={v => v.toFixed(2)} data={shown.map((s: any) => {
          const med = s.mu65 / s.relative_to_book;
          return { label: shortSegment(s.segment), title: s.segment, value: s.relative_to_book, lo: s.mu65_p025 / med, hi: s.mu65_p975 / med, tone: s.relative_to_book > 1 ? '#1B3139' : '#2E86AB' };
        })} />
        <div className="text-xs text-slate-500 mt-1">Bar = point estimate, whisker = bootstrap 95% interval, dashed line = book average. Hover a row for the full segment key.</div>
      </Card>
      <div className="grid lg:grid-cols-5 gap-4">
        <Card title="Parallel engine" className="lg:col-span-5">
          <Tabs tabs={['Spark (running today)', 'Ray (next-gen Python)']} value={tab} onChange={setTab} />
          <div className="mt-3">{tab.startsWith('Spark') ? <Code>{SPARK}</Code> : <Code>{RAY}</Code>}</div>
          <div className="text-xs text-slate-500 mt-2">Rule of thumb: Spark for data parallelism (same operation over many rows/groups); Ray for logic parallelism (stateful workers, nested simulation, parameter sweeps, an existing Python engine).</div>
        </Card>
      </div>
      <Card title="Factory runs">
        <Table dense rows={data?.runs} cols={[
          { key: 'run_ts', label: 'When', fmt: ts }, { key: 'requested_by', label: 'By', fmt: v => <span className="text-xs">{v}</span> },
          { key: 'segment_by', label: 'Segments', fmt: v => <span className="text-xs">{v}</span> }, { key: 'n_fits', label: 'Fits', align: 'right', fmt: v => n(v) },
          { key: 'parallel_seconds', label: 'Parallel', align: 'right', fmt: secs }, { key: 'sequential_seconds_est', label: 'Sequential', align: 'right', fmt: secs },
          { key: 'speedup', label: 'Speed-up', align: 'right', fmt: v => `× ${n(v, 1)}` },
        ]} />
      </Card>
    </Page>
  );
}
