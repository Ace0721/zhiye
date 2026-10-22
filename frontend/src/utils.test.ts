import { describe, expect, it } from "vitest";
import { safeFilename, taskLabel, validateFile } from "./utils";
import type { TaskState } from "./types";

describe("上传文件校验", () => {
  it("拒绝空文件、错误类型和超限文件", () => {
    expect(
      validateFile({ name: "课件.PDF", size: 50 * 1024 * 1024 }),
    ).toBeNull();
    expect(validateFile({ name: "课件.pptx", size: 10 })).toBeNull();
    expect(validateFile({ name: "file.pdf.exe", size: 10 })).toContain("PDF");
    expect(validateFile({ name: "file.pdf", size: 0 })).toContain("为空");
    expect(
      validateFile({ name: "file.pdf", size: 50 * 1024 * 1024 + 1 }),
    ).toContain("50MB");
  });
});
it("进度文字使用真实块数", () => {
  expect(
    taskLabel({
      status: "generating",
      done_blocks: 3,
      total_blocks: 5,
    } as TaskState),
  ).toContain("3/5");
});
it("导出文件名去除路径及非法字符", () => {
  expect(safeFilename("../数学:复习?")).not.toMatch(/[/\\:?]/);
  expect(safeFilename("")).toBe("知页-考前救命包.docx");
  expect(safeFilename("数学", "notes")).toBe("数学-精简复习资料.docx");
});
