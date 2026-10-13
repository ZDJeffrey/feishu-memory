# 首次配置与迁移

此流程由使用技能的 Agent 执行。运行 `python3 scripts/memory.py doctor` 检查安装和配置；命令路径以实际技能目录为准。以下命令中的 profile、目录和资源标识来自当前用户的选择与 CLI 实际返回。

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

有合适配置时复用它。CLI 提供的配置或授权链接按原样展示，并按官方技能配二维码；浏览器授权或管理员审批完成后再继续。采用官方技能的非阻塞/分步登录方式，以实际版本支持的参数为准。

初版只使用文档与云空间能力。验证用户身份的文档读写、目录清单和搜索权限；其中搜索使用 `search:docs:read`，目录读取使用 `space:document:retrieve`。已有应用需要补权限时按 CLI 返回的缺失项处理。密钥和令牌由 CLI 凭据存储管理。

## 连接已有记忆空间

用户迁移已有空间时，将其资源配置放在 `~/.config/feishu-memory/config.json`，或通过 `--config` 指定。核对 profile 和实际 CLI 路径，在新机器重新授权，然后运行 `begin`。本机锁只协调本机写入。

## 创建新的记忆空间

用户没有已有空间时，使用官方 `lark-drive` 和 `lark-doc` 工作流创建独立根目录，例如“Agent记忆系统”，在其中建立导航、协作准则、项目和系统维护目录。

创建两份短文档：导航保存各类入口及用途；核心准则保存用户已经明确表达的要求及来源。尚无偏好时记录待建立状态。项目页按实际任务创建，保存目标、状态、决定、下一步和证据。结构可参考 [文档骨架](templates.md)。

将 [配置模板](config.example.json) 中的字段替换为 CLI 返回的资源标识和 URL，保存到用户配置目录。`folders` 记录目录到父目录的链，`documents` 登记文档及直接父目录，`projects` 映射项目短名。创建和登记后用目录清单与文档回读核对归属。

执行 `begin`、一次限定目录搜索和一次章节读取。第一次实际任务完成时执行写回并检查回执，随后从另一个工作目录读取更新后的项目状态。

## 新对话发现

在仓库根目录运行 `python3 scripts/install.py --activate`，将技能安装到 Codex 的技能目录，并向全局 `AGENTS.md` 添加简短调用入口；原有指令保留。仅安装技能可省略 `--activate`，在对话中显式使用 `$feishu-memory`。

运行时配置、认证凭据、快照和回执留在用户环境；源码仓库包含通用技能和配置模板。发布前检查待提交文件清单。
