# VanishClaw 日报推送

这个目录是“硅谷 AI 原声日报”的业务调度层。通用的 VanishClaw 上传、短连接、认证和
消息协议已经下沉到全局 Vanish skill：
`/Users/jay/.agents/skills/vanish/scripts/vanish-claw-push.mjs`。

每天的流程是：按北京时间确定日期，探测 GitHub Pages 上当天的 `index.html` 与
`screenshots.png`，严格校验图片为 1744×960、8-bit RGB PNG，上传图片后建立一次
全局 Vanish skill 向群 `50224901` 发送 `img_mix`，收到服务端确认后立即断开。

安全措施：

- 身份信息和 VanishClaw 协议只由全局 Vanish skill 管理，不写入本项目。
- 同一天服务端确认成功后不再重复发送。
- 消息发出但未收到确认时，不自动重发，避免群里出现重复消息。
- 当天远程日报未发布时只记录“未就绪”，不发送旧日报。

人工只探测、不发送：

```sh
node "vanish claw push/push.mjs" --dry-run
```

只检查身份认证与短连接、不发送：

```sh
node "/Users/jay/.agents/skills/vanish/scripts/vanish.mjs" claw check
```

临时指定其他群（不会修改正式配置）：

```sh
node "vanish claw push/push.mjs" --group-id 50174819
```

正式推送由 Codex 的每日 08:00 自动任务调用：

```sh
node "vanish claw push/push.mjs"
```
