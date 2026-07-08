import { useEffect, useMemo, useState } from "react";

import { ApiError, getPracticeAttempt, getReadingPack, importReadingPack, listPracticeAttempts, listReadingPacks, submitPracticeAttempt, validateReadingPack } from "./api";
import { mockReadingPack } from "./mockData";
import type { ImportValidationResult, PracticeAttemptDetail, PracticeAttemptSummary, ReadingPack, ReadingPackImportResponse, ReadingPackSummary } from "./types";
import "./styles.css";

type ViewKey = "dashboard" | "import" | "library" | "workspace" | "attempts" | "vocabulary" | "sentences" | "settings";

const navItems: { key: ViewKey; label: string; helper: string }[] = [
  { key: "dashboard", label: "Dashboard", helper: "学习首页" },
  { key: "library", label: "Library", helper: "阅读材料" },
  { key: "import", label: "Import", helper: "导入材料" },
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

function getAccuracyLabel(accuracy: number) {
  if (accuracy >= 0.85) return "表现优秀";
  if (accuracy >= 0.6) return "表现稳定";
  return "需要复盘";
}

function getAttemptStatus(accuracy: number) {
  if (accuracy >= 0.85) return "strong";
  if (accuracy >= 0.6) return "ok";
  return "review";
}

function getAttemptDisplayTime(createdAt?: string) {
  return formatDate(createdAt);
}

function getAttemptHeading(attempt: Pick<PracticeAttemptSummary, "pack_id" | "created_at">) {
  return `${attempt.pack_id} · ${getAttemptDisplayTime(attempt.created_at)}`;
}

type ImportPreview = {
  packId: string;
  title: string;
  description: string;
  language: string;
  level: string;
  source: string;
  passageCount: number;
  questionCount: number;
  firstPassageTitle: string;
  firstPassageText: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function textField(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : "-";
}

function listField(value: unknown) {
  return Array.isArray(value) ? value : [];
}

function previewImportPayload(payload: Record<string, unknown>): ImportPreview {
  const passages = listField(payload.passages).filter(isRecord);
  const questions = listField(payload.questions).filter(isRecord);
  const firstPassage = passages[0];
  const firstParagraphs = firstPassage ? listField(firstPassage.paragraphs).filter(isRecord) : [];
  const passagePreview = firstParagraphs
    .map((paragraph) => textField(paragraph.text))
    .filter((line) => line !== "-")
    .slice(0, 2)
    .join(" / ");
  const contentPreview = firstPassage ? textField(firstPassage.content) : "-";
  const source = isRecord(payload.source) && Object.keys(payload.source).length > 0 ? JSON.stringify(payload.source) : "-";

  return {
    packId: textField(payload.pack_id),
    title: textField(payload.title),
    description: textField(payload.description),
    language: textField(payload.language),
    level: textField(payload.level),
    source,
    passageCount: passages.length,
    questionCount: questions.length,
    firstPassageTitle: firstPassage ? textField(firstPassage.title) : "-",
    firstPassageText: passagePreview || contentPreview
  };
}

function parseImportDraft(text: string) {
  const trimmed = text.trim();
  if (!trimmed) {
    return { payload: null, error: "请先粘贴 reading_pack JSON", preview: null as ImportPreview | null };
  }

  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (!isRecord(parsed)) {
      return { payload: null, error: "reading_pack JSON 必须是对象", preview: null as ImportPreview | null };
    }
    return { payload: parsed, error: null, preview: previewImportPayload(parsed) };
  } catch (error) {
    const message = error instanceof Error ? error.message : "无法解析 JSON";
    return { payload: null, error: `JSON 格式无法解析：${message}`, preview: null as ImportPreview | null };
  }
}

function isImportValidationResult(value: unknown): value is ImportValidationResult {
  return isRecord(value)
    && typeof value.valid === "boolean"
    && Array.isArray(value.errors)
    && Array.isArray(value.warnings)
    && isRecord(value.stats)
    && typeof value.stats.passage_count === "number"
    && typeof value.stats.paragraph_count === "number"
    && typeof value.stats.question_count === "number";
}

function formatImportError(detail: unknown) {
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (isImportValidationResult(detail)) {
    if (detail.errors.length > 0) {
      return detail.errors.join("；");
    }
    return detail.valid ? "校验通过" : "校验未通过";
  }
  if (isRecord(detail)) {
    const message = textField(detail.message);
    if (message !== "-") {
      return message;
    }
    const errors = listField(detail.errors).filter((item): item is string => typeof item === "string" && item.trim().length > 0);
    if (errors.length > 0) {
      return errors.join("；");
    }
  }
  return "后端未连接，暂时无法校验或导入，请先启动本地后端";
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
    () => pack.questions.length > 0 && pack.questions.every((question) => Boolean(selectedAnswers[question.question_id])),
    [pack.questions, selectedAnswers]
  );
  const answeredCount = useMemo(
    () => pack.questions.filter((question) => Boolean(selectedAnswers[question.question_id])).length,
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

  async function refreshReadingPacks() {
    const summaries = await listReadingPacks();
    setPacks(summaries);
    setIsUsingFallback(false);
    return summaries;
  }

  async function loadInitialData() {
    setWorkspaceError(null);
    try {
      const summaries = await refreshReadingPacks();
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
        selected_answer: selectedAnswers[question.question_id] ?? ""
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

  async function handleOpenImportedPack(packId: string) {
    try {
      await refreshReadingPacks();
      await loadPack(packId, "workspace");
    } catch {
      setNotice("材料已导入，但刷新列表时遇到问题，请稍后重试。");
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
        {activeView === "import" && (
          <ImportView onOpenImportedPack={handleOpenImportedPack} />
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

function ImportView({ onOpenImportedPack }: { onOpenImportedPack: (packId: string) => Promise<void>; }) {
  const [jsonText, setJsonText] = useState("");
  const [validationResult, setValidationResult] = useState<ImportValidationResult | null>(null);
  const [importResult, setImportResult] = useState<ReadingPackImportResponse | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [isImporting, setIsImporting] = useState(false);

  const draft = useMemo(() => parseImportDraft(jsonText), [jsonText]);
  const preview = draft.preview;

  async function handleValidate() {
    const nextDraft = parseImportDraft(jsonText);
    setValidationResult(null);
    setImportResult(null);
    setImportError(null);
    if (!nextDraft.payload) {
      setImportError(nextDraft.error);
      return;
    }

    setIsValidating(true);
    try {
      const result = await validateReadingPack(nextDraft.payload);
      setValidationResult(result);
      setImportError(result.valid ? null : formatImportError(result));
    } catch (error) {
      if (error instanceof ApiError) {
        if (isImportValidationResult(error.detail)) {
          setValidationResult(error.detail);
          setImportError(formatImportError(error.detail));
        } else if (error.status === 409) {
          setImportError("pack_id 已存在，材料可能已经导入。");
        } else {
          setImportError(formatImportError(error.detail));
        }
      } else {
        setImportError("后端未连接，暂时无法校验或导入，请先启动本地后端");
      }
    } finally {
      setIsValidating(false);
    }
  }

  async function handleImport() {
    const nextDraft = parseImportDraft(jsonText);
    setImportError(null);
    if (!nextDraft.payload) {
      setImportResult(null);
      setImportError(nextDraft.error);
      return;
    }

    setIsImporting(true);
    try {
      const result = await importReadingPack(nextDraft.payload);
      setValidationResult(result.validation);
      setImportResult(result);
      setImportError(null);
    } catch (error) {
      setImportResult(null);
      if (error instanceof ApiError) {
        if (error.status === 409) {
          setImportError("pack_id 已存在，材料可能已经导入。");
        } else if (isImportValidationResult(error.detail)) {
          setValidationResult(error.detail);
          setImportError(formatImportError(error.detail));
        } else {
          setImportError(formatImportError(error.detail));
        }
      } else {
        setImportError("后端未连接，暂时无法校验或导入，请先启动本地后端");
      }
    } finally {
      setIsImporting(false);
    }
  }

  const validationMessage = validationResult
    ? validationResult.valid
      ? "校验通过，可以导入。"
      : "校验未通过，请先修正下面的问题。"
    : "";

  return (
    <section className="page-stack">
      <div className="page-header slim">
        <div>
          <p className="eyebrow">Import</p>
          <h1>导入 reading_pack</h1>
          <p>粘贴阅读材料 JSON，先校验再导入。导入成功后可刷新 Library，并进入 Workspace 开始阅读作答。</p>
        </div>
      </div>

      <div className="content-section import-panel">
        <div className="import-editor">
          <label className="import-help" htmlFor="reading-pack-json">reading_pack JSON</label>
          <textarea
            id="reading-pack-json"
            className="json-input"
            value={jsonText}
            onChange={(event) => {
              setJsonText(event.target.value);
              setValidationResult(null);
              setImportResult(null);
              setImportError(null);
            }}
            placeholder="请粘贴 reading_pack JSON"
          />
          <div className="import-actions">
            <button type="button" className="secondary-action" onClick={handleValidate} disabled={isValidating || isImporting}>
              {isValidating ? "校验中……" : "校验"}
            </button>
            <button type="button" className="primary-action" onClick={handleImport} disabled={isImporting || isValidating}>
              {isImporting ? "导入中……" : "导入"}
            </button>
          </div>
          <p className="import-help">支持先在本地校验，再把通过的材料导入 SQLite。空 JSON、非法 JSON 和重复 pack_id 都会显示明确提示。</p>
          {draft.error && <div className="status-message error">{draft.error}</div>}
          {importError && <div className="status-message error">{importError}</div>}
          {validationResult && (
            <div className={`status-message ${validationResult.valid ? "success" : "warning"}`}>
              {validationMessage}
            </div>
          )}
        </div>

        <div className="import-result-card">
          <div className="section-title-row">
            <div>
              <p className="eyebrow">Preview</p>
              <h2>导入预览</h2>
            </div>
          </div>
          {preview ? (
            <div className="import-preview">
              <div className="import-preview-grid">
                <span><strong>pack_id</strong><small>{preview.packId}</small></span>
                <span><strong>title</strong><small>{preview.title}</small></span>
                <span><strong>description</strong><small>{preview.description}</small></span>
                <span><strong>language</strong><small>{preview.language}</small></span>
                <span><strong>level</strong><small>{preview.level}</small></span>
                <span><strong>source</strong><small>{preview.source}</small></span>
                <span><strong>passages</strong><small>{preview.passageCount}</small></span>
                <span><strong>questions</strong><small>{preview.questionCount}</small></span>
              </div>
              <div className="import-preview-block">
                <strong>第一篇 passage</strong>
                <p>{preview.firstPassageTitle}</p>
              </div>
              <div className="import-preview-block">
                <strong>前几行文本</strong>
                <p>{preview.firstPassageText}</p>
              </div>
            </div>
          ) : (
            <EmptyState title="等待 JSON 输入" description="粘贴 reading_pack JSON 后，这里会显示材料摘要、题目数量和第一篇 passage 的预览。" />
          )}

          {validationResult && (
            <div className="import-preview">
              <div className="import-preview-block">
                <strong>校验统计</strong>
                <p>{validationResult.stats.passage_count} passages · {validationResult.stats.paragraph_count} paragraphs · {validationResult.stats.question_count} questions</p>
              </div>
              {validationResult.errors.length > 0 && (
                <div className="import-preview-block">
                  <strong>错误</strong>
                  <ul className="validation-list">
                    {validationResult.errors.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                </div>
              )}
              {validationResult.warnings.length > 0 && (
                <div className="import-preview-block">
                  <strong>警告</strong>
                  <ul className="validation-list">
                    {validationResult.warnings.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                </div>
              )}
            </div>
          )}

          {importResult && (
            <div className="import-preview import-result-card">
              <div className="status-message success">导入成功，Library 已可刷新并打开这份材料。</div>
              <div className="import-preview-block">
                <strong>已导入</strong>
                <p>{importResult.pack.pack_id}</p>
              </div>
              <div className="import-preview-block">
                <strong>接下来</strong>
                <p>点击下面的按钮，刷新列表并进入 Workspace。</p>
              </div>
              <button type="button" className="primary-action" onClick={() => void onOpenImportedPack(importResult.pack.pack_id)}>
                进入 Workspace
              </button>
            </div>
          )}
        </div>
      </div>
    </section>
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
      <div className="dashboard-hero">
        <div>
          <p className="eyebrow">Dashboard</p>
          <h1>今天从一篇阅读开始</h1>
          <p>围绕阅读、作答和本地练习记录，把每天的英语训练做得更稳定、更可持续。</p>
        </div>
        <div className="inline-actions">
          <button className="primary-action" type="button" onClick={onContinue}>继续学习</button>
          <button type="button" className="secondary-action" onClick={onOpenLibrary}>查看 Library</button>
        </div>
      </div>

      {isUsingFallback && (
        <div className="fallback-note">
          后端暂未连接，当前首页内容来自示例数据，你仍然可以先预览学习流程和界面结构。
        </div>
      )}

      <div className="study-summary-grid">
        <div className="study-summary-card">
          <span>当前材料</span>
          <strong>{pack.title}</strong>
          <small>{isUsingFallback ? "示例材料预览" : "当前学习材料"}</small>
        </div>
        <div className="study-summary-card">
          <span>今日训练</span>
          <strong>{pack.question_count}</strong>
          <small>本份材料题目数</small>
        </div>
        <div className="study-summary-card">
          <span>最近正确率</span>
          <strong>{recentAttempt ? percent(recentAttempt.accuracy) : "暂无"}</strong>
          <small>{recentAttempt ? `${recentAttempt.correct_count}/${recentAttempt.total_questions}` : "完成一次练习后显示"}</small>
        </div>
        <div className="study-summary-card">
          <span>最近状态</span>
          <strong>{recentAttempt ? getAccuracyLabel(recentAttempt.accuracy) : "等待开始"}</strong>
          <small>{recentAttempt ? getAttemptDisplayTime(recentAttempt.created_at) : "先完成一轮阅读练习"}</small>
        </div>
      </div>

      <div className="content-section two-column-section">
        <div>
          <p className="eyebrow">Continue</p>
          <h2>{pack.title}</h2>
          <p className="muted-text">进入 Workspace 后可以继续阅读文章、完成选择题，并把本次练习保存到本地记录中。</p>
          <div className="inline-actions">
            <button type="button" onClick={onContinue}>进入 Workspace</button>
            <button type="button" className="secondary-action" onClick={onOpenLibrary}>切换材料</button>
          </div>
        </div>
        <div className="dashboard-attempts">
          <div className="section-title-row">
            <div>
              <p className="eyebrow">Recent attempts</p>
              <h2>最近练习记录</h2>
            </div>
          </div>
          {attempts.length === 0 ? <p className="muted-text">还没有练习记录。完成一次阅读训练后，这里会显示最近结果。</p> : attempts.slice(0, 3).map((attempt) => (
            <button key={attempt.attempt_id} className="attempt-history-row" type="button" onClick={() => onOpenAttempt(attempt.attempt_id)}>
              <div>
                <strong>{attempt.pack_id}</strong>
                <small>{getAttemptDisplayTime(attempt.created_at)}</small>
              </div>
              <div className="attempt-metric">
                <span>{attempt.correct_count}/{attempt.total_questions}</span>
                <span className={`accuracy-pill ${getAttemptStatus(attempt.accuracy)}`}>{percent(attempt.accuracy)}</span>
              </div>
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
  const status = getAttemptStatus(result.accuracy);

  return (
    <div className="attempt-result">
      <div className="attempt-report-header">
        <div>
          <p className="eyebrow">Result</p>
          <h2>练习报告</h2>
          <p className="muted-text">{getAttemptHeading(result)}</p>
        </div>
        <span className={`accuracy-pill ${status}`}>{getAccuracyLabel(result.accuracy)}</span>
      </div>
      <div className="result-summary">
        <span><strong>{result.total_questions}</strong> 总题数</span>
        <span><strong>{result.correct_count}</strong> 正确数</span>
        <span><strong>{percent(result.accuracy)}</strong> 正确率</span>
      </div>
      <div className="attempt-answer-table">
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
          <p>按材料与时间查看最近练习，快速回顾每次作答结果。</p>
        </div>
        <button type="button" onClick={onRefresh}>刷新记录</button>
      </div>

      <div className="attempts-layout">
        <div className="attempt-list-panel">
          <div className="section-title-row">
            <div>
              <p className="eyebrow">History</p>
              <h2>历史记录</h2>
            </div>
          </div>
          {attempts.length === 0 ? <p className="muted-text">还没有本地练习记录。先在 Workspace 完成一次训练，这里就会出现历史结果。</p> : (
            <div className="attempt-history-list">
              {attempts.map((attempt) => (
                <button key={attempt.attempt_id} className={selectedAttempt?.attempt_id === attempt.attempt_id ? "attempt-history-row active" : "attempt-history-row"} type="button" onClick={() => onOpenAttempt(attempt.attempt_id)}>
                  <div>
                    <strong>{attempt.pack_id}</strong>
                    <small>{getAttemptDisplayTime(attempt.created_at)}</small>
                  </div>
                  <div className="attempt-metric">
                    <span>{attempt.correct_count}/{attempt.total_questions}</span>
                    <span className={`accuracy-pill ${getAttemptStatus(attempt.accuracy)}`}>{percent(attempt.accuracy)}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="attempt-detail-panel">
          {selectedAttempt ? <AttemptResult result={selectedAttempt} /> : <EmptyState title="选择一条练习记录" description="点击左侧历史记录后，这里会显示本次练习的正确率和每题作答结果。" />}
        </div>
      </div>
    </section>
  );
}

export default App;
