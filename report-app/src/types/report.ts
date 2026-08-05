export type Language = "en" | "zh";

export type Expert = {
  handle: string;
  name: string;
  avatar: string;
  title: string;
  org: string;
  tags: string[];
};

export type Theme = {
  id: string;
  title: string;
  shortLabel: string;
  evidenceLabel: string;
};

export type TweetMedia = {
  type: "photo" | "video";
  url: string;
  width?: number;
  height?: number;
  videoUrl?: string;
  durationMs?: number;
};

export type ArticleCard = {
  title: string;
  previewText?: string;
};

export type QuotedTweet = {
  id: string;
  text: string;
  authorName: string;
  authorHandle: string;
  url: string;
  media: TweetMedia[];
  article?: ArticleCard;
};

export type Signal = {
  id: string;
  themeId: string;
  expertHandle: string;
  createdAt: string;
  timeLabel: string;
  originalText: string;
  translation: string;
  url: string;
  media: TweetMedia[];
  quotedTweet?: QuotedTweet;
};

export type DailyReport = {
  date: string;
  title: string;
  headline: string;
  windowLabel: string;
  metrics: {
    monitoredExperts: number;
    activeExperts: number;
    selectedSignals: number;
    themes: number;
  };
  experts: Expert[];
  themes: Theme[];
  signals: Signal[];
};
