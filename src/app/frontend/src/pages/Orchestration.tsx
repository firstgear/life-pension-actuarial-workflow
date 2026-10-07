import { useState } from 'react';
import { Play, Pause, PlayCircle } from 'lucide-react';
import { Page, Card, Table, Badge, Button, RunTracker, useApi, Code, Ext, statusTone, ErrorBox } from '../components/ui';
import { post } from '../lib/api';
import { n, ts } from '../lib/format';

const TRIGGER_TONE: Record<string, string> = {
  'file arrival': 'blue', 'table update': 'violet', 'model update': 'brand', scheduled: 'amber', continuous: 'green', manual: 'slate',
};

const SPOT_YAML = `# docs/illustrative/x_ray_spot.yml — classic ML runtime, spot workers, Ray-on-Spark
job_clusters:
  - job_cluster_key: ray_spot
    new_cluster:
      spark_version: 16.4.x-cpu-ml-scala2.12
      node_type_id: m6i.2xlarge
      autoscale: { min_workers: 2, max_workers: 16 }
      aws_attributes:
        availability: SPOT_WITH_FALLBACK     # spot workers, on-demand fallback
        first_on_demand: 1                   # driver stays on-demand
tasks:
  - task_key: ray_factory
    job_cluster_key: ray_spot
    notebook_task: { notebook_path: ../src/notebooks/04b_model_factory_ray.py }
    libraries: [ { pypi: { package: "ray[default]>=2.37" } } ]`;

const COMPUTE = [
  { c: 'Serverless jobs', used: 'Used now', what: 'Every notebook job in this demo: mart, GLMs, factory, projection, stochastic', why: 'No clusters to size or patch; starts in seconds; pay per run' },
  { c: 'Serverless pipelines', used: 'Used now', what: 'Extract bronze → silver with expectations', why: 'Incremental, DQ metrics built in' },
  { c: 'Serverless SQL warehouse', used: 'Used now', what: 'This app, Genie, BI', why: 'Concurrency for many analysts' },
  { c: 'Serverless GPU', used: 'Next step', what: 'Nested stochastic / PyTorch or JAX kernels (the torch backend)', why: 'Same array code, 10–100× on vectorised Monte Carlo' },
  { c: 'Classic + spot + Ray', used: 'Illustrative', what: 'Ray-on-Spark for Python logic parallelism (factory, projection engine)', why: 'Cheapest burst capacity for long, fault-tolerant runs' },
  { c: 'External engine (Batch/AKS)', used: 'Integrate', what: 'Existing in-house valuation engine called as a job task', why: 'Keep the engine, gain orchestration, lineage, audit' },
];

const PATTERNS = [
  ['Orchestrate an existing engine', 'A job task submits the in-house engine (or Prophet / ResQ / Igloo batch) on its own compute; inputs and results land in Delta.'],
  ['Feed and consume via Delta', 'Governed model points and assumptions exported to the engine; results ingested back for A/E, reconciliation and Genie.'],
  ['Shadow / parallel run', 'Run the Databricks calculation next to the incumbent and compare statistically before switching anything.'],
  ['Lift a kernel', 'Move a single Python-able kernel (e.g. GLM estimation) to Spark/Ray; leave the rest where it is.'],
];

const POC = [
  ['End-to-end runtime', 'extract → approved assumptions → BEL'], ['ETL runtime', 'Experience-data preparation vs SQL Server today'],
  ['Estimation runtime', 'single GLM fit and the full GLM suite'], ['Concurrency', 'how many actuaries / runs at once'],
  ['Peak compute & burst scale', 'cores at peak, time to scale'], ['Cost per run', 'DBU + cloud vs today\'s cost per run'],
  ['Statistical equivalence', 'coefficients / BEL match the incumbent within tolerance'], ['Reproducibility', 're-run any result from data + code + model version'],
  ['Operational complexity', 'people and steps to run a valuation cycle'],
];


export default function Orchestration() {
  const { data, error, reload } = useApi<any[]>('/orchestration/jobs', 15000);
  const [run, setRun] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const act = async (fn: () => Promise<any>) => { setErr(null); try { const r = await fn(); if (r?.run_id) setRun(r); reload(); } catch (e: any) { setErr(e.message); } };
  return (
    <Page section="10 · Orchestration & Compute" title="Every trigger type, one platform"
      subtitle="Every calculation is a job: versioned in the Asset Bundle, triggered by events (a file lands, a table changes, a model is promoted), on a schedule, continuously or on demand, with retries, dependencies and full run history."
      capability="Lakeflow Jobs (file arrival · table update · model update · scheduled · continuous · manual) · Databricks Asset Bundles (everything here is code) · serverless compute">
      <ErrorBox error={error || err} />
      {run && <RunTracker run={run} label="Job run" />}
      <Card title="Job & trigger catalogue (live from the Jobs API)">
        <Table rows={data} cols={[
          { key: 'name', label: 'Job', fmt: (v, r) => <Ext href={r.url}>{String(v).replace('Actuarial Workbench · ', '')}</Ext> },
          { key: 'trigger_type', label: 'Trigger', fmt: (v, r) => <span><Badge tone={TRIGGER_TONE[v] ?? 'slate'}>{v}</Badge>{r.pause_status === 'PAUSED' && <Badge tone="slate">paused</Badge>}</span> },
          { key: 'trigger_detail', label: 'Condition', fmt: v => <span className="text-xs text-slate-600 font-mono">{v}</span> },
          { key: 'tasks', label: 'Tasks', fmt: v => <span className="text-xs">{(v ?? []).join(' → ')}</span> },
          { key: 'last_run', label: 'Last run', fmt: v => v ? <span className="text-xs"><Badge tone={statusTone(v.state)}>{v.state}</Badge> {ts(v.start_time)} <span className="text-slate-400">{v.trigger?.toLowerCase()}</span></span> : '—' },
          { key: 'key', label: '', fmt: (k, r) => (
            <div className="flex gap-1">
              {r.trigger_type !== 'continuous' && <Button small variant="secondary" onClick={() => act(() => post(`/orchestration/jobs/${k}/run`))}><Play className="w-3 h-3" />Run</Button>}
              {(r.trigger_type === 'continuous' || r.trigger_type === 'scheduled') && (
                <Button small variant="secondary" onClick={() => act(() => post(`/orchestration/jobs/${k}/pause`, { paused: r.pause_status !== 'PAUSED' }))}>
                  {r.pause_status === 'PAUSED' ? <><PlayCircle className="w-3 h-3" />Unpause</> : <><Pause className="w-3 h-3" />Pause</>}</Button>)}
            </div>) },
        ]} />
        <div className="text-xs text-slate-500 mt-2">“Model update”: the native trigger on a UC model alias is in preview; here the @champion move is published to <code>model_champion_events</code> and picked up by a table-update trigger, with the same behaviour.</div>
      </Card>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Compute — the right engine per workload">
          <Table rows={COMPUTE} cols={[
            { key: 'c', label: 'Compute' }, { key: 'used', label: 'In this demo', fmt: v => <Badge tone={v === 'Used now' ? 'green' : v === 'Integrate' ? 'blue' : 'amber'}>{v}</Badge> },
            { key: 'what', label: 'For', fmt: v => <span className="text-xs">{v}</span> }, { key: 'why', label: 'Why', fmt: v => <span className="text-xs text-slate-600">{v}</span> },
          ]} />
        </Card>
        <Card title="Spot + Ray — the config (illustrative; this workspace is serverless-only)"><Code>{SPOT_YAML}</Code></Card>
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Integrate, don't rip out — patterns with existing engines">
          <div className="space-y-2">{PATTERNS.map(([t, d]) => <div key={t} className="text-sm"><b>{t}.</b> <span className="text-slate-600">{d}</span></div>)}</div>
          <div className="text-xs text-slate-500 mt-3">Decision rule: Python you want to parallelise → Spark/Ray on Databricks. An existing binary/runtime or specialised VM capacity → keep it on Batch/AKS and orchestrate it from a job.</div>
        </Card>
        <Card title="Proposed PoC — two tracks, same metrics">
          <div className="grid grid-cols-2 gap-3 text-xs mb-3">
            <div className="rounded-lg border p-2"><b>A.</b> data prep on Databricks → external engine → results back → compare / validate / audit</div>
            <div className="rounded-lg border border-brand/40 p-2"><b>B.</b> data prep on Databricks → Databricks compute → results → compare / validate / audit</div>
          </div>
          <Table dense rows={POC.map(([m, d]) => ({ m, d }))} cols={[{ key: 'm', label: 'Metric' }, { key: 'd', label: 'Measured as', fmt: v => <span className="text-xs text-slate-600">{v}</span> }]} />
        </Card>
      </div>
    </Page>
  );
}
