import { useState } from "react";
import type { Expert, Signal, Theme } from "../types/report";
import { ExpertSignalCard } from "./ExpertSignalCard";

type ThemeSectionProps = {
  theme: Theme;
  signals: Signal[];
  expertsByHandle: Record<string, Expert>;
};

export function ThemeSection({ theme, signals, expertsByHandle }: ThemeSectionProps) {
  const [showTranslation, setShowTranslation] = useState(false);

  return (
    <section className="theme-section" id={theme.id}>
      <div className="theme-section__intro">
        <p>{theme.shortLabel}</p>
        <h2>{theme.title}</h2>
        <span>{signals.length} 条高信号 X 内容；范围：{theme.evidenceLabel}</span>
        <button className="translation-toggle" type="button" onClick={() => setShowTranslation((value) => !value)}>
          {showTranslation ? "隐藏中文" : "显示中文"}
        </button>
      </div>
      <div className="signal-grid">
        {signals.map((signal, index) => (
          <ExpertSignalCard
            key={signal.id}
            expert={expertsByHandle[signal.expertHandle]}
            signal={signal}
            showTranslation={showTranslation}
            featured={index === 0 && signals.length > 2}
          />
        ))}
      </div>
    </section>
  );
}
