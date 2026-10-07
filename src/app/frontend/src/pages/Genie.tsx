import { Page, Card, useApi, Ext } from '../components/ui';
import GenieChat from '../components/GenieChat';

const QUESTIONS = [
  'What is the actual vs expected mortality by scheme for the champion model?',
  'Which segments have A/E above 1.1?',
  'How did total BEL change between the last two projection runs and why?',
  'Show deaths and exposure by age band and sex for 2020 onwards',
  'Which extracts are pending approval and how many rows were quarantined?',
  'Who approved the current mortality champion and when?',
  'What is the longevity stress impact on BEL by scheme?',
  'Compare lapse rates for average-rate vs market-rate products since 2022',
];

export default function Genie() {
  const { data: cfg } = useApi<any>('/config');
  return (
    <Page section="9 · Actuarial AI" title="Ask the book — self-service, governed, explained"
      subtitle="Actuaries, finance and risk ask questions in plain English over the governed experience mart and valuation results. Genie shows its reasoning and the SQL, and respects Unity Catalog permissions."
      capability="AI/BI Genie space over Unity Catalog tables · actuarial instructions (A/E definition, exposure-weighted rates, EUR) · SQL warehouse (serverless) · same permissions as everything else">
      {cfg?.genie_space_id ? (
        <GenieChat spaceId={cfg.genie_space_id} fullScreenUrl={cfg.genie_url} suggestions={QUESTIONS} height={620} variant="card"
          title="Actuarial Genie" subtitle="Experience, assumptions, valuation results, approvals" />
      ) : (
        <Card title="Genie space not configured yet">
          <p className="text-sm text-slate-600">Set <code>GENIE_SPACE_ID</code> in <code>app.yaml</code> (created by <code>scripts/deploy.sh</code>) and redeploy. Questions to try:</p>
          <ul className="list-disc pl-5 text-sm mt-2 space-y-1">{QUESTIONS.map(q => <li key={q}>{q}</li>)}</ul>
          <div className="mt-3 text-sm"><Ext href={cfg?.catalog_url}>Browse the tables in Catalog Explorer</Ext></div>
        </Card>
      )}
    </Page>
  );
}
