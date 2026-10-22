import { Lightbulb, RotateCcw } from "lucide-react";
import type { Answer, KnowledgeCard } from "../types";
import OptionButton from "./OptionButton";
import SourceRefs from "./SourceRefs";

export default function Card({
  card,
  answer,
  pending,
  onAnswer,
  review,
}: {
  card: KnowledgeCard;
  answer?: Answer;
  pending: boolean;
  onAnswer: (index: number) => void;
  review: boolean;
}) {
  return (
    <article className="knowledge-card" aria-label={card.title}>
      <div className="card-topline">
        <span className="eyebrow">
          {review ? "再来一遍 · 错题回炉" : "ONE CARD, ONE IDEA"}
        </span>
        <span className="tiny-tag">知识卡</span>
      </div>
      <h1 className="card-title">{card.title}</h1>
      <div className="px-7"><SourceRefs deckId={card.deck_id} refs={card.source_refs}/></div>
      <p className="explanation">{card.plain_explanation}</p>
      <div className="key-point">
        <Lightbulb size={21} className="shrink-0" />
        <div>
          <span className="eyebrow block mb-2">只记住这一句</span>
          <p>{card.key_point}</p>
        </div>
      </div>
      <div className="question-divider">
        <span>试着回答</span>
        <span>单选 · 4 个选项</span>
      </div>
      <h2 className="question">{card.question}</h2>
      <div className="grid gap-2.5">
        {card.options.map((option, index) => (
          <OptionButton
            key={index}
            index={index}
            text={option}
            selected={answer?.selected_index === index}
            correct={card.correct_index === index}
            revealed={!!answer}
            disabled={pending}
            onClick={() => onAnswer(index)}
          />
        ))}
      </div>
      {pending && (
        <p className="text-sm muted mt-3" role="status">
          正在保存答案…
        </p>
      )}
      {answer && (
        <div
          className={`feedback ${answer.is_correct ? "good" : ""}`}
          role="status"
        >
          {answer.is_correct ? (
            <>
              <strong>答对了，记住它。</strong>
              <p>准备好就滑到下一张。</p>
            </>
          ) : (
            <>
              <strong className="flex items-center gap-2">
                <RotateCcw size={16} />
                换个说法，再理解一次
              </strong>
              <p>{answer.reexplain}</p>
              <span className="text-xs">
                这张卡已加入错题本，稍后会再出现。
              </span>
            </>
          )}
        </div>
      )}
    </article>
  );
}
