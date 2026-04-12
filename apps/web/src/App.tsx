import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { MonitorDashboard } from "./components/MonitorDashboard";
import { RunMapPage } from "./components/RunMapPage";
import { RunMetricsPage } from "./components/RunMetricsPage";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MonitorDashboard />} />
        <Route path="/metrics/map" element={<RunMapPage />} />
        <Route
          path="/metrics/debug"
          element={<Navigate to="/metrics" replace />}
        />
        <Route path="/metrics" element={<RunMetricsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
