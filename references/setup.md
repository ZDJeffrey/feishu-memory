# 首次配置与迁移

此流程由使用技能的 Agent 在首次任务中执行，完成后继续原任务。命令路径以实际技能目录为准；profile、目录和资源标识来自用户已有配置、明确选择及 CLI 实际返回。

先检查 Python 3.9+，缺少时安装当前平台适用的运行时，再执行 `python3 scripts/memory.py doctor`。Windows 可用 `py -3`。复用已配置的环境和有效授权，按检查结果补齐缺失项。

## 安装飞书 CLI

CLI 不存在时，先读取 [larksuite/cli 官方 README](https://github.com/larksuite/cli/blob/main/README.zh.md) 的 AI Agent 快速开始，核对当前平台和环境要求。检查 Node.js、npm/npx；安装了版本管理器时先加载其环境。缺少运行时时依据官方要求安装，再继续。

2026-10-13 核对的 npm 安装入口为：

```bash
npx @larksuite/cli@latest install
```

该入口安装 CLI 和配套技能。检查 `lark-cli --version`，并定位 `lark-shared`、`lark-doc`、`lark-drive`。安装路径未进入当前执行环境时使用实际返回的路径或设置 `FEISHU_MEMORY_CLI`。后续安装以当前官方 README 和已安装版本帮助为准。

## 配置与授权

读取官方 `lark-shared` 技能及身份、配置和权限参考。复用用户选择的 CLI profile；新配置使用独立 profile，例如 `memory`。执行前核对当前版本的帮助，按官方流程配置应用并取得用户授权：

```bash
lark-cli --profile memory config init --new
lark-cli --profile memory auth login --domain docs,drive
lark-cli --profile memory auth status --json --verify
```

有合适配置时复用它。CLI 提供的配置或授权链接按原样展示，并按官方技能配二维码；浏览器授权或管理员审批完成后，校验状态并恢复原任务。采用官方技能的非阻塞/分步登录方式，以实际版本支持的参数为准。

初版只使用文档与云空间能力。验证用户身份的文档读写、目录清单和搜索权限；其中搜索使用 `search:docs:read`，目录读取使用 `space:document:retrieve`。已有应用需要补权限时按 CLI 返回的缺失项处理。密钥和令牌由 CLI 凭据存储管理。

## 连接已有记忆空间

先检查用户指定的配置和默认配置文件。已有配置时核对 profile、实际 CLI 路径和授权，再运行 `begin`。迁移配置默认放在 `~/.config/feishu-memory/config.json`，也可通过 `--config` 指定。

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
