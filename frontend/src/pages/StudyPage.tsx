import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Download } from "lucide-react";
import { api, isDesktop } from "../api";
import MindMap from "../components/MindMap";
import type { StudyMaterial } from "../types";
import { networkMessage, safeFilename } from "../utils";

export default function StudyPage() {
  const { deckId } = useParams();
  const [material, setMaterial] = useState<StudyMaterial>();
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [retry, setRetry] = useState(0);
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState<"map" | "notes">("map");
  useEffect(() => {
    const controller = new AbortController();
    setError(""); setMaterial(undefined);
    api.study(Number(deckId), controller.signal).then(setMaterial).catch(error => {
      if (!controller.signal.aborted) setError(networkMessage(error));
    });
    return () => controller.abort();
  }, [deckId, retry]);
  async function download() {
    if (!material || saving) return;
    setSaving(true); setError(""); setNotice("");
    try {
      const blob = await api.studyWord(material.deck_id);
      const filename = safeFilename(material.title).replace(/\.md$/, "-精简复习资料.docx");
      if (isDesktop()) {
        const { invoke } = await import("@tauri-apps/api/core");
        const path = await invoke<string | null>("save_study_docx", { filename, content: Array.from(new Uint8Array(await blob.arrayBuffer())) });
        if (path) setNotice("Word 复习资料已保存");
      } else {
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url; anchor.download = filename;
        document.body.append(anchor); anchor.click(); anchor.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        setNotice("Word 下载已开始");
      }
    } catch (error) { setError(networkMessage(error)); }
    finally { setSaving(false); }
  }
  return <div className="study-page">
    <Link className="back-link" to="/"><ArrowLeft size={16} />我的课件</Link>
    <span className="eyebrow block mt-8">REVIEW THE BIG PICTURE</span>
    <h1 className="page-title">复习工作台<span className="accent">。</span></h1>
    <p className="page-subtitle">课件已提炼的知识点，整理成一份资料、一张导图。不用先答题，也不额外调用 AI。</p>
    {error && <div className="error-message my-4" role="alert">{error}<button className="text-link ml-3" onClick={() => setRetry(value => value + 1)}>重新加载</button></div>}
    {!material && !error && <p className="muted my-6" role="status">正在整理知识点…</p>}
    {material && <>
      <div className="study-heading"><div><h2>{material.title}</h2><p className="muted text-sm">{material.points.length} 个知识点{material.excluded_count > 0 ? ` · 已过滤 ${material.excluded_count} 项课程事务或重复重点` : ""}</p></div>
        <button className="button primary" disabled={saving} onClick={() => void download()}><Download size={17} />{saving ? "正在导出…" : "下载 Word 精简资料"}</button></div>
      {notice && <p className="success-message my-4" role="status">{notice}</p>}
      <div className="study-tabs" role="tablist" aria-label="复习方式">
        <button role="tab" aria-selected={tab === "map"} aria-controls="study-map" id="map-tab" onClick={() => setTab("map")}>互动思维导图</button>
        <button role="tab" aria-selected={tab === "notes"} aria-controls="study-notes" id="notes-tab" onClick={() => setTab("notes")}>精简复习资料</button>
        <Link className="text-link" to={`/decks/${deckId}`}>刷卡自测 →</Link>
      </div>
      <div role="tabpanel" id="study-map" aria-labelledby="map-tab" hidden={tab !== "map"}><MindMap key={material.deck_id} title={material.title} points={material.points} /></div>
      <div role="tabpanel" id="study-notes" aria-labelledby="notes-tab" hidden={tab !== "notes"}>
        <section className="study-notes"><h2>重点速记</h2><ol>{material.points.map(point => <li key={point.card_id}><strong>{point.title}：</strong>{point.key_point}</li>)}</ol>
          <h2>知识点简明解释</h2>{material.points.map(point => <article key={point.card_id}><h3>{point.title}</h3><p>{point.explanation}</p>{point.wrong_count > 0 && <p className="muted">易错补充（答错 {point.wrong_count} 次）：{point.clarification}</p>}</article>)}
        </section>
      </div>
      <p className="muted text-xs my-5">根据课件生成的知识卡整理，不保证覆盖原课件全部内容；请结合原课件核对公式与结论。</p>
    </>}
  </div>;
}
