# doc-to-knowledge 封装分发记录

> 📅 2026-03-30 17:32  
> 📍 /Users/leiliu/CodeBuddy/skill-for-share/doc-to-knowledge/

---

## 1. 任务描述

将内部 `doc-to-knowledge` skill（路径：`superbubu/.codebuddy/skills/doc-to-knowledge/`）封装为可对外分享的脱敏版本，放入统一分发仓库 `skill-for-share/`。

## 2. 脱敏清单

| 敏感项 | 原始值 | 处理方式 |
|--------|--------|----------|
| FEISHU_APP_ID | `cli_a9279b...` | 替换为 `cli_xxxxx` |
| FEISHU_APP_SECRET | `OzuxHAFI...` | 替换为 `xxxxx` |
| OPENAI_API_KEY | `sk-963020...` | 替换为 `sk-xxxxx` |
| 飞书 app_token | `Vvorb6Ci...` | 替换为 `YOUR_BITABLE_APP_TOKEN` |
| 飞书 table_id | `tbliCU8h...` | 替换为 `YOUR_TABLE_ID` |
| 飞书 folder_token | `UbDZfTwJ...` | 替换为 `YOUR_FOLDER_TOKEN` |
| 飞书 doc_tokens (8个) | 真实 token 列表 | 替换为示例占位符 |
| 代理网关 IP | `43.162.95.137:5050` | 替换为 `your-proxy-gateway.example.com` |
| 品牌名"腾讯广告/腾讯营销" | 代码 Prompt 中 | 替换为"数字营销"通用描述 |
| 应用名"龙虾机器人" | 注释中 | 已移除 |
| 内部路径 `/Users/leiliu/...` | pipeline/doc_reader 中 | 已移除上游路径 fallback |

## 3. 文件清单（15 个文件）

### 核心脚本（6 个）
- `scripts/pipeline.py` — 主入口（596→完整保留，去内部引用）
- `scripts/feishu_client.py` — 飞书 API 客户端（346 行）
- `scripts/doc_reader.py` — 文档解析层（简化 fallback 链路）
- `scripts/knowledge_extractor.py` — AI 提取核心（753 行，品牌脱敏）
- `scripts/bitable_writer.py` — 多维表格写入（229 行）
- `scripts/gemini_client.py` — Gemini 客户端（脱敏代理 IP）

### 配置文档（9 个）
- `README.md` — 新增，面向外部用户
- `SKILL.md` — 改写，增加版本/作者/License
- `SKILL_SPEC.md` — 改写，去品牌、去内部引用
- `config.example.json` — 脱敏配置模板
- `.env.example` — 脱敏环境变量模板
- `requirements.txt` — 增加 python-docx 可选说明
- `.gitignore` — 新增
- `references/SETUP_GUIDE.md` — 新增，飞书配置指南
- `output/.gitkeep` — 保持目录结构

## 4. 决策记录

- **不包含辅助脚本**：link_knowledge_to_demand.py、link_reverse.py、refresh_visual.py 等 13 个辅助脚本与可视化/需求关联相关，属于内部工作流，不纳入对外分享版
- **不包含 output/ 中的真实数据**：output/ 目录仅保留 .gitkeep
- **Prompt 中品牌替换**：所有"腾讯广告""腾讯营销"替换为通用"数字营销"，用户可自行修改
- **统一分发仓库约定**：`/Users/leiliu/CodeBuddy/skill-for-share/` 下每个 skill 独立子目录（memory ID: 76111706）

## 5. 验证结果

- ✅ 敏感信息扫描：0 处泄漏
- ✅ 目录结构：15 个文件，3 个子目录
- ✅ 核心功能完整：pipeline + 5 个模块全部保留
- ✅ .gitignore 防护：config.json 和 .env 不会被误提交
