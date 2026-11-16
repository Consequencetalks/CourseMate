import type { QuestionResult } from "./types";

const LIMIT = 2000;

export function askText(language: string, question: QuestionResult): string {
  const wrong = optionLine(question.selected_option, question.options);
  const right = optionLine(question.correct_option, question.options);
  let stem = question.stem.trim();
  let text = message(language, stem, wrong, right);
  while (text.length > LIMIT && stem.length > 0) {
    stem = stem.slice(0, -1).trimEnd();
    text = message(language, stem ? `${stem}…` : "", wrong, right);
  }
  return text.length <= LIMIT ? text : "";
}

function optionLine(letter: string, options: Record<string, string>): string {
  const label = options[letter] ?? "";
  return label ? `${letter}. ${label}` : letter;
}

function message(language: string, stem: string, wrong: string, right: string): string {
  if (language === "zh") {
    return `为什么这个选择是错的？\n\n题目：${stem}\n我选了 ${wrong}\n正确选项是 ${right}\n\n请根据所选课件说明两者的差别。`;
  }
  return `Why is this choice wrong?\n\nQuestion: ${stem}\nI chose ${wrong}\nThe correct option is ${right}\n\nExplain the difference using the selected documents.`;
}
