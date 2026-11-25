# Feishu Memory

为具有本机工具的 Agent（Antigravity/Gemini、Codex/GPT、Claude Code）提供可迁移的飞书远程记忆：启动时秒级同步目录与核心规范，按需懒加载目标子树，任务结束后精准局部写回并维护两级索引。

## 安装

```bash
npx skills add ZDJeffrey/feishu-memory --skill feishu-memory --global
```

或从源码安装：

```bash
git clone https://github.com/ZDJeffrey/feishu-memory.git
cd feishu-memory
python3 scripts/install.py
```

`install.py` 将技能安装到目标技能目录，不修改 `AGENTS.md` 或 `CLAUDE.md`。使用时在对话中显式引入 `/feishu-memory` 或 `$feishu-memory`。

## 核心流程

1. **首次配置**：按 [首次配置](references/setup.md) 安装 `lark-cli`、绑定 App ID 并完成浏览器授权，自动连接“知识与协作入口”并写入 `~/.config/feishu-memory/config.json`。
2. **秒级启动与按需读取**：主 Agent 直接运行 `python3 scripts/mirror.py sync`，同步目录元数据、更新核心规范页并生成本地 `TREE.md`；进入具体项目时运行 `mirror.py pull --scope <目录>` 懒加载目标子树。
3. **精准写回与 Mermaid 优先**：主 Agent 直接通过 `mirror.py locate` 与 `lark-cli docs +update` 局部写回并回读，不强制拆分专用飞书子 Agent；常规流程图、时序图与架构图默认使用 `<whiteboard type="mermaid">`。
4. **安全红线**：写入限于记忆 Wiki 空间；删除/移动节点、权限变更、整篇 `overwrite` 及扩大外部范围前必须取得用户确认。

## 验证

```bash
python3 scripts/check.py
lark-cli --profile agent-memory auth status --json --verify
```
