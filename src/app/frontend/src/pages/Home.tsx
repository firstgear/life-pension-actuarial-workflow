import { Link } from 'react-router-dom';
import { ArrowRight, Server, Cloud } from 'lucide-react';
import { Card, Kpi, Badge, useApi, Table } from '../components/ui';
import { NAV } from '../App';
import { eur, n, secs, ts } from '../lib/format';

const SPINE: Record<string, string> = {
  '/ingestion': 'policy admin extracts land, DQ gate, actuary approves',
  '/mart': 'Spark builds the GLM-ready exposure mart',
  '/assumptions': 'Mortality, disability and lapse models in MLflow',
  '/factory': 'Thousands of segment GLMs in parallel',
  '/deployment': 'Four-eyes approval moves @champion',
  '/projection': 'BEL re-projected automatically',
  '/stochastic': 'Nested stochastic + Solvency II-style stresses',
  '/governance': 'Every number traceable: data + code + model',
  '/genie': 'Self-service questions in plain English',
  '/orchestration': 'Event, schedule, continuous and manual triggers',
};

export default function Home() {
  const { data } = useApi<any>('/overview', 30000);
  const b = data?.book ?? {}, e = data?.experience ?? {}, bel = data?.bel ?? {}, p = data?.pending ?? {}, f = data?.factory ?? {};
  return (
    <div className="p-8 max-w-[1400px] mx-auto space-y-6">
      <div className="rounded-2xl bg-navy text-white p-8 relative overflow-hidden">
        <div className="text-xs font-semibold uppercase tracking-wider text-brand">A day in the life of a life &amp; pension actuary — on Databricks</div>
        <h1 className="text-3xl font-semibold mt-2 max-w-4xl">From policy extract to approved assumption to re-projected liabilities — on one governed platform.</h1>
        <p className="mt-4 text-slate-300 max-w-4xl">
          Databricks orchestrates actuarial workloads and scales the heavy calculations — it does some of the maths, not all,
          and integrates with your existing engines. Lift what you do today onto one governed platform, one low-risk step at a time.
        </p>
        <div className="mt-4"><Badge tone="amber">All data synthetic — methods real, numbers illustrative</Badge></div>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <Card title={<span className="flex items-center gap-2"><Server className="w-4 h-4" />Today</span>}>
          <ul className="text-sm text-slate-700 space-y-1.5 list-disc pl-5">
            <li>In-house reserving and pricing engines; statistical estimation in R on SQL Server data</li>
            <li>Fixed on-premises hardware, up for renewal</li>
            <li>GLM estimation runs overnight; capacity is sized for the peak and idle the rest of the time</li>
            <li>Lineage, approvals and reproducibility handled by process, not by the platform</li>
          </ul>
        </Card>
        <Card title={<span className="flex items-center gap-2"><Cloud className="w-4 h-4 text-brand" />With Databricks</span>}>
          <ul className="text-sm text-slate-700 space-y-1.5 list-disc pl-5">
            <li><b>Spark</b> for the data plane (ETL, joins, exposure aggregation); <b>Ray</b> / <b>GPU</b> for Python logic at scale</li>
            <li><b>Jobs</b> orchestrate it all: table-update, model-update, scheduled, continuous and manual triggers (file-arrival where file events are enabled)</li>
            <li><b>MLflow + Unity Catalog</b>: every model versioned, approved and traceable to its data</li>
            <li><b>Genie</b>: self-service questions over the governed results; existing engines stay and plug in</li>
          </ul>
        </Card>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-6 gap-4">
        <Kpi label="Policies (sample book)" value={n(b.policies)} sub={`${n(b.in_force)} in force`} />
        <Kpi label="Life-years observed" value={n(e.life_years)} sub={e.first_year ? `${e.first_year}–${e.last_year}` : 'run job 02'} />
        <Kpi label="Deaths" value={n(e.deaths)} sub={e.ae_std ? `A/E vs standard table ${Number(e.ae_std).toFixed(3)}` : undefined} />
        <Kpi label="Best-estimate liability" value={eur(bel.total_bel_eur)} sub={bel.model_version ? `mortality model v${bel.model_version} · ${secs(bel.seconds)}` : 'run job 05'} accent />
        <Kpi label="Model factory" value={f.n_fits ? `${n(f.n_fits)} GLMs` : '—'} sub={f.speedup ? `${secs(f.parallel_seconds)} · ×${Number(f.speedup).toFixed(0)} vs sequential` : 'run job 04'} />
        <Kpi label="Waiting for approval" value={`${n(p.pending_extracts ?? 0)} / ${n(p.pending_models ?? 0)}`} sub="extracts / models" />
      </div>

      <Card title="The workflow — click a step">
        <div className="grid md:grid-cols-5 gap-3">
          {NAV.filter(x => x.n).map(({ to, n: num, label, icon: Icon }) => (
            <Link key={to} to={to} className="group rounded-lg border border-slate-200 p-3 hover:border-brand hover:shadow-sm transition">
              <div className="flex items-center gap-2 text-sm font-medium text-slate-900"><Icon className="w-4 h-4 text-brand" />{num}. {label}</div>
              <div className="text-xs text-slate-500 mt-1">{SPINE[to]}</div>
              <ArrowRight className="w-3.5 h-3.5 mt-2 text-slate-300 group-hover:text-brand" />
            </Link>
          ))}
        </div>
      </Card>

      <div className="grid lg:grid-cols-3 gap-4">
        <Card title="Current champions (Unity Catalog @champion)">
          <Table rows={Object.entries(data?.champions ?? {}).map(([m, v]) => ({ m, v }))}
            cols={[{ key: 'm', label: 'Model' }, { key: 'v', label: 'Version', align: 'right', fmt: v => <Badge tone="green">v{v}</Badge> }]} />
        </Card>
        <Card title="Latest activity (audit log)" className="lg:col-span-2">
          <Table dense rows={data?.activity} cols={[
            { key: 'event_ts', label: 'When', fmt: ts }, { key: 'event_type', label: 'Event', fmt: v => <Badge>{v}</Badge> },
            { key: 'entity_id', label: 'Entity', fmt: v => <span className="text-xs">{String(v).split('.').pop()}</span> },
            { key: 'entity_version', label: 'Ver.' }, { key: 'actor', label: 'Actor', fmt: v => <span className="text-xs">{v}</span> },
          ]} />
        </Card>
      </div>
    </div>
  );
}
