# 首次配置与迁移

此流程由使用技能的 Agent 在首次任务中执行，完成后继续原任务。命令路径以实际技能目录为准；profile、目录和资源标识来自用户已有配置、明确选择及 CLI 实际返回。

先检查 Python 3.9+，缺少时安装当前平台适用的运行时，再执行 `python3 scripts/memory.py doctor`。Windows 可用 `py -3`。复用已配置的环境和有效授权，按检查结果补齐缺失项。

## 默认交互流程

用户通过 `npx` 安装技能并调用后，提供已有应用的 App ID。Agent 安装缺失的 CLI、选择 profile、生成终端配置命令；用户执行命令并隐藏输入 App Secret。Agent 核对应用配置后发起用户授权，用户在浏览器授权，Agent 完成登录、发现或建立记忆空间、生成本机资源配置、登记入口并验证。已有配置和有效授权直接复用，用户无需事先准备 profile 名称或资源配置文件。

## 安装飞书 CLI

CLI 不存在时，先读取 [larksuite/cli 官方 README](https://github.com/larksuite/cli/blob/main/README.zh.md) 的安装步骤，核对当前平台和环境要求。检查 Node.js、npm/npx；安装了版本管理器时先加载其环境。缺少运行时时依据官方要求安装，再继续。应用配置按下文选择复用或新建分支；README 的 `config init --new` 用于新建应用。

2026-10-13 核对的 npm 安装入口为：

```bash
npx @larksuite/cli@latest install
```

该入口安装 CLI 和配套技能。检查 `lark-cli --version`，并定位 `lark-shared`、`lark-doc`、`lark-drive`。安装路径未进入当前执行环境时使用实际返回的路径或设置 `FEISHU_MEMORY_CLI`。后续安装以当前官方 README 和已安装版本帮助为准。

## 配置与授权

读取官方 `lark-shared` 技能及身份、配置和权限参考，核对当前版本的 `config init --help`、`profile list` 和 `auth login --help`。应用、用户登录和记忆空间分别配置：应用由 App ID 标识，CLI profile 是本机配置名，记忆资源由 `feishu-memory/config.json` 定位。

### 复用已有应用

本机已有目标 profile 时，核对其 App ID、品牌和授权状态后直接复用。应用尚未绑定时向用户索取 App ID，由 Agent 选择独立 profile，例如 `memory`；同名配置属于其他应用时选用另一个名称。换机器时沿用原应用，profile 名称按当前机器选择。

由 Agent 将下例的 App ID、profile 和 CLI 可执行路径替换为实际值，再交给用户直接运行。用户在该机器的交互终端隐藏输入 App Secret，通过标准输入交给 CLI；密钥由 CLI 管理，不进入聊天、命令参数、资源配置或仓库。以下示例适用于 Bash/Zsh，其他 shell 生成相应语法：

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

`--name` 创建或更新 Agent 选定的 profile，后续资源配置记录该名称。用户完成终端操作后，Agent 核对应用和 profile，再进入用户登录步骤。原应用已开通的权限可以继续使用，新增权限按 CLI 返回的缺失项处理。

### 新建应用

用户明确需要新建应用时，执行 `lark-cli config init --name memory --new`，按官方技能引导完成配置和审批。默认流程使用用户提供的已有 App ID。

### 用户登录与验证

应用绑定完成后，新机器通过原飞书账号完成用户授权：

```bash
lark-cli --profile memory auth login --domain docs,drive,wiki --no-wait --json
```

按官方技能的分步流程先展示授权链接和二维码，用户完成后用本次返回的 `device_code` 执行 `lark-cli --profile memory auth login --device-code <DEVICE_CODE>`，再运行 `lark-cli --profile memory auth status --json --verify`。已有有效登录时直接验证。每台机器独立完成登录；访问令牌和刷新令牌由该机器的 CLI 管理。

Wiki 分层入口使用文档、云空间和知识库能力。验证用户身份的文档读写、目录清单和搜索权限；其中搜索使用 `search:docs:read`，目录读取使用 `space:document:retrieve`。已有应用需要补权限时按 CLI 返回的缺失项处理。密钥和令牌由 CLI 凭据存储管理。

## 自动发现与连接记忆空间

授权完成后由 Agent 执行：

1. 有用户指定的配置、默认配置或入口时，核对后连接。资源配置的 `profile` 使用本机实际选定值，导航中记录的旧机器 profile 和 CLI 路径按环境信息处理。
2. 缺少资源配置时，先按标题搜索自己拥有的“知识与协作入口”（--only-title --mine），每页 5 条、最多 3 页；解析候选节点与空间，读取首页和核心摘要，按 [Wiki 分层入口](wiki-navigation.md) 重建必要配置。多个有效入口时请用户选择。没有 Wiki 候选时，读取官方 `lark-drive` 搜索参考，以已授权用户身份查找自己拥有的“记忆系统入口”，例如 `lark-cli --profile memory drive +search --as user --query '记忆系统入口' --only-title --mine --doc-types docx --page-size 5`。保持查询条件检查分页，最多 3 页，去除标题高亮后严格匹配；检索未完成时保留未决状态。
3. 读取原 Drive 候选入口；若其中指向新的 Wiki 首页，先解析并核验该入口。取得独立根目录和核心准则链接，只列举验证这些资源及当前项目所需的目录。核对真实目录链、导航和核心准则；完整检索后只有一个有效候选时自动连接，多个候选时请用户选择。
4. 没有入口候选时，再按标题查找自己拥有的“Agent记忆系统”文件夹，并检查其导航与核心准则。首次建立任务中，检索正常且没有有效空间时按下一节创建；已知迁移任务仍未定位到原空间时，请用户提供入口链接。认证、权限错误或未完成的分页先处理相应问题。
5. 按 [配置模板](config.example.json) 生成 `~/.config/feishu-memory/config.json`，登记实际 profile、根目录、必要目录链、`navigation`、`core` 和当前项目入口；其他内容按需登记。运行 `begin`、范围搜索和章节读取，验证后继续原任务。

用户也可私下迁移已有资源配置，或通过 `--config` 指定位置；这是可选方式。配置保存资源位置，不包含 App Secret 或用户令牌。CLI 的用户登录由各机器独立完成，本机锁只协调本机写入。

## 创建新的记忆空间

用户没有已有空间时，按 [Wiki 分层入口](wiki-navigation.md) 建立私有 Wiki、短首页与核心摘要，以及按需扩展的分类索引。另以独立 Drive 根目录保存详细记忆和维护产物，记忆正文通过 Wiki 索引定位。现有 Drive 结构可继续使用，启用 Wiki 时创建索引与概述并保留正文位置。

Wiki 首页使用稳定标题“知识与协作入口”，核心摘要保存已经确认的常用规则；完整偏好与项目状态按需链接。原 Drive“记忆系统入口”可作为旧机器接续的定位页，指向 Wiki 首页。尚无偏好时记录待建立状态；概述与详细状态分别维护，结构见 [Wiki 分层入口](wiki-navigation.md)。

将 [配置模板](config.example.json) 中的字段替换为 CLI 返回的资源标识和 URL，保存到用户配置目录。`folders` 记录目录到父目录的链，`documents` 登记文档及直接父目录，`projects` 映射项目短名。创建和登记后用目录清单与文档回读核对归属。

执行 `begin`、一次限定目录搜索和一次章节读取。第一次实际任务完成时执行写回并检查回执，随后从另一个工作目录读取更新后的项目状态。

## 新对话发现

首次在 Codex 中调用本技能时，执行当前技能目录的安装器登记全局入口：

```bash
python3 scripts/install.py --activate-only
```

该模式保留当前技能安装位置，适用于 `npx skills add`、Codex 技能安装器或手动安装。入口按照 [Codex 指令发现规则](https://developers.openai.com/codex/guides/agents-md) 写入 `${CODEX_HOME:-~/.codex}` 下生效的 `AGENTS.override.md`（存在且非空时）或 `AGENTS.md`，只更新本技能的标记区并保留其他指令；重复执行保持同一入口。用户明确限定仅本次使用时省略登记。

从源码仓库安装到 Codex 技能目录可运行 `python3 scripts/install.py --activate`。后续对话直接使用 `$feishu-memory` 加任务描述，或按全局入口在相关任务中调用。

运行时配置、认证凭据、快照和回执留在用户环境；源码仓库包含通用技能和配置模板。发布前检查待提交文件清单。
