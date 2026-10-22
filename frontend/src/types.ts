export interface KnowledgeCard {
  id: number;
  deck_id: number;
  order_index: number;
  title: string;
  plain_explanation: string;
  key_point: string;
  question: string;
  options: string[];
  correct_index: number;
  reexplain: string;
  created_at: string;
}
export interface TaskState {
  status: "queued" | "parsing" | "generating" | "completed" | "failed";
  progress: number;
  total_blocks: number;
  done_blocks: number;
  error: string | null;
  deck_id: number | null;
  card_count: number;
  failed_blocks: { block_index: number; source: string; error: string }[];
}
export interface AISettings {
  base_url: string;
  model: string;
  api_key_configured: boolean;
}
export interface SettingsInput {
  base_url: string;
  model: string;
  api_key?: string;
}
export interface Answer {
  selected_index: number;
  is_correct: boolean;
  reexplain: string;
}
export interface DeckInfo {
  id: number;
  title: string;
  card_count: number;
  created_at: string;
}

export interface ReviewSummary {
  title: string;
  total_cards: number;
  wrong_count: number;
  points: { card_id: number; title: string; key_point: string; wrong_count: number }[];
  wrong_cards: { card_id: number; title: string; question: string; correct_answer: string; reexplain: string; wrong_count: number }[];
}

export interface StudyPoint {
  card_id: number;
  title: string;
  key_point: string;
  explanation: string;
  clarification: string;
  wrong_count: number;
}
export interface StudyMaterial {
  deck_id: number;
  title: string;
  points: StudyPoint[];
  excluded_count: number;
}

export interface RevisionNotes {
  title: string;
  overview: string;
  sections: { heading: string; bullets: string[] }[];
  pitfalls: string[];
}
export interface MapNode {
  label: string;
  relation: string;
  detail: string;
  children: MapNode[];
}
export interface RevisionMap {
  title: string;
  overview: string;
  branches: MapNode[];
}
export interface StudyState<T> {
  status: "idle" | "queued" | "generating" | "completed" | "failed";
  progress: number;
  error: string | null;
  data: T | null;
  source_type: "course_text" | "knowledge_cards" | null;
}
