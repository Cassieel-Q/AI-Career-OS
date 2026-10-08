export type InterviewPresentationSession = {
  status: string;
  next_question: string | null;
  turns: Array<{ round_number: number; question: string; answer: string | null }>;
};

export function interviewPresentation(session: InterviewPresentationSession | null, awaitingNext: boolean) {
  const answered = session?.turns.filter((turn) => turn.answer != null) ?? [];
  const lastAnswered = answered.at(-1) ?? null;
  const complete = session?.status === "COMPLETED";
  const holdFeedback = awaitingNext && !complete && Boolean(lastAnswered);
  return {
    question: holdFeedback || complete ? lastAnswered?.question ?? "" : session?.next_question ?? "",
    answer: holdFeedback || complete ? lastAnswered?.answer ?? "" : "",
    answeredCount: answered.length,
    footerLabel: complete ? "查看面试复盘" : holdFeedback ? "进入下一题" : "提交回答",
    canAnswer: Boolean(session?.next_question) && !complete && !holdFeedback,
  };
}
