import type { ReadingPack } from "./types";

export const mockReadingPack: ReadingPack = {
  pack_id: "demo-reading-pack",
  title: "Demo Reading Pack",
  passage_count: 1,
  question_count: 2,
  passages: [
    {
      passage_id: "demo-passage",
      title: "A Local Reading Habit",
      content: "Mira reads near the window. She writes one useful word after reading.",
      order: 1,
      paragraphs: [
        { paragraph_id: "demo-p-1", order: 1, text: "Mira reads near the window." },
        { paragraph_id: "demo-p-2", order: 2, text: "She writes one useful word after reading." }
      ]
    }
  ],
  questions: [
    {
      question_id: "demo-q-1",
      passage_id: "demo-passage",
      question_no: "1",
      question_type: "single_choice",
      stem: "Where does Mira read?",
      answer: "A",
      analysis: "The first sentence says she reads near the window.",
      options: [
        { label: "A", text: "Near the window." },
        { label: "B", text: "In a shop." },
        { label: "C", text: "Beside a lake." },
        { label: "D", text: "On a bus." }
      ]
    },
    {
      question_id: "demo-q-2",
      passage_id: "demo-passage",
      question_no: "2",
      question_type: "single_choice",
      stem: "What does she write after reading?",
      answer: "B",
      analysis: "The second sentence says she writes one useful word.",
      options: [
        { label: "A", text: "A long letter." },
        { label: "B", text: "One useful word." },
        { label: "C", text: "A shopping list." },
        { label: "D", text: "A song." }
      ]
    }
  ]
};
