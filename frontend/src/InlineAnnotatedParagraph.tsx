import type { CSSProperties, KeyboardEvent, MouseEvent } from "react";

import { buildAnnotationSegments, getParagraphSelection, type ParagraphSelection } from "./annotationText";
import type { AnnotationColorMap } from "./annotationColors";
import type { AnnotationType, ReadingAnnotation } from "./types";

type Props = {
  paragraphId: string;
  order: number;
  text: string;
  annotations: ReadingAnnotation[];
  annotationColors: AnnotationColorMap;
  focusedAnnotationId?: string | null;
  focusedParagraphId?: string | null;
  onSelectionContextMenu: (event: MouseEvent<HTMLElement>, selection: ParagraphSelection) => void;
  onOpenAnnotations: (annotations: ReadingAnnotation[]) => void;
};

const annotationTypeLabels: Record<AnnotationType, string> = {
  answer_evidence: "答案依据",
  synonym_replacement: "同义替换",
  vocabulary: "生词",
  difficult_sentence: "长难句"
};

function buildSegmentFill(colors: string[]) {
  if (colors.length <= 1) {
    return colors[0];
  }

  const step = 100 / colors.length;
  return `linear-gradient(90deg, ${colors.map((color, index) => {
    const start = Number((index * step).toFixed(2));
    const end = Number(((index + 1) * step).toFixed(2));
    return `${color} ${start}%, ${color} ${end}%`;
  }).join(", ")})`;
}

function buildAnnotationStyle(annotations: ReadingAnnotation[], annotationColors: AnnotationColorMap): CSSProperties {
  const colors = [...new Set(annotations.map((annotation) => annotationColors[annotation.annotation_type]))];
  const primaryColor = colors[0] ?? annotationColors.vocabulary;
  return {
    "--annotation-highlight-fill": buildSegmentFill(colors),
    "--annotation-highlight-underline": primaryColor
  } as CSSProperties;
}

function getAnnotationSummary(annotations: ReadingAnnotation[]) {
  return annotations.map((annotation) => annotationTypeLabels[annotation.annotation_type]).join("、");
}

export function InlineAnnotatedParagraph({ paragraphId, order, text, annotations, annotationColors, focusedAnnotationId, focusedParagraphId, onSelectionContextMenu, onOpenAnnotations }: Props) {
  const segments = buildAnnotationSegments(text, annotations);

  function openSegment(segmentAnnotations: ReadingAnnotation[]) {
    if (segmentAnnotations.length > 0) onOpenAnnotations(segmentAnnotations);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLSpanElement>, segmentAnnotations: ReadingAnnotation[]) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openSegment(segmentAnnotations);
    }
  }

  return (
    <p
      id={`workspace-paragraph-${paragraphId}`}
      data-paragraph-id={paragraphId}
      className={focusedParagraphId === paragraphId ? "workspace-paragraph highlighted" : "workspace-paragraph"}
    >
      <span className="paragraph-order" aria-hidden="true">{order}</span>
      <span
        className="paragraph-text"
        data-paragraph-text="true"
        onContextMenu={(event) => {
          const selection = getParagraphSelection(event.currentTarget, text);
          if (selection) onSelectionContextMenu(event, selection);
        }}
      >
        {segments.map((segment) => segment.annotations.length === 0 ? segment.text : (
          <span
            key={`${paragraphId}:${segment.startOffset}:${segment.endOffset}:${segment.annotations.map((annotation) => annotation.annotation_id).join(":")}`}
            className={focusedAnnotationId && segment.annotations.some((annotation) => annotation.annotation_id === focusedAnnotationId) ? "inline-annotation focused" : "inline-annotation"}
            role="button"
            tabIndex={0}
            style={buildAnnotationStyle(segment.annotations, annotationColors)}
            title={getAnnotationSummary(segment.annotations)}
            aria-label={`标注：${getAnnotationSummary(segment.annotations)}`}
            onClick={() => openSegment(segment.annotations)}
            onKeyDown={(event) => handleKeyDown(event, segment.annotations)}
          >
            {segment.text}
          </span>
        ))}
      </span>
    </p>
  );
}
