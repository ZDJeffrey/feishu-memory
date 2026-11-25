---
name: feishu-memory
description: 通过飞书 CLI 为具有本地工具的 Agent 提供远程记忆。首次调用按需安装、配置并连接记忆空间，随后按需同步上下文并在收尾时更新。仅在用户于当前会话显式引入 feishu-memory 时使用；任务类型本身不触发。
---

# Feishu Memory

飞书 Wiki 保存远程记忆与项目知识，本机配置只保存 CLI profile 与 Wiki 入口，认证凭据由 `lark-cli` 管理。主 Agent 直接调用 `mirror.py` 与 `lark-cli` 完成同步、按需检索与局部写回，不强制拆分专用飞书子 Agent；仅在多篇批量重构或复杂 DSL/SVG 画板制作时按需派发子 Agent。

仅当用户在当前会话显式引入本技能（点选、@ 引用、`$feishu-memory`、`/feishu-memory` 或明确要求）时启用，并持续至用户停用；子 Agent 仅继承父任务显式传递的启用状态。安装不修改 `AGENTS.md` 或 `CLAUDE.md`。

所有飞书草稿、下载资源和中间文件统一落在系统临时目录（如 `/tmp`），绝不写入项目目录；调用 `docs +script --command init-draft` 前显式将命令工作目录设为系统临时目录。

## 首次调用

1. 检查 `lark-cli` 与本机配置 `~/.config/feishu-memory/config.json`（支持 `FEISHU_MEMORY_CONFIG` 覆盖）。缺失时读取 [首次配置](references/setup.md)。
2. 应用未绑定时请用户提供 App ID，给出终端配置命令（隐藏输入 App Secret）并引导浏览器授权。
3. 按标题“知识与协作入口”连接已有空间或按 [Wiki 分层入口](references/wiki-navigation.md) 新建，写入本机配置后验证。令牌过期时按 `lark-shared` 重新授权。

## 启动与按需读取

1. **秒级同步**：运行 `python3 scripts/mirror.py sync`，仅同步目录树元数据、拉取有变化的核心规范页，并在缓存目录 `~/.cache/feishu-memory/<space_id>/TREE.md` 生成全库实时目录与缓存状态。
2. **最小上下文启动**：读取核心摘要（`知识与协作入口/核心协作准则 · 摘要.md`）与一级入口（`知识与协作入口.md`）；需要定位全库页面时查看 `TREE.md`。
3. **子树懒加载**：确定目标项目或主题后，按需运行 `python3 scripts/mirror.py pull --scope <目录或页面>` 拉取目标子树（优先读该目录树根的二级索引页），再用 `rg` 与按行读取精准定位章节。

| 任务或动作 | 按需读取范围 |
| --- | --- |
| 编码、重构、项目初始化 | `Agent 记忆/代码规范.md`；验收读 `任务交付与文档组织.md` 的核心机制验收 |
| git commit | `Agent 记忆/个人偏好档案.md` 的 Git 提交章节 |
| 环境或 GPU 工作 | `Agent 记忆/个人偏好档案.md` 环境章节 + `开发机与运行环境/` 对应档案 |
| 文档与论文写作 | `Agent 记忆/写作规范.md`；结构骨架读 `任务交付与文档组织.md`；论文追加 `论文写作规范.md` |
| 分派子 Agent | `Agent 记忆/模型能力与任务分配.md` 与 [Agent 协作](references/agent-collaboration.md) |
| 维护 feishu-memory 技能 | `记忆系统/建设指南.md` 的技能维护与发布章节 |
| 项目接续、学习或排障 | 目标根目录的二级概述页 → 相关子页面章节，或 `Debug 记录/` |

启动摘要与入口合计控制在 4000 字符以内，常规单次展开控制在 12000 字符以内；拿到足够决策依据即停止展开，禁止全库扫描读入。

## 写入与维护

仅在完整任务结束或用户要求整理时写入飞书，探索过程留在本地。正文直接呈现当前有效事实与结论，不写入完整 32/64 位哈希、字节数或操作过程流水账，代码溯源使用 7 位短 commit 链接。

1. **精准定位**：运行 `python3 scripts/mirror.py locate <页面> <标题或文本>` 或 `docs +fetch --scope section --detail with-ids` 取得最新 `revision_id` 与 block ID。
2. **就地整合写回**：遵循 [读写操作](references/operations.md) 使用 `lark-cli docs +update` 局部写回。有索引表或状态表的页面必须直接增改表格行，禁止表外追加；日常更新允许直接重写、合并同主题章节并清理过期内容。流程图、依赖图、时序图与简明架构图默认优先使用 `<whiteboard type="mermaid">`。
3. **回读与缓存刷新**：写入后回读核对内容、表格与图示，运行 `mirror.py pull --doc <页面>` 刷新单页本地缓存；同步更新所属目录的二级索引页（仅当目录树增减时更新一级索引页）。改坏时用 `+history-list` 与 `+history-revert` 回滚。

## 写入范围与确认红线

写入严格限定在记忆 Wiki 空间内；外部资料默认只读（见 [外部资源接入](references/external-resources.md)）。以下操作必须先向用户说明目标与影响并取得确认：

- 删除或移动文档、文件夹、Wiki 节点；
- 修改分享、成员与权限设置；
- 整篇 `overwrite` 或跨多章大幅推倒重建；
- 写入知识库之外的位置或扩大外部资料读写范围。
