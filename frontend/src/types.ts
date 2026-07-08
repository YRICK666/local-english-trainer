export type OptionLabel = "A" | "B" | "C" | "D";

export type ReadingPackSummary = {
  pack_id: string;
  title: string;
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
  language?: string;
  passages: Passage[];
  questions: ReadingQuestion[];
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
