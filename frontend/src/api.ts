import type {
  AnnotationCreate,
  AnnotationCreateResult,
  AnnotationDeleteResponse,
  AttemptAnswerIn,
  ImportValidationResult,
  PracticeAttemptDetail,
  PracticeAttemptSummary,
  ReadingAnnotation,
  ReadingPack,
  ReadingPackImportResponse,
  ReadingPackSummary,
  SentenceDeleteResponse,
  SentenceItem,
  SentenceItemCreate,
  SentenceItemUpdate,
  VocabularyDeleteResponse,
  VocabularyItem,
  VocabularyItemCreate,
  VocabularyItemUpdate
} from "./types";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `Request failed with status ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  if (!response.ok) {
    let detail: unknown = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? body;
    } catch {
      detail = response.statusText;
    }
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

export function validateReadingPack(payload: unknown) {
  return requestJson<ImportValidationResult>("/api/import/reading-pack/validate", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function importReadingPack(payload: unknown) {
  return requestJson<ReadingPackImportResponse>("/api/import/reading-pack", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listReadingPacks() {
  return requestJson<ReadingPackSummary[]>("/api/reading-packs");
}

export function getReadingPack(packId: string) {
  return requestJson<ReadingPack>(`/api/reading-packs/${encodeURIComponent(packId)}`);
}

export function submitPracticeAttempt(packId: string, answers: AttemptAnswerIn[]) {
  return requestJson<PracticeAttemptDetail>("/api/practice-attempts", {
    method: "POST",
    body: JSON.stringify({ pack_id: packId, answers })
  });
}

export function listPracticeAttempts() {
  return requestJson<PracticeAttemptSummary[]>("/api/practice-attempts");
}

export function getPracticeAttempt(attemptId: string) {
  return requestJson<PracticeAttemptDetail>(`/api/practice-attempts/${encodeURIComponent(attemptId)}`);
}

export function listAnnotations(packId: string) {
  return requestJson<ReadingAnnotation[]>(`/api/annotations?pack_id=${encodeURIComponent(packId)}`);
}

export function createAnnotation(payload: AnnotationCreate) {
  return requestJson<AnnotationCreateResult>("/api/annotations", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function deleteAnnotation(annotationId: string) {
  return requestJson<AnnotationDeleteResponse>(`/api/annotations/${encodeURIComponent(annotationId)}`, {
    method: "DELETE"
  });
}

export function createVocabularyItem(payload: VocabularyItemCreate) {
  return requestJson<VocabularyItem>("/api/vocabulary", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listVocabularyItems() {
  return requestJson<VocabularyItem[]>("/api/vocabulary");
}

export function getVocabularyItem(vocabId: string) {
  return requestJson<VocabularyItem>(`/api/vocabulary/${encodeURIComponent(vocabId)}`);
}

export function updateVocabularyItem(vocabId: string, payload: VocabularyItemUpdate) {
  return requestJson<VocabularyItem>(`/api/vocabulary/${encodeURIComponent(vocabId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export function deleteVocabularyItem(vocabId: string) {
  return requestJson<VocabularyDeleteResponse>(`/api/vocabulary/${encodeURIComponent(vocabId)}`, {
    method: "DELETE"
  });
}

export function listSentenceItems() {
  return requestJson<SentenceItem[]>("/api/sentences");
}

export function getSentenceItem(sentenceId: string) {
  return requestJson<SentenceItem>(`/api/sentences/${encodeURIComponent(sentenceId)}`);
}

export function createSentenceItem(payload: SentenceItemCreate) {
  return requestJson<SentenceItem>("/api/sentences", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateSentenceItem(sentenceId: string, payload: SentenceItemUpdate) {
  return requestJson<SentenceItem>(`/api/sentences/${encodeURIComponent(sentenceId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export function deleteSentenceItem(sentenceId: string) {
  return requestJson<SentenceDeleteResponse>(`/api/sentences/${encodeURIComponent(sentenceId)}`, {
    method: "DELETE"
  });
}
