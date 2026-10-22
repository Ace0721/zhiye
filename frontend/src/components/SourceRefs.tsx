import { useEffect, useState } from "react";
import { api } from "../api";
import type { SourceRef } from "../types";
import { networkMessage } from "../utils";
import Dialog from "./Dialog";

export default function SourceRefs({deckId, refs = []}: {deckId: number; refs?: SourceRef[]}) {
  const [selected, setSelected] = useState<SourceRef>();
  const [source, setSource] = useState<{text: string; source_filename: string}>();
  const [error, setError] = useState("");
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    setSource(undefined); setError("");
    api.sourcePage(deckId, selected.page, controller.signal).then(setSource).catch(error => { if (!controller.signal.aborted) setError(networkMessage(error)); });
    return () => controller.abort();
  }, [deckId, selected]);
  return <div className="source-refs">
    {refs.length ? <><span>参考来源</span>{refs.map((ref, index) => <button key={index} className="source-pill" onClick={() => setSelected(ref)}>第 {ref.page} 页/张 ↗</button>)}</> : <span className="muted">暂无可核对的来源页码，旧课件可重新上传补齐</span>}
    {selected && <Dialog title={`第 ${selected.page} 页/张 · 原文核对`} onClose={() => setSelected(undefined)}>
      <p className="muted text-sm">PDF 按文件页序，PPT 按幻灯片顺序。引文已校验出现在该页，但 AI 的结论仍需结合原文判断。</p>
      <blockquote className="source-quote">{selected.quote}</blockquote>
      {error && <p className="error-message" role="alert">{error}</p>}
      {!source && !error && <p role="status">正在读取本地正文…</p>}
      {source && <><p className="muted text-xs mb-3">{source.source_filename} · 解析文字</p><pre className="source-page-text">{source.text}</pre></>}
    </Dialog>}
  </div>;
}
