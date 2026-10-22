import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Check, Download, RotateCcw } from "lucide-react";
import { api, isDesktop } from "../api";
import { networkMessage, safeFilename } from "../utils";
import type { ReviewSummary } from "../types";
import SourceRefs from "../components/SourceRefs";

export default function SummaryPage() {
  const { deckId } = useParams();
  const [summary, setSummary] = useState<ReviewSummary>();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    api
      .summary(Number(deckId), controller.signal)
      .then(setSummary)
      .catch((error) => {
        if (!controller.signal.aborted) setError(networkMessage(error));
      });
    return () => controller.abort();
  }, [deckId, retry]);
  async function download() {
    if (!summary || saving) return;
    setSaving(true); setNotice(""); setError("");
    try {
      const blob = await api.summaryWord(Number(deckId));
      if (isDesktop()) {
        const { invoke } = await import("@tauri-apps/api/core");
        const path = await invoke<string | null>("save_study_docx", {
          filename: safeFilename(summary.title),
          content: Array.from(new Uint8Array(await blob.arrayBuffer())),
        });
        if (path) setNotice("Word 救命包已保存");
      } else {
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = safeFilename(summary.title);
        document.body.append(anchor);
        anchor.click();
        anchor.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        setNotice("已开始下载");
      }
    } catch (error) {
      setError(networkMessage(error));
    } finally { setSaving(false); }
  }
  return (
    <div className="summary-page">
      <Link to="/" className="back-link">
        <ArrowLeft size={16} />
        我的课件
      </Link>
      <span className="eyebrow block mt-8">YOUR LAST-MINUTE LIFELINE</span>
      <h1 className="page-title">
        考前救命包
      </h1>
      <p className="page-subtitle">
        根据你的答题记录，按答错次数整理薄弱点和错题解释，可直接下载 Word。无需再次调用 AI。
      </p>
      {error && (
        <div className="error-message mt-5" role="alert">
          {error}
          <button
            className="text-link ml-3"
            onClick={() => setRetry((value) => value + 1)}
          >
            重试
          </button>
        </div>
      )}
      {!summary && !error && (
        <p className="muted mt-8" role="status">
          正在整理复习重点…
        </p>
      )}
      {summary && (
        <>
          <div className="summary-banner">
            <div>
              <h2 className="font-semibold">{summary.title}</h2>
              <p className="text-xs muted mt-2">
                {summary.total_cards} 张知识卡 · {summary.wrong_count}{" "}
                张历史错题
              </p>
            </div>
            <div className="summary-stat">
              {String(summary.wrong_count).padStart(2, "0")}
              <span className="text-xs ml-2">待巩固</span>
            </div>
          </div>
          <div className="summary-actions">
            <Link className="button secondary" to={`/decks/${deckId}/study`}>Word 资料 / 互动导图</Link>
            <button className="button primary" disabled={saving} onClick={() => void download()}>
              <Download size={17} />
              {saving ? "正在导出…" : "下载 Word（.docx）"}
            </button>
            <Link
              className="button secondary"
              to={`/decks/${deckId}?mode=wrong`}
            >
              <RotateCcw size={17} />
              再刷错题
            </Link>
          </div>
          {notice && (
            <p
              className="success-message flex gap-2 items-center mt-4"
              role="status"
            >
              <Check size={16} />
              {notice}
            </p>
          )}
          <section className="study-notes mt-6" aria-label="考前救命包预览">
            <h2>{summary.wrong_count ? "高频易错重点" : "重点速记"}</h2>
            <ol>{summary.points.map(point => <li key={point.card_id}><strong>{point.title}</strong>{point.wrong_count > 0 && <span className="muted">（答错 {point.wrong_count} 次）</span>}：{point.key_point}<SourceRefs deckId={Number(deckId)} refs={point.source_refs}/></li>)}</ol>
            <h2>错题回顾</h2>
            {summary.wrong_cards.length ? summary.wrong_cards.map(card => <article key={card.card_id}>
              <h3>{card.title}</h3><p>{card.question}</p><p><strong>正确答案：</strong>{card.correct_answer}</p><p className="muted"><strong>再讲一遍：</strong>{card.reexplain}</p>
            </article>) : <p className="muted">暂无历史错题，可以先复习上方重点，再通过刷卡自测检验掌握情况。</p>}
          </section>
        </>
      )}
    </div>
  );
}
