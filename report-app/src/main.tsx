import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import report from "./data/daily-report.json";
import type { DailyReport } from "./types/report";
import App from "./App";
import "./styles/globals.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App report={report as DailyReport} />
  </StrictMode>,
);
