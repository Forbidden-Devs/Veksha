import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../../shared/api";
import { useT } from "../../shared/i18n";
import type { ChatMessage, MessageResponse } from "../../shared/types";
import { ChatInput } from "../components/ChatInput";
import { ChatMessages } from "../components/ChatMessages";
import { useApp } from "../App";

type ChatMode = "assistant" | "translator";

export function ChatScreen() {
  const { username, openReminder, targetLang, nativeLang } = useApp();
  const t = useT();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [chatMode, setChatMode] = useState<ChatMode>("assistant");
  const [explainedMsgs, setExplainedMsgs] = useState<Set<string>>(new Set());

  function addMessage(text: string, role: ChatMessage["role"]): void {
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), text, role, time: new Date() },
    ]);
  }

  function switchMode(next: ChatMode) {
    if (next === chatMode) return;
    setChatMode(next);
    setMessages([]);
  }

  async function handleExplain(msgId: string, originalText: string, translation: string) {
    setExplainedMsgs(prev => new Set(prev).add(msgId));
    setSending(true);
    try {
      const res = await api.explain(username, originalText, translation);
      addMessage(res.explanation, "bot");
    } catch {
      // silently ignore
    } finally {
      setSending(false);
    }
  }

  const handleSend = useCallback(
    async (text: string) => {
      addMessage(text, "user");
      setSending(true);
      try {
        if (chatMode === "translator") {
          const res = await api.translate(username, text, nativeLang, targetLang, true);
          const speechLang = res.detected_source_lang === targetLang ? nativeLang : targetLang;
          const msgId = crypto.randomUUID();
          setMessages(prev => [...prev, {
            id: msgId, text: res.translation, role: "bot", time: new Date(),
            isTranslation: true, originalText: text, speechLang,
          }]);
        } else {
          const response: MessageResponse = await api.sendMessage(username, text);
          for (const msg of response.messages) addMessage(msg, "bot");
        }
      } catch (err) {
        addMessage(`Error: ${(err as Error).message}`, "error");
      } finally {
        setSending(false);
      }
    },
    [username, chatMode, nativeLang, targetLang]
  );

  return (
    <section className="screen screen-chat">
      <header className="chat-header">
        <div className="chat-mode-tabs">
          <button
            className={`chat-mode-tab${chatMode === "assistant" ? " active" : ""}`}
            onClick={() => switchMode("assistant")}
          >
            {t.chat_mode_assistant ?? "Assistant"}
          </button>
          <button
            className={`chat-mode-tab${chatMode === "translator" ? " active" : ""}`}
            onClick={() => switchMode("translator")}
          >
            {t.chat_mode_translate ?? "Translate"}
          </button>
        </div>
        <div className="header-actions">
          <RemindersButton username={username} onOpen={openReminder} />
        </div>
      </header>

      {chatMode === "assistant" && messages.length === 0 ? (
        <div className="chat-messages">
          <div className="chat-greeting-row">
            <div className="logo-badge logo-badge-sm">Ve</div>
            <div className="msg msg-bot chat-greeting">
              <span>{t.chat_greeting}</span>
              <div className="chat-chips">
                {[t.chat_chip_topic, t.chat_chip_words, t.chat_chip_explain].map((chip) => (
                  <button key={chip} className="chat-chip" onClick={() => handleSend(chip)} disabled={sending}>
                    {chip}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : (
        <ChatMessages messages={messages} onExplain={handleExplain} explainedMsgs={explainedMsgs} />
      )}
      <ChatInput onSend={handleSend} disabled={sending} />
    </section>
  );
}

// ---------------------------------------------------------------------------
// Reminders button
// ---------------------------------------------------------------------------

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
