import { Routes, Route, Navigate } from 'react-router-dom';
import Landing from './pages/Landing';
import Dashboard from './pages/Dashboard';
import JudgeConsole from './pages/JudgeConsole';
import PitchDeck from './pages/PitchDeck';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/try" element={<JudgeConsole />} />
      <Route path="/pitch" element={<PitchDeck />} />
      <Route path="/v2" element={<Navigate to="/" replace />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/dashboard/activity" element={<Dashboard />} />
      <Route path="/dashboard/limits" element={<Dashboard />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

