import type { AttemptAnswerIn, PracticeAttemptDetail, PracticeAttemptSummary, ReadingPack, ReadingPackImportResponse, ReadingPackSummary, ImportValidationResult } from "./types";

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
