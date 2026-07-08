# AGENTS.md

## 项目定位

本项目是一个本地英语学习系统，核心是：

阅读训练 + 本地单词库搭建

它不是 OCR 项目，不是单纯刷题 App，也不是单纯背单词 App。

核心学习流程：

导入 reading_pack
→ 阅读文章
→ 做题
→ 标答案依据
→ 标同义替换
→ 标生词
→ 标长难句
→ 生词进入本地单词库
→ 长难句进入句子库
→ 后续复习

## 开发原则

1. 优先保证项目可运行、可理解、可回滚。
2. 每一轮只做一个小闭环。
3. 不要一次性铺开过多功能。
4. 后端、前端、测试要同步收口。
5. 修改完成后必须说明改了什么、测试结果如何。
6. 默认本地运行，默认使用 SQLite。
7. 前端风格保持简约、清爽、文本优先、学习工具感。

## 命名约束

1. 不要使用 v1、v2 这种命名。
2. 不要把功能命名成 xxx v1、xxx v2。
3. 使用自然名称，例如：
   - reading_pack import
   - practice attempts
   - reading annotations
   - vocabulary library
   - sentence library

## 禁止事项

除非用户明确要求，否则不要做：

1. OCR
2. AI 功能
3. 云服务接入
4. 模型训练
5. PDF 解析
6. Anki 导出
7. 复杂复习算法
8. 大规模 UI 重构
9. 恢复旧 CET6/OCR/private paper 文件
10. 提交真实学习资料正文
11. 提交数据库文件
12. 提交 node_modules
13. 提交构建产物

## 数据安全约束

不要提交：

- .env
- *.sqlite3
- *.db
- data/user/*
- frontend/dist/
- frontend/build-output/
- frontend/node_modules/
- Python 虚拟环境
- Python 缓存
- 日志文件

## Codex 工作方式

每次开始任务前：

1. 确认当前目录是项目根目录。
2. 运行 git status。
3. 阅读本文件和 README.md。
4. 只完成用户指定的当前任务。
5. 不要扩大范围。

每次完成任务后：

1. 运行后端测试：python -m pytest
2. 运行前端构建：cd frontend && npm run build
3. 输出简短总结：
   - 修改了哪些文件
   - 新增了哪些表或接口
   - 前端改了什么
   - 哪些地方仍是 mock/fallback
   - pytest 结果
   - build 结果

## 当前阶段优先级

优先完成这些闭环：

1. reading_pack 导入和读取
2. Workspace 作答
3. practice attempt 保存
4. reading annotation 持久化
5. vocabulary / sentence 入库

不要在这些闭环完成前扩展 OCR、AI 或复杂复习功能。
