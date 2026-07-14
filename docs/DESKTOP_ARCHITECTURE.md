# Desktop Architecture

- Status: P2 minimal Tauri static shell complete
- 本文记录最终 Windows 桌面架构的基础协议与后续实施边界。
- 已有 FastAPI PyInstaller sidecar 与最小 Tauri 静态壳；尚未集成 sidecar 生命周期、安装器或真实数据库迁移。


## P0 Dependency Reproducibility

本轮建立 Windows 桌面成品的依赖与工具链基线，仍处于 `Foundation in progress`：

- Node 固定为 `24.12.0`，npm 固定为 `11.6.2`。
- 前端依赖使用精确版本，并提交正式 `frontend/package-lock.json`。
- 正式前端构建使用 `npm ci` 后运行 `npm run build:web`，输出仍为 `frontend/build-output/`。
- Python 桌面构建基线使用独立 CPython `3.11.5` 和仓库内隔离 `.venv-desktop-build`，不得使用默认 Conda Python 生成 lock。
- Python 依赖分为 `requirements/runtime.in`、`requirements/dev.in`、`requirements/desktop.in`，并分别生成带 hash 的 `.lock` 文件。
- `pip-tools` 仅安装在隔离 venv 中作为锁定工具，不属于应用 runtime/dev/desktop 直接依赖。
- `version.json` 是跨语言应用版本、API protocol version 和 schema version 的单一人工编辑来源。
- 未来创建 Tauri 工程后，`Cargo.lock` 必须作为正式源文件提交。
- 本轮尚未创建 Tauri 工程、PyInstaller sidecar 或安装器，也未触碰真实数据库。
- Packaging 工具链仍需后续验证 Rust、MSVC/Windows SDK、NSIS 和签名工具。

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
- `desktop_production`：sidecar 必须从 `LOCAL_ENGLISH_TRAINER_USER_DATA_ROOT` 接收明确的数据根目录，不得依赖当前工作目录或自动读取 bootstrap。未来 Tauri 只在首次启动时读取 bootstrap 并把用户选定目录传给 sidecar。

配置来源优先级：

1. 函数显式参数。
2. 环境变量：`LOCAL_ENGLISH_TRAINER_MODE`、`LOCAL_ENGLISH_TRAINER_DATABASE_URL`、`LOCAL_ENGLISH_TRAINER_USER_DATA_ROOT`。
3. 运行模式默认值。

## User Data Layout

桌面正式用户数据目录由用户在首次启动时明确选择，例如 `G:\LocalEnglishTrainerData`：

```text
G:\LocalEnglishTrainerData\
  data\
    local_english_trainer.sqlite3
  backups\
  imports\
  exports\
  logs\
  cache\
```

`%LOCALAPPDATA%\LocalEnglishTrainer\bootstrap.json` 是唯一允许留在 C 盘的轻量指针，UTF-8 内容严格为 `config_version` 和 `data_root`。它用临时文件加 `os.replace` 原子写入，不保存 token、端口、ready 文件、数据库内容或阅读内容。删除该配置只删除该 JSON，不删除用户数据目录。

安装目录与用户数据目录必须分离。安装器、sidecar 可执行文件和静态前端资源不应写入用户学习数据；SQLite、备份、导入导出和日志属于 user data root。`backend.app.desktop_storage` 拒绝相对路径、普通文件、仓库源码根目录和仓库 `data` 目录；不自动选择磁盘或扫描旧数据库。
## Version Protocol

跨语言版本权威来源为根目录 `version.json`，通过 `scripts/sync_version.py` 同步到 `backend/app/version.py` 和 `frontend/package.json`：

- `APP_VERSION`
- `API_PROTOCOL_VERSION`
- `SCHEMA_VERSION`

`SCHEMA_VERSION` 表示应用期望的数据库 schema 版本。本轮只建立代码端协议和跨语言版本同步，不创建 metadata 表，不写入现有数据库。后续 Data Safety 阶段再引入 metadata 表、迁移注册表和失败恢复流程。

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

## P1 FastAPI Sidecar

P1 adds the independently runnable Python sidecar while the overall desktop status remains `Foundation in progress`:

- `backend.desktop_sidecar` accepts only `desktop_production` configuration from environment variables and requires an explicit user data root, startup token, and ready-file path.
- It binds a pre-owned `127.0.0.1:0` socket and hands that socket directly to Uvicorn, so the reported port is OS-assigned without a find-then-bind race.
- Every HTTP API request, including `/health`, requires `X-Local-English-Trainer-Token`. The token is checked with constant-time comparison, remains process-memory-only, and is not included in logs or ready JSON.
- Browser origins are an empty allowlist by default; a future Tauri shell supplies explicit origins through `LOCAL_ENGLISH_TRAINER_ALLOWED_ORIGINS`.
- After FastAPI startup completes, the sidecar atomically writes a ready JSON containing loopback host/port, PID, run mode, and the application/API/schema version handshake. It removes the file during shutdown.
- `POST /desktop/shutdown` exists only in the sidecar security wrapper and asks Uvicorn to exit gracefully after returning its response.
- Logs use a rotating UTF-8 file at `<user_data_root>\logs\sidecar.log`. P1 smoke tests use system temporary user-data roots only; no real learning database is migrated or read.
- `desktop/sidecar/local_english_trainer_api.spec` builds a PyInstaller `onedir` sidecar without React static assets, user data, tests, or node modules. The executable has no independent console dependency.
- P1 本身未创建 Tauri 壳或安装器；P2 后已存在静态 Tauri 壳，sidecar 生命周期集成与安装器仍未实施。

## P1.5 External Data Root and Selected Database Migration

- `DesktopStorageLayout` 固定外部数据根目录下的 `data`、`backups`、`imports`、`exports`、`logs`、`cache` 和 `data/local_english_trainer.sqlite3`，目录创建可重复执行。
- sidecar 启动时先准备和验证这个布局，只有成功后才设置数据库环境、配置日志、绑定端口和写 ready JSON；无效根目录不会启动服务或生成 ready 文件。
- `migrate_selected_database` 仅接受用户显式提供的绝对源 SQLite 文件和显式目标根目录。它以 SQLite 只读连接对源库执行 `PRAGMA integrity_check`，用 `sqlite3.Connection.backup` 写入目标 `data` 目录中的临时文件，再校验临时目标，并以 `os.replace` 原子替换正式目标。
- 已存在的正式目标绝不覆盖；迁移失败会删除本轮临时文件，保留源数据库和既有目标。该流程不执行 schema upgrade、不搜索磁盘，也不把源路径写入普通运行日志。


## P2 Minimal Tauri Static Shell

- 根目录以精确锁定的本地 `@tauri-apps/cli` 管理桌面命令，前端业务依赖继续保留在 `frontend/package.json`。
- `src-tauri/` 使用 Tauri 2，最小 capability 仅授予 `core:default`；未加入 Shell、文件系统、HTTP 或进程插件权限。
- Vite 固定只绑定 `127.0.0.1:1420` 并启用 `strictPort`；保留既有 `/api` proxy。真实交互式 Windows 会话已通过 `tauri dev`，未启动 FastAPI 时 `/api` 的连接拒绝是预期现象。
- `tauri build --debug --no-bundle` 已通过，生成的 debug exe 可在 Vite 未运行时启动 React 静态资源。
- P2 不启动或打包 sidecar，不访问 SQLite，不接入用户数据目录、首次启动或迁移，也不生成 NSIS/MSI 安装包。
- 下一阶段为 P2.25/P2.5 前置设计：定义平台无关的数据访问边界，并验证 PyInstaller onedir sidecar 作为 Tauri resource 的打包与生命周期方案。

### Desktop Packaging

- P2.25/P2.5 设计并验证 PyInstaller onedir sidecar 作为 Tauri resource 的打包方式。
- 建立 sidecar 启动、端口选择、/health version handshake 和退出生命周期。

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