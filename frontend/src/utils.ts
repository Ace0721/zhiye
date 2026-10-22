import type { TaskState } from "./types";

export function validateFile(file: Pick<File, "name" | "size">): string | null {
  if (!/\.(pdf|pptx)$/i.test(file.name)) return "请选择 PDF 或 PPTX 课件";
  if (!file.size) return "文件为空，请重新选择";
  if (file.size > 50 * 1024 * 1024) return "课件不能超过 50MB";
  return null;
}
export function taskLabel(task: TaskState): string {
  switch (task.status) {
    case "queued":
      return "课件已收到，准备解析";
    case "parsing":
      return "正在本地解析课件";
    case "generating":
      return `生成卡片中（${task.done_blocks}/${task.total_blocks} 块）`;
    case "completed":
      return "知识卡已准备好";
    case "failed":
      return "这次生成未完成";
  }
}
export function safeFilename(title: string, purpose: "summary" | "notes" = "summary"): string {
  return (
    (title
      .replace(/[<>:"/\\|?*\x00-\x1f]/g, "_")
      .trim()
      .slice(0, 80) || "知页") + (purpose === "notes" ? "-精简复习资料.docx" : "-考前救命包.docx")
  );
}
export function networkMessage(error: unknown): string {
  return error instanceof Error ? error.message : "操作失败，请重试";
}
