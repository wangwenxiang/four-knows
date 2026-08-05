from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


SOURCE = Path("reports/active-last-day-search-2026-06-30.json")
OUT = Path("reports/active-last-day-visual-2026-06-30.html")
HERO = "../assets/ai-signal-radar-hero.png"


CATEGORIES = {
    "agent-workflow": {
        "label": "Agent 工作流",
        "short": "Agent",
        "tone": "teal",
        "desc": "编码 Agent、子 Agent、模型路由和工作流交互的更新。",
        "leader_takeaway": "Coding Agent 正在从“能完成任务”进入“运行时系统”阶段，模型路由、子 Agent 委派和上下文缓存会成为成本、质量与体验的核心抓手。",
    },
    "memory-rag": {
        "label": "记忆与检索",
        "short": "Memory/RAG",
        "tone": "green",
        "desc": "Wiki Memory、Retrieval Harness、文档检索工具链。",
        "leader_takeaway": "RAG 不再只是问答检索，而是在变成 Agent 可以调用的一组文档工具和组织记忆能力。",
    },
    "eval-quality": {
        "label": "评测与质量",
        "short": "Evals",
        "tone": "gold",
        "desc": "Agent 轨迹评审、产品评估、Human-as-a-judge 等信号。",
        "leader_takeaway": "AI 产品评估正在前移到产品设计和运行轨迹层，自动评审会成为企业级 Agent 落地的基础设施。",
    },
    "policy-platform": {
        "label": "平台与规则",
        "short": "Platform",
        "tone": "rose",
        "desc": "模型服务条款、访问控制、平台生态和创业公司支持。",
        "leader_takeaway": "模型平台的服务条款、访问控制和生态扶持，会影响下游产品和模型训练策略。",
    },
    "creative-ai": {
        "label": "创意与视频",
        "short": "Creative",
        "tone": "blue",
        "desc": "视频生成、创意工具、内容生产工作流。",
        "leader_takeaway": "创意 AI 的竞争重点不只在模型效果，也在公司文化、区域合作和内容生产体系。",
    },
    "community": {
        "label": "社区互动",
        "short": "Community",
        "tone": "gray",
        "desc": "会议、活动、简短回复和社交互动，情报价值较低。",
        "leader_takeaway": "社区互动通常只作为背景噪声和关系信号，不进入领导版精华日报。",
    },
    "ai-infra": {
        "label": "AI 基础设施",
        "short": "Infra",
        "tone": "violet",
        "desc": "数据、脑机接口、算力和底层基础设施信号。",
        "leader_takeaway": "AI 基础设施信号偏长期，应结合战略方向持续观察。",
    },
}


NOTES = {
    "2071776847327805825": ("agent-workflow", "medium", "建议对方尝试 Claude Desktop，认为它基本覆盖了相关交互需求。", "Claude 桌面端被视为更接近原生工作流入口，说明 AI 助手正在从网页对话迁移到桌面生产环境。"),
    "2071753139058024851": ("agent-workflow", "medium", "解释 Claude 动态工作流：直接让 Claude 使用某个 workflow；移动端和网页暂不支持 Fast mode。", "Claude 工作流能力在不同端上的支持差异，会影响团队把 Agent 流程产品化时的入口选择。"),
    "2071752401087058106": ("community", "low", "简短回复：使用 `/focus`。", "低信号操作回复，可作为 Claude Code/Claude 工作流命令线索保留。"),
    "2071748721948188819": ("community", "low", "简短回复：向下箭头后回车。", "低信号交互细节。"),
    "2071748634522095654": ("community", "low", "简短确认：可以。", "低信号互动。"),
    "2071718682250928421": ("agent-workflow", "high", "Scott Wu 讨论 coding agent 的模型路由：不同模型即使都能完成任务，也会有行为和风格差异；任务难度也要在 agent 实际探索代码后才知道。他认为需要能评估风格/行为的 eval，并让 agent 动态更新和重路由；Devin Fusion 据称可降本 30%-40%。", "这是今天最硬的 AI 编码 Agent 信号：模型路由不只是成本优化，而是要把任务理解、风格一致性和动态决策纳入 agent runtime。"),
    "2071963841009942671": ("memory-rag", "high", "Harrison Chase 归纳一种常见 memory 模式：Wiki Memory，例如 DeepWiki、AutoWiki、LLM Wiki。", "Wiki Memory 正在成为 Agent 记忆工程的可命名模式，值得用于团队知识库和代码库理解方案。"),
    "2071963622298050997": ("memory-rag", "medium", "提出关键词：Wiki Memory。", "虽短，但与后续解释连在一起，指向 Agent 记忆的一种新抽象。"),
    "2071935422033428499": ("agent-workflow", "medium", "展示 dynamic subagents 的呈现方式，说明子 Agent 状态展示本身也需要产品设计。", "多 Agent 不只是后端编排，前端如何让用户理解 Agent 分工也会成为产品门槛。"),
    "2071633874736804066": ("agent-workflow", "high", "介绍 deepagents 中的 dynamic subagents：可以用程序方式拉起子 Agent，并展示 6 种用例。", "子 Agent 从静态配置转向动态生成，意味着复杂任务可以按需拆解为临时专家。"),
    "2071630837976822237": ("eval-quality", "high", "LangChain 开始向早期伙伴推出 Trace Judge 模型，用于以闭源模型约 1/100 的成本检测 agent 轨迹错误。", "Agent 可观测性与自动评审开始产品化，后续可能成为企业 Agent 落地的标配组件。"),
    "2071802591147901339": ("community", "low", "活动/社交回复，提到德国比赛和 Raising Cane's。", "低信号社交内容。"),
    "2071737452323303750": ("agent-workflow", "high", "Jerry Liu 认可模型路由与子 Agent 委派的方案，同时强调要让所有 Agent 都能命中累积上下文缓存。", "把 sub-agent delegation 与 cache hit 结合，是降低多 Agent 成本和延迟的关键工程点。"),
    "2071735844793385020": ("community", "low", "活动预告：AI engineer pickleball 聚会。", "社区活动信号，技术价值较低。"),
    "2071729856900215261": ("memory-rag", "high", "LlamaIndex 发布 LlamaParse Retrieval Harness，定位为 2026 版文档 RAG。它为 Agent 提供混合检索、文件列表、文件 grep、片段读取等工具，面向从 10 个文档到百万级文档的规模化检索。", "RAG 正在从单次问答检索升级为 Agent 可调用的工具集合，文档系统需要暴露更细粒度的检索/读取动作。"),
    "2071645563104481603": ("policy-platform", "medium", "Simon Willison 认为，即使法律上难以证明，Anthropic 和 OpenAI 也可能切断 Meta 对未来模型的访问。", "模型供应商的访问控制会成为平台风险，尤其影响用闭源模型训练竞争系统的团队。"),
    "2071645405176340982": ("policy-platform", "medium", "Simon 认为相关条款可能可执行，合约纠纷中的 discovery 可能揭示训练日志和数据混合。", "围绕模型输出再训练的合约风险，可能比版权风险更直接。"),
    "2071642134655164560": ("policy-platform", "medium", "Simon 区分版权风险与合约风险：用 Claude/GPT 训练竞争模型的问题更多来自已签署服务条款。", "企业使用闭源模型做训练数据或评测数据时，需要把 ToS 纳入合规检查。"),
    "2071635301987185108": ("policy-platform", "medium", "Simon 认为这更像服务条款问题，而不是 fair use 问题。", "再次强化：模型平台条款会影响下游模型训练自由度。"),
    "2071731411204333896": ("policy-platform", "medium", "Greg Brockman 提到 OpenAI 支持创业公司。", "短内容但来自 OpenAI 联合创始人，指向平台生态和创业公司扶持叙事。"),
    "2071937112375689362": ("community", "low", "Thomas Wolf 发了简短的旧金山问候。", "低信号社交内容。"),
    "2071713645927784543": ("eval-quality", "high", "Shreya Shankar 推荐 Hamel 关于 AI 产品评估的文章：先让产品更容易评估，再去固化 eval。", "评测前置到产品设计阶段，是 AI 产品工程化成熟的重要判断。"),
    "2071838126910378135": ("eval-quality", "medium", "Hamel 用一句话概括：模型就是产品。", "强调 AI 产品体验很大程度上由模型行为直接决定。"),
    "2071798647654867448": ("eval-quality", "medium", "Hamel 认为自己在平台上收到的大量回复已经是 AI 生成。", "反映内容平台正在被 AI 回复污染，也会影响社区数据质量和用户反馈评估。"),
    "2071771102389600668": ("eval-quality", "medium", "Hamel 调侃 Human-as-a-judge。", "提示人类评审在 AI 产品评估里也会暴露一致性和可靠性问题。"),
    "2071720498166464550": ("community", "low", "礼貌性感谢回复。", "低信号互动。"),
    "2071720353261629601": ("eval-quality", "medium", "Hamel 表示已申请 LangChain Trace Judge 早期访问，并希望团队成员也获得权限。", "说明实践派评测专家对 Agent trace judge 有直接兴趣，可作为该方向热度佐证。"),
    "2071864906916516183": ("community", "low", "swyx 对 Latent Space 旧内容做简短互动。", "社区互动。"),
    "2071864193435980081": ("community", "low", "swyx 回顾 AI Engineer workshop day。", "会议活动信号。"),
    "2071846850198712819": ("community", "low", "简短活动/情绪回复。", "低信号互动。"),
    "2071845862595305480": ("community", "low", "表示遗憾没能线下打招呼，并期待对方演讲。", "会议社交信号。"),
    "2071845454040781271": ("community", "low", "提到 Together Compute 漫画展位很有趣。", "AI Engineer 会议现场氛围信号。"),
    "2071815172046680318": ("community", "low", "Yohei Nakajima 简短称赞对方。", "低信号互动。"),
    "2071724735604674718": ("community", "low", "Yohei 提到 AI Engineer 活动。", "社区活动信号。"),
    "2071757856248873430": ("creative-ai", "medium", "Runway 创始人 Cristobal Valenzuela 表示很高兴与日本 MIXI 继续扩大合作。", "Runway 在日本市场/合作伙伴生态继续推进，创意 AI 正在走向区域合作。"),
    "2071637576318894515": ("creative-ai", "high", "Cristobal 分享对 Runway 文化、技术和使命的深度文章，主题是如何构建新世界。", "这类深访通常包含产品路线和组织方法，值得后续细读。"),
    "2071617674946179264": ("ai-infra", "medium", "Alexandr Wang 提到 Meta AI 团队在非侵入式脑机接口方面的新工作。", "脑机接口与 AI 团队结合，属于前沿但偏长期的基础设施/交互信号。"),
}


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    rows = []
    cutoff = datetime.fromisoformat(source["cutoff"])
    generated_at = datetime.fromisoformat(source["finishedAt"])

    for person in source["results"]:
        if not person["recent_count"]:
            continue
        for tweet in person["tweets"]:
            category, signal, translation, why = NOTES[tweet["id"]]
            created = datetime.fromisoformat(tweet["created_at"])
            rows.append(
                {
                    "id": tweet["id"],
                    "handle": person["handle"],
                    "name": person["name"],
                    "domain": person["domain"],
                    "priority": person["priority"],
                    "created": created,
                    "created_cn": created.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%m-%d %H:%M"),
                    "text": tweet["text"],
                    "translation": translation,
                    "why": why,
                    "url": tweet["url"],
                    "category": category,
                    "signal": signal,
                }
            )

    rows.sort(key=lambda item: (signal_rank(item["signal"]), item["created"]), reverse=True)
    featured_rows = [row for row in rows if row["signal"] == "high"]
    grouped = defaultdict(list)
    for row in featured_rows:
        grouped[row["category"]].append(row)

    stats = {
        "monitored": len(source["results"]),
        "active_accounts": len({row["handle"] for row in rows}),
        "captured": len(rows),
        "selected": len(featured_rows),
        "suppressed": len(rows) - len(featured_rows),
        "categories": len(grouped),
    }
    category_counts = Counter(row["category"] for row in featured_rows)

    OUT.write_text(
        render_html(source, cutoff, generated_at, featured_rows, grouped, stats, category_counts),
        encoding="utf-8",
    )
    print(f"Wrote {OUT}")


def signal_rank(signal: str) -> int:
    return {"low": 1, "medium": 2, "high": 3}.get(signal, 0)


def render_html(source, cutoff, generated_at, rows, grouped, stats, category_counts) -> str:
    local_tz = ZoneInfo("Asia/Shanghai")
    start = cutoff.astimezone(local_tz).strftime("%Y-%m-%d %H:%M")
    end = generated_at.astimezone(local_tz).strftime("%Y-%m-%d %H:%M")
    category_overview = render_category_overview(category_counts, len(rows))
    lead_row = rows[0]
    summary_items = "\n".join(
        f"""
        <article class="brief-item tone-{CATEGORIES[row['category']]['tone']}">
          <div class="brief-top">
            <span>{html.escape(CATEGORIES[row['category']]['label'])}</span>
            <a href="{html.escape(row['url'])}" target="_blank" rel="noreferrer">@{html.escape(row['handle'])}</a>
          </div>
          <h3>{html.escape(row['translation'])}</h3>
          <p>{html.escape(row['why'])}</p>
        </article>
        """
        for row in rows[:6]
    )
    theme_items = "\n".join(
        render_theme_summary(category, grouped[category])
        for category in CATEGORIES
        if grouped.get(category)
    )
    category_sections = "\n".join(
        render_category_section(category, grouped[category])
        for category in CATEGORIES
        if grouped.get(category)
    )
    data_script = json.dumps(
        {
            "rows": [
                {
                    "category": row["category"],
                    "signal": row["signal"],
                    "handle": row["handle"],
                    "name": row["name"],
                    "translation": row["translation"],
                    "why": row["why"],
                    "url": row["url"],
                    "created": row["created_cn"],
                }
                for row in rows
            ]
        },
        ensure_ascii=False,
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI 专家动态日报 · 2026-06-30</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700;800&family=Geist+Mono:wght@400;500;600&family=Noto+Sans+SC:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #f7f7f4;
      --paper: #fbfbf8;
      --ink: #08090a;
      --muted: #666b72;
      --faint: #9aa0a8;
      --line: #d9dce1;
      --panel: rgba(255,255,253,.94);
      --accent: #0057ff;
      --accent-ink: #ffffff;
      --accent-soft: #e8efff;
      --teal: var(--accent);
      --green: var(--accent);
      --gold: var(--accent);
      --rose: var(--accent);
      --blue: var(--accent);
      --violet: var(--accent);
      --shadow: 0 1px 0 rgba(8,9,10,.06), 0 18px 50px rgba(8,9,10,.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Geist", "Noto Sans SC", "Microsoft YaHei UI", sans-serif;
      color: var(--ink);
      background:
        linear-gradient(rgba(8,9,10,.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(8,9,10,.035) 1px, transparent 1px),
        radial-gradient(circle at 72% 0%, rgba(0,87,255,.10), transparent 28%),
        var(--bg);
      background-size: 28px 28px, 28px 28px, auto, auto;
    }}
    body::before {{
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: .045;
      background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 160 160' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
      mix-blend-mode: multiply;
    }}
    a {{ color: inherit; text-decoration: none; }}
    .hero {{
      min-height: 82vh;
      display: flex;
      align-items: stretch;
      position: relative;
      overflow: hidden;
      padding: 0;
      color: white;
      background-color: #08090a;
      background-image: linear-gradient(90deg, rgba(8,9,10,.98) 0%, rgba(8,9,10,.86) 42%, rgba(8,9,10,.20) 78%), url("{HERO}");
      background-size: cover;
      background-position: center;
    }}
    .hero::after {{
      content: "";
      position: absolute;
      inset: auto 0 0;
      height: 34%;
      background: linear-gradient(0deg, rgba(247,247,244,1), rgba(247,247,244,0));
      pointer-events: none;
    }}
    .hero-inner {{
      position: relative;
      z-index: 1;
      width: min(1240px, calc(100% - 48px));
      margin: 0 auto;
      display: grid;
      grid-template-columns: minmax(0, 1.05fr) minmax(340px, .62fr);
      gap: 40px;
      align-items: end;
      padding: 96px 0 108px;
    }}
    .hero-copy {{ min-width: 0; }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      min-height: 28px;
      border-left: 3px solid var(--accent);
      padding: 0 0 0 12px;
      color: rgba(255,255,255,.72);
      font-family: "Geist Mono", monospace;
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: .08em;
    }}
    .hero h1 {{
      max-width: 820px;
      margin: 22px 0 18px;
      font-size: clamp(48px, 8.3vw, 132px);
      font-weight: 800;
      line-height: .86;
      letter-spacing: -.055em;
    }}
    .hero h1 span {{ display: block; }}
    .hero p {{
      max-width: 660px;
      margin: 0;
      color: rgba(255,255,255,.74);
      font-size: 18px;
      line-height: 1.75;
      font-weight: 400;
    }}
    .hero-panel {{
      align-self: end;
      border: 1px solid rgba(255,255,255,.18);
      background: rgba(8,9,10,.52);
      backdrop-filter: blur(18px);
      padding: 18px;
    }}
    .hero-panel h2 {{
      margin: 0 0 12px;
      font-size: 13px;
      font-family: "Geist Mono", monospace;
      color: rgba(255,255,255,.64);
      text-transform: uppercase;
      letter-spacing: .08em;
    }}
    .hero-panel strong {{
      display: block;
      color: #fff;
      font-size: 19px;
      line-height: 1.45;
      letter-spacing: -.01em;
    }}
    .hero-panel p {{
      margin-top: 10px;
      color: rgba(255,255,255,.62);
      font-size: 14px;
      line-height: 1.65;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 1px;
      margin-top: 34px;
      max-width: 820px;
      background: rgba(255,255,255,.2);
      border: 1px solid rgba(255,255,255,.2);
    }}
    .stat {{
      border: 0;
      padding: 16px;
      background: rgba(8,9,10,.42);
      backdrop-filter: blur(16px);
    }}
    .stat b {{ display: block; font-size: 34px; line-height: 1; letter-spacing: -.04em; }}
    .stat span {{ display: block; margin-top: 9px; color: rgba(255,255,255,.62); font-size: 12px; font-family: "Geist Mono", monospace; text-transform: uppercase; letter-spacing:.05em; }}
    main {{
      width: min(1240px, calc(100% - 32px));
      margin: -58px auto 80px;
      position: relative;
      z-index: 2;
    }}
    .toolbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 20px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 0;
      background: rgba(251,251,248,.88);
      box-shadow: var(--shadow);
      backdrop-filter: blur(18px);
      position: sticky;
      top: 0;
      z-index: 10;
    }}
    .selection {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .quality-pill {{
      min-height: 36px;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border: 1px solid var(--line);
      border-radius: 0;
      padding: 0 10px;
      color: var(--ink);
      background: white;
      font: inherit;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: -.01em;
    }}
    .quality-pill b {{
      min-width: 24px;
      height: 22px;
      display: grid;
      place-items: center;
      background: #eef2ef;
      font-size: 12px;
      font-family: "Geist Mono", monospace;
    }}
    .quality-pill.primary {{
      color: white;
      border-color: var(--accent);
      background: var(--accent);
    }}
    .quality-pill.primary b {{ color: var(--ink); background: #fff; }}
    .window {{
      color: var(--muted);
      font-family: "Geist Mono", monospace;
      font-size: 12px;
      line-height: 1.4;
      text-align: right;
    }}
    .overview-grid {{
      display: grid;
      grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr);
      gap: 16px;
      margin-bottom: 34px;
    }}
    .claim-box, .distribution {{
      border: 1px solid var(--line);
      background: var(--panel);
      box-shadow: var(--shadow);
    }}
    .claim-box {{
      display: grid;
      gap: 16px;
      padding: 22px;
      border-top: 4px solid var(--accent);
    }}
    .claim-box .label, .distribution .label {{
      margin: 0;
      color: var(--muted);
      font-family: "Geist Mono", monospace;
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: .08em;
    }}
    .claim-box h2 {{
      margin: 0;
      max-width: 680px;
      font-size: clamp(24px, 3vw, 44px);
      line-height: 1.05;
      letter-spacing: -.045em;
    }}
    .claim-box p {{
      margin: 0;
      color: #3f454c;
      font-size: 16px;
      line-height: 1.7;
    }}
    .distribution {{
      padding: 18px;
    }}
    .bar-list {{
      display: grid;
      gap: 12px;
      margin-top: 18px;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: 128px minmax(0, 1fr) 34px;
      gap: 12px;
      align-items: center;
      font-size: 13px;
    }}
    .bar-row span:first-child {{
      font-weight: 700;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .bar-track {{
      height: 10px;
      background: #eceef2;
      position: relative;
      overflow: hidden;
    }}
    .bar-fill {{
      height: 100%;
      background: var(--accent);
      width: var(--w);
    }}
    .bar-row b {{
      font-family: "Geist Mono", monospace;
      color: var(--muted);
      font-size: 12px;
      text-align: right;
    }}
    .theme-section {{
      margin: 34px 0;
    }}
    .theme-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 1px;
      border: 1px solid var(--line);
      background: var(--line);
    }}
    .theme-card {{
      min-height: 220px;
      display: grid;
      align-content: space-between;
      gap: 18px;
      padding: 20px;
      background: var(--panel);
      border-top: 3px solid var(--accent);
    }}
    .theme-card h3 {{
      margin: 0;
      font-size: 22px;
      line-height: 1.15;
      letter-spacing: -.035em;
    }}
    .theme-card p {{
      margin: 0;
      color: #3f454c;
      font-size: 14px;
      line-height: 1.68;
    }}
    .theme-card .theme-meta {{
      color: var(--muted);
      font-family: "Geist Mono", monospace;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: .06em;
    }}
    .section-title {{
      margin: 30px 0 16px;
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 14px;
    }}
    .section-title h2 {{ margin: 0; font-size: 30px; letter-spacing: -.04em; }}
    .section-title p {{ margin: 0; color: var(--muted); font-size: 15px; line-height: 1.5; }}
    .brief-grid {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 1px;
      border: 1px solid var(--line);
      background: var(--line);
    }}
    .brief-item, .tweet-card {{
      border: 1px solid var(--line);
      border-radius: 0;
      background: var(--panel);
    }}
    .brief-item {{
      min-height: 250px;
      padding: 20px;
      border: 0;
      grid-column: span 3;
      box-shadow: none;
    }}
    .brief-item:first-child {{ grid-column: span 3; background: #08090a; color: #fff; }}
    .brief-item:nth-child(2) {{ grid-column: span 3; }}
    .brief-top {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      color: var(--muted);
      font-family: "Geist Mono", monospace;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: .06em;
    }}
    .brief-item:first-child .brief-top {{ color: rgba(255,255,255,.6); }}
    .brief-top a {{ color: var(--accent); }}
    .brief-item h3 {{
      margin: 18px 0 12px;
      font-size: 20px;
      line-height: 1.32;
      letter-spacing: -.025em;
    }}
    .brief-item:first-child h3 {{ font-size: 26px; line-height: 1.18; }}
    .brief-item p {{
      margin: 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.65;
    }}
    .brief-item:first-child p {{ color: rgba(255,255,255,.68); }}
    .category-band {{
      margin-top: 18px;
      padding-top: 8px;
    }}
    .category-head {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: center;
      margin: 34px 0 12px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--line);
    }}
    .category-head h2 {{ margin: 0; font-size: 26px; letter-spacing: -.035em; }}
    .category-head p {{ margin: 5px 0 0; color: var(--muted); font-size: 14px; }}
    .count-pill {{
      min-width: 48px;
      height: 34px;
      display: grid;
      place-items: center;
      color: white;
      background: #08090a;
      font-family: "Geist Mono", monospace;
      font-weight: 600;
    }}
    .tweet-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    .tweet-card {{
      min-height: 242px;
      padding: 18px;
      display: grid;
      gap: 12px;
      border-left-width: 3px;
      box-shadow: none;
    }}
    .meta {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      color: var(--muted);
      font-family: "Geist Mono", monospace;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: .05em;
    }}
    .signal {{
      min-width: 54px;
      height: 24px;
      display: inline-grid;
      place-items: center;
      color: white;
      font-size: 11px;
    }}
    .signal.high {{ background: var(--accent); }}
    .signal.medium {{ background: #08090a; }}
    .signal.low {{ background: #737b77; }}
    .tweet-card h3 {{
      margin: 0;
      font-size: 17px;
      line-height: 1.45;
      letter-spacing: -.02em;
    }}
    .why {{
      margin: 0;
      color: #40504a;
      font-size: 14px;
      line-height: 1.65;
    }}
    .origin {{
      margin: 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.55;
      border-left: 1px solid var(--line);
      padding-left: 10px;
    }}
    .card-foot {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-top: auto;
    }}
    .author {{
      display: grid;
      gap: 2px;
      min-width: 0;
    }}
    .author b {{ font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .author span {{ color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .link {{
      min-height: 34px;
      display: inline-grid;
      place-items: center;
      border: 1px solid var(--line);
      padding: 0 10px;
      color: var(--accent);
      background: white;
      font-family: "Geist Mono", monospace;
      font-size: 12px;
      font-weight: 600;
      white-space: nowrap;
    }}
    .tone-teal {{ border-color: rgba(14,133,132,.28); border-left-color: var(--teal); border-top-color: var(--teal); }}
    .tone-green {{ border-color: rgba(85,127,69,.28); border-left-color: var(--green); border-top-color: var(--green); }}
    .tone-gold {{ border-color: rgba(182,122,23,.3); border-left-color: var(--gold); border-top-color: var(--gold); }}
    .tone-rose {{ border-color: rgba(184,79,100,.28); border-left-color: var(--rose); border-top-color: var(--rose); }}
    .tone-blue {{ border-color: rgba(53,111,154,.28); border-left-color: var(--blue); border-top-color: var(--blue); }}
    .tone-violet {{ border-color: rgba(113,86,156,.28); border-left-color: var(--violet); border-top-color: var(--violet); }}
    .tone-gray {{ border-color: rgba(115,123,119,.24); border-left-color: #8a918c; border-top-color: #8a918c; }}
    .hide {{ display: none; }}
    @media (max-width: 900px) {{
      .hero {{ min-height: 78vh; background-position: 63% center; }}
      .hero-inner {{ width: min(100% - 28px, 720px); grid-template-columns: 1fr; gap: 22px; padding: 48px 0 78px; }}
      .hero h1 {{ font-size: clamp(48px, 17vw, 72px); }}
      .hero p {{ font-size: 15px; }}
      .hero-panel {{ padding: 14px; }}
      .stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .overview-grid, .tweet-grid, .theme-grid {{ grid-template-columns: 1fr; }}
      .brief-grid {{ grid-template-columns: 1fr; }}
      .brief-item, .brief-item:first-child, .brief-item:nth-child(2) {{ grid-column: auto; min-height: auto; }}
      main {{ width: min(100% - 24px, 720px); margin-top: -42px; }}
      .toolbar {{ align-items: stretch; flex-direction: column; }}
      .window {{ text-align: left; }}
      .section-title {{ align-items: start; flex-direction: column; }}
      .bar-row {{ grid-template-columns: 112px minmax(0, 1fr) 28px; }}
    }}
  </style>
</head>
<body>
  <header class="hero">
    <div class="hero-inner">
      <div class="hero-copy">
        <div class="eyebrow">AI Expert Signal Radar · Daily Brief</div>
        <h1><span>AI 专家动态</span><span>日报</span></h1>
        <p>面向领导阅读的高质量 AI 大 V 精华简报：只展示最近 24 小时内值得跟进的技术与产业信号，中低价值互动已降噪处理。</p>
        <div class="stats">
          <div class="stat"><b>{stats['monitored']}</b><span>监控账号</span></div>
          <div class="stat"><b>{stats['captured']}</b><span>抓取动态</span></div>
          <div class="stat"><b>{stats['selected']}</b><span>精选入选</span></div>
          <div class="stat"><b>{stats['categories']}</b><span>主题分类</span></div>
        </div>
      </div>
      <aside class="hero-panel">
        <h2>Lead Signal</h2>
        <strong>{html.escape(lead_row['translation'])}</strong>
        <p>{html.escape(lead_row['why'])}</p>
      </aside>
    </div>
  </header>

  <main>
    <nav class="toolbar">
      <div class="selection">
        <div class="quality-pill primary"><span>领导版精选</span><b>{len(rows)}</b></div>
        <div class="quality-pill"><span>已降噪中低信号</span><b>{stats['suppressed']}</b></div>
        <div class="quality-pill"><span>活跃账号</span><b>{stats['active_accounts']}</b></div>
      </div>
      <div class="window">{html.escape(start)} 至 {html.escape(end)}<br>北京时间</div>
    </nav>

    <section class="overview-grid">
      <div class="claim-box">
        <p class="label">Executive Summary</p>
        <h2>今天的主线不是模型发布，而是 Agent 工程开始补齐运行时、记忆和评测。</h2>
        <p>高信号集中在 coding agent 的动态模型路由、子 Agent 编排、Wiki Memory、Retrieval Harness 和 Trace Judge。页面仅展示入选精选，社交互动、活动寒暄和短回复不进入领导版正文。</p>
      </div>
      <div class="distribution">
        <p class="label">Selected Themes</p>
        <div class="bar-list">
          {category_overview}
        </div>
      </div>
    </section>

    <section class="theme-section">
      <div class="section-title">
        <div>
          <h2>主题解读</h2>
          <p>把单条动态归并为可跟进的技术/产业主题，避免把推文流水账直接交给领导。</p>
        </div>
      </div>
      <div class="theme-grid">
        {theme_items}
      </div>
    </section>

    <section>
      <div class="section-title">
        <div>
          <h2>今日精选</h2>
          <p>按信号强度和可跟进价值筛选，只保留需要进一步关注或转化为内部讨论的问题。</p>
        </div>
      </div>
      <div class="brief-grid">
        {summary_items}
      </div>
    </section>

    <section class="category-band">
      <div class="section-title">
        <div>
          <h2>精选证据</h2>
          <p>按主题保留来源和判断依据，方便需要时追溯原文。</p>
        </div>
      </div>
      {category_sections}
    </section>
  </main>

  <script type="application/json" id="report-data">{html.escape(data_script)}</script>
</body>
</html>
"""


def render_category_section(category: str, rows: list[dict]) -> str:
    meta = CATEGORIES[category]
    cards = "\n".join(render_card(row) for row in rows)
    return f"""
    <section class="category-section" data-category="{html.escape(category)}">
      <div class="category-head">
        <div>
          <h2>{html.escape(meta['label'])}</h2>
          <p>{html.escape(meta['desc'])}</p>
        </div>
        <div class="count-pill">{len(rows)}</div>
      </div>
      <div class="tweet-grid">
        {cards}
      </div>
    </section>
    """


def render_theme_summary(category: str, rows: list[dict]) -> str:
    meta = CATEGORIES[category]
    handles = ", ".join(f"@{row['handle']}" for row in rows[:3])
    return f"""
    <article class="theme-card tone-{meta['tone']}">
      <div>
        <div class="theme-meta">{len(rows)} selected signals · {html.escape(handles)}</div>
        <h3>{html.escape(meta['label'])}</h3>
      </div>
      <p>{html.escape(meta['leader_takeaway'])}</p>
    </article>
    """


def render_category_overview(category_counts: Counter, total: int) -> str:
    rows = []
    for key, meta in CATEGORIES.items():
        count = category_counts.get(key, 0)
        if not count:
            continue
        width = max(6, round(count / total * 100, 1))
        rows.append(
            f"""
            <div class="bar-row">
              <span>{html.escape(meta['label'])}</span>
              <div class="bar-track"><div class="bar-fill" style="--w:{width}%"></div></div>
              <b>{count}</b>
            </div>
            """
        )
    return "\n".join(rows)


def render_card(row: dict) -> str:
    meta = CATEGORIES[row["category"]]
    signal_label = {"high": "高", "medium": "中", "low": "低"}[row["signal"]]
    return f"""
    <article class="tweet-card tone-{meta['tone']}" data-category="{html.escape(row['category'])}">
      <div class="meta">
        <span>{html.escape(row['created_cn'])}</span>
        <span class="signal {html.escape(row['signal'])}">{signal_label}信号</span>
      </div>
      <h3>{html.escape(row['translation'])}</h3>
      <p class="why">{html.escape(row['why'])}</p>
      <div class="card-foot">
        <div class="author">
          <b>@{html.escape(row['handle'])}</b>
          <span>{html.escape(row['name'])} · {html.escape(row['domain'])}</span>
        </div>
        <a class="link" href="{html.escape(row['url'])}" target="_blank" rel="noreferrer">原文</a>
      </div>
    </article>
    """


if __name__ == "__main__":
    main()
