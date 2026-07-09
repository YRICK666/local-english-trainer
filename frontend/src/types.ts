export type OptionLabel = "A" | "B" | "C" | "D";

export type ImportValidationStats = {
  passage_count: number;
  paragraph_count: number;
  question_count: number;
};

export type ImportValidationResult = {
  valid: boolean;
  errors: string[];
  warnings: string[];
  stats: ImportValidationStats;
};

export type ReadingPackSummary = {
  pack_id: string;
  title: string;
  description?: string;
  language?: string;
  level?: string;
  tags?: string[];
  source?: Record<string, unknown>;
  passage_count: number;
  question_count: number;
};

export type Paragraph = {
  paragraph_id: string;
  text: string;
  order: number;
};

export type Passage = {
  passage_id: string;
  title?: string;
  content: string;
  paragraphs: Paragraph[];
  order: number;
};

export type QuestionOption = {
  option_id?: string;
  label: OptionLabel;
  text: string;
};

export type ReadingQuestion = {
  question_id: string;
  passage_id: string;
  question_no?: string;
  question_type: "single_choice";
  stem: string;
  answer?: OptionLabel;
  analysis?: string;
  evidence_hint?: string;
  options: QuestionOption[];
};

export type ReadingPack = ReadingPackSummary & {
  metadata?: Record<string, unknown>;
  passages: Passage[];
  questions: ReadingQuestion[];
};

export type ReadingPackDetail = ReadingPackSummary & {
  metadata: Record<string, unknown>;
  passages: Passage[];
  questions: ReadingQuestion[];
};

export type ReadingPackImportResponse = {
  imported: boolean;
  pack: ReadingPackDetail;
  validation: ImportValidationResult;
};

export type AttemptAnswerIn = {
  question_id: string;
  selected_answer: string;
};

export type AttemptAnswer = {
  answer_id: string;
  attempt_id: string;
  question_id: string;
  selected_answer: string;
  correct_answer: string;
  is_correct: boolean;
};

export type PracticeAttemptSummary = {
  attempt_id: string;
  pack_id: string;
  total_questions: number;
  correct_count: number;
  accuracy: number;
  created_at?: string;
};

export type PracticeAttemptDetail = PracticeAttemptSummary & {
  answers: AttemptAnswer[];
};

export type AnnotationType = "answer_evidence" | "synonym_replacement" | "vocabulary" | "difficult_sentence";

export type ReadingAnnotation = {
  annotation_id: string;
  pack_id: string;
  passage_id: string;
  paragraph_id: string;
  question_id?: string | null;
  annotation_type: AnnotationType;
  selected_text: string;
  note?: string | null;
  created_at?: string | null;
};

export type AnnotationCreate = {
  pack_id: string;
  passage_id: string;
  paragraph_id: string;
  question_id?: string | null;
  annotation_type: AnnotationType;
  selected_text: string;
  note?: string | null;
};

export type AnnotationDeleteResponse = {
  deleted: boolean;
  annotation_id: string;
};
export type VocabularyReviewStatus = "new" | "learning" | "familiar";

export type VocabularyItem = {
  vocab_id: string;
  word: string;
  meaning?: string | null;
  source_sentence?: string | null;
  source_pack_id?: string | null;
  source_passage_id?: string | null;
  source_paragraph_id?: string | null;
  source_annotation_id?: string | null;
  review_status: VocabularyReviewStatus;
  created_at?: string | null;
};

export type VocabularyItemUpdate = {
  word?: string | null;
  meaning?: string | null;
  source_sentence?: string | null;
  source_pack_id?: string | null;
  source_passage_id?: string | null;
  source_paragraph_id?: string | null;
  source_annotation_id?: string | null;
  review_status?: VocabularyReviewStatus | null;
};

export type VocabularyDeleteResponse = {
  deleted: boolean;
  vocab_id: string;
};

