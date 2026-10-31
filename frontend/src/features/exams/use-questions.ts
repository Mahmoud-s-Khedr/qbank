import { useQueries } from "@tanstack/react-query";
import {
  fetchQuestion,
  questionKey,
  type QuestionOut,
} from "@/api/hooks/review";

export function useQuestionsById(ids: readonly string[]) {
  const results = useQueries({
    queries: ids.map((id) => ({
      queryKey: questionKey(id),
      queryFn: () => fetchQuestion(id),
      staleTime: 30_000,
    })),
  });
  const map = new Map<string, QuestionOut>();
  ids.forEach((id, index) => {
    const data = results[index]?.data;
    if (data) map.set(id, data);
  });
  return map;
}
