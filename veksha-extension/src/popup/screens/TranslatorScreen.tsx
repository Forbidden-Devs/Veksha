import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../../shared/api";
import { useT } from "../../shared/i18n";
import type { ChatMessage } from "../../shared/types";
import { ChatInput } from "../components/ChatInput";
import { ChatMessages } from "../components/ChatMessages";
import { useApp } from "../App";

export function TranslatorScreen() {
  const { username, openReminder, targetLang, nativeLang } = useApp();
  const t = useT();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [explainedMsgs, setExplainedMsgs] = useState<Set<string>>(new Set());

  function addMessage(text: string, role: ChatMessage["role"]): void {
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), text, role, time: new Date() },
    ]);
  }

  async function handleExplain(msgId: string, originalText: string, translation: string) {
    setExplainedMsgs((prev) => new Set(prev).add(msgId));
    setSending(true);
    try {
      const res = await api.explain(username, originalText, translation);
      addMessage(res.explanation, "bot");
    } catch {
      // The translation stays usable even when an optional explanation fails.
    } finally {
      setSending(false);
    }
  }

  const handleSend = useCallback(
    async (text: string) => {
      addMessage(text, "user");
      setSending(true);
      try {
        const res = await api.translate(username, text, nativeLang, targetLang, true);
        const speechLang = res.detected_source_lang === targetLang ? nativeLang : targetLang;
        setMessages((prev) => [...prev, {
          id: crypto.randomUUID(),
          text: res.translation,
          role: "bot",
          time: new Date(),
          isTranslation: true,
          originalText: text,
          speechLang,
        }]);
      } catch (err) {
        addMessage(`Error: ${(err as Error).message}`, "error");
      } finally {
        setSending(false);
      }
    },
    [username, nativeLang, targetLang],
  );

  return (
    <section className="screen screen-chat">
      <header className="chat-header">
        <strong className="translator-heading">{t.chat_mode_translate}</strong>
        <div className="header-actions">
          <RemindersButton username={username} onOpen={openReminder} />
        </div>
      </header>

      <ChatMessages messages={messages} onExplain={handleExplain} explainedMsgs={explainedMsgs} />
      <ChatInput onSend={handleSend} disabled={sending} />
    </section>
  );
}

function RemindersButton({ username, onOpen }: { username: string; onOpen: () => void }) {
  const t = useT();
  const [hasDue, setHasDue] = useState(false);
  const checkedRef = useRef(false);

  useEffect(() => {
    if (checkedRef.current) return;
    checkedRef.current = true;
    api.getReminders(username).then((r) => setHasDue(r.should_remind)).catch(() => {});
  }, [username]);

  async function handleClick() {
    try {
      const result = await api.getReminders(username);
      setHasDue(result.should_remind);
      if (result.should_remind) onOpen();
    } catch {}
  }

  return (
    <button className="icon-btn" title={t.chat_reminders} aria-label={t.chat_reminders} onClick={handleClick}>
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
        <path d="M13.73 21a2 2 0 0 1-3.46 0" />
      </svg>
      {hasDue && <span className="dot" />}
    </button>
  );
}
