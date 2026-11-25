# 读写操作

主 Agent 直接调用 `mirror.py` 与 `lark-cli`。以下命令中 `PROFILE`、`SPACE_ID` 取自 `~/.config/feishu-memory/config.json`；调用 `lark-cli` 时 `--profile PROFILE` 放在子命令前，`--as user` 放在子命令后（下表省略）。参数细节以官方 `lark-doc`、`lark-wiki`、`lark-whiteboard` 技能及 `--help` 为准。

## 本地工作目录

飞书草稿、下载资源、预览和临时 `.mmd`/`.xml` 文件统一放在系统临时目录（如 `/tmp`）。使用 `docs +script --command init-draft` 前，显式将命令工作目录设为系统临时目录，使生成的 `draft_*_folder` 落在项目目录之外；`--content @./file` 仅接受当前工作目录下的相对路径。

## 懒加载缓存（`mirror.py`）

`scripts/mirror.py` 维护 `~/.cache/feishu-memory/<space_id>` 下的轻量 Markdown 缓存与实时目录树 `TREE.md`。

| 命令 | 作用 |
| --- | --- |
| `mirror.py sync` | 启动默认命令：并行同步目录树元数据，仅拉取有变化的核心规范页，并刷新 `TREE.md` |
| `mirror.py status` | 对比远端变更，列出新增、修改、移动与删除页面，不拉取正文 |
| `mirror.py pull --scope 目录` | 懒加载指定目录/子树下未缓存或有变更的页面（6 线程并发） |
| `mirror.py pull --doc 页面` | 强制刷新指定页面（支持 token、URL、路径或标题，可重复） |
| `mirror.py pull --summary` | 拉取全库所有未缓存或变更页面并输出简报 |
| `mirror.py locate 页面 文字` | 定位标题对应章节可用于 `block_replace` 的 block 范围，标出无 ID 列表与原生画板 |

本地缓存仅供只读检索（`rg` 与按行读取）。Markdown 导出不保留文字颜色、高亮块颜色与下划线，写回时必须基于远端 XML 操作。

## 远端读取与局部写回

修改前用 `mirror.py locate` 或 `docs +fetch --scope section --detail with-ids` 获取目标块最新 XML 与 `revision_id`；写入时务必传入 `--revision-id`。版本冲突时重新读取合并，每次结构变更后旧 block ID 失效。

| 操作 | 命令 |
| --- | --- |
| 按节读取 XML | `docs +fetch --doc DOC --scope section --start-block-id ID --detail with-ids` |
| 按关键词读取 | `docs +fetch --doc DOC --scope keyword --keyword 'a\|b' --context-after 1 --detail with-ids` |
| 替换块/章节 | `docs +update --doc DOC --command block_replace --start-block-id A --end-block-id B --revision-id REV --content @./part.xml` |
| 删除块/章节 | `docs +update --doc DOC --command block_delete --start-block-id A --end-block-id B --revision-id REV` |
| 锚点后插入 | `docs +update --doc DOC --command block_insert_after --block-id ANCHOR --revision-id REV --content @./part.xml` |
| 行内短文本替换 | `docs +update --doc DOC --command str_replace --pattern '旧' --content '新' --revision-id REV` |
| 整篇替换（需确认） | `block_replace --start-block-id 0 --end-block-id -1`，内容以 `<title>` 开头 |
| 移动 Wiki 节点 | `wiki +move --node-token NODE --target-space-id SPACE_ID --target-parent-token PARENT` |
| 移入云盘文档 | `wiki +move --obj-type docx --obj-token TOKEN --target-space-id SPACE_ID --target-parent-token PARENT` |
| 重命名页面 | `drive +update-title --url WIKI_URL --title 新标题` |

**写回约束**：
- **禁止表外追加**：含索引表或状态表的页面，新增或变更必须直接修改表格内部；日常同主题更新允许直接重写合并章节。
- **列表无 block ID**：替换范围两端均为具体 ID 时中间不能夹 `<ol>`/`<ul>`，需分段替换或以 `0`/`-1` 为端。
- **原生画板与附件保护**：非 Mermaid 原生画板与附件不可直接包含在替换范围内（否则丢失），需避开或先 `block_move_after` 移开。
- **回读与刷新**：写入后检查 `warnings`，用 `--detail full` 核对样式，并执行 `mirror.py pull --doc DOC` 更新本地缓存。

## 绘图：Mermaid 优先与画板适配

### 1. 默认通道：Mermaid 画板（优先选用）

流程图、状态机、调用时序、模块依赖和简明架构图统一使用 `<whiteboard type="mermaid">`，原生使用主题色并自动适配浅/深色模式，`mirror.py` 导出时自动还原为 ` ```mermaid ` 源码。

- **简单图内联写入**：在 XML 中写 `<whiteboard type="mermaid">...</whiteboard>`，注意转义 `<`、`>`、`&`（如 `-->` 写作 `--&gt;`）。
- **多箭头或复杂图文件传入（推荐）**：将 Mermaid 源码写入临时工作目录的 `diagram.mmd`，XML 写 `<whiteboard type="mermaid" path="@./diagram.mmd"></whiteboard>`，彻底免除 XML 转义错误。
- **更新已有画板**：`whiteboard +update --whiteboard-token TOKEN --input_format mermaid --source @./diagram.mmd --overwrite`。
- **注意**：将本地 Markdown 中的 ` ```mermaid ` 写回飞书时，必须转为 `<whiteboard type="mermaid">`，不要写成普通代码块 `<pre lang="mermaid">`。

### 2. 专业通道：DSL / SVG 原生画板（按需选用）

仅在需要水平多轨 Timeline、精确内存布局或复杂出版级架构总览图时使用。为保证深浅色模式可读，遵循以下适配流程：

1. 不画背景矩形；节点用中饱和色（蓝 `#5178C6`、绿 `#509863`、紫 `#8569CB`、红 `#D25D5A`）作边框和半透明填充（`opacity` 0.12–0.20）；不设置 `textColor`。
2. `npx -y @larksuite/whiteboard-cli@^0.2.13 -i diagram.json -o diagram.png --check` 校验溢出与重叠。
3. `--to openapi --format json` 转换后，将所有含 `text_color_type` 的对象改为 `text_color_type: 0`、`theme_text_color_code: -1`。
4. `whiteboard +update --input_format raw --source @./diagram.openapi.json --overwrite --idempotent-token ID` 写入，并用 `--output-type preview` 检查渲染结果。

## 文字颜色与回滚

- 文字与背景色一律使用命名色（如 `<span text-color="green">`、`<span background-color="light-yellow">`），随浅/深色模式自动切换，不写 RGB。
- 回滚：先用 `docs +history-list --doc DOC --page-size 20` 查版本，再执行 `docs +history-revert --doc DOC --history-version-id ID`（若返回 `running`，用 `+history-revert-status` 确认 `done`）并回读核对。
