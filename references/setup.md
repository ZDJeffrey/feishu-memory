# 配置与连接

此流程由使用技能的 Agent 在首次任务中执行，完成后继续原任务。命令路径以实际技能目录为准；profile、目录和资源标识来自用户已有配置、明确选择及 CLI 实际返回。

先检查 `lark-cli` 是否在 PATH 中、本机配置 `~/.config/feishu-memory/config.json` 是否存在，再执行 `lark-cli --profile PROFILE auth status --json --verify` 核对授权。复用已配置的环境和有效授权，按检查结果补齐缺失项。

## 默认交互流程

用户安装技能并调用后，提供已有应用的 App ID。Agent 安装缺失的 CLI、选择 profile、生成终端配置命令；用户执行命令并隐藏输入 App Secret。Agent 核对应用配置后发起用户授权，用户在浏览器授权，Agent 完成登录、发现或建立记忆空间、写入本机配置、登记入口并验证。已有配置和有效授权直接复用，用户无需事先准备 profile 名称或配置文件。

## 安装飞书 CLI

CLI 不存在时，先读取 [larksuite/cli 官方 README](https://github.com/larksuite/cli/blob/main/README.zh.md) 的安装步骤，核对当前平台和环境要求。检查 Node.js、npm/npx；安装了版本管理器时先加载其环境。缺少运行时时依据官方要求安装，再继续。应用配置按下文选择复用或新建分支；README 的 `config init --new` 用于新建应用。

2026-10-15 核对的 npm 安装入口为：

```bash
npx @larksuite/cli@latest install
```

该入口安装 CLI 和配套技能。检查 `lark-cli --version`，并定位 `lark-shared`、`lark-doc`、`lark-drive`、`lark-wiki`、`lark-whiteboard`。Agent 的命令执行环境限制交互或网络安装时，请用户在本机终端运行该命令。后续安装以当前官方 README 和已安装版本帮助为准。

## 配置与授权

读取官方 `lark-shared` 技能及身份、配置和权限参考，核对当前版本的 `config init --help`、`profile list` 和 `auth login --help`。应用、用户登录和记忆空间分别配置：应用由 App ID 标识，CLI profile 是本机配置名，记忆空间由 `feishu-memory/config.json` 定位。

### 复用已有应用

本机已有目标 profile 时，核对其 App ID、品牌和授权状态后直接复用。应用尚未绑定时向用户索取 App ID，由 Agent 选择独立 profile，例如 `memory`；同名配置属于其他应用时选用另一个名称。换机器时沿用原应用，profile 名称按当前机器选择。

由 Agent 将下例的 App ID、profile 和 CLI 可执行路径替换为实际值，再交给用户直接运行。用户在该机器的交互终端隐藏输入 App Secret，通过标准输入交给 CLI；密钥由 CLI 管理，不进入聊天、命令参数、本机配置或仓库。以下示例适用于 Bash/Zsh，其他 shell 生成相应语法：

```bash
python3 - <<'PY'
import getpass
import subprocess

secret = getpass.getpass("App Secret: ")
result = subprocess.run(
    ["lark-cli", "config", "init", "--name", "memory", "--app-id", "<APP_ID>", "--app-secret-stdin", "--brand", "feishu"],
    input=secret + "\n",
    text=True,
)
raise SystemExit(result.returncode)
PY
```

`--name` 创建或更新 Agent 选定的 profile，本机配置记录该名称。用户完成终端操作后，Agent 用 `lark-cli profile list` 核对应用和 profile，再进入用户登录步骤。原应用已开通的权限可以继续使用，新增权限按 CLI 返回的缺失项处理。

### 新建应用

用户明确需要新建应用时，执行 `lark-cli config init --name memory --new`，按官方技能引导完成配置和审批。默认流程使用用户提供的已有 App ID。

### 用户登录与验证

应用绑定完成后，新机器通过原飞书账号完成用户授权：

```bash
lark-cli --profile memory auth login --domain docs,drive,wiki --no-wait --json
```

按官方技能的分步流程先展示授权链接和二维码，提醒用户核对授权页上的验证码，并在本轮结束、等待用户确认。用户完成后用本次返回的 `device_code` 执行 `lark-cli --profile memory auth login --device-code <DEVICE_CODE>`，再运行 `lark-cli --profile memory auth status --json --verify`。已有有效登录时直接验证。每台机器独立完成登录；访问令牌和刷新令牌由该机器的 CLI 管理，刷新令牌过期后重新执行授权。

Wiki 分层入口使用文档、云空间和知识库能力。验证用户身份的文档读写、目录清单和搜索权限；其中搜索使用 `search:docs:read`，目录读取使用 `space:document:retrieve`。已有应用需要补权限时按 CLI 返回的缺失项处理。

## 自动发现与连接记忆空间

授权完成后由 Agent 执行：

1. 用户提供 Wiki 入口时优先解析；本机已有配置时核验后复用。同一应用下须由具有知识库访问权限的用户登录。
2. 未指定入口时，按标题搜索自己拥有的“知识与协作入口”：`lark-cli --profile PROFILE drive +search --as user --query '知识与协作入口' --only-title --mine --doc-types docx --page-size 5`。保持查询条件检查分页，最多 3 页；去除标题高亮后严格匹配。唯一有效候选自动连接，多个候选请用户选择。认证、权限或未完成分页的问题按实际返回处理；已知空间无法定位时请求入口链接。
3. 用 `wiki +node-get --node-token NODE` 解析候选，取得 `space_id`、节点和内容对象，确认其为 docx 根节点；用 `wiki +node-list` 列出首页下一层，定位“核心协作准则 · 摘要”。
4. 按 [配置模板](config.example.json) 写入 `~/.config/feishu-memory/config.json`：profile、Wiki 的 `space_id`、根节点与 URL、核心摘要的节点与 URL。项目与主题不写入本机配置，由首页与各目录树维护。
5. 读取核心摘要与首页，再读取一个项目或主题概述、执行一次限定空间搜索和一次章节读取，确认路径可用；运行 `python3 scripts/mirror.py pull` 建立本地副本后继续原任务。

检索正常且确认没有已有空间时，按下一节创建。配置可通过 `FEISHU_MEMORY_CONFIG` 指定；应用凭据与用户令牌由各机器的 CLI 独立管理。

## 创建新的记忆空间

用户没有已有空间时，按 [Wiki 分层入口](wiki-navigation.md) 建立私有 Wiki、短首页与核心摘要，以及按需扩展的分类索引。通用记忆正文直接在 Wiki 维护；项目与学习主题按需在知识库根目录建立同级目录树。

Wiki 首页使用稳定标题“知识与协作入口”，核心摘要保存已经确认的常用规则；完整偏好与项目状态按需链接。尚无偏好时记录待建立状态；概述与详细状态分别维护，结构见 [Wiki 分层入口](wiki-navigation.md)。

创建后用节点列表与文档回读核对归属与权限，再写入本机配置并执行上一节第 5 步的验证。第一次实际任务完成时执行写回并回读。

## 新对话发现

原生按描述发现技能的 Agent（如 Claude Code）安装技能后即可使用，无需额外登记。通过 `AGENTS.md` 读取全局指令的 Agent（如 Codex）首次调用本技能时，执行当前技能目录的安装器登记全局入口：

```bash
python3 scripts/install.py --activate-only
```

该模式保留当前技能安装位置，适用于 `npx skills add`、技能安装器或手动安装。入口按照 [Codex 指令发现规则](https://developers.openai.com/codex/guides/agents-md) 写入 `${CODEX_HOME:-~/.codex}` 下生效的 `AGENTS.override.md`（存在且非空时）或 `AGENTS.md`，只更新本技能的标记区并保留其他指令；重复执行保持同一入口。`--codex-home` 可指定其他使用同类机制的目录。用户明确限定仅本次使用时省略登记。

从源码仓库安装到 Codex 技能目录可运行 `python3 scripts/install.py --activate`。

本机配置、认证凭据和临时文件留在用户环境；源码仓库包含通用技能和配置模板。发布前检查待提交文件清单。
