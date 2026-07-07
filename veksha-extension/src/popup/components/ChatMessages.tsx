import { useEffect, useRef } from "react";
import { useT } from "../../shared/i18n";
import { canSpeak, speakText } from "../../shared/speech";
import type { ChatMessage } from "../../shared/types";

interface Props {
  messages: ChatMessage[];
  onExplain?: (msgId: string, originalText: string, translation: string) => void;
  explainedMsgs?: Set<string>;
}

function MessageBubble({
  msg,
  onExplain,
  explained,
}: {
  msg: ChatMessage;
  onExplain?: Props["onExplain"];
  explained?: boolean;
}) {
  const t = useT();

  if (msg.role === "error") {
    return <div className="msg msg-error">{msg.text}</div>;
  }

  const showExplain =
    msg.isTranslation && msg.originalText && onExplain && !explained;
  const showListen = msg.isTranslation && Boolean(msg.speechLang) && canSpeak();

  return (
    <div className="msg-group">
      <div className={`msg msg-${msg.role}`}>
        <span>{msg.text}</span>
      </div>
      {(showExplain || showListen) && (
        <div className="msg-action-row">
          {showListen && (
            <button
              className="msg-listen-btn"
              title={t.chat_listen}
              aria-label={t.chat_listen}
              onClick={() => speakText(msg.text, msg.speechLang!)}
            >
              <span aria-hidden="true">🔊</span>
              <span>{t.chat_listen}</span>
            </button>
          )}
          {showExplain && (
            <button
              className="msg-explain-btn"
              onClick={() => onExplain!(msg.id, msg.originalText!, msg.text)}
            >
              {t.chat_explain} →
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export function ChatMessages({ messages, onExplain, explainedMsgs }: Props) {
  const t = useT();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="chat-messages">
      <div className="chat-day-divider"><span>{t.chat_today}</span></div>
      {messages.map((msg) => (
        <MessageBubble
          key={msg.id}
          msg={msg}
          onExplain={onExplain}
          explained={explainedMsgs?.has(msg.id)}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
