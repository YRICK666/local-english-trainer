import type { ReadingAnnotation } from "./types";

export type AnnotationSegment = {
  startOffset: number;
  endOffset: number;
  text: string;
  annotations: ReadingAnnotation[];
};

export type ParagraphSelection = {
  selectedText: string;
  startOffset: number;
  endOffset: number;
};

const codePoints = (value: string) => Array.from(value);

function uniqueLegacyRange(text: string, selectedText: string) {
  if (!selectedText) return null;
  const source = codePoints(text);
  const needle = codePoints(selectedText);
  const matches: number[] = [];
  for (let index = 0; index <= source.length - needle.length; index += 1) {
    if (needle.every((character, offset) => source[index + offset] === character)) matches.push(index);
  }
  return matches.length === 1 ? { startOffset: matches[0], endOffset: matches[0] + needle.length } : null;
}

function validRange(text: string, annotation: ReadingAnnotation) {
  const points = codePoints(text);
  if (annotation.start_offset != null && annotation.end_offset != null) {
    if (annotation.start_offset < 0 || annotation.start_offset >= annotation.end_offset || annotation.end_offset > points.length) return null;
    return points.slice(annotation.start_offset, annotation.end_offset).join("") === annotation.selected_text
      ? { startOffset: annotation.start_offset, endOffset: annotation.end_offset }
      : null;
  }
  return uniqueLegacyRange(text, annotation.selected_text);
}

export function buildAnnotationSegments(text: string, annotations: ReadingAnnotation[]): AnnotationSegment[] {
  const points = codePoints(text);
  const ranges = annotations.flatMap((annotation) => {
    const range = validRange(text, annotation);
    return range ? [{ ...range, annotation }] : [];
  });
  const boundaries = [...new Set([0, points.length, ...ranges.flatMap((range) => [range.startOffset, range.endOffset])])].sort((left, right) => left - right);
  return boundaries.slice(0, -1).map((startOffset, index) => {
    const endOffset = boundaries[index + 1];
    return {
      startOffset,
      endOffset,
      text: points.slice(startOffset, endOffset).join(""),
      annotations: ranges
        .filter((range) => range.startOffset < endOffset && range.endOffset > startOffset)
        .map((range) => range.annotation)
        .sort((left, right) => left.annotation_id.localeCompare(right.annotation_id))
    };
  }).filter((segment) => segment.text.length > 0);
}

export function getParagraphSelection(textElement: HTMLElement, paragraphText: string): ParagraphSelection | null {
  const selection = window.getSelection();
  if (!selection || selection.rangeCount !== 1 || selection.isCollapsed) return null;
  const range = selection.getRangeAt(0);
  if (!textElement.contains(range.startContainer) || !textElement.contains(range.endContainer)) return null;

  const prefix = range.cloneRange();
  prefix.selectNodeContents(textElement);
  prefix.setEnd(range.startContainer, range.startOffset);
  const selectedPoints = codePoints(range.toString());
  let first = 0;
  let last = selectedPoints.length;
  while (first < last && /^\s$/u.test(selectedPoints[first])) first += 1;
  while (last > first && /^\s$/u.test(selectedPoints[last - 1])) last -= 1;
  if (first === last) return null;

  const startOffset = codePoints(prefix.toString()).length + first;
  const selectedText = selectedPoints.slice(first, last).join("");
  const endOffset = startOffset + codePoints(selectedText).length;
  return codePoints(paragraphText).slice(startOffset, endOffset).join("") === selectedText
    ? { selectedText, startOffset, endOffset }
    : null;
}