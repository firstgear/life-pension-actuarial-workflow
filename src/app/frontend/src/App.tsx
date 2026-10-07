import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import {
  Home as HomeIcon, Database, Table2, FlaskConical, Boxes, ShieldCheck, LineChart, Activity, ScrollText, Sparkles, Workflow, HeartPulse,
} from 'lucide-react';
import Home from './pages/Home';
import Ingestion from './pages/Ingestion';
import Mart from './pages/Mart';
import Assumptions from './pages/Assumptions';
import Factory from './pages/Factory';
import Deployment from './pages/Deployment';
import Projection from './pages/Projection';
import Stochastic from './pages/Stochastic';
import Governance from './pages/Governance';
import Genie from './pages/Genie';
import Orchestration from './pages/Orchestration';

export const NAV = [
  { to: '/', label: 'Home', icon: HomeIcon },
  { to: '/ingestion', n: 1, label: 'Data Ingestion', icon: Database },
  { to: '/mart', n: 2, label: 'Experience Mart', icon: Table2 },
  { to: '/assumptions', n: 3, label: 'Assumption Models', icon: FlaskConical },
  { to: '/factory', n: 4, label: 'Model Factory', icon: Boxes },
  { to: '/deployment', n: 5, label: 'Deployment & Approval', icon: ShieldCheck },
  { to: '/projection', n: 6, label: 'Projection Engine', icon: LineChart },
  { to: '/stochastic', n: 7, label: 'Stochastic & Stress', icon: Activity },
  { to: '/governance', n: 8, label: 'Model Governance', icon: ScrollText },
  { to: '/genie', n: 9, label: 'Actuarial AI (Genie)', icon: Sparkles },
  { to: '/orchestration', n: 10, label: 'Orchestration & Compute', icon: Workflow },
];

function Sidebar() {
  const { pathname } = useLocation();
  return (
    <aside className="w-64 bg-navy text-white min-h-screen flex flex-col shrink-0 sticky top-0 h-screen">
      <Link to="/" className="px-5 py-5 flex items-center gap-3 border-b border-white/10 hover:opacity-90">
        <HeartPulse className="w-7 h-7 text-brand" />
        <div>
          <div className="text-sm font-semibold leading-tight">Life &amp; Pension<br />Actuarial Workbench</div>
          <div className="text-[10px] text-slate-400 mt-0.5">Generic Life & Pension Insurer · synthetic data</div>
        </div>
      </Link>
      <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">
        {NAV.map(({ to, n, label, icon: Icon }) => {
          const active = to === '/' ? pathname === '/' : pathname.startsWith(to);
          return (
            <Link key={to} to={to} className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${active ? 'bg-white/10 text-white font-medium' : 'text-slate-400 hover:text-white hover:bg-white/5'}`}>
              <Icon className={`w-4 h-4 shrink-0 ${active ? 'text-brand' : ''}`} />
              {n && <span className="text-[10px] text-slate-500 w-4">{n}</span>}{label}
            </Link>
          );
        })}
      </nav>
      <div className="px-5 py-3 border-t border-white/10 text-[10px] text-slate-400 space-y-1">
        <span className="inline-block px-2 py-0.5 rounded-full bg-amber-400/20 text-amber-300 font-semibold">SYNTHETIC DATA</span>
        <div>Demo on Databricks — illustrative, not production results.</div>
      </div>
    </aside>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-100 flex text-slate-800">
        <Sidebar />
        <main className="flex-1 min-w-0">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/ingestion" element={<Ingestion />} />
            <Route path="/mart" element={<Mart />} />
            <Route path="/assumptions" element={<Assumptions />} />
            <Route path="/factory" element={<Factory />} />
            <Route path="/deployment" element={<Deployment />} />
            <Route path="/projection" element={<Projection />} />
            <Route path="/stochastic" element={<Stochastic />} />
            <Route path="/governance" element={<Governance />} />
            <Route path="/genie" element={<Genie />} />
            <Route path="/orchestration" element={<Orchestration />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
