import { Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './components/AppLayout.jsx';
import CopilotPanel from './components/CopilotPanel.jsx';
import Dashboard from './pages/Dashboard.jsx';
import RegulatoryFeed from './pages/RegulatoryFeed.jsx';
import RegulationRepository from './pages/RegulationRepository.jsx';
import Obligations from './pages/Obligations.jsx';
import PolicyMapping from './pages/PolicyMapping.jsx';
import GapAnalysis from './pages/GapAnalysis.jsx';
import PolicyDrafts from './pages/PolicyDrafts.jsx';
import Tasks from './pages/Tasks.jsx';
import Approvals from './pages/Approvals.jsx';
import Knowledge from './pages/Knowledge.jsx';
import AuditTrail from './pages/AuditTrail.jsx';
import RepositoryHealth from './pages/RepositoryHealth.jsx';
import Settings from './pages/Settings.jsx';
import DemoCockpit from './pages/DemoCockpit.jsx';

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/feed" element={<RegulatoryFeed />} />
        <Route path="/regulations" element={<RegulationRepository />} />
        <Route path="/regulations/:id" element={<RegulationRepository />} />
        <Route path="/obligations" element={<Obligations />} />
        <Route path="/mapping" element={<PolicyMapping />} />
        <Route path="/gaps" element={<GapAnalysis />} />
        <Route path="/drafts" element={<PolicyDrafts />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/approvals" element={<Approvals />} />
        <Route path="/knowledge" element={<Knowledge />} />
        <Route path="/audit" element={<AuditTrail />} />
        <Route path="/health" element={<RepositoryHealth />} />
        <Route path="/copilot" element={<CopilotPanel fullPage />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/demo" element={<DemoCockpit />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
