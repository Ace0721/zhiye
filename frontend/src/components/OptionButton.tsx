import { Check, X } from "lucide-react";

export default function OptionButton({
  index,
  text,
  selected,
  correct,
  revealed,
  disabled,
  onClick,
}: {
  index: number;
  text: string;
  selected: boolean;
  correct: boolean;
  revealed: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  const state =
    revealed && correct ? "correct" : revealed && selected ? "incorrect" : "";
  return (
    <button
      className={`option ${state}`}
      disabled={disabled || revealed}
      onClick={onClick}
      aria-pressed={selected}
    >
      <span className="option-letter">{"ABCD"[index]}</span>
      <span className="flex-1 text-left">{text}</span>
      {revealed && correct ? (
        <Check size={19} aria-label="正确答案" />
      ) : revealed && selected ? (
        <X size={19} aria-label="回答错误" />
      ) : null}
    </button>
  );
}
