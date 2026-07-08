# Stage Report Guide

本文件规定 local-english-trainer 每个大阶段完成后的总结格式。

阶段总结不是流水账，而是为了让新对话、Codex 或未来的自己快速接上项目状态。

## 1. 保存位置

阶段总结统一保存到：

    docs/stage-reports/

建议命名格式：

    001-reading-pack-import.md
    002-practice-attempt-tracking.md
    003-vocabulary-storage.md

编号只表示阶段顺序，不表示软件版本。

## 2. 阶段总结必须包含的内容

每份阶段总结至少包含：

1. 阶段目标；
2. 本阶段完成内容；
3. 修改文件清单；
4. 新增或修改的接口；
5. 前端页面或交互变化；
6. 数据库或数据结构变化；
7. 测试和构建结果；
8. 已知问题；
9. 下一步建议；
10. Git 状态说明。

## 3. 测试结果写法

不要只写测试通过，要写清楚命令和结果。

推荐格式：

    命令：
    pytest

    结果：
    5 passed

前端构建推荐格式：

    命令：
    npm run build

    结果：
    passed

## 4. 文件清单写法

文件清单要具体到路径，例如：

    backend/app/services/practice_attempt_service.py
    backend/app/main.py
    frontend/src/components/QuestionPanel.tsx
    tests/test_practice_attempt_api.py

不要只写修改了后端和前端。

## 5. Git 状态写法

阶段总结末尾建议记录：

    git status --short
    git ls-files | Select-String "node_modules|__pycache__|sqlite3|pytest_runtime_tmp|frontend/dist|frontend/build-output|\.log"

第二条命令必须没有输出，才说明没有把运行产物纳入版本控制。
