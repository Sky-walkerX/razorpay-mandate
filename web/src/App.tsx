import { Routes, Route, Navigate } from 'react-router-dom';
import { BootLoader } from './components/brand/BootLoader';
import Landing from './pages/Landing';
import Dashboard from './pages/Dashboard';
import JudgeConsole from './pages/JudgeConsole';
import PitchDeck from './pages/PitchDeck';
import Storefront from './pages/Storefront';
import Alignment from './pages/Alignment';

export default function App() {
  return (
    <>
      <BootLoader />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/try" element={<JudgeConsole />} />
        <Route path="/store" element={<Storefront />} />
        <Route path="/pitch" element={<PitchDeck />} />
        <Route path="/rails" element={<Alignment />} />
        <Route path="/v2" element={<Navigate to="/" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/dashboard/activity" element={<Dashboard />} />
        <Route path="/dashboard/limits" element={<Dashboard />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

