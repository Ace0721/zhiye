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
  studyState: (id: number, kind: "notes" | "map", signal?: AbortSignal) =>
    request<StudyState<RevisionNotes | RevisionMap>>(`/api/decks/${id}/study/${kind}`, { signal }),
  generateStudy: (id: number, kind: "notes" | "map") =>
    request<StudyState<RevisionNotes | RevisionMap>>(`/api/decks/${id}/study/${kind}`, { method: "POST" }),
  study: (id: number, signal?: AbortSignal) =>
    request<StudyMaterial>(`/api/decks/${id}/study`, { signal }),
  studyWord: (id: number) =>
    request<Blob>(`/api/decks/${id}/study.docx`, {}, 60000, "blob"),
  upload(file: File) {
    const body = new FormData();
    body.append("file", file);
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
    request<{
      title: string;
      markdown: string;
      wrong_count: number;
      total_cards: number;
    }>(`/api/decks/${id}/summary`, { signal }),
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
