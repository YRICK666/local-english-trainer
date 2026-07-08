import { useEffect, useMemo, useState } from "react";

import { ApiError, getPracticeAttempt, getReadingPack, listPracticeAttempts, listReadingPacks, submitPracticeAttempt } from "./api";
import { mockReadingPack } from "./mockData";
import type { PracticeAttemptDetail, PracticeAttemptSummary, ReadingPack, ReadingPackSummary } from "./types";
import "./styles.css";

type ViewKey = "dashboard" | "library" | "workspace" | "attempts" | "vocabulary" | "sentences" | "settings";

const navItems: { key: ViewKey; label: string; helper: string }[] = [
  { key: "dashboard", label: "Dashboard", helper: "学习首页" },
  { key: "library", label: "Library", helper: "阅读材料" },
  { key: "workspace", label: "Workspace", helper: "阅读训练" },
  { key: "attempts", label: "Attempts", helper: "练习记录" },
  { key: "vocabulary", label: "Vocabulary", helper: "本地词库" },
  { key: "sentences", label: "Sentences", helper: "长难句库" },
  { key: "settings", label: "Settings", helper: "偏好设置" }
];

function percent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function formatDate(value?: string) {
  if (!value) return "时间不确定";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="empty-state">
      <h2>{title}</h2>
      <p>{description}</p>
    </div>
  );
}

function App() {
  const [activeView, setActiveView] = useState<ViewKey>("dashboard");
  const [pack, setPack] = useState<ReadingPack>(mockReadingPack);
  const [packs, setPacks] = useState<ReadingPackSummary[]>([]);
  const [selectedAnswers, setSelectedAnswers] = useState<Record<string, string>>({});
  const [attempts, setAttempts] = useState<PracticeAttemptSummary[]>([]);
  const [selectedAttempt, setSelectedAttempt] = useState<PracticeAttemptDetail | null>(null);
  const [latestAttempt, setLatestAttempt] = useState<PracticeAttemptDetail | null>(null);
  const [notice, setNotice] = useState("");
  const [isUsingFallback, setIsUsingFallback] = useState(true);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [isPackLoading, setIsPackLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);

  const passage = pack.passages[0];
  const canSubmit = useMemo(
    () => pack.questions.length > 0 && pack.questions.every((question) => selectedAnswers[question.question_id]),
    [pack.questions, selectedAnswers]
  );
  const answeredCount = useMemo(
    () => pack.questions.filter((question) => selectedAnswers[question.question_id]).length,
    [pack.questions, selectedAnswers]
  );
  const result = latestAttempt ?? selectedAttempt;
  const recentAttempt = attempts[0];

  async function refreshAttempts() {
    try {
      const nextAttempts = await listPracticeAttempts();
      setAttempts(nextAttempts);
    } catch {
      setNotice("后端未连接，暂时无法读取练习记录。");
    }
  }

  async function loadInitialData() {
    setWorkspaceError(null);
    try {
      const summaries = await listReadingPacks();
      setPacks(summaries);
      setIsUsingFallback(false);
      if (summaries.length > 0) {
        const firstPack = await getReadingPack(summaries[0].pack_id);
        setPack(firstPack);
        setSelectedAnswers({});
        setLatestAttempt(null);
        setSelectedAttempt(null);
        setNotice("");
      } else {
        setPack(mockReadingPack);
        setIsUsingFallback(true);
        setNotice("还没有导入阅读材料，请先导入 reading_pack。当前显示示例数据。");
      }
      await refreshAttempts();
    } catch {
      setPack(mockReadingPack);
      setPacks([]);
      setIsUsingFallback(true);
      setNotice("后端未连接，可使用示例数据预览界面；提交练习记录需要启动后端。");
    } finally {
      setIsInitialLoading(false);
    }
  }

  async function loadPack(packId: string, nextView: ViewKey = "workspace") {
    setIsPackLoading(true);
    setWorkspaceError(null);
    try {
      const nextPack = await getReadingPack(packId);
      setPack(nextPack);
      setSelectedAnswers({});
      setLatestAttempt(null);
      setSelectedAttempt(null);
      setNotice("");
      setIsUsingFallback(false);
      setActiveView(nextView);
    } catch {
      setNotice("后端未连接，无法读取该阅读材料。可先使用示例数据预览 Workspace。");
      setIsUsingFallback(true);
      setActiveView(nextView);
    } finally {
      setIsPackLoading(false);
    }
  }

  async function handleSubmitAttempt() {
    setIsSubmitting(true);
    setWorkspaceError(null);
    try {
      const attempt = await submitPracticeAttempt(pack.pack_id, pack.questions.map((question) => ({
        question_id: question.question_id,
        selected_answer: selectedAnswers[question.question_id]
      })));
      setLatestAttempt(attempt);
      setSelectedAttempt(attempt);
      setNotice("本次练习记录已保存到本地数据库。");
      setActiveView("workspace");
      await refreshAttempts();
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "提交失败";
      setWorkspaceError("提交失败，请检查后端服务是否正在运行。");
      setNotice(`后端未连接或提交失败：${message}`);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function openAttempt(attemptId: string) {
    try {
      const attempt = await getPracticeAttempt(attemptId);
      setSelectedAttempt(attempt);
      setLatestAttempt(null);
      setActiveView("attempts");
    } catch {
      setNotice("后端未连接，无法读取练习详情。");
    }
  }

  useEffect(() => {
    loadInitialData();
  }, []);

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Main navigation">
        <div className="brand-block">
          <span className="brand-mark">LE</span>
          <div>
            <strong>Local English Trainer</strong>
            <span>Reading platform</span>
          </div>
        </div>
        <nav className="nav-list">
          {navItems.map((item) => (
            <button
              key={item.key}
              className={activeView === item.key ? "nav-item active" : "nav-item"}
              type="button"
              onClick={() => setActiveView(item.key)}
            >
              <span>{item.label}</span>
              <small>{item.helper}</small>
            </button>
          ))}
        </nav>
      </aside>

      <main className="main-content">
        {isInitialLoading ? (
          <div className="loading-card">正在整理你的阅读材料……</div>
        ) : (<>
          {notice && <p className="notice">{notice}</p>}
        {activeView === "dashboard" && (
          <DashboardView
            pack={pack}
            attempts={attempts}
            recentAttempt={recentAttempt}
            isUsingFallback={isUsingFallback}
            onContinue={() => setActiveView("workspace")}
            onOpenLibrary={() => setActiveView("library")}
            onOpenAttempt={openAttempt}
          />
        )}
        {activeView === "library" && (
          <LibraryView
            packs={packs}
            currentPack={pack}
            isUsingFallback={isUsingFallback}
            onRefresh={loadInitialData}
            onOpenPack={(packId) => loadPack(packId)}
          />
        )}
        {activeView === "workspace" && (
          <WorkspaceView
            pack={pack}
            packs={packs}
            passage={passage}
            selectedAnswers={selectedAnswers}
            answeredCount={answeredCount}
            canSubmit={canSubmit}
            isUsingFallback={isUsingFallback}
            result={result}
            isPackLoading={isPackLoading}
            isSubmitting={isSubmitting}
            workspaceError={workspaceError}
            onRefresh={loadInitialData}
            onLoadPack={(packId) => loadPack(packId, "workspace")}
            onSelectAnswer={(questionId, answer) => setSelectedAnswers((prev) => ({ ...prev, [questionId]: answer }))}
            onSubmitAttempt={handleSubmitAttempt}
            onOpenAttempts={() => setActiveView("attempts")}
          />
        )}
        {activeView === "attempts" && (
          <AttemptsView attempts={attempts} selectedAttempt={selectedAttempt} onRefresh={refreshAttempts} onOpenAttempt={openAttempt} />
        )}
        {activeView === "vocabulary" && (
          <EmptyState title="Vocabulary" description="本阶段只做学习平台外壳与 Workspace 视觉升级；本地词库入口先保留清爽空状态。" />
        )}
        {activeView === "sentences" && (
          <EmptyState title="Sentences" description="长难句库入口已放入侧边栏，本阶段不做真实入库、标注或高亮切分。" />
        )}
        {activeView === "settings" && (
          <EmptyState title="Settings" description="偏好设置入口先占位，后续可放阅读字号、行宽、主题等本地设置。" />
        )}
        </>)}
      </main>
    </div>
  );
}

function DashboardView({
  pack,
  attempts,
  recentAttempt,
  isUsingFallback,
  onContinue,
  onOpenLibrary,
  onOpenAttempt
}: {
  pack: ReadingPack;
  attempts: PracticeAttemptSummary[];
  recentAttempt?: PracticeAttemptSummary;
  isUsingFallback: boolean;
  onContinue: () => void;
  onOpenLibrary: () => void;
  onOpenAttempt: (attemptId: string) => void;
}) {
  return (
    <section className="page-stack">
      <div className="page-header">
        <div>
          <p className="eyebrow">Dashboard</p>
          <h1>今天从一篇阅读开始</h1>
          <p>围绕材料阅读、选择题作答和本地练习记录，稳定推进你的英语学习闭环。</p>
        </div>
        <button className="primary-action" type="button" onClick={onContinue}>继续学习</button>
      </div>

      <div className="overview-grid">
        <div className="overview-card">
          <span>当前材料</span>
          <strong>{pack.title}</strong>
          <small>{isUsingFallback ? "示例数据" : "来自本地数据库"}</small>
        </div>
        <div className="overview-card">
          <span>今日训练</span>
          <strong>{pack.question_count}</strong>
          <small>当前材料题目数</small>
        </div>
        <div className="overview-card">
          <span>最近正确率</span>
          <strong>{recentAttempt ? percent(recentAttempt.accuracy) : "暂无"}</strong>
          <small>{recentAttempt ? `${recentAttempt.correct_count}/${recentAttempt.total_questions}` : "完成一次练习后显示"}</small>
        </div>
      </div>

      <div className="content-section two-column-section">
        <div>
          <p className="eyebrow">Continue</p>
          <h2>{pack.title}</h2>
          <p className="muted-text">进入 Workspace 后可以阅读文章、完成选择题，并提交本次练习记录。</p>
          <div className="inline-actions">
            <button type="button" onClick={onContinue}>进入 Workspace</button>
            <button type="button" className="secondary-action" onClick={onOpenLibrary}>查看 Library</button>
          </div>
        </div>
        <div className="recent-list compact">
          <div className="section-title-row">
            <h2>最近练习</h2>
          </div>
          {attempts.length === 0 ? <p className="muted-text">暂无练习记录。</p> : attempts.slice(0, 3).map((attempt) => (
            <button key={attempt.attempt_id} type="button" onClick={() => onOpenAttempt(attempt.attempt_id)}>
              <span>{attempt.pack_id}</span>
              <strong>{attempt.correct_count}/{attempt.total_questions} · {percent(attempt.accuracy)}</strong>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

function LibraryView({
  packs,
  currentPack,
  isUsingFallback,
  onRefresh,
  onOpenPack
}: {
  packs: ReadingPackSummary[];
  currentPack: ReadingPack;
  isUsingFallback: boolean;
  onRefresh: () => void;
  onOpenPack: (packId: string) => void;
}) {
  return (
    <section className="page-stack">
      <div className="page-header slim">
        <div>
          <p className="eyebrow">Library</p>
          <h1>阅读材料库</h1>
          <p>选择一份已导入的 reading_pack，进入 Workspace 开始训练。</p>
        </div>
        <button type="button" onClick={onRefresh}>刷新材料</button>
      </div>
      {packs.length === 0 ? (
        <EmptyState
          title="还没有导入阅读材料"
          description={isUsingFallback ? "后端未连接或数据库为空，当前只能使用示例数据预览 Workspace。" : "请先导入 reading_pack，然后回到 Library 查看材料。"}
        />
      ) : (
        <div className="library-list">
          {packs.map((item) => (
            <button key={item.pack_id} className={item.pack_id === currentPack.pack_id ? "library-row active" : "library-row"} type="button" onClick={() => onOpenPack(item.pack_id)}>
              <span>
                <strong>{item.title}</strong>
                <small>{item.pack_id}</small>
              </span>
              <span>{item.passage_count} passages · {item.question_count} questions</span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function WorkspaceView({
  pack,
  packs,
  passage,
  selectedAnswers,
  answeredCount,
  canSubmit,
  isUsingFallback,
  result,
  isPackLoading,
  isSubmitting,
  workspaceError,
  onRefresh,
  onLoadPack,
  onSelectAnswer,
  onSubmitAttempt,
  onOpenAttempts
}: {
  pack: ReadingPack;
  packs: ReadingPackSummary[];
  passage: ReadingPack["passages"][number] | undefined;
  selectedAnswers: Record<string, string>;
  answeredCount: number;
  canSubmit: boolean;
  isUsingFallback: boolean;
  result: PracticeAttemptDetail | null;
  isPackLoading: boolean;
  isSubmitting: boolean;
  workspaceError: string | null;
  onRefresh: () => void;
  onLoadPack: (packId: string) => void;
  onSelectAnswer: (questionId: string, answer: string) => void;
  onSubmitAttempt: () => void;
  onOpenAttempts: () => void;
}) {
  const remaining = pack.questions.length - answeredCount;
  return (
    <section className="workspace-page">
      <div className="training-header">
        <div>
          <p className="eyebrow">Workspace</p>
          <h1>{pack.title}</h1>
          <p>{isUsingFallback ? "后端未连接，可使用示例数据预览界面。" : `${pack.passage_count} passages · ${pack.question_count} questions`}</p>
        </div>
        <div className="training-actions">
          <select value={pack.pack_id} onChange={(event) => onLoadPack(event.target.value)} disabled={packs.length === 0}>
            {packs.length === 0 && <option value={pack.pack_id}>示例数据：{pack.title}</option>}
            {packs.map((item) => <option key={item.pack_id} value={item.pack_id}>{item.title}</option>)}
          </select>
          <button type="button" onClick={onRefresh}>刷新</button>
        </div>
      </div>

      {packs.length === 0 && isUsingFallback && (
        <div className="inline-status">还没有导入阅读材料，请先到 Import 页面导入。当前显示示例数据。</div>
      )}

      {isPackLoading ? (
        <div className="loading-card">正在打开这篇训练材料……</div>
      ) : (
      <div className="workspace-grid">
        <article className="workspace-pane article-pane">
          <div className="pane-title">
            <p className="eyebrow">Passage</p>
            <h2>{passage?.title ?? pack.title}</h2>
          </div>
          <div className="paragraphs">
            {passage?.paragraphs.map((paragraph) => (
              <p key={paragraph.paragraph_id}><span>{paragraph.order}</span>{paragraph.text}</p>
            ))}
          </div>
        </article>

        <section className="workspace-pane question-pane">
          <div className="question-topbar">
            <div>
              <p className="eyebrow">Questions</p>
              <h2>{answeredCount}/{pack.questions.length} 已作答</h2>
            </div>
            <button className="primary-action" type="button" onClick={onSubmitAttempt} disabled={!canSubmit || isSubmitting}>
              {isSubmitting ? "提交中……" : "提交本次练习"}
            </button>
          </div>

          {!result && !isSubmitting && !workspaceError && (
            <div className="workspace-status">
              {canSubmit
                ? "已完成全部题目，可以提交本次练习。"
                : `还差 ${remaining} 题即可提交。`
              }
            </div>
          )}

          {workspaceError && (
            <div className="workspace-error">{workspaceError}</div>
          )}

          <div className="question-list">
            {pack.questions.map((question) => (
              <div className="question-card" key={question.question_id}>
                <h3>{question.question_no || question.question_id}. {question.stem}</h3>
                <div className="options">
                  {question.options.map((option) => (
                    <button
                      className={selectedAnswers[question.question_id] === option.label ? "option-button selected" : "option-button"}
                      key={option.label}
                      type="button"
                      onClick={() => onSelectAnswer(question.question_id, option.label)}
                    >
                      <strong>{option.label}</strong><span>{option.text}</span>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {result && <AttemptResult result={result} />}
          <button className="text-action" type="button" onClick={onOpenAttempts}>查看最近练习记录</button>
        </section>
      </div>
      )}
    </section>
  );
}

function AttemptResult({ result }: { result: PracticeAttemptDetail }) {
  return (
    <div className="attempt-result">
      <div className="section-title-row">
        <div>
          <p className="eyebrow">Result</p>
          <h2>练习结果</h2>
        </div>
        <strong>{percent(result.accuracy)}</strong>
      </div>
      <div className="result-summary">
        <span>总题数：{result.total_questions}</span>
        <span>正确数：{result.correct_count}</span>
        <span>正确率：{percent(result.accuracy)}</span>
      </div>
      <div className="answer-review-list">
        {result.answers.map((answer) => (
          <p key={answer.answer_id} className={answer.is_correct ? "answer-review right" : "answer-review wrong"}>
            <strong>{answer.question_id}</strong>
            <span>你的选择：{answer.selected_answer}</span>
            <span>正确答案：{answer.correct_answer}</span>
          </p>
        ))}
      </div>
    </div>
  );
}

function AttemptsView({
  attempts,
  selectedAttempt,
  onRefresh,
  onOpenAttempt
}: {
  attempts: PracticeAttemptSummary[];
  selectedAttempt: PracticeAttemptDetail | null;
  onRefresh: () => void;
  onOpenAttempt: (attemptId: string) => void;
}) {
  return (
    <section className="page-stack">
      <div className="page-header slim">
        <div>
          <p className="eyebrow">Attempts</p>
          <h1>练习历史</h1>
          <p>查看本地保存的最近练习记录和单题结果。</p>
        </div>
        <button type="button" onClick={onRefresh}>刷新记录</button>
      </div>

      <div className="attempts-layout">
        <div className="attempt-list-panel">
          {attempts.length === 0 ? <p className="muted-text">暂无本地练习记录。</p> : attempts.map((attempt) => (
            <button key={attempt.attempt_id} className={selectedAttempt?.attempt_id === attempt.attempt_id ? "attempt-row active" : "attempt-row"} type="button" onClick={() => onOpenAttempt(attempt.attempt_id)}>
              <span>
                <strong>{attempt.pack_id}</strong>
                <small>{formatDate(attempt.created_at)}</small>
              </span>
              <strong>{attempt.correct_count}/{attempt.total_questions} · {percent(attempt.accuracy)}</strong>
            </button>
          ))}
        </div>
        <div className="attempt-detail-panel">
          {selectedAttempt ? <AttemptResult result={selectedAttempt} /> : <EmptyState title="选择一条记录" description="点击左侧练习记录后，这里会显示每题选择与正确答案。" />}
        </div>
      </div>
    </section>
  );
}

export default App;
