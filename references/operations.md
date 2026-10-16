# 读写操作

Agent 直接调用 `lark-cli`。以下命令中 `PROFILE`、`SPACE_ID`、入口 URL 取自本机配置 `~/.config/feishu-memory/config.json`。读写记忆使用用户身份：`--profile PROFILE` 放在子命令之前，`--as user` 放在子命令之后，例如 `lark-cli --profile memory docs +fetch --doc URL --as user`；下表省略这两项。参数细节以官方 `lark-doc`、`lark-wiki`、`lark-drive`、`lark-whiteboard` 技能及 `--help` 为准；`--doc` 接受 Docx 或 Wiki 的 URL/token。

## 读取

| 目的 | 命令 |
| --- | --- |
| 启动上下文 | `docs +fetch --doc CORE_URL`；`docs +fetch --doc HOME_URL`（已知项目或主题时以对应概述替换首页） |
| 列出当前层节点 | `wiki +node-list --space-id SPACE_ID --parent-node-token NODE --page-size 5` |
| 在记忆空间检索 | `drive +search --query '主题词' --space-ids SPACE_ID --page-size 5`；按标题定位加 `--only-title` |
| 在资料目录检索 | `drive +search --query '主题词' --folder-tokens FOLDER --page-size 5`，FOLDER 取自概述中的资源索引 |
| 长文档先看目录 | `docs +fetch --doc DOC --scope outline --max-depth 2` |
| 读取一节 | `docs +fetch --doc DOC --scope section --start-block-id HEADING_ID --detail with-ids` |
| 按关键词读取 | `docs +fetch --doc DOC --scope keyword --keyword 'a\|b' --context-after 1 --detail with-ids` |
| 查看文件夹 | `drive files list --params '{"folder_token":"FOLDER","page_size":50}'` |

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

先选替换与删除：同一主题只保留一份当前表述，被取代的内容直接改写或删去，不在原文旁追加修订说明，也不按“第 N 轮”“本轮”逐次追加章节。比较、映射与字段用表格；流程、架构、时序和依赖用画板，在 XML 中写 `<whiteboard type="mermaid">…</whiteboard>`，复杂图按官方 `lark-doc` 画板流程处理。写法与飞书格式见记忆空间中的写作规范（存在时）。

`overwrite` 会重建正文与 block ID，可能丢失评论和画板等资源，仅在用户确认整篇重建时使用。写入后检查返回的 `result` 与 `warnings`，再按影响范围回读核对文字、结构、链接与资源块。

## 大幅修改：本地草稿

重构一节或整篇时，在本地编辑完整 XML 再写回，比逐 block 调用更可靠：

1. 在 `/tmp` 下建工作目录并进入；`docs +fetch --doc DOC --detail full` 拉取 XML 与 `revision_id`，保留原文件作对照。
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

新增项目先在项目索引与限定空间搜索中检查已有条目，再通过官方技能创建 Wiki 概述、按需的详细状态页及平级资料文件夹。概述的资源索引登记资料入口、用途、读取范围与可写位置；回读核对后更新项目索引页。学习主题同样处理。资源位置以远程索引为准，本机配置不登记单篇文档。
