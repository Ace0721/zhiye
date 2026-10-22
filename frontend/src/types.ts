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
