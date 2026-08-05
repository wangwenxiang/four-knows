import { ArrowUpRight } from "lucide-react";
import type { Expert, QuotedTweet, Signal, TweetMedia } from "../types/report";
import { ExpertIdentity } from "./ExpertIdentity";

type ExpertSignalCardProps = {
  expert: Expert;
  signal: Signal;
  showTranslation: boolean;
  featured?: boolean;
};

export function ExpertSignalCard({ expert, signal, showTranslation, featured = false }: ExpertSignalCardProps) {
  return (
    <article className={`signal-card ${featured ? "signal-card--featured" : ""}`}>
      <ExpertIdentity expert={expert} />
      <div className="signal-card__body">
        <div className="signal-card__meta">
          <span>{signal.timeLabel}</span>
          <strong>Original X Post</strong>
        </div>
        <blockquote className="x-post-text">{signal.originalText}</blockquote>
        <TweetMediaGrid media={signal.media} />
        {signal.quotedTweet ? <QuotedTweetCard quotedTweet={signal.quotedTweet} /> : null}
        {showTranslation ? (
          <div className="translation-panel">
            <span>中文译文</span>
            <p>{signal.translation}</p>
          </div>
        ) : null}
      </div>
      <a className="source-link" href={signal.url} target="_blank" rel="noreferrer">
        Open on X <ArrowUpRight size={14} />
      </a>
    </article>
  );
}

function TweetMediaGrid({ media }: { media: TweetMedia[] }) {
  if (!media.length) {
    return null;
  }
  return (
    <div className={`tweet-media-grid tweet-media-grid--${Math.min(media.length, 4)}`}>
      {media.map((item, index) => (
        <MediaItem key={`${item.url}-${index}`} item={item} />
      ))}
    </div>
  );
}

function MediaItem({ item }: { item: TweetMedia }) {
  if (item.type === "video") {
    return (
      <a className="tweet-media tweet-media--video" href={item.videoUrl || item.url} target="_blank" rel="noreferrer">
        <img src={item.url} alt="Video preview from X post" />
        <span>Video</span>
      </a>
    );
  }
  return (
    <a className="tweet-media" href={item.url} target="_blank" rel="noreferrer">
      <img src={item.url} alt="Image from X post" />
    </a>
  );
}

function QuotedTweetCard({ quotedTweet }: { quotedTweet: QuotedTweet }) {
  return (
    <a className="quoted-tweet" href={quotedTweet.url} target="_blank" rel="noreferrer">
      <div className="quoted-tweet__author">
        <strong>{quotedTweet.authorName}</strong>
        <span>@{quotedTweet.authorHandle}</span>
      </div>
      <p>{quotedTweet.text}</p>
      <TweetMediaGrid media={quotedTweet.media} />
      {quotedTweet.article ? (
        <div className="article-card">
          <strong>{quotedTweet.article.title}</strong>
          {quotedTweet.article.previewText ? <p>{quotedTweet.article.previewText}</p> : null}
        </div>
      ) : null}
    </a>
  );
}
