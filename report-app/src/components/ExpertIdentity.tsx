import type { Expert } from "../types/report";

type ExpertIdentityProps = {
  expert: Expert;
  compact?: boolean;
};

export function ExpertIdentity({ expert, compact = false }: ExpertIdentityProps) {
  return (
    <div className={`expert ${compact ? "expert--compact" : ""}`}>
      <img src={expert.avatar} alt={`${expert.name} avatar`} />
      <div className="expert__text">
        <div className="expert__name">
          <strong>{expert.name}</strong>
          <span>@{expert.handle}</span>
        </div>
        <p>{[expert.title, expert.org].filter(Boolean).join(", ")}</p>
        {!compact && expert.tags.length > 0 ? (
          <div className="expert__tags">
            {expert.tags.map((tag) => (
              <span key={tag}>{tag}</span>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
