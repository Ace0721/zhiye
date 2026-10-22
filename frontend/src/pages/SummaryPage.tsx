import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Check, Copy, Download, RotateCcw } from "lucide-react";
import { api, isDesktop } from "../api";
import { networkMessage, safeFilename } from "../utils";

export default function SummaryPage() {
  const { deckId } = useParams();
  const [summary, setSummary] = useState<{
    title: string;
    markdown: string;
    wrong_count: number;
    total_cards: number;
  }>();
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
  async function copy() {
    if (!summary) return;
    try {
      await navigator.clipboard.writeText(summary.markdown);
      setNotice("Markdown 已复制");
    } catch {
      setError("剪贴板不可用，请使用下载按钮，或手动选择下方文字复制");
    }
  }
  async function download() {
    if (!summary) return;
    try {
      if (isDesktop()) {
        const { invoke } = await import("@tauri-apps/api/core");
        const path = await invoke<string | null>("save_markdown", {
          filename: safeFilename(summary.title),
          content: summary.markdown,
        });
        if (path) setNotice("救命包已保存");
      } else {
        const url = URL.createObjectURL(
          new Blob([summary.markdown], { type: "text/markdown;charset=utf-8" }),
        );
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
    }
  }
  return (
    <div className="summary-page">
      <Link to="/" className="back-link">
        <ArrowLeft size={16} />
        我的课件
      </Link>
      <span className="eyebrow block mt-8">YOUR LAST-MINUTE LIFELINE</span>
      <h1 className="page-title">
        考前救命包<span className="accent">。</span>
      </h1>
      <p className="page-subtitle">
        把容易忘的，留在眼前。所有内容在本地汇总，无需再次调用 AI。
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
            <button className="button primary" onClick={() => void download()}>
              <Download size={17} />
              下载 .md
            </button>
            <button className="button secondary" onClick={() => void copy()}>
              <Copy size={17} />
              复制 Markdown
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
          <pre className="markdown-preview">{summary.markdown}</pre>
        </>
      )}
    </div>
  );
}
