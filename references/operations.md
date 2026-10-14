# 读写操作

可从任意工作目录运行技能内的 `scripts/memory.py`，路径按实际安装位置解析。配置通过 `--config PATH` 或 `FEISHU_MEMORY_CONFIG` 指定，默认 `~/.config/feishu-memory/config.json`。快照、搜索缓存和回执统一保存到 `~/.local/state/feishu-memory/`，各会话共用；可用 `--state-dir PATH` 显式指定其他位置，路径支持 `~` 展开。

```text
python3 SKILL_DIR/scripts/memory.py doctor
python3 SKILL_DIR/scripts/memory.py begin
python3 SKILL_DIR/scripts/memory.py begin --project PROJECT
python3 SKILL_DIR/scripts/memory.py begin --topic TOPIC
python3 SKILL_DIR/scripts/memory.py browse navigation
python3 SKILL_DIR/scripts/memory.py search '项目名 主题词'
python3 SKILL_DIR/scripts/memory.py read KEY --section '章节名'
```

`read KEY` 返回目录，`--section` 精确匹配标题，`--keyword` 按关键词读取，`--full` 用于确需通读的短文档。KEY 来自配置中的 `documents`。返回 `snapshot`、`revision` 和当前 block ID；`outline_only=true` 时按目录继续缩小范围。

`begin` 默认只读核心摘要与首页，指定项目或主题时读取对应概述；startup_budget 默认 4000 字符，包含 XML。`browse KEY` 每页列出 5 个直接子节点，只返回元数据；用 --page-token 继续当前层。

`search` 默认检索已登记 Wiki 空间；未配置 Wiki 时检索原记忆目录，--source memory 可显式检索原目录。每页最多 5 条，保留 source、has_more 与 page_token；翻页沿用同一查询和来源。新页面可能尚未进入搜索索引，可先用 browse 或登记键读取。外部资料按 [外部资源接入](external-resources.md) 的范围使用对应官方技能。

## 更新

读取目标章节，把完整的新 XML 文本块以唯一文件名保存到状态目录的 `drafts/` 下，并提供真实来源位置：

```text
python3 SKILL_DIR/scripts/memory.py replace KEY --snapshot SNAPSHOT --block-id BLOCK --xml FILE --source SOURCE
```

`--dry-run` 生成预览回执。Wiki 文档读写核对已登记空间、节点父链和内容对象；Drive 写入核对原目录链。执行器支持同类型 `p`、`li`、`h1`–`h4` 的完整替换；复杂资源、评论、表格和新章节使用官方 `lark-doc` 工作流。写入回执保存来源、前后内容、基准版本、结果和回读内容。

| 结果 | 后续动作 |
| --- | --- |
| `verified` | 更新已回读，继续下一项或交付 |
| `unchanged` | 正文相同，已跳过写入 |
| `conflict`，退出码 2 | 重新读取并合并当前内容 |
| `write_requested` / `readback_required` / `review_required` | 核对回执和远程内容，再决定后续操作 |

本机进程锁串行协调该执行器，CLI 接收读取时的基准版本。跨机器或绕过执行器的并发由统一写入方协调。凭据保存在 CLI 凭据存储中。

## 内容与项目登记

项目页保存目标、当前状态、关键决定、下一步和证据入口。长期条目含稳定 ID、类型、范围、来源、日期、状态和版本；替代关系放在元数据中，正文呈现当前结论。用户明确反馈、实测、来源声明与推断分别标明。

新增项目记忆先在导航和限定目录搜索中检查现有条目，再通过官方技能创建项目概述、按需的详细状态页及目录；面向用户的项目正文按外部资源索引维护。回读并核对位置后，更新远程导航与本地配置：`folders` 保存目录链，`documents` 保存键名、token、url、parent，`projects` 将项目短名映射到概述键名，`topics` 同样映射学习主题；详细状态页独立登记。Wiki 登记见 [分层入口](wiki-navigation.md)。最后从其他工作目录运行 `begin --project PROJECT` 验证接续。

资源配置可根据远程导航与目录清单重建。快照和搜索响应是缓存，完成任务后可清理；保留支持重要结论的写入回执。用户配置、缓存和回执独立于源码仓库。
