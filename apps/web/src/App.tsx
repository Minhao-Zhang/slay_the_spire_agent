import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { MonitorDashboard } from "./components/MonitorDashboard";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MonitorDashboard />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
