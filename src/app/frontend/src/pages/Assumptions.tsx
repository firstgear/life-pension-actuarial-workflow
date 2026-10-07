import { useState } from 'react';
import { Page, Card, Kpi, Table, Tabs, Badge, Button, RunTracker, useApi, Ext } from '../components/ui';
import { HBar, Lines, PALETTE, Stat } from '../components/charts';
import { post } from '../lib/api';
import { n, pct, ts } from '../lib/format';

const FACTOR_LABEL: Record<string, string> = {
  sex: 'Sex', scheme: 'Scheme', product_type: 'Product type', salary_band: 'Salary band', duration_band: 'Policy duration',
  employer_sector: 'Employer sector',
};

function Relativities({ rows }: { rows: any[] }) {
  const factors = [...new Set(rows.filter(r => r.level !== 'per unit').map(r => r.factor))];
  return (
    <div className="grid md:grid-cols-2 gap-x-8 gap-y-4">
      {factors.map(f => (
        <div key={f}>
          <div className="text-xs font-semibold text-slate-600 uppercase mb-1">{FACTOR_LABEL[f] ?? f}</div>
          <HBar refLine={1} labelWidth={150} data={rows.filter(r => r.factor === f).map(r => ({
            label: `${r.level}${r.is_reference ? ' (ref)' : ''}`, value: r.relativity, lo: r.is_reference ? undefined : r.ci_low, hi: r.is_reference ? undefined : r.ci_high,
            tone: r.is_reference ? '#94a3b8' : r.relativity > 1 ? '#1B3139' : '#2E86AB' }))} />
        </div>
      ))}
    </div>
  );
}

function Mortality() {
  const { data } = useApi<any>('/assumptions/mortality');
  const rel = data?.relativities ?? [];
  const age = rel.find((r: any) => r.factor === 'age'), yr = rel.find((r: any) => r.factor === 'year_c');
  const latest = data?.versions?.[0];
  const m = latest?.metrics ?? {};
  const aeDims = ['age_band', 'sex', 'scheme', 'salary_band', 'period'];
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-4">
        <Kpi label="Latest version" value={latest ? `v${latest.model_version}` : '—'} sub={latest?.params?.label} />
        <Kpi label="Age slope" value={age ? `+${pct(age.relativity - 1)} / yr` : '—'} sub="Gompertz: mortality per year of age" />
        <Kpi label="Mortality improvement" value={yr ? `${pct(1 - yr.relativity, 2)} p.a.` : '—'} sub="calendar-year trend" />
        <Kpi label="Pseudo R²" value={n(m.pseudo_r2, 3)} sub={`deviance ${n(m.deviance)}`} />
        <Kpi label="AIC" value={n(m.aic)} sub={`dispersion ${n(m.dispersion, 2)}`} />
        <Kpi label="Overall A/E" value={n(m.ae_overall, 3)} sub={`${n(m.events)} deaths · ${n(m.exposure)} life-years`} />
      </div>
      <Card title={`Relativities with 95% confidence intervals (v${latest?.model_version ?? '—'}) — read like a rating table`}
        right={<Ext href={data?.links?.model}>model in Unity Catalog</Ext>}>
        <div className="text-xs text-slate-500 mb-3 font-mono">log E[deaths] = log(exposure) + β₀ + β·age + γ·(year−2020) + sex + scheme + product + salary + duration</div>
        {rel.length ? <Relativities rows={rel} /> : <div className="text-sm text-slate-500">Run job 03 to estimate.</div>}
      </Card>
      <Card title="Actual vs expected by segment — champion vs challenger vs standard table">
        <Table dense max={60} rows={(data?.ae ?? []).filter((r: any) => aeDims.includes(r.dimension))} cols={[
          { key: 'dimension', label: 'Dimension' }, { key: 'level', label: 'Level' }, { key: 'deaths', label: 'Deaths', align: 'right', fmt: v => n(v) },
          { key: 'ae_champion', label: 'A/E champion', align: 'right', fmt: v => <AE v={v} /> },
          { key: 'ae_challenger', label: 'A/E challenger', align: 'right', fmt: v => <AE v={v} /> },
          { key: 'ae_standard_table', label: 'A/E standard table', align: 'right', fmt: v => <AE v={v} /> },
        ]} />
      </Card>
      <Card title="All versions (MLflow runs registered in Unity Catalog)">
        <Table dense rows={data?.versions} cols={[
          { key: 'model_version', label: 'Version', fmt: v => <Badge>v{v}</Badge> }, { key: 'params', label: 'Specification', fmt: v => v?.label },
          { key: 'metrics', label: 'AIC', align: 'right', fmt: v => n(v?.aic) }, { key: 'trained_at', label: 'Trained', fmt: ts },
          { key: 'mart_table_version', label: 'Mart version', align: 'right' }, { key: 'code_version', label: 'Code' },
          { key: 'run_id', label: 'MLflow run', fmt: v => <span className="text-xs font-mono">{String(v).slice(0, 8)}</span> },
        ]} />
      </Card>
    </div>
  );
}

function AE({ v }: { v: any }) {
  if (v == null) return <>—</>;
  const x = Number(v), off = Math.abs(x - 1);
  return <span className={off > 0.1 ? 'text-red-700 font-semibold' : off > 0.05 ? 'text-amber-700' : 'text-emerald-700'}>{x.toFixed(3)}</span>;
}

function Disability() {
  const { data } = useApi<any>('/assumptions/disability');
  const km = data?.km ?? [];
  const dims = [...new Set(km.map((r: any) => r.dimension))] as string[];
  return (
    <div className="space-y-4">
      <div className="grid lg:grid-cols-2 gap-4">
        {dims.map(d => {
          const lv = [...new Set(km.filter((r: any) => r.dimension === d).map((r: any) => r.level))] as string[];
          return (
            <Card key={d} title={`Recovery — Kaplan-Meier: share still disabled, by ${d.replace(/_/g, ' ')}`}>
              <Lines yMin={0} yFmt={v => pct(v, 0)} xLabel="years since onset" step series={lv.map((l, i) => ({
                name: `${l} (median ${n(km.find((r: any) => r.dimension === d && r.level === l)?.median_years, 1)} y)`,
                color: PALETTE[i], points: km.filter((r: any) => r.dimension === d && r.level === l).map((r: any) => [r.years, r.still_disabled]) }))} />
            </Card>
          );
        })}
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Recovery — Cox proportional hazards (lifelines)">
          <Table dense rows={data?.hazard_ratios} cols={[
            { key: 'covariate', label: 'Covariate' }, { key: 'hazard_ratio', label: 'Hazard ratio', align: 'right', fmt: v => n(v, 3) },
            { key: 'ci_low', label: '95% CI', align: 'right', fmt: (v, r) => `${n(v, 2)} – ${n(r.ci_high, 2)}` }, { key: 'p_value', label: 'p', align: 'right', fmt: v => n(v, 4) },
          ]} />
          <div className="text-xs text-slate-500 mt-2">Concordance {n(data?.hazard_ratios?.[0]?.concordance, 3)}. HR &lt; 1 = slower recovery (older onset).</div>
        </Card>
        <Card title="Disability incidence — Poisson GLM relativities">
          <HBar refLine={1} labelWidth={150} data={(data?.incidence ?? []).filter((r: any) => r.level !== 'per unit').map((r: any) => ({
            label: `${r.factor}: ${r.level}`, value: r.relativity, lo: r.is_reference ? undefined : r.ci_low, hi: r.is_reference ? undefined : r.ci_high,
            tone: r.is_reference ? '#94a3b8' : '#1B3139' }))} />
        </Card>
      </div>
    </div>
  );
}

function Lapse() {
  const { data } = useApi<any>('/assumptions/lapse');
  const cmp = Object.fromEntries((data?.comparison ?? []).map((r: any) => [r.model, r]));
  const seg = (data?.segments ?? []).filter((r: any) => r.dimension === 'product_type+regime');
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Kpi label="GLM (champion) — Gini" value={n(cmp.glm?.gini, 3)} sub={`AUC ${n(cmp.glm?.auc, 3)} · log-loss ${n(cmp.glm?.log_loss, 4)}`} />
        <Kpi label="LightGBM (challenger) — Gini" value={n(cmp.lgbm?.gini, 3)} sub={`AUC ${n(cmp.lgbm?.auc, 3)} · log-loss ${n(cmp.lgbm?.log_loss, 4)}`} accent />
        <Kpi label="Lift" value={cmp.glm && cmp.lgbm ? `+${n((cmp.lgbm.gini - cmp.glm.gini) * 100, 1)} Gini pts` : '—'} sub="what the GLM is missing" />
        <Kpi label="Role" value="GLM stays champion" sub="GBM = insight & challenger, not a black box in the reserve" />
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Where the GLM is wrong: guaranteed products after the 2022 rate rise">
          <Table rows={seg} cols={[
            { key: 'segment', label: 'Segment' }, { key: 'n', label: 'Policy-years', align: 'right', fmt: v => n(v) },
            { key: 'actual', label: 'Actual', align: 'right', fmt: v => pct(v, 2) }, { key: 'glm', label: 'GLM', align: 'right', fmt: v => pct(v, 2) },
            { key: 'lgbm', label: 'LightGBM', align: 'right', fmt: v => pct(v, 2) },
          ]} />
          <div className="text-xs text-slate-500 mt-2">The finding feeds back into the GLM as a new factor (rate regime × product) — the actuary stays in control.</div>
        </Card>
        <Card title="LightGBM explainability — mean |SHAP|">
          <HBar fmt={v => v.toFixed(3)} labelWidth={130} data={(data?.importance ?? []).map((r: any) => ({ label: r.feature, value: r.mean_abs_shap, tone: '#FF3621' }))} />
        </Card>
      </div>
      <Card title="Best-estimate lapse assumptions used by the projection (2021+ experience)">
        <Table dense rows={data?.assumptions} cols={[
          { key: 'scheme', label: 'Scheme' }, { key: 'product_type', label: 'Product' }, { key: 'surrenders', label: 'Surrenders', align: 'right', fmt: v => n(v) },
          { key: 'exposure', label: 'Exposure', align: 'right', fmt: v => n(v) }, { key: 'lapse_rate', label: 'Lapse rate', align: 'right', fmt: v => pct(v, 2) },
        ]} />
      </Card>
    </div>
  );
}

export default function Assumptions() {
  const [tab, setTab] = useState('Mortality');
  const [run, setRun] = useState<any>(null);
  const { data: cfg } = useApi<any>('/config');
  return (
    <Page section="3 · Assumption Models" title="Mortality, disability and lapse — estimated, logged, registered"
      subtitle="statsmodels Poisson GLMs for mortality and disability incidence, lifelines survival models for recovery, logistic GLM vs LightGBM for lapse. Every fit is an MLflow run, registered in Unity Catalog as @challenger."
      capability="Serverless job (table-update trigger on experience_mart) · statsmodels · lifelines · LightGBM · MLflow tracking · Unity Catalog model registry with aliases"
      actions={<Button variant="secondary" onClick={async () => setRun(await post('/assumptions/retrain'))}>Re-estimate now</Button>}>
      {run && <RunTracker run={run} label="Assumption models (job 03)" />}
      <Tabs tabs={['Mortality', 'Disability', 'Lapse']} value={tab} onChange={setTab} />
      {tab === 'Mortality' && <Mortality />}
      {tab === 'Disability' && <Disability />}
      {tab === 'Lapse' && <Lapse />}
      <Card><Stat k="Where it lives" v={`${cfg?.catalog ?? '<catalog>'}.${cfg?.schema ?? '<schema>'} · mortality_glm, disability_incidence_glm, disability_recovery_cox, lapse_glm, lapse_lgbm`} /></Card>
    </Page>
  );
}
