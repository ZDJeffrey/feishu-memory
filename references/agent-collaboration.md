# Agent 协作

本技能采用**逻辑角色层 + 运行器路由层**分离设计。日常飞书同步与局部读写均由主 Agent 直接调用 `mirror.py` 与 `lark-cli` 完成，不再强制拆分专用飞书子 Agent；仅在多篇批量重构、大规模独立调研、并行编码或复杂 DSL/SVG 画板制作时派发子 Agent。完整选型与定价依据见 Wiki 中的《模型能力与任务分配》。

## 双平台路由速查

| 逻辑角色 | Antigravity / Gemini 路由 | Codex / GPT 路由 |
| --- | --- | --- |
| **主 Agent（规划/写作/重构/验收/日常 CLI）** | Gemini 4 Neon（日常主力） / Gemini 4 Carbon（高难深度攻关） | `gpt-6-astra` |
| **执行者（常规编程/环境/大规模调研/浏览器）** | `flash`（Gemini 4 Hydrogen）；浏览器用 `browser`（`flash`），只读调研用 `research` | `gpt-6.1-terra`（`medium`/`high`）；复杂升级 `gpt-6.1-sol` |
| **批处理执行者（批量测试/命令监控/简单提取）** | `flash_lite`（Gemini 3.5 Flash-Lite）；需主模型推理深度时再显式用 `inherit` | `gpt-6.1-luna`（`low`/`medium`） |
| **异步等待机制** | 原生反应式唤醒（发起异步任务后结束回合等待通知，不轮询） | `wait_agent({timeout_ms: 60000})` 超时续接，不额外轮询 |

## 派发约定

1. 派发子 Agent 时显式传递：任务目标、修改范围、验收标准、`feishu-memory` 已启用状态及需要读取的规范路径。子 Agent 复用父会话已同步的本地缓存目录，不重复执行全库同步。
2. 同一文件或同一飞书页面保持单一写入者；仅相互独立的子任务才并行派发。
3. 飞书草稿与中间资源统一放在系统临时目录，子 Agent 遵守同一约定。
