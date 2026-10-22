import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Check,
  FileText,
  Layers3,
  ShieldCheck,
  Upload,
  X,
} from "lucide-react";
import { api } from "../api";
import type { DeckInfo, TaskState, OutputKind } from "../types";
import { networkMessage, taskLabel, validateFile } from "../utils";
import ProgressBar from "../components/ProgressBar";

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [outputs, setOutputs] = useState<OutputKind[]>(["cards"]);
  const [taskId, setTaskId] = useState(() =>
    sessionStorage.getItem("zhiye-task"),
  );
  const [task, setTask] = useState<TaskState | null>(null);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [retry, setRetry] = useState(0);
  const [decks, setDecks] = useState<DeckInfo[]>([]);
  const [libraryError, setLibraryError] = useState("");
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    api
      .decks(controller.signal)
      .then(setDecks)
      .catch((error) => {
        if (!controller.signal.aborted) setLibraryError(networkMessage(error));
      });
    return () => controller.abort();
  }, [task?.status, retry]);

  useEffect(() => {
    if (!taskId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const state = await api.task(taskId!, controller.signal);
        if (controller.signal.aborted) return;
        setTask(state);
        setError("");
        if (state.status === "completed" || state.status === "failed") {
          sessionStorage.removeItem("zhiye-task");
        } else timer = setTimeout(poll, 1000);
      } catch (error) {
        if (!controller.signal.aborted) setError(networkMessage(error));
      }
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [taskId, retry]);

  function choose(selected?: File) {
    if (!selected) return;
    const message = validateFile(selected);
    if (message) {
      setError(message);
      return;
    }
    setFile(selected);
    setError("");
    setTask(null);
    setTaskId(null);
    sessionStorage.removeItem("zhiye-task");
  }
  async function upload() {
    if (!file || uploading || !outputs.length) return;
    setError("");
    setUploading(true);
    setTask(null);
    try {
      const result = await api.upload(file, outputs);
      sessionStorage.setItem("zhiye-task", result.task_id);
      setTaskId(result.task_id);
    } catch (error) {
      setError(networkMessage(error));
    } finally {
      setUploading(false);
    }
  }
  const busy =
    uploading ||
    (!!taskId && !["completed", "failed"].includes(task?.status ?? "queued"));
  return (
    <div className="upload-page">
      <div className="page-kicker">
        <span className="status-dot" />
        课件在本地，知识随身带
      </div>
      <section className="upload-layout">
        <div className="upload-intro">
          <span className="eyebrow">LESS SCROLLING. MORE KNOWING.</span>
          <h1>
            课件太厚？
            <br />
            一张一张<span className="accent">刷明白</span>
          </h1>
          <p className="intro-copy">
            把老师的课件，变成你的复习资料。
            <br />
            刷卡自测、精简提纲、逻辑导图。
            <br />
            按需要选择，复习更有方向。
          </p>
          <div className="intro-rule" />
          <div className="flex items-center gap-3 text-sm">
            <span className="number-mark">01 — 03</span>
            <span className="muted">上传课件 → 刷卡自测 → 考前救命包</span>
          </div>
        </div>
        <div className="upload-panel">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-lg font-semibold">从一份课件开始</h2>
            <span className="tiny-tag">PDF / PPTX</span>
          </div>
          {!taskId ? (
            <>
              <button
                className={`drop-zone ${dragging ? "dragging" : ""}`}
                disabled={busy}
                onClick={() => input.current?.click()}
                onDragOver={(event) => {
                  event.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(event) => {
                  event.preventDefault();
                  setDragging(false);
                  if (!busy) choose(event.dataTransfer.files[0]);
                }}
              >
                <span className="upload-icon">
                  <Upload size={27} strokeWidth={1.5} />
                </span>
                <strong>{file ? file.name : "把课件拖到这里"}</strong>
                <span>
                  {file
                    ? `${(file.size / 1024 / 1024).toFixed(1)} MB · 点击重新选择`
                    : "或点击选择文件"}
                </span>
                <small>支持 PDF、PPTX，最大 50MB</small>
              </button>
              <input
                ref={input}
                type="file"
                accept=".pdf,.pptx"
                className="sr-only"
                aria-label="选择课件"
                onChange={(event) => choose(event.target.files?.[0])}
              />
              <fieldset className="output-picker mt-5">
                <legend>这次想生成什么</legend>
                {([['cards', '知识卡', '解释与选择题'], ['notes', 'Word 提纲', '精简复习资料'], ['map', '思维导图', '梳理概念关系']] as const).map(([kind, label, description]) =>
                  <label key={kind} className={outputs.includes(kind) ? "selected" : ""}><input type="checkbox" checked={outputs.includes(kind)} disabled={busy} onChange={event => setOutputs(current => event.target.checked ? [...current, kind] : current.filter(item => item !== kind))} /><span><strong>{label}</strong><small>{description}</small></span></label>)}
                <p className="muted text-xs mt-2">可多选；只选择提纲或导图时不会生成选择题。每项生成会使用你配置的 API。</p>
              </fieldset>
              <button
                className="button primary w-full mt-5"
                disabled={!file || uploading || !outputs.length}
                onClick={() => void upload()}
              >
                {uploading ? "正在上传课件…" : "生成所选内容"}
                <ArrowRight size={18} />
              </button>
            </>
          ) : (
            <div className="task-panel" aria-live="polite">
              <div
                className={`task-icon ${task?.status === "completed" ? "done" : ""}`}
              >
                {task?.status === "completed" ? (
                  <Check />
                ) : task?.status === "failed" ? (
                  <X />
                ) : (
                  <Layers3 />
                )}
              </div>
              <h3 className="text-xl font-semibold my-4">
                {task ? taskLabel(task) : "已上传，等待任务状态"}
              </h3>
              {task && (
                <ProgressBar value={task.progress} label={taskLabel(task)} />
              )}
              {task?.status === "completed" && (
                <>
                  <p className="muted my-5">
                    已保存：{task.generated_outputs?.map(kind => ({cards: `知识卡 ${task.card_count} 张`, notes: 'Word 提纲', map: '思维导图'})[kind]).join('、') || `知识卡 ${task.card_count} 张`}
                    {task.failed_blocks.length > 0 &&
                      `，${task.failed_blocks.length} 块未成功`}
                    。
                  </p>
                  {Object.entries(task.output_errors ?? {}).map(([kind, message]) => <p className="error-message mb-3 text-sm" key={kind}>{({cards:'知识卡',notes:'Word 提纲',map:'思维导图'} as Record<string,string>)[kind]}未成功：{message}</p>)}
                  {task.failed_blocks.length > 0 && (
                    <details className="text-sm text-left mb-4">
                      <summary>查看未成功的内容</summary>
                      {task.failed_blocks.map((block) => (
                        <p key={block.block_index} className="mt-2">
                          {block.source}：{block.error}
                        </p>
                      ))}
                    </details>
                  )}
                  {task.card_count > 0 && <Link
                    className="button primary w-full"
                    to={`/decks/${task.deck_id}`}
                  >
                    开始学习
                    <ArrowRight size={18} />
                  </Link>}
                  <Link className="button secondary w-full mt-3" to={`/decks/${task.deck_id}/study?tab=${task.generated_outputs?.includes('notes') ? 'notes' : 'map'}`}>查看 Word 提纲 / 思维导图</Link>
                </>
              )}
              {task?.status === "failed" && (
                <>
                  <p className="error-message my-4">{task.error}</p>
                  {task.deck_id && <Link className="text-link block mb-4" to={`/decks/${task.deck_id}/study?tab=${task.requested_outputs?.includes('notes') ? 'notes' : 'map'}`}>查看已保存课件并重试生成</Link>}
                  <button
                    className="button primary w-full"
                    onClick={() => {
                      setTaskId(null);
                      setTask(null);
                    }}
                  >
                    重新上传
                  </button>
                </>
              )}
            </div>
          )}
          {error && (
            <div className="error-message mt-4" role="alert">
              {error}
              {taskId && (
                <button
                  className="text-link block mt-2"
                  onClick={() => setRetry((value) => value + 1)}
                >
                  重新连接并查询进度
                </button>
              )}
            </div>
          )}
          {task?.status === "completed" && (
            <button
              className="text-link mt-5 w-full"
              onClick={() => {
                setTaskId(null);
                setTask(null);
                setFile(null);
              }}
            >
              再上传一份课件
            </button>
          )}
          <div className="privacy-note">
            <ShieldCheck size={17} className="shrink-0" />
            <p>
              原文件仅在本地解析。提取的文字会发送到你配置的 AI 服务，API Key
              由你自己提供。<Link to="/settings">配置 AI →</Link>
            </p>
          </div>
        </div>
      </section>
      <section className="feature-strip">
        <div>
          <span className="feature-number">01</span>
          <div>
            <h3>人话解释</h3>
            <p>绕开大段术语，先把概念讲清楚</p>
          </div>
        </div>
        <div>
          <span className="feature-number">02</span>
          <div>
            <h3>答错就回炉</h3>
            <p>换一种说法，再给理解一次机会</p>
          </div>
        </div>
        <div>
          <span className="feature-number">03</span>
          <div>
            <h3>考前救命包</h3>
            <p>把薄弱点和错题，整理成一份 Word</p>
          </div>
        </div>
      </section>
      <section className="library-section">
        <div className="section-heading">
          <h2>
            我的课件
            <span className="muted ml-2 text-sm font-normal">
              {decks.length} 份
            </span>
          </h2>
          <span className="eyebrow">YOUR STUDY SHELF</span>
        </div>
        {libraryError && (
          <p className="error-message text-sm" role="alert">
            {libraryError}
            <button
              className="text-link ml-3"
              onClick={() => {
                setLibraryError("");
                setRetry((value) => value + 1);
              }}
            >
              重试
            </button>
          </p>
        )}
        {decks.length ? (
          <div className="deck-grid">
            {decks.map((deck) => (
              <div
                className="deck-tile"
                key={deck.id}
              >
                <FileText size={22} />
                <div className="min-w-0 flex-1">
                  <Link to={deck.card_count ? `/decks/${deck.id}` : `/decks/${deck.id}/study?tab=${deck.available_outputs?.includes('notes') ? 'notes' : 'map'}`}><h3 className="truncate">{deck.title}</h3></Link>
                  <p>
                    {deck.card_count ? `${deck.card_count} 张知识卡` : deck.available_outputs?.map(kind => ({cards:'知识卡',notes:'Word 提纲',map:'思维导图'})[kind]).join(' / ') || '尚未完成生成'} ·{" "}
                    {new Date(deck.created_at).toLocaleDateString("zh-CN")}
                  </p>
                  <Link className="text-link text-sm" to={`/decks/${deck.id}/study?tab=${deck.available_outputs?.includes('notes') ? 'notes' : 'map'}`}>Word 资料 / 互动导图 →</Link>
                </div>
                <Link to={deck.card_count ? `/decks/${deck.id}` : `/decks/${deck.id}/study?tab=${deck.available_outputs?.includes('notes') ? 'notes' : 'map'}`} aria-label={`查看${deck.title}`}><ArrowRight size={17} /></Link>
              </div>
            ))}
          </div>
        ) : (
          !libraryError && (
            <div className="empty-shelf">
              <FileText size={22} />
              <p>第一份课件，等你放上来。</p>
            </div>
          )
        )}
      </section>
    </div>
  );
}
