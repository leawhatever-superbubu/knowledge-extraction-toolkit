# doc-to-knowledge 更新日志

## [2026-04-09]
### ✨ 新特性 (New Features)
- **解绑飞书强依赖**：全面支持无飞书环境运行。如果是处理本地文档（Word/Markdown），不再强制要求配置 `FEISHU_APP_ID` 等飞书凭证。
- **本地 Markdown 多格式输出**：新增了 `--output-format` 参数支持多种输出模式。
  - 支持 `markdown`（默认）：输出排版精美的 Markdown 知识点（完美兼容腾讯文档/Notion粘贴）。
  - 支持 `json`：导出结构化数据。
  - 支持 `feishu`：写入飞书多维表格。
  - 支持 `all`：同时输出全部格式。
- **新增小白说明书**：增加 `README_小白教程.md`，提供面向非技术人员的保姆级使用指南。

### 🔧 优化 (Improvements)
- 将输出模块 `local_writer.py` 成功移植并集成到 `pipeline.py` 中。
- 移除原先的 `--json-only`，统一整合为更强大的 `--output-format`。