type ReportFooterProps = {
  windowLabel: string;
};

export function ReportFooter({ windowLabel }: ReportFooterProps) {
  return (
    <footer className="report-footer">
      <span>{windowLabel}</span>
      <span>来源：X 专家账号公开动态</span>
    </footer>
  );
}
