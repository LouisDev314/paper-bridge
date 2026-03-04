export function stripInlineNumericCitations(answerMarkdown: string): string {
  const withoutCitations = answerMarkdown.replace(/\[\d+\]/g, "");

  const cleanedLines = withoutCitations.split(/\r?\n/).map((line) =>
    line
      .replace(/[ \t]{2,}/g, " ")
      .replace(/\s+([.,;:!?])/g, "$1")
      .trimEnd(),
  );

  return cleanedLines.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

export function answerMarkdownToPlainText(answerMarkdown: string): string {
  const citationCleaned = stripInlineNumericCitations(answerMarkdown);

  const plainLines = citationCleaned.split(/\r?\n/).map((line) =>
    line
      .replace(/^#{1,6}\s+/, "")
      .replace(/^\s*[-*+]\s+/, "• ")
      .replace(/^\s*>\s?/, "")
      .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, "$1")
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1")
      .replace(/`{1,3}([^`]+)`{1,3}/g, "$1")
      .replace(/(\*\*|__)(.*?)\1/g, "$2")
      .replace(/(\*|_)(.*?)\1/g, "$2")
      .replace(/[ \t]{2,}/g, " ")
      .replace(/\s+([.,;:!?])/g, "$1")
      .trimEnd(),
  );

  return plainLines.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}
