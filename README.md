# AI V-Radar

`four-knows` 生成并发布“硅谷 AI 原声”日报：从固定的 X 专家名单和热点方向抓取最近 23 小时的技术动态，输出中英双语页面与海报。

日报生产规范和校验规则见 [`.agents/skills/ai-v-radar-daily/SKILL.md`](.agents/skills/ai-v-radar-daily/SKILL.md)。

## 主要入口

```bash
python3 scripts/fetch_ai_v_radar.py --hours 23 --fetch-mode search \
  --search-batch-size 8 --search-max-pages 5 \
  --expansion-watchlist config/ai_x_expansion_watchlist.json \
  --hotspot-queries config/ai_x_hotspot_queries.json --hotspot-max-pages 3 \
  --workers 2 --retries 2 --avatar-workers 3 \
  --translation-batch-size 8 --translation-workers 2 --translation-retries 2
```

产物写入 `ai-v-radar/YYYYMMDD/`，其中包括日报页面、审核数据、海报 HTML 和 1744×960 RGB PNG。翻译和作者头像分别复用 `ai-v-radar/translation-cache.json` 与 `ai-v-radar/avatar-cache.json`。

每日 08:00 的群推送由 Codex 自动任务调用：

```bash
node "vanish claw push/push.mjs"
```

它只在当天日报页面和海报均已上线且格式有效时，使用 VanishClaw 发送图文卡片；发送状态保存在本地忽略的 `.state/` 目录中以避免重复推送。
