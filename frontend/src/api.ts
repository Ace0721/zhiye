import type {
  AISettings,
  Answer,
  DeckInfo,
  KnowledgeCard,
  SettingsInput,
  TaskState,
  StudyMaterial,
  StudyState,
  RevisionNotes,
  RevisionMap,
  ReviewSummary,
  OutputKind,
  LearningState,
  LibraryData,
} from "./types";

let desktopBase: Promise<string> | undefined;
export function isDesktop(): boolean {
  return "__TAURI_INTERNALS__" in window;
}
export async function apiBase(): Promise<string> {
  if (isDesktop()) {
    desktopBase ??= import("@tauri-apps/api/core").then(async ({ invoke }) => {
      const port = await invoke<number>("get_api_port");
      return `http://127.0.0.1:${port}`;
    });
    try {
      return await desktopBase;
    } catch (error) {
      desktopBase = undefined;
      throw error;
    }
  }
  return (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000").replace(
    /\/$/,
    "",
  );
}

export async function request<T>(
  path: string,
  init: RequestInit = {},
  timeout = 15000,
  responseType: "json" | "blob" = "json",
): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  const callerSignal = init.signal;
  if (callerSignal?.aborted) controller.abort();
  callerSignal?.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(abort, timeout);
  try {
    const response = await fetch(`${await apiBase()}${path}`, {
      ...init,
      signal: controller.signal,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new Error(
        typeof body?.detail === "string"
          ? body.detail
          : `请求失败（${response.status}），请检查输入后重试`,
      );
    }
    if (response.status === 204) return undefined as T;
    return (await (responseType === "blob" ? response.blob() : response.json())) as T;
  } catch (error) {
    if (error instanceof TypeError)
      throw new Error("连接中断，请检查网络和后端服务，然后重试");
    if (controller.signal.aborted && !callerSignal?.aborted)
      throw new Error("请求超时，请检查后端服务后重试");
    throw error;
  } finally {
    clearTimeout(timer);
    callerSignal?.removeEventListener("abort", abort);
  }
}
const json = (body: unknown, method = "POST"): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
export const api = {
  library: (signal?: AbortSignal) => request<LibraryData>(`/api/library?offset_minutes=${-new Date().getTimezoneOffset()}`, {signal}),
  saveTags: (id: number, tags: string[]) => request<{tags: string[]}>(`/api/decks/${id}/tags`, json({tags}, "PUT")),
  openSession: (id: number, mode: "all" | "wrong", restart = false, signal?: AbortSignal) =>
    request<LearningState>(`/api/decks/${id}/session`, {...json({mode, restart}), signal}),
  moveSession: (id: number, state: LearningState, index: number, completed = false) =>
    request<LearningState>(`/api/decks/${id}/session/${state.mode}`, json({revision: state.revision, index, completed}, "PUT")),
  answerSession: (id: number, state: LearningState, selected_index: number) =>
    request<LearningState>(`/api/decks/${id}/session/${state.mode}/answer`, json({revision: state.revision, index: state.index, selected_index})),
  saveCard: (card: KnowledgeCard) => request<KnowledgeCard>(`/api/cards/${card.id}`, json({
    title: card.title, plain_explanation: card.plain_explanation, key_point: card.key_point,
    question: card.question, options: card.options, correct_index: card.correct_index, reexplain: card.reexplain,
    source_refs: card.source_refs ?? [], revision: card.revision ?? 0,
  }, "PUT")),
  deleteCard: (id: number) => request<void>(`/api/cards/${id}`, { method: "DELETE" }),
  regenerateCard: (card: KnowledgeCard) => request<KnowledgeCard>(`/api/cards/${card.id}/regenerate`, json({ revision: card.revision ?? 0 }), 135000),
  saveStudy: (id: number, kind: "notes" | "map", data: RevisionNotes | RevisionMap, revision: string) =>
    request<StudyState<RevisionNotes | RevisionMap>>(`/api/decks/${id}/study/${kind}`, json({ data, revision }, "PUT")),
  sourcePage: (id: number, page: number, signal?: AbortSignal) => request<{page: number; text: string; source_filename: string}>(`/api/decks/${id}/sources/${page}`, { signal }),
  studyState: (id: number, kind: "notes" | "map", signal?: AbortSignal) =>
    request<StudyState<RevisionNotes | RevisionMap>>(`/api/decks/${id}/study/${kind}`, { signal }),
  generateStudy: (id: number, kind: "notes" | "map") =>
    request<StudyState<RevisionNotes | RevisionMap>>(`/api/decks/${id}/study/${kind}`, { method: "POST" }),
  study: (id: number, signal?: AbortSignal) =>
    request<StudyMaterial>(`/api/decks/${id}/study`, { signal }),
  studyWord: (id: number) =>
    request<Blob>(`/api/decks/${id}/study.docx`, {}, 60000, "blob"),
  upload(file: File, outputs: OutputKind[] = ["cards"]) {
    const body = new FormData();
    body.append("file", file);
    body.append("outputs", outputs.join(","));
    return request<{ task_id: string }>(
      "/api/upload",
      { method: "POST", body },
      120000,
    );
  },
  task: (id: string, signal?: AbortSignal) =>
    request<TaskState>(`/api/tasks/${id}`, { signal }),
  cards: (id: number, signal?: AbortSignal) =>
    request<KnowledgeCard[]>(`/api/decks/${id}/cards`, { signal }),
  decks: (signal?: AbortSignal) =>
    request<DeckInfo[]>("/api/decks", { signal }),
  answer: (id: number, index: number) =>
    request<Answer>(`/api/cards/${id}/answer`, json({ selected_index: index })),
  wrong: (id: number, signal?: AbortSignal) =>
    request<KnowledgeCard[]>(`/api/decks/${id}/wrong`, { signal }),
  summary: (id: number, signal?: AbortSignal) =>
    request<ReviewSummary>(`/api/decks/${id}/summary`, { signal }),
  summaryWord: (id: number) =>
    request<Blob>(`/api/decks/${id}/summary.docx`, {}, 60000, "blob"),
  settings: () => request<AISettings>("/api/settings"),
  saveSettings: (body: SettingsInput) =>
    request<AISettings>("/api/settings", json(body, "PUT")),
  testSettings: (body: SettingsInput) =>
    request<{ success: boolean; error_type: string | null; message: string }>(
      "/api/settings/test",
      json(body),
      135000,
    ),
};
