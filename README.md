# local-english-trainer

本项目是一个本地英语学习系统，核心是：

阅读训练 + 本地单词库搭建。

当前阶段目标是先完成最小学习闭环：

1. 导入 reading_pack
2. 在 Workspace 阅读和作答
3. 保存练习记录 practice attempt
4. 后续再做阅读标注持久化
5. 再做本地单词库和句子库

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

- reading_pack 基础导入
- reading_pack 本地 SQLite 保存
- Workspace 前端读取和作答
- practice attempt 保存和读取
- 前端最近练习记录入口

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
