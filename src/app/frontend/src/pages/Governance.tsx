import { useState } from 'react';
import { Page, Card, Table, Badge, useApi, statusTone } from '../components/ui';
import { Stat } from '../components/charts';
import { n, ts } from '../lib/format';

export default function Governance() {
  const [filter, setFilter] = useState('');
  const audit = useApi<any[]>(`/governance/audit${filter ? `?event_type=${filter}` : ''}`, 15000);
  const rep = useApi<any>('/governance/reproducibility', 30000);
  const ev = rep.data?.champion_events ?? [];
  const currentMort = ev.find((e: any) => e.model_name === 'mortality_glm');
  const v = (rep.data?.versions ?? []).find((x: any) => x.model_name === 'mortality_glm' && String(x.model_version) === String(currentMort?.new_version));
  const ap = (rep.data?.approvals ?? []).find((a: any) => a.model_name === 'mortality_glm' && a.status === 'APPROVED' && String(a.model_version) === String(currentMort?.new_version));
  const types = ['', 'EXTRACT_RECEIVED', 'EXTRACT_APPROVED', 'MART_REBUILT', 'MODEL_REGISTERED', 'MODEL_PROPOSED', 'MODEL_PROMOTED', 'PROJECTION_RUN', 'FACTORY_RUN', 'STOCHASTIC_RUN', 'STRESS_RUN'];
  return (
    <Page section="8 · Model Governance" title="Every number traceable — data, code, model, decision"
      subtitle="The question a regulator or auditor asks: which data, which code, which model version, and who approved it? Here the platform answers it, so nobody has to rebuild it from emails and file shares."
      capability="Unity Catalog lineage, permissions and audit · Delta time travel (data version) · MLflow run (code, parameters, metrics, artefacts) · approval and champion-event tables · append-only audit log">
      <div className="grid lg:grid-cols-3 gap-4">
        <Card title="Reproducibility tuple — current mortality champion">
          <Stat k="Model" v={`mortality_glm v${currentMort?.new_version ?? '—'}`} />
          <Stat k="Experience mart (Delta version)" v={v?.mart_table_version ?? '—'} />
          <Stat k="Code version (actuarial_lib)" v={v?.code_version ?? '—'} />
          <Stat k="MLflow run" v={<span className="font-mono text-xs">{v?.run_id?.slice(0, 12) ?? '—'}</span>} />
          <Stat k="Specification" v={<span className="text-xs">{v?.params?.label ?? '—'}</span>} />
          <Stat k="Approved by" v={<span className="text-xs">{ap?.reviewed_by ?? currentMort?.actor ?? '—'}</span>} />
          <Stat k="Promoted" v={ts(currentMort?.event_ts)} />
        </Card>
        <Card title="Model card — mortality assumption" className="lg:col-span-2">
          <div className="text-sm text-slate-700 space-y-2">
            <p><b>Purpose.</b> Best-estimate mortality for valuation (BEL) and pricing of pension and life annuity products.</p>
            <p><b>Method.</b> Poisson GLM, log link, offset log(central exposure); Gompertz age term, calendar-year improvement trend, categorical factors for sex, scheme, product, salary band and policy duration. Estimated in statsmodels.</p>
            <p><b>Data.</b> Approved experience data 2015 onward (synthetic in this demo), aggregated in <code>experience_mart</code>; extracts gated by DQ expectations and actuarial sign-off.</p>
            <p><b>Validation.</b> A/E by age band, sex, scheme, salary band and period vs champion and standard table; deviance/AIC vs the incumbent; confidence intervals on every relativity; segment bootstrap from the model factory.</p>
            <p><b>Limitations.</b> Main-effects model; no cohort term; improvement assumed linear on the log scale over the observation window.</p>
            <p><b>Controls.</b> Four-eyes promotion, automatic re-projection on promotion, rollback to @previous_champion, full audit trail.</p>
          </div>
        </Card>
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Champion history (drives the projection trigger)">
          <Table dense rows={ev} cols={[
            { key: 'event_ts', label: 'When', fmt: ts }, { key: 'model_name', label: 'Model' }, { key: 'new_version', label: 'New', fmt: v => <Badge tone="green">v{v}</Badge> },
            { key: 'previous_version', label: 'Previous', fmt: v => v ? `v${v}` : '—' }, { key: 'actor', label: 'By', fmt: v => <span className="text-xs">{v}</span> },
          ]} />
        </Card>
        <Card title="Model versions — data + code + run">
          <Table dense rows={rep.data?.versions} cols={[
            { key: 'model_name', label: 'Model' }, { key: 'model_version', label: 'Ver.' }, { key: 'trained_at', label: 'Trained', fmt: ts },
            { key: 'mart_table_version', label: 'Mart v.' }, { key: 'code_version', label: 'Code' },
            { key: 'metrics', label: 'AIC', align: 'right', fmt: v => n(v?.aic) },
          ]} />
        </Card>
      </div>
      <Card title="Audit log" right={
        <select value={filter} onChange={e => setFilter(e.target.value)} className="border border-slate-300 rounded-lg px-2 py-1 text-xs">
          {types.map(t => <option key={t} value={t}>{t || 'all events'}</option>)}</select>}>
        <Table dense max={100} rows={audit.data} cols={[
          { key: 'event_ts', label: 'When', fmt: ts }, { key: 'event_type', label: 'Event', fmt: v => <Badge tone={statusTone(v?.includes('REJECT') ? 'REJECTED' : v?.includes('APPROV') || v?.includes('PROMOT') ? 'APPROVED' : '')}>{v}</Badge> },
          { key: 'entity_id', label: 'Entity', fmt: v => <span className="text-xs">{String(v).split('.').pop()}</span> }, { key: 'entity_version', label: 'Ver.' },
          { key: 'actor', label: 'Actor', fmt: v => <span className="text-xs">{v}</span> }, { key: 'source', label: 'Source', fmt: v => <span className="text-xs">{v}</span> },
          { key: 'details', label: 'Details', fmt: v => <span className="text-xs text-slate-500 font-mono">{String(v ?? '').slice(0, 90)}</span> },
        ]} />
      </Card>
    </Page>
  );
}
