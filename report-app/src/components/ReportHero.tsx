import { CalendarDays } from "lucide-react";
import type { DailyReport } from "../types/report";

type ReportHeroProps = {
  report: DailyReport;
};

export function ReportHero({ report }: ReportHeroProps) {
  return (
    <header className="hero">
      <div className="hero__content">
        <div className="hero__kicker">
          <CalendarDays size={15} />
          <span>{report.date}</span>
        </div>
        <h1>
          <span>AI 专家动态</span>
          <span>日报</span>
        </h1>
        <p className="hero__headline">{report.headline}</p>
        <div className="hero__metrics" aria-label="日报概览">
          <Metric value={report.metrics.monitoredExperts} label="监控专家" />
          <Metric value={report.metrics.activeExperts} label="活跃专家" />
          <Metric value={report.metrics.selectedSignals} label="精选原文" />
          <Metric value={report.metrics.themes} label="主题" />
        </div>
      </div>
    </header>
  );
}

function Metric({ value, label }: { value: number; label: string }) {
  return (
    <div className="metric">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}
