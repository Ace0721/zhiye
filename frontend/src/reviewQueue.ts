import type { Answer, KnowledgeCard } from "./types";

export function removeQueuedCard(queue: KnowledgeCard[], answers: Record<number, Answer>, index: number) {
  const id = queue[index].id;
  const retained = queue.map((card,position) => ({card,position})).filter(item => item.card.id !== id);
  // 同卡可能在回炉队列中出现多次，按原位置计数，不能直接沿用旧索引。
  const before = retained.filter(item => item.position < index).length;
  return {
    queue: retained.map(item => item.card),
    answers: Object.fromEntries(retained.flatMap((item,position) => answers[item.position] ? [[position,answers[item.position]]] : [])),
    index: Math.max(0, Math.min(before, retained.length - 1)),
  };
}

export function replaceQueuedCard(queue: KnowledgeCard[], answers: Record<number, Answer>, card: KnowledgeCard) {
  const old = queue.find(item => item.id === card.id)!;
  const reset = old.question !== card.question || old.correct_index !== card.correct_index || JSON.stringify(old.options) !== JSON.stringify(card.options);
  return {
    queue: queue.map(item => item.id === card.id ? card : item),
    answers: Object.fromEntries(Object.entries(answers).filter(([position]) => !reset || queue[Number(position)].id !== card.id).map(([position,answer]) => [position,queue[Number(position)].id === card.id ? {...answer,reexplain:card.reexplain} : answer])),
  };
}
