# local-english-trainer

本项目是一个本地英语学习系统，核心是：

阅读训练 + 本地单词库搭建。

当前阶段已经完成最小学习闭环，并进入阅读标注与本地词库 / 句库沉淀阶段：

1. 导入 reading_pack
2. 在 Workspace 阅读和作答
3. 保存练习记录 practice attempt
4. 在原文中创建 reading annotation
5. 将生词和长难句沉淀到本地词库 / 句库
6. 从词库 / 句库回看来源原文

## 技术栈

后端：

- Python
- FastAPI
- SQLite
- pytest

前端：

- React
- TypeScript
- Vite

## 当前已完成

### Reading Workspace

- reading_pack 基础导入、校验和本地 SQLite 保存
- Workspace 前端读取、多 passage 阅读和作答
- practice attempt 保存、读取和历史详情
- 同一 paragraph 内文字选取
- 右键创建四类 annotation：答案依据、同义替换、生词、长难句
- 原文持久化内联高亮，支持重叠和包含标注
- annotation 详情查看和删除

### Vocabulary / Sentences

- `vocabulary` annotation 自动进入本地词库
- `difficult_sentence` annotation 自动进入本地句库
- 词库记录来源句，以及 pack / passage / paragraph / annotation 来源字段
- 句库记录 pack / passage / paragraph / annotation 来源字段
- 从词库或句库返回 Workspace 来源位置
- 删除 annotation 不删除已沉淀的学习项目，只清空对应 `source_annotation_id`

### Settings

- 四类 annotation 颜色配置
- 颜色设置保存到浏览器 `localStorage`
- 支持恢复默认颜色

### Backend

- reading annotation 支持 `start_offset` / `end_offset`
- 旧 SQLite 表通过 additive、idempotent 方式补齐 offset 字段
- `vocabulary` / `difficult_sentence` annotation 自动入库保持原子事务，失败 rollback

## 当前限制与后续方向

- 选区限制在单个 paragraph 内，不支持跨段标注
- 答案依据和同义替换的题号绑定交互仍待加强
- 尚未实现 AI annotation suggestions 导入或云端 AI 接入
- 不自动生成释义、翻译或句法分析

## 本地运行

后端启动：

python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000

前端启动：

cd frontend
npm run dev

后端测试：

python -m pytest

前端构建：

cd frontend
npm run build

## 开发约束

详细规则见根目录 AGENTS.md。

除非明确要求，不做：

- OCR
- AI 功能
- PDF 解析
- 云服务
- 模型训练
- Anki 导出
- 复杂复习算法
- 大规模 UI 重构

## Desktop P2 static shell

P2 已完成最小 Tauri 2 静态桌面壳：Tauri 在真实交互式 Windows 会话中可启动现有 React/Vite UI；debug no-bundle 构建出的 exe 也可在没有 Vite 的情况下启动。

执行 Cargo 或 Tauri 命令前，仅在当前 PowerShell 进程设置 `RUSTUP_HOME`、`CARGO_HOME` 和本地代理，加载 `G:\DevTools\VSBuildTools\Common7\Tools\Launch-VsDevShell.ps1`，并将 Windows SDK x64 bin 临时加入 `PATH`。

开发模式：

```powershell
npm run tauri:dev -- --verbose --no-watch --exit-on-panic
```

debug no-bundle 构建：

```powershell
npm run tauri:build:debug
```

当前 P2 不启动 FastAPI 或 PyInstaller sidecar，不访问数据库，也不生成 NSIS/MSI 安装包。下一阶段是 P2.25/P2.5 前置设计：定义平台无关的数据访问边界，并规划 sidecar resource 的打包和生命周期集成。