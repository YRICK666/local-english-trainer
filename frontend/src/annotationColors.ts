import type { AnnotationType } from "./types";

export type AnnotationColorMap = Record<AnnotationType, string>;

export const ANNOTATION_COLORS_STORAGE_KEY = "local-english-trainer.annotation-colors";

export const DEFAULT_ANNOTATION_COLORS: AnnotationColorMap = {
  answer_evidence: "#DCEBFF",
  synonym_replacement: "#FFE3C2",
  vocabulary: "#F7EDAF",
  difficult_sentence: "#D8F1DF"
};

const ANNOTATION_COLOR_VARIABLES: Record<AnnotationType, string> = {
  answer_evidence: "--annotation-answer-evidence",
  synonym_replacement: "--annotation-synonym-replacement",
  vocabulary: "--annotation-vocabulary",
  difficult_sentence: "--annotation-difficult-sentence"
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isValidAnnotationColor(value: unknown): value is string {
  return typeof value === "string" && /^#[0-9A-Fa-f]{6}$/.test(value.trim());
}

export function normalizeAnnotationColors(value: unknown): AnnotationColorMap {
  const record = isRecord(value) ? value : {};

  return {
    answer_evidence: isValidAnnotationColor(record.answer_evidence) ? record.answer_evidence.toUpperCase() : DEFAULT_ANNOTATION_COLORS.answer_evidence,
    synonym_replacement: isValidAnnotationColor(record.synonym_replacement) ? record.synonym_replacement.toUpperCase() : DEFAULT_ANNOTATION_COLORS.synonym_replacement,
    vocabulary: isValidAnnotationColor(record.vocabulary) ? record.vocabulary.toUpperCase() : DEFAULT_ANNOTATION_COLORS.vocabulary,
    difficult_sentence: isValidAnnotationColor(record.difficult_sentence) ? record.difficult_sentence.toUpperCase() : DEFAULT_ANNOTATION_COLORS.difficult_sentence
  };
}

export function loadAnnotationColors(): AnnotationColorMap {
  if (typeof window === "undefined") {
    return { ...DEFAULT_ANNOTATION_COLORS };
  }

  try {
    const raw = window.localStorage.getItem(ANNOTATION_COLORS_STORAGE_KEY);
    if (!raw) {
      return { ...DEFAULT_ANNOTATION_COLORS };
    }
    return normalizeAnnotationColors(JSON.parse(raw));
  } catch {
    return { ...DEFAULT_ANNOTATION_COLORS };
  }
}

export function saveAnnotationColors(colors: AnnotationColorMap): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.setItem(ANNOTATION_COLORS_STORAGE_KEY, JSON.stringify(normalizeAnnotationColors(colors)));
  } catch {
    // Ignore storage failures so Settings cannot break reading flow.
  }
}

export function getAnnotationColorCssVariables(colors: AnnotationColorMap): Record<string, string> {
  const normalized = normalizeAnnotationColors(colors);
  return {
    [ANNOTATION_COLOR_VARIABLES.answer_evidence]: normalized.answer_evidence,
    [ANNOTATION_COLOR_VARIABLES.synonym_replacement]: normalized.synonym_replacement,
    [ANNOTATION_COLOR_VARIABLES.vocabulary]: normalized.vocabulary,
    [ANNOTATION_COLOR_VARIABLES.difficult_sentence]: normalized.difficult_sentence
  };
}
