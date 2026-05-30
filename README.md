# ygo-ai CLI

YGOPro Lua 卡牌脚本开发 CLI — 三层架构中的"手"（Hands）层。

## 架构

```
Vault (脑)  → Obsidian 知识库：OCG 规则、效果描述规范、Lua 编卡知识
CLI   (手)  → 本工具：无状态的数据查询和诊断工具
Skills(神经) → Claude Code 技能：工作流编排器
```

CLI 只提供无状态工具，不含知识、不含 AI 决策。所有 AI 生成由 Skills 层处理。

## 安装

### 前置条件

- Python 3.10+
- Bun（用于 Lua 诊断引擎）

```bash
# 安装 Bun
curl -fsSL https://bun.sh/install | bash

# 安装 CLI
pip install ygo-ai-cli
```

### 初始化

```bash
ygo-ai setup
ygo-ai data update
```

## 命令

### `ygo-ai from-cdb` — 卡牌数据库查询

浏览和搜索 `.cdb` 卡牌数据库。

```bash
# 列出前 50 张卡
ygo-ai from-cdb

# 按密码查看单卡
ygo-ai from-cdb --code 89631139

# 按关键词搜索
ygo-ai from-cdb --search "黑魔导"

# 指定数据库路径
ygo-ai from-cdb --db-path /path/to/cards.cdb --search "青眼"

# JSON 输出
ygo-ai from-cdb --search "青眼" --json
```

### `ygo-ai diagnose` — Lua 脚本诊断

对 Lua 脚本进行静态分析，检查常见错误。

```bash
ygo-ai diagnose -s path/to/script.lua
```

### `ygo-ai data` — 数据管理

下载和管理官方卡牌数据。

```bash
# 下载所有数据（cdb + strings + banlist + scripts + pics）
ygo-ai data update

# 只下载 CDB
ygo-ai data update --type cdb

# 只下载卡图
ygo-ai data update --type pics

# 下载指定卡牌的卡图
ygo-ai data update --type pics --cards-codes 89631139,10000

# 预览下载内容
ygo-ai data update --dry-run

# 查看当前数据状态
ygo-ai data info

# 查看数据源
ygo-ai data sources
```

### `ygo-ai setup` — 初始化配置

创建 `~/.ygo-ai/config.jsonc` 默认配置文件。

```bash
ygo-ai setup
ygo-ai setup --force  # 覆盖已有配置
```

## 配置

配置优先级（从高到低）：

1. CLI 参数（`--db-path`、`--script-dir`、`--pics-dir`）
2. 环境变量（`YGO_AI_DB_PATH`、`YGO_AI_SCRIPT_DIR`、`YGO_AI_PICS_DIR`）
3. 用户配置文件（`~/.ygo-ai/config.jsonc`）
4. 内置默认配置（`config.jsonc`）

### 配置文件示例

```jsonc
{
  // 卡牌数据库路径
  "default_db_path": "~/.ygo-ai/data/cards.cdb",
  // Lua 脚本目录
  "default_script_dir": "~/.ygo-ai/scripts",
  // 卡图目录
  "default_pics_dir": "~/.ygo-ai/pics"
}
```

### 自定义数据源

在 `~/.ygo-ai/sources.json` 中覆盖默认下载源。

## 数据目录结构

```
~/.ygo-ai/
  config.jsonc        # 用户配置
  sources.json        # 自定义数据源（可选）
  data/
    cards.cdb         # 卡牌数据库
    strings.conf      # 字符串配置
    lflist.conf       # 禁限表
  scripts/            # Lua 脚本
  pics/               # 卡图
```

## 相关项目

| 项目 | 说明 |
|------|------|
| [ygo-knowledge-vault](https://github.com/YOUR_ORG/ygo-knowledge-vault) | YGO 知识库模板（OCG 规则、编卡知识） |
| [ygo-skills](https://github.com/YOUR_ORG/ygo-skills) | Claude Code 技能文件（YGO-Script/Desc/Cdb） |

## 许可证

MIT License
