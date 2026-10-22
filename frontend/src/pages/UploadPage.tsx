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
import type { DeckInfo, TaskState } from "../types";
import { networkMessage, taskLabel, validateFile } from "../utils";
import ProgressBar from "../components/ProgressBar";

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
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
    if (!file || uploading) return;
    setError("");
    setUploading(true);
    setTask(null);
    try {
      const result = await api.upload(file);
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
            一张一张<span className="accent">刷明白。</span>
          </h1>
          <p className="intro-copy">
            把老师的课件，变成你的知识卡。
            <br />
            一句解释、一个重点、一题自测。
            <br />
            通勤十分钟，也能学进去。
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
              <button
                className="button primary w-full mt-5"
                disabled={!file || uploading}
                onClick={() => void upload()}
              >
                {uploading ? "正在上传课件…" : "生成我的知识卡"}
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
                    成功生成{" "}
                    <strong className="text-ink">{task.card_count}</strong> 张卡
                    {task.failed_blocks.length > 0 &&
                      `，${task.failed_blocks.length} 块未成功`}
                    。
                  </p>
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
                  <Link
                    className="button primary w-full"
                    to={`/decks/${task.deck_id}`}
                  >
                    开始学习
                    <ArrowRight size={18} />
                  </Link>
                  <Link className="button secondary w-full mt-3" to={`/decks/${task.deck_id}/study`}>Word 复习资料 / 互动导图</Link>
                </>
              )}
              {task?.status === "failed" && (
                <>
                  <p className="error-message my-4">{task.error}</p>
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
                  <Link to={`/decks/${deck.id}`}><h3 className="truncate">{deck.title}</h3></Link>
                  <p>
                    {deck.card_count} 张知识卡 ·{" "}
                    {new Date(deck.created_at).toLocaleDateString("zh-CN")}
                  </p>
                  <Link className="text-link text-sm" to={`/decks/${deck.id}/study`}>Word 资料 / 互动导图 →</Link>
                </div>
                <Link to={`/decks/${deck.id}`} aria-label={`学习${deck.title}`}><ArrowRight size={17} /></Link>
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
