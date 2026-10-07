import { useState } from 'react';
import { Play } from 'lucide-react';
import { Page, Card, Kpi, Table, Button, RunTracker, useApi, Code, ErrorBox } from '../components/ui';
import { Fan, Histogram, HBar } from '../components/charts';
import { post } from '../lib/api';
import { eur, n, pct, secs, ts } from '../lib/format';

const TREE = `outer real-world scenario  (ESG short-rate path × longevity-trend shock)
├── liability portfolio  → re-discounted on the path, mortality × shock
└── inner risk-neutral Monte Carlo  → cost of the interest-rate guarantee
                                      on average-rate (with-profits) savings`;

export default function Stochastic() {
  const { data, reload } = useApi<any>('/stochastic/summary', 20000);
  const [outer, setOuter] = useState(1000), [inner, setInner] = useState(500000), [backend, setBackend] = useState('numpy');
  const [run, setRun] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const r = data?.runs?.[0];
  const go = async () => { setErr(null); try { setRun(await post('/stochastic/run', { n_outer: outer, n_inner: inner, backend })); } catch (e: any) { setErr(e.message); } };
  return (
    <Page section="7 · Stochastic & Stress" title="Nested stochastic valuation and Solvency II-style stresses"
      subtitle="Every outer scenario is independent, so the work fans out. The same array kernel runs in NumPy, Numba (JIT CPU) or PyTorch (GPU when attached)."
      capability="Spark applyInPandas over scenario chunks on serverless · NumPy / Numba / PyTorch kernels · serverless GPU and Ray as the next step for heavier nested runs · results in Delta">
      <ErrorBox error={err} />
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-4">
        <Kpi label="Mean liability (BEL + TVOG)" value={eur(r?.mean_liability_eur)} accent />
        <Kpi label="99.5th percentile" value={eur(r?.p995_eur)} sub={`p95 ${eur(r?.p95_eur)}`} />
        <Kpi label="SCR proxy (99.5% − mean)" value={eur(r?.scr_proxy_eur)} sub="illustrative, not a regulatory SCR" />
        <Kpi label="Time value of guarantees" value={eur(r?.mean_tvog_eur)} sub="mean over outer scenarios" />
        <Kpi label="Paths simulated" value={r ? n(r.n_outer * r.n_inner) : '—'} sub={r ? `${n(r.n_outer)} outer × ${n(r.n_inner)} inner · ${r.backend}` : 'run job 06'} />
        <Kpi label="Wall-clock" value={secs(r?.parallel_seconds)} sub={r ? `${secs(r.sequential_seconds_est)} of task time` : undefined} />
      </div>
      <div className="grid lg:grid-cols-3 gap-4">
        <Card title="Distribution of total liability across outer scenarios" className="lg:col-span-2">
          <Histogram bins={data?.histogram ?? []} xFmt={v => eur(v).replace(' EUR', '')}
            markers={r ? [{ x: r.mean_liability_eur, label: 'mean', color: '#1B3139' }, { x: r.p995_eur, label: '99.5%' }] : []} />
        </Card>
        <Card title="Run the nested simulation">
          <div className="space-y-3 text-sm">
            <label className="block">Outer scenarios
              <select value={outer} onChange={e => setOuter(Number(e.target.value))} className="mt-1 w-full border border-slate-300 rounded-lg px-2 py-1.5">
                {[100, 250, 500, 1000].map(v => <option key={v} value={v}>{v}</option>)}</select></label>
            <label className="block">Inner paths per outer scenario
              <select value={inner} onChange={e => setInner(Number(e.target.value))} className="mt-1 w-full border border-slate-300 rounded-lg px-2 py-1.5">
                {[20000, 100000, 500000, 1000000].map(v => <option key={v} value={v}>{n(v)}</option>)}</select></label>
            <label className="block">Kernel
              <select value={backend} onChange={e => setBackend(e.target.value)} className="mt-1 w-full border border-slate-300 rounded-lg px-2 py-1.5">
                <option value="numpy">NumPy (reference)</option><option value="numba">Numba (JIT, CPU)</option></select></label>
            <Button onClick={go}><Play className="w-4 h-4" />Run stochastic & stress</Button>
          </div>
          {run && <div className="mt-3"><RunTracker run={run} label="Stochastic & stress (job 06)" onDone={reload} /></div>}
        </Card>
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Stress tests — change in BEL (champion model)">
          <HBar labelWidth={210} fmt={v => eur(v)} data={(data?.stress ?? []).filter((s: any) => s.stress !== 'Base').map((s: any) => ({ label: s.stress, value: s.delta_eur, tone: s.delta_eur > 0 ? '#FF3621' : '#00A972' }))} />
          <Table dense rows={data?.stress} cols={[
            { key: 'stress', label: 'Stress' }, { key: 'bel_eur', label: 'BEL', align: 'right', fmt: eur },
            { key: 'delta_eur', label: 'Δ BEL', align: 'right', fmt: eur }, { key: 'delta_pct', label: 'Δ %', align: 'right', fmt: v => pct(v, 2) },
          ]} />
        </Card>
        <div className="space-y-4">
          <Card title="Economic scenario set — short rate, percentiles by projection year">
            <Fan xLabel="projection year" rows={(data?.rate_fan ?? []).map((x: any) => ({ x: x.projection_year, ...x }))} />
          </Card>
          <Card title="Nested structure"><Code>{TREE}</Code></Card>
        </div>
      </div>
      <Card title="Stochastic runs">
        <Table dense rows={data?.runs} cols={[
          { key: 'run_ts', label: 'When', fmt: ts }, { key: 'n_outer', label: 'Outer', align: 'right', fmt: v => n(v) }, { key: 'n_inner', label: 'Inner', align: 'right', fmt: v => n(v) },
          { key: 'backend', label: 'Kernel' }, { key: 'mean_liability_eur', label: 'Mean', align: 'right', fmt: eur }, { key: 'p995_eur', label: '99.5%', align: 'right', fmt: eur },
          { key: 'parallel_seconds', label: 'Wall-clock', align: 'right', fmt: secs }, { key: 'sequential_seconds_est', label: 'Task time', align: 'right', fmt: secs },
        ]} />
      </Card>
    </Page>
  );
}
