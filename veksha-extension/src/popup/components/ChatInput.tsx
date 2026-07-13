import { useEffect, useRef, useState } from "react";
import { useT } from "../../shared/i18n";

interface Props {
  onSend: (text: string) => void;
  disabled: boolean;
}

export function ChatInput({ onSend, disabled }: Props) {
  const t = useT();
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function autoResize() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 90) + "px";
  }

  useEffect(() => { autoResize(); }, [value]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = value.trim();
    if (!text || disabled) return;
    onSend(text);
    setValue("");
  }

  const canSend = !disabled && value.trim().length > 0;

  return (
    <form className="chat-input-row" onSubmit={handleSubmit}>
      <div className="chat-input-area">
        <textarea
          ref={textareaRef}
          className="chat-input"
          placeholder={t.chat_placeholder}
          rows={1}
          autoComplete="off"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit(e as unknown as React.FormEvent); }
          }}
        />
      </div>
      <button type="submit" className="send-btn" aria-label="Send" disabled={!canSend}>
        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
          <path d="M3 11.5L20.5 3 13 20.5l-2.2-7.3L3 11.5z" />
        </svg>
      </button>
    </form>
  );
}
