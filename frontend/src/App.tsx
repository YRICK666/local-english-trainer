import { useEffect, useMemo, useState } from "react";

import { ApiError, createAnnotation, createVocabularyItem, deleteAnnotation, deleteVocabularyItem, getPracticeAttempt, getReadingPack, getVocabularyItem, importReadingPack, listAnnotations, listPracticeAttempts, listReadingPacks, listVocabularyItems, submitPracticeAttempt, updateVocabularyItem, validateReadingPack } from "./api";
import { mockReadingPack } from "./mockData";
import type { AnnotationCreate, AnnotationType, ImportValidationResult, PracticeAttemptDetail, PracticeAttemptSummary, ReadingAnnotation, ReadingPack, ReadingPackImportResponse, ReadingPackSummary, VocabularyItem, VocabularyItemCreate, VocabularyItemUpdate, VocabularyReviewStatus } from "./types";
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

function sortPassages<T extends { order: number }>(items: T[]) {
  return [...items].sort((left, right) => left.order - right.order);
}

const annotationTypeOptions: { value: AnnotationType; label: string }[] = [
  { value: "answer_evidence", label: "答案依据" },
  { value: "synonym_replacement", label: "同义替换" },
  { value: "vocabulary", label: "生词" },
  { value: "difficult_sentence", label: "长难句" }
];

function getAnnotationTypeLabel(type: AnnotationType) {
  return annotationTypeOptions.find((item) => item.value === type)?.label ?? type;
}

function getParagraphLabel(order?: number) {
  return order ? `第 ${order} 段` : "段落";
}

const vocabularyReviewStatusOptions: { value: VocabularyReviewStatus; label: string }[] = [
  { value: "new", label: "新词" },
  { value: "learning", label: "学习中" },
  { value: "familiar", label: "熟悉" }
];

function getVocabularyReviewStatusLabel(status: VocabularyReviewStatus) {
  return vocabularyReviewStatusOptions.find((item) => item.value === status)?.label ?? status;
}

function normalizeNullableText(value: string) {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
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
  const [currentPassageId, setCurrentPassageId] = useState<string>(mockReadingPack.passages[0]?.passage_id ?? "");
  const [attempts, setAttempts] = useState<PracticeAttemptSummary[]>([]);
  const [selectedAttempt, setSelectedAttempt] = useState<PracticeAttemptDetail | null>(null);
  const [latestAttempt, setLatestAttempt] = useState<PracticeAttemptDetail | null>(null);
  const [notice, setNotice] = useState("");
  const [isUsingFallback, setIsUsingFallback] = useState(true);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [isPackLoading, setIsPackLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [annotations, setAnnotations] = useState<ReadingAnnotation[]>([]);
  const [annotationError, setAnnotationError] = useState<string | null>(null);
  const [isAnnotationsLoading, setIsAnnotationsLoading] = useState(false);
  const [isAnnotationSaving, setIsAnnotationSaving] = useState(false);
  const [deletingAnnotationId, setDeletingAnnotationId] = useState<string | null>(null);
  const [addingVocabularyAnnotationId, setAddingVocabularyAnnotationId] = useState<string | null>(null);
  const [annotationNotice, setAnnotationNotice] = useState<string | null>(null);
  const [vocabularyItems, setVocabularyItems] = useState<VocabularyItem[]>([]);
  const [selectedVocabularyId, setSelectedVocabularyId] = useState<string | null>(null);
  const [selectedVocabularyItem, setSelectedVocabularyItem] = useState<VocabularyItem | null>(null);
  const [vocabularyError, setVocabularyError] = useState<string | null>(null);
  const [isVocabularyLoading, setIsVocabularyLoading] = useState(false);
  const [isVocabularyDetailLoading, setIsVocabularyDetailLoading] = useState(false);
  const [isVocabularySaving, setIsVocabularySaving] = useState(false);
  const [deletingVocabularyId, setDeletingVocabularyId] = useState<string | null>(null);

  const orderedPassages = useMemo(() => sortPassages(pack.passages), [pack.passages]);
  const currentPassage = orderedPassages.find((item) => item.passage_id === currentPassageId) ?? orderedPassages[0];
  const currentPassageQuestions = useMemo(
    () => pack.questions.filter((question) => question.passage_id === currentPassage?.passage_id),
    [currentPassage?.passage_id, pack.questions]
  );
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
  const annotationUnavailableMessage = "后端未连接，标注暂时无法保存；阅读和作答仍可继续。";
  const fallbackAnnotationMessage = "示例数据下不能保存标注，请先导入材料并启动后端。";
  const addVocabularyUnavailableMessage = "后端未连接，暂时无法把这条生词标注加入词库。";
  const vocabularyUnavailableMessage = "后端未连接，暂时无法读取本地词库。";
  const vocabularySaveUnavailableMessage = "后端未连接，暂时无法保存词条修改。";
  const vocabularyDeleteUnavailableMessage = "后端未连接，暂时无法删除词条。";

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

  async function refreshAnnotations(packId: string) {
    setIsAnnotationsLoading(true);
    setAnnotationError(null);
    setAnnotationNotice(null);
    try {
      const nextAnnotations = await listAnnotations(packId);
      setAnnotations(nextAnnotations);
    } catch {
      setAnnotations([]);
      setAnnotationError(annotationUnavailableMessage);
      setAnnotationNotice(null);
    } finally {
      setIsAnnotationsLoading(false);
    }
  }

  async function handleCreateAnnotation(payload: AnnotationCreate): Promise<boolean> {
    if (payload.selected_text.trim().length === 0) {
      setAnnotationError("请先输入要标注的词、短语或句子。");
      return false;
    }

    if (isUsingFallback) {
      setAnnotationError(fallbackAnnotationMessage);
      return false;
    }

    setIsAnnotationSaving(true);
    setAnnotationError(null);
    try {
      const created = await createAnnotation(payload);
      setAnnotations((prev) => [...prev, created]);
      return true;
    } catch {
      setAnnotationError(annotationUnavailableMessage);
      return false;
    } finally {
      setIsAnnotationSaving(false);
    }
  }

  async function handleDeleteAnnotation(annotationId: string) {
    setDeletingAnnotationId(annotationId);
    setAnnotationError(null);
    setAnnotationNotice(null);
    try {
      await deleteAnnotation(annotationId);
      setAnnotations((prev) => prev.filter((annotation) => annotation.annotation_id !== annotationId));
    } catch {
      setAnnotationError(annotationUnavailableMessage);
    } finally {
      setDeletingAnnotationId(null);
    }
  }


  async function handleAddAnnotationToVocabulary(annotation: ReadingAnnotation) {
    if (isUsingFallback) {
      setAnnotationNotice(null);
      setAnnotationError(fallbackAnnotationMessage);
      return false;
    }

    setAddingVocabularyAnnotationId(annotation.annotation_id);
    setAnnotationError(null);
    setAnnotationNotice(null);
    try {
      const payload: VocabularyItemCreate = {
        word: annotation.selected_text,
        source_annotation_id: annotation.annotation_id,
        source_pack_id: annotation.pack_id,
        source_passage_id: annotation.passage_id,
        source_paragraph_id: annotation.paragraph_id,
        review_status: "new"
      };
      const created = await createVocabularyItem(payload);
      setAnnotationNotice(`已加入词库：${created.word}`);
      return true;
    } catch (error) {
      const message = error instanceof ApiError ? error.message : addVocabularyUnavailableMessage;
      setAnnotationError(`加入词库失败：${message}`);
      return false;
    } finally {
      setAddingVocabularyAnnotationId(null);
    }
  }


  async function openVocabularyItem(vocabId: string, fallbackItem?: VocabularyItem) {
    setSelectedVocabularyId(vocabId);
    setVocabularyError(null);
    if (fallbackItem) {
      setSelectedVocabularyItem(fallbackItem);
    }

    setIsVocabularyDetailLoading(true);
    try {
      const detail = await getVocabularyItem(vocabId);
      setSelectedVocabularyItem(detail);
      setVocabularyItems((prev) => prev.map((item) => item.vocab_id === detail.vocab_id ? detail : item));
    } catch {
      if (!fallbackItem) {
        setSelectedVocabularyItem(null);
      }
      setVocabularyError(vocabularyUnavailableMessage);
    } finally {
      setIsVocabularyDetailLoading(false);
    }
  }

  async function refreshVocabularyItems(preferredVocabId?: string) {
    setIsVocabularyLoading(true);
    setVocabularyError(null);
    setDeletingVocabularyId(null);
    try {
      const items = await listVocabularyItems();
      setVocabularyItems(items);
      if (items.length === 0) {
        setSelectedVocabularyId(null);
        setSelectedVocabularyItem(null);
        return;
      }

      const targetId = preferredVocabId && items.some((item) => item.vocab_id === preferredVocabId)
        ? preferredVocabId
        : selectedVocabularyId && items.some((item) => item.vocab_id === selectedVocabularyId)
          ? selectedVocabularyId
          : items[0].vocab_id;
      const cachedItem = items.find((item) => item.vocab_id === targetId) ?? items[0];
      await openVocabularyItem(cachedItem.vocab_id, cachedItem);
    } catch {
      setVocabularyItems([]);
      setSelectedVocabularyId(null);
      setSelectedVocabularyItem(null);
      setVocabularyError(vocabularyUnavailableMessage);
    } finally {
      setIsVocabularyLoading(false);
    }
  }

  async function handleUpdateVocabularyItem(vocabId: string, payload: VocabularyItemUpdate) {
    setIsVocabularySaving(true);
    setVocabularyError(null);
    try {
      const updated = await updateVocabularyItem(vocabId, payload);
      setVocabularyItems((prev) => prev.map((item) => item.vocab_id === updated.vocab_id ? updated : item));
      setSelectedVocabularyItem(updated);
      setSelectedVocabularyId(updated.vocab_id);
      return updated;
    } catch {
      setVocabularyError(vocabularySaveUnavailableMessage);
      return null;
    } finally {
      setIsVocabularySaving(false);
    }
  }

  async function handleDeleteVocabularyItem(vocabId: string) {
    setDeletingVocabularyId(vocabId);
    setVocabularyError(null);
    try {
      await deleteVocabularyItem(vocabId);
      const remainingItems = vocabularyItems.filter((item) => item.vocab_id !== vocabId);
      setVocabularyItems(remainingItems);
      if (selectedVocabularyId === vocabId) {
        if (remainingItems.length === 0) {
          setSelectedVocabularyId(null);
          setSelectedVocabularyItem(null);
        } else {
          const nextItem = remainingItems[0];
          await openVocabularyItem(nextItem.vocab_id, nextItem);
        }
      }
      return true;
    } catch {
      setVocabularyError(vocabularyDeleteUnavailableMessage);
      return false;
    } finally {
      setDeletingVocabularyId(null);
    }
  }
  async function loadInitialData() {
    setWorkspaceError(null);
    setAnnotations([]);
    setAnnotationError(null);
    setAnnotationNotice(null);
    setDeletingAnnotationId(null);
    try {
      const summaries = await refreshReadingPacks();
      if (summaries.length > 0) {
        const firstPack = await getReadingPack(summaries[0].pack_id);
        setPack(firstPack);
        setSelectedAnswers({});
        setCurrentPassageId(sortPassages(firstPack.passages)[0]?.passage_id ?? "");
        setLatestAttempt(null);
        setSelectedAttempt(null);
        setNotice("");
        await refreshAnnotations(firstPack.pack_id);
      } else {
        setPack(mockReadingPack);
        setCurrentPassageId(sortPassages(mockReadingPack.passages)[0]?.passage_id ?? "");
        setIsUsingFallback(true);
        setAnnotations([]);
        setAnnotationError(fallbackAnnotationMessage);
        setAnnotationNotice(null);
        setNotice("还没有导入阅读材料，请先导入 reading_pack。当前显示示例数据。");
      }
      await refreshAttempts();
    } catch {
      setPack(mockReadingPack);
      setPacks([]);
      setCurrentPassageId(sortPassages(mockReadingPack.passages)[0]?.passage_id ?? "");
      setIsUsingFallback(true);
      setAnnotations([]);
      setAnnotationError(annotationUnavailableMessage);
      setNotice("后端未连接，可使用示例数据预览界面；提交练习记录需要启动后端。");
    } finally {
      setIsInitialLoading(false);
    }
  }

  async function loadPack(packId: string, nextView: ViewKey = "workspace") {
    setIsPackLoading(true);
    setWorkspaceError(null);
    setAnnotations([]);
    setAnnotationError(null);
    setAnnotationNotice(null);
    setDeletingAnnotationId(null);
    try {
      const nextPack = await getReadingPack(packId);
      setPack(nextPack);
      setSelectedAnswers({});
      setCurrentPassageId(sortPassages(nextPack.passages)[0]?.passage_id ?? "");
      setLatestAttempt(null);
      setSelectedAttempt(null);
      setNotice("");
      setIsUsingFallback(false);
      setActiveView(nextView);
      await refreshAnnotations(nextPack.pack_id);
    } catch {
      setAnnotations([]);
      setAnnotationError(annotationUnavailableMessage);
      setAnnotationNotice(null);
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

  async function handleImportSuccess() {
    await refreshReadingPacks();
  }

  useEffect(() => {
    loadInitialData();
  }, []);

  useEffect(() => {
    if (activeView === "vocabulary") {
      void refreshVocabularyItems();
    }
  }, [activeView]);

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
          <ImportView onOpenImportedPack={handleOpenImportedPack} onImportSuccess={handleImportSuccess} />
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
            passages={orderedPassages}
            currentPassage={currentPassage}
            currentPassageQuestions={currentPassageQuestions}
            currentPassageId={currentPassage?.passage_id ?? ""}
            selectedAnswers={selectedAnswers}
            answeredCount={answeredCount}
            canSubmit={canSubmit}
            isUsingFallback={isUsingFallback}
            annotations={annotations}
            annotationError={annotationError}
            isAnnotationsLoading={isAnnotationsLoading}
            isAnnotationSaving={isAnnotationSaving}
            deletingAnnotationId={deletingAnnotationId}
            addingVocabularyAnnotationId={addingVocabularyAnnotationId}
            annotationNotice={annotationNotice}
            result={result}
            isPackLoading={isPackLoading}
            isSubmitting={isSubmitting}
            workspaceError={workspaceError}
            onRefresh={loadInitialData}
            onLoadPack={(packId) => loadPack(packId, "workspace")}
            onSelectPassage={setCurrentPassageId}
            onSelectAnswer={(questionId, answer) => setSelectedAnswers((prev) => ({ ...prev, [questionId]: answer }))}
            onCreateAnnotation={handleCreateAnnotation}
            onDeleteAnnotation={handleDeleteAnnotation}
            onAddAnnotationToVocabulary={handleAddAnnotationToVocabulary}
            onSubmitAttempt={handleSubmitAttempt}
            onOpenAttempts={() => setActiveView("attempts")}
          />
        )}
        {activeView === "attempts" && (
          <AttemptsView attempts={attempts} selectedAttempt={selectedAttempt} onRefresh={refreshAttempts} onOpenAttempt={openAttempt} />
        )}
        {activeView === "vocabulary" && (
          <VocabularyView
            items={vocabularyItems}
            selectedItem={selectedVocabularyItem}
            selectedVocabularyId={selectedVocabularyId}
            vocabularyError={vocabularyError}
            isLoading={isVocabularyLoading}
            isDetailLoading={isVocabularyDetailLoading}
            isSaving={isVocabularySaving}
            deletingVocabularyId={deletingVocabularyId}
            onRefresh={() => refreshVocabularyItems()}
            onSelectItem={(vocabId) => {
              const cachedItem = vocabularyItems.find((item) => item.vocab_id === vocabId);
              void openVocabularyItem(vocabId, cachedItem);
            }}
            onUpdateItem={handleUpdateVocabularyItem}
            onDeleteItem={handleDeleteVocabularyItem}
          />
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

function ImportView({
  onOpenImportedPack,
  onImportSuccess
}: {
  onOpenImportedPack: (packId: string) => Promise<void>;
  onImportSuccess: () => Promise<void>;
}) {
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
      try {
        await onImportSuccess();
        setImportError(null);
      } catch {
        setImportError("导入成功，但刷新 Library 失败。你可以稍后切换到 Library 查看，或点击进入 Workspace。");
      }
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
  passages,
  currentPassage,
  currentPassageQuestions,
  currentPassageId,
  selectedAnswers,
  answeredCount,
  canSubmit,
  isUsingFallback,
  annotations,
  annotationError,
  isAnnotationsLoading,
  isAnnotationSaving,
  deletingAnnotationId,
  addingVocabularyAnnotationId,
  annotationNotice,
  result,
  isPackLoading,
  isSubmitting,
  workspaceError,
  onRefresh,
  onLoadPack,
  onSelectPassage,
  onSelectAnswer,
  onCreateAnnotation,
  onDeleteAnnotation,
  onAddAnnotationToVocabulary,
  onSubmitAttempt,
  onOpenAttempts
}: {
  pack: ReadingPack;
  packs: ReadingPackSummary[];
  passages: ReadingPack["passages"];
  currentPassage: ReadingPack["passages"][number] | undefined;
  currentPassageQuestions: ReadingPack["questions"];
  currentPassageId: string;
  selectedAnswers: Record<string, string>;
  answeredCount: number;
  canSubmit: boolean;
  isUsingFallback: boolean;
  annotations: ReadingAnnotation[];
  annotationError: string | null;
  isAnnotationsLoading: boolean;
  isAnnotationSaving: boolean;
  deletingAnnotationId: string | null;
  addingVocabularyAnnotationId: string | null;
  annotationNotice: string | null;
  result: PracticeAttemptDetail | null;
  isPackLoading: boolean;
  isSubmitting: boolean;
  workspaceError: string | null;
  onRefresh: () => void;
  onLoadPack: (packId: string) => void;
  onSelectPassage: (passageId: string) => void;
  onSelectAnswer: (questionId: string, answer: string) => void;
  onCreateAnnotation: (payload: AnnotationCreate) => Promise<boolean>;
  onDeleteAnnotation: (annotationId: string) => Promise<void>;
  onAddAnnotationToVocabulary: (annotation: ReadingAnnotation) => Promise<boolean>;
  onSubmitAttempt: () => void;
  onOpenAttempts: () => void;
}) {
  const remaining = pack.questions.length - answeredCount;
  const currentAnsweredCount = currentPassageQuestions.filter((question) => Boolean(selectedAnswers[question.question_id])).length;
  const currentPassageAnnotations = annotations.filter((annotation) => annotation.passage_id === currentPassage?.passage_id);
  const [draftType, setDraftType] = useState<AnnotationType>("answer_evidence");
  const [draftParagraphId, setDraftParagraphId] = useState(currentPassage?.paragraphs[0]?.paragraph_id ?? "");
  const [draftQuestionId, setDraftQuestionId] = useState("");
  const [draftSelectedText, setDraftSelectedText] = useState("");
  const [draftNote, setDraftNote] = useState("");
  const [draftError, setDraftError] = useState<string | null>(null);

  useEffect(() => {
    const firstParagraphId = currentPassage?.paragraphs[0]?.paragraph_id ?? "";
    setDraftParagraphId((prev) => currentPassage?.paragraphs.some((paragraph) => paragraph.paragraph_id === prev) ? prev : firstParagraphId);
    setDraftQuestionId((prev) => currentPassageQuestions.some((question) => question.question_id === prev) ? prev : "");
    setDraftError(null);
  }, [currentPassage?.passage_id, currentPassage?.paragraphs, currentPassageQuestions]);

  const paragraphLabelMap = useMemo(() => new Map(
    (currentPassage?.paragraphs ?? []).map((paragraph) => [paragraph.paragraph_id, getParagraphLabel(paragraph.order)])
  ), [currentPassage?.paragraphs]);
  const questionLabelMap = useMemo(() => new Map(
    currentPassageQuestions.map((question) => [question.question_id, question.question_no || question.question_id])
  ), [currentPassageQuestions]);
  const annotationHelperText = isUsingFallback
    ? "示例数据下不能保存标注，请先导入材料并启动后端。"
    : "手动输入你想保留的词、短语、句子或答案依据，保存到当前阅读材料。";

  function handleUseSelectedText() {
    const selectedText = window.getSelection()?.toString().trim() ?? "";
    if (selectedText) {
      setDraftSelectedText(selectedText);
      setDraftError(null);
      return;
    }

    setDraftError("请先在文章中选中一段文字。");
  }

  async function handleSaveAnnotation() {
    const selectedText = draftSelectedText.trim();
    if (!selectedText) {
      setDraftError("请先输入要标注的词、短语或句子。");
      return;
    }
    if (!currentPassage || !draftParagraphId) {
      setDraftError("当前 passage 缺少可用段落，暂时无法保存标注。");
      return;
    }

    setDraftError(null);
    const created = await onCreateAnnotation({
      pack_id: pack.pack_id,
      passage_id: currentPassage.passage_id,
      paragraph_id: draftParagraphId,
      question_id: draftQuestionId || null,
      annotation_type: draftType,
      selected_text: selectedText,
      note: draftNote.trim() ? draftNote.trim() : null
    });

    if (created) {
      setDraftSelectedText("");
      setDraftNote("");
      setDraftQuestionId("");
    }
  }

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
          {passages.length > 1 && (
            <div className="passage-switcher" aria-label="Passage navigation">
              {passages.map((passage) => {
                const passageQuestions = pack.questions.filter((question) => question.passage_id === passage.passage_id);
                const completedCount = passageQuestions.filter((question) => Boolean(selectedAnswers[question.question_id])).length;

                return (
                  <button
                    key={passage.passage_id}
                    type="button"
                    className={passage.passage_id === currentPassageId ? "passage-tab active" : "passage-tab"}
                    onClick={() => onSelectPassage(passage.passage_id)}
                  >
                    <strong>Passage {passage.order}</strong>
                    <span>{passage.title || `${pack.title} · Passage ${passage.order}`}</span>
                    <small>{completedCount}/{passageQuestions.length} 已作答</small>
                  </button>
                );
              })}
            </div>
          )}
          <div className="pane-title">
            <p className="eyebrow">Passage</p>
            <h2>{currentPassage?.title ?? pack.title}</h2>
            {passages.length > 1 && currentPassage && (
              <p className="muted-text">第 {currentPassage.order} 篇，共 {passages.length} 篇</p>
            )}
          </div>
          <div className="paragraphs">
            {currentPassage?.paragraphs.map((paragraph) => (
              <p key={paragraph.paragraph_id}><span>{paragraph.order}</span>{paragraph.text}</p>
            ))}
          </div>
        </article>

        <section className="workspace-pane question-pane">
          <div className="question-topbar">
            <div>
              <p className="eyebrow">Questions</p>
              <h2>{currentAnsweredCount}/{currentPassageQuestions.length} 当前篇章已作答</h2>
              <p className="muted-text">{answeredCount}/{pack.questions.length} 全部题目已作答</p>
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
            {currentPassageQuestions.map((question) => (
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
            {currentPassageQuestions.length === 0 && (
              <div className="workspace-status">当前 passage 暂时没有关联题目。</div>
            )}
          </div>

          <section className="annotation-panel">
            <div className="section-title-row">
              <div>
                <p className="eyebrow">Annotations</p>
                <h2>{currentPassageAnnotations.length} 条当前篇章标注</h2>
                <p className="muted-text">当前篇章 {currentPassageAnnotations.length} 条 / 本材料共 {annotations.length} 条</p>
              </div>
            </div>

            <div className="annotation-form">
              <p className="import-help">{annotationHelperText}</p>
              <div className="annotation-grid">
                <label className="annotation-field">
                  <span>标注类型</span>
                  <select value={draftType} onChange={(event) => setDraftType(event.target.value as AnnotationType)} disabled={isUsingFallback || isAnnotationSaving}>
                    {annotationTypeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </select>
                </label>
                <label className="annotation-field">
                  <span>关联段落</span>
                  <select value={draftParagraphId} onChange={(event) => setDraftParagraphId(event.target.value)} disabled={isUsingFallback || isAnnotationSaving || !currentPassage}>
                    {(currentPassage?.paragraphs ?? []).map((paragraph) => <option key={paragraph.paragraph_id} value={paragraph.paragraph_id}>{getParagraphLabel(paragraph.order)}</option>)}
                  </select>
                </label>
                <label className="annotation-field">
                  <span>关联题目</span>
                  <select value={draftQuestionId} onChange={(event) => setDraftQuestionId(event.target.value)} disabled={isUsingFallback || isAnnotationSaving}>
                    <option value="">不关联题目</option>
                    {currentPassageQuestions.map((question) => <option key={question.question_id} value={question.question_id}>{question.question_no || question.question_id}</option>)}
                  </select>
                </label>
              </div>
              <label className="annotation-field">
                <span>标注内容</span>
                <textarea
                  value={draftSelectedText}
                  onChange={(event) => setDraftSelectedText(event.target.value)}
                  placeholder="输入要标注的词、短语或句子"
                  disabled={isUsingFallback || isAnnotationSaving}
                />
                <div className="annotation-inline-actions">
                  <button
                    type="button"
                    className="secondary-action"
                    onClick={handleUseSelectedText}
                    disabled={isUsingFallback || isAnnotationSaving}
                  >
                    填入选中文字
                  </button>
                </div>
              </label>
              <label className="annotation-field">
                <span>备注</span>
                <textarea
                  value={draftNote}
                  onChange={(event) => setDraftNote(event.target.value)}
                  placeholder="可选备注，例如同义替换关系、答案依据说明"
                  disabled={isUsingFallback || isAnnotationSaving}
                />
              </label>
              {draftError && <div className="annotation-error">{draftError}</div>}
              {annotationNotice && <div className="workspace-status annotation-status">{annotationNotice}</div>}
              {annotationError && <div className="annotation-error">{annotationError}</div>}
              {isAnnotationsLoading && <p className="muted-text">正在加载本材料标注……</p>}
              <button className="primary-action" type="button" onClick={() => void handleSaveAnnotation()} disabled={isUsingFallback || isAnnotationSaving || !currentPassage || !draftParagraphId}>
                {isAnnotationSaving ? "保存中……" : "保存标注"}
              </button>
            </div>

            <div className="annotation-list">
              {currentPassageAnnotations.length === 0 ? (
                <p className="annotation-empty">当前 passage 还没有标注。</p>
              ) : currentPassageAnnotations.map((annotation) => (
                <div key={annotation.annotation_id} className="annotation-row">
                  <div className="annotation-meta">
                    <span className="annotation-type-pill">{getAnnotationTypeLabel(annotation.annotation_type)}</span>
                    <span>{paragraphLabelMap.get(annotation.paragraph_id) ?? annotation.paragraph_id}</span>
                    {annotation.question_id && <span>题目 {questionLabelMap.get(annotation.question_id) ?? annotation.question_id}</span>}
                    <span>{formatDate(annotation.created_at ?? undefined)}</span>
                  </div>
                  <strong>{annotation.selected_text}</strong>
                  {annotation.note && <p>{annotation.note}</p>}
                  <div className="annotation-row-actions">
                    {annotation.annotation_type === "vocabulary" && (
                      <button
                        type="button"
                        className="secondary-action"
                        disabled={addingVocabularyAnnotationId === annotation.annotation_id}
                        onClick={() => void onAddAnnotationToVocabulary(annotation)}
                      >
                        {addingVocabularyAnnotationId === annotation.annotation_id ? "加入中……" : "加入词库"}
                      </button>
                    )}
                    <button
                      type="button"
                      className="danger-action"
                      disabled={deletingAnnotationId === annotation.annotation_id}
                      onClick={() => void onDeleteAnnotation(annotation.annotation_id)}
                    >
                      {deletingAnnotationId === annotation.annotation_id ? "删除中……" : "删除"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {result && <AttemptResult result={result} />}
          <button className="text-action" type="button" onClick={onOpenAttempts}>查看最近练习记录</button>
        </section>
      </div>
      )}
    </section>
  );
}

function VocabularyView({
  items,
  selectedItem,
  selectedVocabularyId,
  vocabularyError,
  isLoading,
  isDetailLoading,
  isSaving,
  deletingVocabularyId,
  onRefresh,
  onSelectItem,
  onUpdateItem,
  onDeleteItem
}: {
  items: VocabularyItem[];
  selectedItem: VocabularyItem | null;
  selectedVocabularyId: string | null;
  vocabularyError: string | null;
  isLoading: boolean;
  isDetailLoading: boolean;
  isSaving: boolean;
  deletingVocabularyId: string | null;
  onRefresh: () => Promise<void>;
  onSelectItem: (vocabId: string) => void;
  onUpdateItem: (vocabId: string, payload: VocabularyItemUpdate) => Promise<VocabularyItem | null>;
  onDeleteItem: (vocabId: string) => Promise<boolean>;
}) {
  const [draftMeaning, setDraftMeaning] = useState("");
  const [draftSourceSentence, setDraftSourceSentence] = useState("");
  const [draftReviewStatus, setDraftReviewStatus] = useState<VocabularyReviewStatus>("new");
  const [formNotice, setFormNotice] = useState<string | null>(null);

  useEffect(() => {
    setDraftMeaning(selectedItem?.meaning ?? "");
    setDraftSourceSentence(selectedItem?.source_sentence ?? "");
    setDraftReviewStatus(selectedItem?.review_status ?? "new");
    setFormNotice(null);
  }, [selectedItem]);

  async function handleSave() {
    if (!selectedItem) {
      return;
    }

    const payload: VocabularyItemUpdate = {};
    const nextMeaning = normalizeNullableText(draftMeaning);
    const nextSourceSentence = normalizeNullableText(draftSourceSentence);

    if (nextMeaning !== (selectedItem.meaning ?? null)) {
      payload.meaning = nextMeaning;
    }
    if (nextSourceSentence !== (selectedItem.source_sentence ?? null)) {
      payload.source_sentence = nextSourceSentence;
    }
    if (draftReviewStatus !== selectedItem.review_status) {
      payload.review_status = draftReviewStatus;
    }

    if (Object.keys(payload).length === 0) {
      setFormNotice("当前没有需要保存的修改。");
      return;
    }

    const updated = await onUpdateItem(selectedItem.vocab_id, payload);
    if (updated) {
      setFormNotice("词条已更新。");
    }
  }

  async function handleDelete() {
    if (!selectedItem) {
      return;
    }

    const deleted = await onDeleteItem(selectedItem.vocab_id);
    if (deleted) {
      setFormNotice("词条已删除。");
    }
  }

  return (
    <section className="page-stack">
      <div className="page-header slim">
        <div>
          <p className="eyebrow">Vocabulary</p>
          <h1>本地词库</h1>
          <p>查看已入库的词条，并维护释义、来源句和当前熟悉程度。</p>
        </div>
        <div className="inline-actions">
          <button type="button" onClick={() => void onRefresh()}>刷新词库</button>
        </div>
      </div>

      {vocabularyError && <div className="workspace-error">{vocabularyError}</div>}

      {isLoading && items.length === 0 ? (
        <div className="loading-card">正在读取本地词库……</div>
      ) : items.length === 0 ? (
        <div className="empty-state">
          <h2>还没有词条</h2>
          <p>还没有词条。你可以先在 Workspace 标注生词，后续会支持从标注加入词库。</p>
        </div>
      ) : (
        <div className="vocabulary-layout">
          <div className="vocabulary-list-panel">
            <div className="section-title-row">
              <div>
                <p className="eyebrow">Items</p>
                <h2>{items.length} 条词条</h2>
              </div>
            </div>
            <div className="vocabulary-list">
              {items.map((item) => (
                <button
                  key={item.vocab_id}
                  type="button"
                  className={selectedVocabularyId === item.vocab_id ? "vocabulary-row active" : "vocabulary-row"}
                  onClick={() => onSelectItem(item.vocab_id)}
                >
                  <div>
                    <strong>{item.word}</strong>
                    <small>{item.meaning?.trim() ? item.meaning : "暂未填写释义"}</small>
                  </div>
                  <div className="vocabulary-row-meta">
                    <span className={`review-status-pill ${item.review_status}`}>{getVocabularyReviewStatusLabel(item.review_status)}</span>
                    <small>{formatDate(item.created_at ?? undefined)}</small>
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="vocabulary-detail-panel">
            {!selectedItem ? (
              <EmptyState title="选择一条词条" description="点击左侧词条后，这里会显示可编辑的释义、来源句和复习状态。" />
            ) : (
              <div className="vocabulary-detail-stack">
                <div className="section-title-row">
                  <div>
                    <p className="eyebrow">Detail</p>
                    <h2>{selectedItem.word}</h2>
                    <p className="muted-text">{isDetailLoading ? "正在刷新词条详情……" : "可直接编辑并保存到本地词库。"}</p>
                  </div>
                  <span className={`review-status-pill ${selectedItem.review_status}`}>{getVocabularyReviewStatusLabel(selectedItem.review_status)}</span>
                </div>

                <div className="vocabulary-meta-grid">
                  <div className="vocabulary-meta-card">
                    <strong>source_annotation_id</strong>
                    <span>{selectedItem.source_annotation_id ?? "-"}</span>
                  </div>
                  <div className="vocabulary-meta-card">
                    <strong>created_at</strong>
                    <span>{formatDate(selectedItem.created_at ?? undefined)}</span>
                  </div>
                  <div className="vocabulary-meta-card">
                    <strong>word</strong>
                    <span>{selectedItem.word}</span>
                  </div>
                  <div className="vocabulary-meta-card">
                    <strong>review_status</strong>
                    <span>{selectedItem.review_status}</span>
                  </div>
                </div>

                <div className="vocabulary-edit-form">
                  <label className="vocabulary-field">
                    <span>meaning</span>
                    <textarea
                      value={draftMeaning}
                      onChange={(event) => setDraftMeaning(event.target.value)}
                      placeholder="补充这个词条的中文释义或英文说明"
                      disabled={isSaving || deletingVocabularyId === selectedItem.vocab_id}
                    />
                  </label>

                  <label className="vocabulary-field">
                    <span>source_sentence</span>
                    <textarea
                      value={draftSourceSentence}
                      onChange={(event) => setDraftSourceSentence(event.target.value)}
                      placeholder="补充这个词条来自哪一句原文"
                      disabled={isSaving || deletingVocabularyId === selectedItem.vocab_id}
                    />
                  </label>

                  <label className="vocabulary-field">
                    <span>review_status</span>
                    <select
                      value={draftReviewStatus}
                      onChange={(event) => setDraftReviewStatus(event.target.value as VocabularyReviewStatus)}
                      disabled={isSaving || deletingVocabularyId === selectedItem.vocab_id}
                    >
                      {vocabularyReviewStatusOptions.map((option) => (
                        <option key={option.value} value={option.value}>{option.value} · {option.label}</option>
                      ))}
                    </select>
                  </label>

                  {formNotice && <div className="workspace-status vocabulary-status">{formNotice}</div>}

                  <div className="vocabulary-actions">
                    <button
                      className="primary-action"
                      type="button"
                      onClick={() => void handleSave()}
                      disabled={isSaving || deletingVocabularyId === selectedItem.vocab_id}
                    >
                      {isSaving ? "保存中……" : "保存修改"}
                    </button>
                    <button
                      className="danger-action"
                      type="button"
                      onClick={() => void handleDelete()}
                      disabled={deletingVocabularyId === selectedItem.vocab_id || isSaving}
                    >
                      {deletingVocabularyId === selectedItem.vocab_id ? "删除中……" : "删除词条"}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
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






