# Desktop Architecture

- Status: Foundation in progress
- 本文记录最终 Windows 桌面架构的基础协议与后续实施边界。
- 本轮尚未创建 Tauri 工程、PyInstaller sidecar、NSIS 安装器，也未迁移真实数据库。

## Final Stack

最终桌面形态采用：

- Tauri 2 作为 Windows 桌面壳。
- React 静态前端作为 UI。
- PyInstaller onedir FastAPI sidecar 作为本地 API 进程。
- SQLite 存储用户学习数据。
- NSIS 安装器分发 Windows 版本。

## Why Keep FastAPI

当前后端已经承载 reading pack 导入、练习提交、reading annotations、vocabulary 和 sentence library 的稳定本地 API。保留 FastAPI 可以复用现有服务、测试和数据模型，Tauri 只负责桌面窗口、sidecar 生命周期和安装分发，不重写业务后端。

## Run Modes

运行模式统一为三类：

- `development`：保留当前开发体验，默认数据库仍是仓库下的 `data/local_english_trainer.sqlite3`。
- `test`：必须显式提供测试数据库 URL 或临时 user data root，禁止回退到开发数据库。
- `desktop_production`：使用 `%LOCALAPPDATA%\LocalEnglishTrainer\`，不得依赖当前工作目录。

配置来源优先级：

1. 函数显式参数。
2. 环境变量：`LOCAL_ENGLISH_TRAINER_MODE`、`LOCAL_ENGLISH_TRAINER_DATABASE_URL`、`LOCAL_ENGLISH_TRAINER_USER_DATA_ROOT`。
3. 运行模式默认值。

## User Data Layout

桌面正式用户数据目录：

```text
%LOCALAPPDATA%\LocalEnglishTrainer\
  data\
  backups\
  imports\
  exports\
  logs\
  cache\
  settings.json
```

安装目录与用户数据目录必须分离。安装器、sidecar 可执行文件和静态前端资源不应写入用户学习数据；SQLite、备份、导入导出和日志属于 user data root。

## Version Protocol

Python 侧版本权威来源为 `backend/app/version.py`：

- `APP_VERSION`
- `API_PROTOCOL_VERSION`
- `SCHEMA_VERSION`

`SCHEMA_VERSION` 表示应用期望的数据库 schema 版本。本轮只建立代码端协议，不创建 metadata 表，不写入现有数据库。后续 Data Safety 阶段再引入 metadata 表、迁移注册表和失败恢复流程。

## Sidecar Health Contract

`GET /health` 为后续 Tauri sidecar version handshake 提供稳定 JSON：

```json
{
  "status": "ok",
  "app_version": "0.1.0",
  "api_protocol_version": 1,
  "schema_version": 1,
  "run_mode": "development"
}
```

该接口不得返回完整数据库路径、token、用户资料、reading pack 正文或其他敏感配置。

## Database Safety Principles

后续桌面升级遵循：

1. 先对目标 SQLite 执行 `PRAGMA integrity_check`。
2. 先创建升级前备份。
3. 优先在副本或受控事务中执行升级。
4. 成功后再进入可替换或可继续使用状态。
5. 失败不得覆盖原库，不得留下半成品备份。

本轮提供基础函数：

- 对显式传入 SQLite 路径执行 integrity check。
- 使用 SQLite backup API 生成备份。
- 生成稳定备份名。
- `prepare_database_for_upgrade` 作为后续 schema upgrade 的安全入口。

## Implemented In This Round

本轮已建立：

- `RuntimeConfig` 运行时配置对象。
- 三种 run mode 的路径解析。
- `%LOCALAPPDATA%\LocalEnglishTrainer\` 的 desktop production 默认 root。
- 显式 `ensure_user_directories(config)`，且不会创建空 `settings.json`。
- Python 版本常量。
- `/health` 版本和运行模式响应。
- SQLite integrity check、backup、prepare upgrade 基础函数。
- 对 runtime config、database safety、db compatibility 和 health 的自动测试。

## Not Implemented In This Round

本轮明确没有：

- 创建 `src-tauri/`。
- 安装 Rust、Tauri、PyInstaller 或 NSIS。
- 打包 FastAPI sidecar。
- 创建桌面窗口或安装器。
- 迁移真实 `data/local_english_trainer.sqlite3`。
- 创建 schema metadata 表。
- 修改业务表、reading annotation、Vocabulary、Sentence 或 reading pack 导入逻辑。

## Future Stages

### Desktop Packaging

- 创建 Tauri 2 工程。
- 将 React build 输出接入 Tauri 静态资源。
- 用 PyInstaller onedir 打包 FastAPI sidecar。
- 建立 sidecar 启动、端口选择和 `/health` version handshake。

### Desktop Data Safety

- 引入数据库 metadata 表。
- 建立 schema migration 注册表。
- 完成备份、升级、失败恢复和回滚验收。
- 真实数据库首次升级前要求用户备份确认。

### Desktop Polish

- 桌面启动体验、错误提示、日志查看和用户数据目录打开入口。
- Packaging 后的离线运行体验。

### Release

- NSIS 安装器。
- 安装 / 卸载 / 升级流程验收。
- 明确哪些文件属于安装目录，哪些属于 `%LOCALAPPDATA%` 用户数据。