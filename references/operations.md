# 读写操作

从当前任务目录运行技能内的 `scripts/memory.py`，路径按实际安装位置解析。配置通过 `--config PATH` 或 `FEISHU_MEMORY_CONFIG` 指定，默认 `~/.config/feishu-memory/config.json`。快照和回执默认保存到当前目录的 `.feishu-memory/`，可用 `--state-dir PATH` 改变。

```text
python3 SKILL_DIR/scripts/memory.py doctor
python3 SKILL_DIR/scripts/memory.py begin
python3 SKILL_DIR/scripts/memory.py begin --project PROJECT
python3 SKILL_DIR/scripts/memory.py search '项目名 主题词'
python3 SKILL_DIR/scripts/memory.py read KEY --section '章节名'
```

`read KEY` 返回目录，`--section` 精确匹配标题，`--keyword` 按关键词读取，`--full` 用于确需通读的短文档。KEY 来自配置中的 `documents`。返回 `snapshot`、`revision` 和当前 block ID；`outline_only=true` 时按目录继续缩小范围。

`search` 限定配置的根目录，每页最多 5 条，返回 `has_more` 和 `page_token`。通常检查一页，依据不足时最多继续两页，再调整主题词。新文档可能尚未被索引，可按创建响应直接读取；未登记文档使用官方 CLI 读取，登记其目录链后再用脚本写入。

## 更新

读取目标章节，把完整的新 XML 文本块保存到任务目录，并提供真实来源位置：

```text
python3 SKILL_DIR/scripts/memory.py replace KEY --snapshot SNAPSHOT --block-id BLOCK --xml FILE --source SOURCE
```

`--dry-run` 生成预览回执。执行器支持同类型 `p`、`li`、`h1`–`h4` 的完整替换；复杂资源、评论、表格和新章节使用官方 `lark-doc` 工作流。写入回执保存来源、前后内容、基准版本、结果和回读内容。

| 结果 | 后续动作 |
| --- | --- |
| `verified` | 更新已回读，继续下一项或交付 |
| `unchanged` | 正文相同，已跳过写入 |
| `conflict`，退出码 2 | 重新读取并合并当前内容 |
| `write_requested` / `readback_required` / `review_required` | 核对回执和远程内容，再决定后续操作 |

本机进程锁串行协调该执行器，CLI 接收读取时的基准版本。跨机器或绕过执行器的并发由统一写入方协调。凭据保存在 CLI 凭据存储中。

## 内容与项目登记

项目页保存目标、当前状态、关键决定、下一步和证据入口。长期条目含稳定 ID、类型、范围、来源、日期、状态和版本；替代关系放在元数据中，正文呈现当前结论。用户明确反馈、实测、来源声明与推断分别标明。

新增项目先在导航和限定目录搜索中检查现有条目，再通过官方技能创建独立项目文件夹和状态页。回读并核对位置后，更新远程导航与本地配置：`folders` 保存目录链，`documents` 保存键名、token、url、parent，`projects` 将项目短名映射到文档键名。最后从其他工作目录运行 `begin --project PROJECT` 验证接续。

资源配置可根据远程导航与目录清单重建。快照和搜索响应是缓存，完成任务后可清理；保留支持重要结论的写入回执。用户配置、缓存和回执独立于源码仓库。
