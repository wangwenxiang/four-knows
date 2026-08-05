import type { DailyReport, Expert, Signal, Theme } from "./types/report";
import { ReportHero } from "./components/ReportHero";
import { ThemeSection } from "./components/ThemeSection";
import { ReportFooter } from "./components/ReportFooter";

type AppProps = {
  report: DailyReport;
};

export default function App({ report }: AppProps) {
  const expertsByHandle = Object.fromEntries(report.experts.map((expert) => [expert.handle, expert])) as Record<
    string,
    Expert
  >;
  const signalsByTheme = groupSignalsByTheme(report.signals);

  return (
    <div className="page-shell">
      <ReportHero report={report} />
      <main className="report-main">
        <div className="theme-sections">
          {report.themes.map((theme) => (
            <ThemeSection
              key={theme.id}
              theme={theme}
              signals={signalsByTheme[theme.id] ?? []}
              expertsByHandle={expertsByHandle}
            />
          ))}
        </div>
      </main>
      <ReportFooter windowLabel={report.windowLabel} />
    </div>
  );
}

function groupSignalsByTheme(signals: Signal[]): Record<Theme["id"], Signal[]> {
  return signals.reduce<Record<string, Signal[]>>((acc, signal) => {
    acc[signal.themeId] ??= [];
    acc[signal.themeId].push(signal);
    return acc;
  }, {});
}
