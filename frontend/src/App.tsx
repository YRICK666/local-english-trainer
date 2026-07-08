import { useEffect, useMemo, useState } from "react";

import { ApiError, getPracticeAttempt, getReadingPack, listPracticeAttempts, listReadingPacks, submitPracticeAttempt } from "./api";
import { mockReadingPack } from "./mockData";
import type { PracticeAttemptDetail, PracticeAttemptSummary, ReadingPack } from "./types";
import "./styles.css";

function percent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function App() {
  const [pack, setPack] = useState<ReadingPack>(mockReadingPack);
  const [packs, setPacks] = useState<{ pack_id: string; title: string }[]>([]);
  const [selectedAnswers, setSelectedAnswers] = useState<Record<string, string>>({});
  const [attempts, setAttempts] = useState<PracticeAttemptSummary[]>([]);
  const [selectedAttempt, setSelectedAttempt] = useState<PracticeAttemptDetail | null>(null);
  const [latestAttempt, setLatestAttempt] = useState<PracticeAttemptDetail | null>(null);
  const [notice, setNotice] = useState("后端未连接时可使用示例数据预览；提交练习记录需要启动后端。");

  const passage = pack.passages[0];
  const canSubmit = useMemo(() => pack.questions.length > 0 && pack.questions.every((question) => selectedAnswers[question.question_id]), [pack.questions, selectedAnswers]);

  async function refreshAttempts() {
    try {
      const nextAttempts = await listPracticeAttempts();
      setAttempts(nextAttempts);
    } catch {
      setNotice("后端未连接，暂时无法读取练习记录。");
    }
  }

  async function loadInitialData() {
    try {
      const summaries = await listReadingPacks();
      setPacks(summaries);
      if (summaries.length > 0) {
        const firstPack = await getReadingPack(summaries[0].pack_id);
        setPack(firstPack);
        setSelectedAnswers({});
        setNotice("");
      } else {
        setNotice("还没有导入阅读材料，请先通过后端导入 reading_pack。当前显示示例数据。");
      }
      await refreshAttempts();
    } catch {
      setNotice("后端未连接，可使用示例数据预览；提交练习记录需要启动后端。");
    }
  }

  async function loadPack(packId: string) {
    try {
      const nextPack = await getReadingPack(packId);
      setPack(nextPack);
      setSelectedAnswers({});
      setLatestAttempt(null);
      setNotice("");
    } catch {
      setNotice("后端未连接，无法读取该阅读材料。");
    }
  }

  async function handleSubmitAttempt() {
    try {
      const attempt = await submitPracticeAttempt(pack.pack_id, pack.questions.map((question) => ({
        question_id: question.question_id,
        selected_answer: selectedAnswers[question.question_id]
      })));
      setLatestAttempt(attempt);
      setSelectedAttempt(attempt);
      setNotice("本次练习记录已保存到本地数据库。");
      await refreshAttempts();
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "提交失败";
      setNotice(`后端未连接或提交失败：${message}`);
    }
  }

  async function openAttempt(attemptId: string) {
    try {
      setSelectedAttempt(await getPracticeAttempt(attemptId));
    } catch {
      setNotice("后端未连接，无法读取练习详情。");
    }
  }

  useEffect(() => {
    loadInitialData();
  }, []);

  const result = latestAttempt ?? selectedAttempt;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <strong>local English trainer</strong>
        <span>Reading practice</span>
      </aside>
      <main className="main-content">
        <section className="workspace-toolbar">
          <div>
            <p className="label">Reading pack</p>
            <h1>{pack.title}</h1>
          </div>
          <div className="toolbar-actions">
            <select value={pack.pack_id} onChange={(event) => loadPack(event.target.value)} disabled={packs.length === 0}>
              {packs.length === 0 && <option value={pack.pack_id}>示例数据：{pack.title}</option>}
              {packs.map((item) => <option key={item.pack_id} value={item.pack_id}>{item.title}</option>)}
            </select>
            <button type="button" onClick={loadInitialData}>刷新</button>
          </div>
        </section>
        {notice && <p className="notice">{notice}</p>}
        <div className="workspace-grid">
          <article className="pane article-pane">
            <p className="label">Passage</p>
            <h2>{passage?.title}</h2>
            <div className="paragraphs">
              {passage?.paragraphs.map((paragraph) => (
                <p key={paragraph.paragraph_id}><span>{paragraph.order}</span>{paragraph.text}</p>
              ))}
            </div>
          </article>
          <section className="pane question-pane">
            <div className="question-heading">
              <div>
                <p className="label">Questions</p>
                <h2>作答</h2>
              </div>
              <button type="button" onClick={handleSubmitAttempt} disabled={!canSubmit}>提交本次练习</button>
            </div>
            {pack.questions.map((question) => (
              <div className="question" key={question.question_id}>
                <h3>{question.question_no || question.question_id}. {question.stem}</h3>
                <div className="options">
                  {question.options.map((option) => (
                    <button
                      className={selectedAnswers[question.question_id] === option.label ? "selected" : ""}
                      key={option.label}
                      type="button"
                      onClick={() => setSelectedAnswers((prev) => ({ ...prev, [question.question_id]: option.label }))}
                    >
                      <strong>{option.label}</strong><span>{option.text}</span>
                    </button>
                  ))}
                </div>
              </div>
            ))}
            {result && (
              <div className="attempt-result">
                <h2>提交结果</h2>
                <div className="result-summary">
                  <span>总题数：{result.total_questions}</span>
                  <span>正确数：{result.correct_count}</span>
                  <span>正确率：{percent(result.accuracy)}</span>
                </div>
                {result.answers.map((answer) => (
                  <p key={answer.answer_id} className={answer.is_correct ? "right" : "wrong"}>
                    {answer.question_id}: 用户选择 {answer.selected_answer} / 正确答案 {answer.correct_answer}
                  </p>
                ))}
              </div>
            )}
          </section>
        </div>
        <section className="attempts-section">
          <div className="section-heading">
            <div>
              <p className="label">Attempts</p>
              <h2>最近练习记录</h2>
            </div>
            <button type="button" onClick={refreshAttempts}>刷新记录</button>
          </div>
          {attempts.length === 0 ? <p className="muted">暂无本地练习记录。</p> : (
            <div className="attempt-list">
              {attempts.map((attempt) => (
                <button key={attempt.attempt_id} type="button" onClick={() => openAttempt(attempt.attempt_id)}>
                  <strong>{attempt.pack_id}</strong>
                  <span>{attempt.correct_count}/{attempt.total_questions} · {percent(attempt.accuracy)}</span>
                </button>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
