import { useEffect, useRef, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { ArrowDown, ArrowLeft, ArrowUp, FileDown } from "lucide-react";
import { api } from "../api";
import type { Answer, KnowledgeCard } from "../types";
import { networkMessage } from "../utils";
import Card from "../components/Card";
import ProgressBar from "../components/ProgressBar";
import CardActions from "../components/CardActions";
import { removeQueuedCard, replaceQueuedCard } from "../reviewQueue";

export default function SwipePage() {
  const { deckId } = useParams();
  const [search] = useSearchParams();
  const wrongOnly = search.get("mode") === "wrong";
  const navigate = useNavigate();
  const [queue, setQueue] = useState<KnowledgeCard[]>([]);
  const [initialCount, setInitialCount] = useState(0);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, Answer>>({});
  const [pending, setPending] = useState(false);
  const [contentBusy, setContentBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const scroll = useRef<HTMLDivElement>(null);
  const touch = useRef<{ y: number; atTop: boolean; atBottom: boolean }>();
  const requestLock = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    (wrongOnly
      ? api.wrong(Number(deckId), controller.signal)
      : api.cards(Number(deckId), controller.signal)
    )
      .then((cards) => {
        setQueue(cards);
        setInitialCount(cards.length);
        setIndex(0);
        setAnswers({});
      })
      .catch((error) => {
        if (!controller.signal.aborted) setError(networkMessage(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [deckId, wrongOnly, retry]);
  useEffect(() => {
    scroll.current?.scrollTo({ top: 0, behavior: "instant" });
  }, [index]);

  function next() {
    if (pending || contentBusy || !answers[index]) return;
    if (index + 1 < queue.length) setIndex((value) => value + 1);
    else navigate(`/decks/${deckId}/summary`);
  }
  function previous() {
    if (!pending && !contentBusy) setIndex((value) => Math.max(0, value - 1));
  }
  async function answer(selected: number) {
    if (requestLock.current || contentBusy || answers[index]) return;
    requestLock.current = true;
    setPending(true);
    setError("");
    try {
      const result = await api.answer(queue[index].id, selected);
      setAnswers((current) => ({ ...current, [index]: result }));
      if (!result.is_correct)
        setQueue((current) => [...current, current[index]]);
    } catch (error) {
      setError(networkMessage(error));
    } finally {
      setPending(false);
      requestLock.current = false;
    }
  }
  function changed(card: KnowledgeCard) {
    const result = replaceQueuedCard(queue,answers,card);
    setAnswers(result.answers); setQueue(result.queue);
  }
  function removed() {
    const result = removeQueuedCard(queue,answers,index);
    setQueue(result.queue); setAnswers(result.answers); setIndex(result.index);
    setInitialCount(value => Math.max(0, value - 1));
  }
  if (loading)
    return (
      <div className="empty-page" role="status">
        正在取出知识卡…
      </div>
    );
  if (!queue.length)
    return (
      <div className="empty-page">
        <h1>
          {error
            ? "卡片暂时没能加载"
            : wrongOnly
              ? "还没有错题，继续保持"
              : "这份课件还没有卡片"}
        </h1>
        {error && <p className="error-message my-4">{error}</p>}
        <div className="flex gap-3 mt-5">
          <button
            className="button secondary"
            onClick={() => setRetry((value) => value + 1)}
          >
            重试
          </button>
          <Link className="button primary" to="/">
            返回课件
          </Link>
        </div>
      </div>
    );
  return (
    <div className="swipe-layout">
      <aside className="study-aside">
        <Link to="/" className="back-link">
          <ArrowLeft size={16} />
          我的课件
        </Link>
        <span className="eyebrow block mt-14">FOCUS MODE</span>
        <h2>
          一次，
          <br />
          弄懂一个点
        </h2>
        <p className="muted leading-7">
          不用赶进度。
          <br />
          答错的卡会回来，
          <br />
          直到你把它刷明白。
        </p>
        <Link
          className="text-link flex items-center gap-2 mt-9"
          to={`/decks/${deckId}/summary`}
        >
          <FileDown size={17} />
          查看考前救命包
        </Link>
        <p className="text-xs muted mt-12">
          原始 {initialCount} 张 · 回炉 {queue.length - initialCount} 次
        </p>
      </aside>
      <section className="study-column">
        <div className="study-progress">
          <ProgressBar
            value={(100 * (index + 1)) / queue.length}
            label={`第 ${index + 1} / ${queue.length} 张${index >= initialCount ? " · 回炉复习" : ""}`}
          />
        </div>
        <CardActions key={queue[index].id} card={queue[index]} disabled={pending || contentBusy} onChanged={changed} onDeleted={removed} onBusy={setContentBusy}/>
        <div
          className="card-scroll"
          ref={scroll}
          onTouchStart={(event) => {
            const element = scroll.current!;
            touch.current = {
              y: event.touches[0].clientY,
              atTop: element.scrollTop <= 1,
              atBottom:
                element.scrollTop + element.clientHeight >=
                element.scrollHeight - 2,
            };
          }}
          onTouchEnd={(event) => {
            if (!touch.current || pending || contentBusy) return;
            const delta = event.changedTouches[0].clientY - touch.current.y;
            if (delta < -100 && touch.current.atBottom) next();
            if (delta > 100 && touch.current.atTop) previous();
            touch.current = undefined;
          }}
        >
          <Card
            key={index}
            card={queue[index]}
            answer={answers[index]}
            pending={pending || contentBusy}
            onAnswer={(selected) => void answer(selected)}
            review={wrongOnly || index >= initialCount}
          />
          {error && (
            <p className="error-message m-4" role="alert">
              {error}。答案尚未确认，请重新点选。
            </p>
          )}
        </div>
        <div className="study-controls">
          <button
            className="button secondary"
            onClick={previous}
            disabled={index === 0 || pending || contentBusy}
          >
            <ArrowUp size={17} />
            上一张
          </button>
          <span className="hidden sm:block text-xs muted">上下滑动切卡</span>
          <button
            className="button primary"
            onClick={next}
            disabled={!answers[index] || pending || contentBusy}
          >
            {index + 1 === queue.length ? "完成学习" : "下一张"}
            <ArrowDown size={17} />
          </button>
        </div>
      </section>
    </div>
  );
}
