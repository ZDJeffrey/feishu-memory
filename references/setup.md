# 首次配置与迁移

此流程由使用技能的 Agent 在首次任务中执行，完成后继续原任务。命令路径以实际技能目录为准；profile、目录和资源标识来自用户已有配置、明确选择及 CLI 实际返回。

先检查 Python 3.9+，缺少时安装当前平台适用的运行时，再执行 `python3 scripts/memory.py doctor`。Windows 可用 `py -3`。复用已配置的环境和有效授权，按检查结果补齐缺失项。

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

本机已有目标 profile 时，核对其 App ID、品牌和授权状态后直接复用。换机器时优先绑定原应用；用户尚未说明应用来源时，询问是否已有应用及其 App ID。缺少本机 CLI 配置只说明需要绑定应用。

由用户在新机器的交互终端安全输入原应用的 App Secret，通过标准输入交给 CLI；密钥留在终端和 CLI 凭据存储中，不进入聊天、命令参数、资源配置或仓库。以下示例使用 Python 的隐藏输入，替换 App ID 和 profile 后交给用户在该机器终端执行：

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

`--name` 创建或更新指定 profile；名称应与资源配置中的 `profile` 一致。现有同名 profile 指向其他应用时，先保留它并选用另一个名称。原应用已开通的权限可以继续使用，新增权限按 CLI 返回的缺失项处理。

### 新建应用

用户没有可复用应用，或明确需要独立应用时，执行 `lark-cli config init --name memory --new`，按官方技能引导完成配置和审批。

### 用户登录与验证

应用绑定完成后，新机器通过原飞书账号完成用户授权：

```bash
lark-cli --profile memory auth login --domain docs,drive --no-wait --json
```

按官方技能的分步流程先展示授权链接和二维码，用户完成后用本次返回的 `device_code` 执行 `lark-cli --profile memory auth login --device-code <DEVICE_CODE>`，再运行 `lark-cli --profile memory auth status --json --verify`。已有有效登录时直接验证。每台机器独立完成登录；访问令牌和刷新令牌由该机器的 CLI 管理。

初版只使用文档与云空间能力。验证用户身份的文档读写、目录清单和搜索权限；其中搜索使用 `search:docs:read`，目录读取使用 `space:document:retrieve`。已有应用需要补权限时按 CLI 返回的缺失项处理。密钥和令牌由 CLI 凭据存储管理。

## 连接已有记忆空间

先检查用户指定的配置和默认配置文件。迁移时将原机器的 `~/.config/feishu-memory/config.json` 私下复制到新机器的同一路径，也可通过 `--config` 指定。此文件保存 profile、目录、文档和项目入口，不包含 App Secret 或用户令牌；应用绑定与用户登录按上一节完成。核对 profile 与新机器的 CLI 配置一致，配置含可选 `cli` 路径时按新机器调整，再运行 `begin` 验证连接到原空间。

用户提供飞书入口时，读取导航与有关目录清单，按返回的资源标识重建配置。既无配置也无已选入口时，只询问连接已有空间还是创建独立空间；用户已经明确选择时直接执行。本机锁只协调本机写入。

## 创建新的记忆空间

用户没有已有空间时，使用官方 `lark-drive` 和 `lark-doc` 工作流创建独立根目录，例如“Agent记忆系统”，在其中建立导航、协作准则、项目和系统维护目录。

创建两份短文档：导航保存各类入口及用途；核心准则保存用户已经明确表达的要求及来源。尚无偏好时记录待建立状态。项目页按实际任务创建，保存目标、状态、决定、下一步和证据。结构可参考 [文档骨架](templates.md)。

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
