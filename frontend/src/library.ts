import type { LibraryDeck, SavedSession } from "./types";

export type LibraryFilter = "all" | "active" | "wrong" | "notes" | "map";
export type LibrarySort = "recent" | "newest" | "title" | "progress";
export function sessionPath(session: SavedSession): string {
  return `/decks/${session.deck_id}${session.mode === "wrong" ? "?mode=wrong" : ""}`;
}
export function deckPath(deck: LibraryDeck): string {
  return deck.card_count ? `/decks/${deck.id}` : `/decks/${deck.id}/study?tab=${deck.available_outputs.includes("notes") ? "notes" : "map"}`;
}
export function visibleDecks(decks: LibraryDeck[], query: string, filter: LibraryFilter, sort: LibrarySort): LibraryDeck[] {
  const keywords = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const time = (value: string | null) => value ? Date.parse(value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`) : 0;
  return decks.filter(deck => {
    const text = `${deck.title} ${deck.source_filename} ${deck.tags.join(" ")}`.toLocaleLowerCase();
    return keywords.every(word => text.includes(word)) && (filter === "all" ||
      (filter === "active" && deck.sessions.some(session => !session.completed)) ||
      (filter === "wrong" && deck.wrong_count > 0) || deck.available_outputs.includes(filter as "notes" | "map"));
  }).sort((a,b) => {
    if (sort === "title") return a.title.localeCompare(b.title, "zh-CN") || b.id-a.id;
    if (sort === "progress") return (b.learned_count / (b.card_count || 1) - a.learned_count / (a.card_count || 1)) || b.id-a.id;
    if (sort === "recent") return time(b.last_studied_at) - time(a.last_studied_at) || time(b.created_at)-time(a.created_at) || b.id-a.id;
    return time(b.created_at)-time(a.created_at) || b.id-a.id;
  });
}
export function localDate(value: string): Date {
  return new Date(value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
}
