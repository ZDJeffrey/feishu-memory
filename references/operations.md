# 读写操作

Terra 调用 `lark-cli` 并执行全部飞书远端操作。以下命令中 `PROFILE`、`SPACE_ID`、入口 URL 取自本机配置 `~/.config/feishu-memory/config.json`。读写记忆使用用户身份：`--profile PROFILE` 放在子命令之前，`--as user` 放在子命令之后，例如 `lark-cli --profile memory docs +fetch --doc URL --as user`；下表省略这两项。参数细节以官方 `lark-doc`、`lark-wiki`、`lark-drive`、`lark-whiteboard` 技能及 `--help` 为准；`--doc` 接受 Docx 或 Wiki 的 URL/token。

## 本地工作目录

飞书操作产生的草稿、资源下载、预览、校验结果和临时脚本放在项目目录之外的系统临时目录；只读记忆副本继续使用配置的缓存目录。需要交付到项目中的文件按用户指定位置保存。

新建文档按官方创作流程准备内容，并在初始化草稿时执行以下步骤：

1. 将命令执行工具的 `workdir` 或 `cwd` 设置为系统临时目录；macOS/Linux 可用 `/tmp`，其他平台使用实际系统临时目录。每次命令调用显式设置工作目录，不依赖上一次 shell 的 `cd`。
2. 在该目录运行 `lark-cli docs +script --command init-draft --presentation-decision '…'`，由 CLI 创建独占的 `draft_*_folder`；完整决策 JSON 按官方流程提供。
3. 读取返回的 `data.cwd`、`data.workspace` 和 `data.draft_path`，在对应路径写入草稿与新生成的资源；后续解析、上传与创建命令继续使用 `data.cwd`，相对文件路径以此为基准。
4. 按官方流程保留创作草稿；它们留在项目外的工作目录中。子 Agent 接收此目录约定，独立文档各自初始化草稿工作区。

局部更新可直接通过内联内容或 stdin 传入；需要落盘时也使用上述项目外目录。已有项目资源按允许的路径读取，新增中间文件写入草稿工作区。

## 本地副本

`scripts/mirror.py` 把记忆 Wiki 镜像为本地 Markdown，Terra 负责变化检测和拉取，主 Agent 读取本地文件。启动同步使用 `pull --summary`，Terra 返回状态、相关页面和异常；需要查看差异时按目标页面展开。

| 命令 | 作用 |
| --- | --- |
| `mirror.py status` | 遍历目录并批量查询修改时间，列出远端新增、修改、移动与删除的页面，不拉取 |
| `mirror.py pull --summary` | 只拉取有变化的页面并输出变更数量和副本路径；首次运行建立副本 |
| `mirror.py pull` | 拉取有变化的页面并输出差异（每页默认 40 行，`--diff-lines` 调整） |
| `mirror.py pull --doc 页面` | 强制刷新指定页面；页面可为节点或对象 token、URL、副本路径或标题，可重复 |
| `mirror.py checkout 页面` | 从本地镜像建立独立的 Markdown 工作目录，页面须唯一匹配且为 docx |
| `mirror.py work-status 目录` | 检查基线完整性、本地镜像漂移与画板引用，并输出工作副本差异 |
| `mirror.py locate 页面 文字` | 文字是标题时输出该节可用于 `block_replace` 的 block 范围，并标出没有 ID 的列表与原生画板；否则输出包含该文字的最内层 block；同时提示副本是否落后于远端 |

副本按 Wiki 层级存放：页面为 `<标题>.md`，子页面在同名目录下，文件头记录 URL、对象 token 与 revision；表格、多维表格、幻灯片和文件只保存元数据。副本只用于阅读，拉取会覆盖对应页面；目录可用 `--mirror` 或 `FEISHU_MEMORY_MIRROR` 指定。Markdown 不保留文字颜色与高亮块颜色，不能将工作副本直接作为完整富文档写回。

## 工作副本与冲突

1. Terra 定向刷新目标页后运行 `mirror.py checkout 页面`，在系统临时目录建立独立目录。`baseline.md` 是只读基线，`working.md` 是主 Agent 编辑的原生 Markdown，`task.json` 保存目标、基线 revision、哈希及画板原始标记；单页由一个执行者编辑。
2. Terra 运行 `mirror.py work-status 目录` 检查本地基线、镜像漂移和画板引用，并比较工作稿与基线。此命令只检查本地，输出全文差异，不读取远端或自动写回；Terra 给主 Agent 返回精简结果。
3. 写入前 Terra 读取远端最新内容和目标结构，按 baseline、working 与 remote 三方比较。远端未变时按最新 revision 局部写入；远端变化且改动互不重叠、目标明确时合并到最新内容；同处修改、目标删除或移动导致定位不明、资源与样式语义不明确时暂停，由主 Agent 判断。
4. Terra 用最新 `--revision-id` 执行最小局部修改，保留不涉及的资源；每次写入后重新读取 revision 和 block ID。版本冲突时重新读取并作三方比较；结果不明或部分成功时先回读，确认已完成范围后再继续，避免重复插入。写后核对文字、结构、链接及受影响资源，再定向刷新只读镜像。返回目标 URL、基线与最终 revision、修改范围、验证和待决事项。

## 画板资源

工作副本中可识别的独立画板标记转换为指向 `assets/<token>/description.md` 的普通 Markdown 链接，初始说明仅表示尚未读取；其他格式的画板标记保留原样。Terra 按需读取真实远端画板，维护 token、raw、可取得的源码、预览和语义说明；既有画板以远端内容为准，源码不一定可得，画板变化不能仅凭文档 revision 判断。主 Agent 按语义说明检索，在关键判断时查看预览。

新图或新文档交接时，主 Agent 在 `working.md` 中放置普通链接，例如 `[图示](assets/graph-switch/spec.md)`，并在该 spec 中写明用途、实体和关系、约束、布局形式及验收条件。Terra 根据说明绘制、创建并核验远端画板，记录实际 token 与预览的映射；本地交接链接须解析为对应远端画板，不能原样发布。已有但未识别的画板标记由 Terra 按远端结构处理，主 Agent 无需编辑 XML。画板、附件和复杂表格需按实际远端结构处理，不能仅凭 Markdown 差异自动替换。

## 读取远端

没有副本或需要核对样式时由 Terra 读取远端。读取内容用 `--doc-format markdown`，加 `--jq '.data.document.content'` 只输出正文；定位 block 时才用 `--detail with-ids`，核对样式时用 `--detail full`。


| 目的 | 命令 |
| --- | --- |
| 启动上下文 | `docs +fetch --doc CORE_URL`；`docs +fetch --doc HOME_URL`（已知项目或主题时以对应概述替换首页） |
| 列出当前层节点 | `wiki +node-list --space-id SPACE_ID --parent-node-token NODE --page-size 5` |
| 在记忆空间检索 | `drive +search --query '主题词' --space-ids SPACE_ID --page-size 5`；按标题定位加 `--only-title` |
| 确认搜索结果归属 | `wiki +node-get --node-token NODE`，按 `parent_node_token` 判断所属目录树（标题不带项目前缀） |
| 外部登记目录检索 | `drive +search --query '主题词' --folder-tokens FOLDER --page-size 5`，仅用于概述中登记的知识库外资料 |
| 按内容阅读 | `docs +fetch --doc DOC --doc-format markdown`，比 XML 少约 35%–55% 字符；`--scope keyword`/`section` 的返回带 `start-block-id`/`end-block-id`，可直接用于写回 |
| 长文档先看目录 | `docs +fetch --doc DOC --scope outline --max-depth 2` |
| 读取一节 | `docs +fetch --doc DOC --scope section --start-block-id HEADING_ID --detail with-ids` |
| 按关键词读取 | `docs +fetch --doc DOC --scope keyword --keyword 'a\|b' --context-after 1 --detail with-ids` |
| 查看外部文件夹 | `drive files list --params '{"folder_token":"FOLDER","page_size":50}'` |
| 移入知识库 | `wiki +move --obj-type docx --obj-token TOKEN --target-space-id SPACE_ID --target-parent-token NODE`；类型可为 docx、sheet、bitable、slides、file |
| 重命名页面 | `drive +update-title --url WIKI_URL --title 新标题`，适用于所有节点类型 |

启动正文合计约 4000 字符，常规展开单次约 12000 字符；超出时先读目录再选章节。搜索每页最多 5 条，翻页沿用同一查询和范围；新页面可能尚未进入索引，可先用节点列表定位。不要在记忆空间之外做账号全局搜索。Wiki 正文的 `--doc-types` 是 `docx`，不要用 `wiki` 筛选。

## 更新

每次写入前用 `--detail with-ids` 读取目标范围，记下返回的 `revision_id`，写入时以 `--revision-id` 传回；返回版本冲突时重新读取并合并，不覆盖他人修改。每次写入后旧 block ID 视为失效，基于新的读取结果继续。

| 更新类型 | 何时使用 | 命令 |
| --- | --- | --- |
| 替换 | 结论、状态或表述已变化，包括合并多段、改写整节 | `docs +update --command block_replace --block-id ID` 或 `--start-block-id A --end-block-id B` |
| 删除 | 内容已被取代、重复或失去保留价值 | `docs +update --command block_delete`，参数同上 |
| 新增 | 确属新主题或新章节 | `docs +update --command block_insert_after --block-id ANCHOR` |
| 移动 | 调整章节顺序或归属 | `docs +update --command block_move_after --block-id ANCHOR --src-block-ids IDS` |
| 行内修正 | 术语、数字等短文本 | `docs +update --command str_replace --pattern '旧' --content '新'` |

写入前找到事实的维护位置，将局部内容改写为完整的当前表述，并清理本次变化直接影响的旧状态与重复；相关概述按需摘要并链接详细内容。用户要求阶段整理时，通读相关文档并完整重组。比较、映射与字段用表格；流程、架构、时序和依赖用画板，在 XML 中写 `<whiteboard type="mermaid">…</whiteboard>`，复杂图按官方 `lark-doc` 画板流程处理。内容取舍、写法与飞书格式见记忆空间中的写作规范。

`overwrite` 会重建正文与 block ID，可能丢失评论和画板等资源，仅在用户确认整篇重建时使用。写入后检查返回的 `result` 与 `warnings`，按影响范围回读核对文字、结构、链接与资源块，并检查当前状态是否矛盾、条件是否重复、段落是否混题及内容能否独立理解。

## 大幅修改：本地草稿

重构一节或整篇时，在本地编辑完整 XML 再写回，比逐 block 调用更可靠：

1. 在系统临时目录下创建本任务的独占工作目录，并在每次命令调用中显式设置该工作目录；`docs +fetch --doc DOC --detail full` 拉取 XML 与 `revision_id`，保留原文件作对照。
2. 用文件编辑工具修改；新内容不需要 block ID，原有资源块按下述规则处理。
3. 对比新旧文件确认删改范围，再用 `block_replace` 写回，`--content @./draft.xml` 只接受工作目录内的相对路径，且工作目录不能位于 `/root` 等受保护目录；也可用 `--content -` 经标准输入传入。
4. 以 `--detail full` 回读，核对结构、样式与资源块。

| 规则 | 说明 |
| --- | --- |
| 整篇替换 | `--start-block-id 0 --end-block-id -1`，内容须以 `<title>` 开头 |
| 列表没有 block ID | 范围两端为具体 ID 时中间不能夹 `<ol>`/`<ul>`；改用 `0` 或 `-1` 作为一端，或分段替换 |
| 原生画板与附件 | 非 Mermaid 画板按 token 复制会失败，附件重新上传代价大；把它们留在替换范围之外，或先 `block_move_after` 移开再替换 |
| Mermaid 画板 | 源码在 XML 内，可随替换重建 |
| XML 与 Markdown | 富格式用 XML 写入；Markdown 导入与导出会丢失下划线、文字高亮与高亮块颜色 |
| 样式核对 | 默认 `simple` 读取不含样式，核对高亮、颜色时用 `--detail full` |

## 文字颜色与画板主题

文字颜色与背景色使用命名色：`<span text-color="green">`、`<span background-color="light-yellow">`，可嵌套在 `<b>` 内组合使用；命名色随浅色与深色模式切换，不要写 rgb 值。

画板颜色在 raw 节点中分两类：`*_color_type` 为 0 是主题色，深色模式下自动映射；为 1 是固定色。Mermaid 生成的节点全部是主题色，可直接使用。DSL 或 SVG 指定的颜色都是固定色，且 DSL 一旦设置 `fillColor` 就把节点文字固定为深色，深色模式下难以阅读。DSL 画板按以下步骤生成：

1. 不画背景矩形；节点用中饱和色作 `fillColor` 与 `borderColor`，`rect`/`ellipse` 设 `opacity` 0.12–0.2（`frame` 不支持 `opacity`，需在转换后的 JSON 中设置 `fill_opacity`）；不写 `textColor`。
2. `npx -y @larksuite/whiteboard-cli@^0.2.13 -i diagram.json -o diagram.png` 预览，`--check` 检查溢出与重叠。
3. `--to openapi --format json` 转换后，把所有含 `text_color_type` 的对象改为 `text_color_type: 0`、`theme_text_color_code: -1`：

   ```python
   def theme_text(o):
       if isinstance(o, dict):
           if 'text_color_type' in o:
               o['text_color_type'], o['theme_text_color_code'] = 0, -1
           for v in o.values(): theme_text(v)
       elif isinstance(o, list):
           for v in o: theme_text(v)
   ```

4. `whiteboard +update --input_format raw --source @./diagram.openapi.json --overwrite --idempotent-token ID` 写入；画板刚创建时可能返回 not ready，稍后重试。
5. `whiteboard +export --output-type raw` 确认没有 `text_color_type: 1` 与 `#ffffff` 填充，`--output-type preview` 检查服务端渲染结果。

## 回滚

1. `docs +history-list --doc DOC --page-size 20` 列出历史，按 `revision_id` 或 `edit_time` 选定目标记录。
2. `docs +history-revert --doc DOC --history-version-id ID`；返回 `running` 时用 `+history-revert-status` 查询，只有 `done` 表示成功。
3. 回读核对。大幅重组前记下当前 `revision_id`，便于定位回滚点。

## 内容与项目登记

项目页保存目标、当前状态、关键决定、下一步和证据入口。长期条目含稳定 ID、类型、范围、来源、日期、状态和版本；替代关系放在元数据中，正文呈现当前结论。用户明确反馈、实测、来源声明与推断分别标明。

新增项目先在项目索引与限定空间搜索中检查已有条目，再在知识库根目录创建项目概述作为树根，按需建立子页面；回读核对后在首页与项目索引页登记。学习主题同样处理。知识库之外的资料在概述的资源索引中登记入口与读写范围。本机配置不登记单篇文档。
