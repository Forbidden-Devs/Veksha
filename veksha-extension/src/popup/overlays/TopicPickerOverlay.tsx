import { useEffect, useRef, useState } from "react";
import * as api from "../../shared/api";
import { useT } from "../../shared/i18n";
import type { LessonTopicSummary } from "../../shared/types";

export function TopicPickerOverlay({
  username,
  onSelect,
  onClose,
}: {
  username: string;
  onSelect: (topic: string) => void;
  onClose: () => void;
}) {
  const t = useT();
  const [topics, setTopics] = useState<LessonTopicSummary[] | null>(null);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.getLessonTopics(username)
      .then(r => setTopics(r.topics))
      .catch(() => setTopics([]));
  }, [username]);

  useEffect(() => {
    if (topics !== null && topics.length === 0) {
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [topics]);

  async function handleCreate() {
    const name = newName.trim();
    if (!name || creating) return;
    setCreating(true);
    try {
      await api.createLessonTopic(username, name);
      onSelect(name);
    } catch {
      setCreating(false);
    }
  }

  function masteryBar(mastery: number) {
    const pct = Math.round(mastery * 100);
    return (
      <div className="topic-mastery-bar">
        <div className="topic-mastery-fill" style={{ width: `${pct}%` }} />
      </div>
    );
  }

  return (
    <div className="lesson-overlay">
      <div className="lesson-header" data-drag-handle>
        <div className="logo-badge logo-badge-sm">Ve</div>
        <span className="lesson-header-title">{t.menu_learn}</span>
        <button className="icon-btn" style={{ marginLeft: "auto" }} aria-label="Close" onClick={onClose}>
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="topic-picker-body">
        {topics === null ? (
          <p className="topic-picker-status">{t.topics_loading}</p>
        ) : topics.length === 0 ? (
          <div className="topic-empty">
            <div className="topic-empty-icon">🎓</div>
            <h3 className="topic-empty-title">{t.topics_empty_title}</h3>
            <p className="topic-empty-hint">{t.topics_empty_hint}</p>
          </div>
        ) : (
          <ul className="topic-list">
            {topics.map(topic => (
              <li key={topic.name} className="topic-item" onClick={() => onSelect(topic.name)}>
                <div className="topic-item-info">
                  <span className="topic-item-name">{topic.name}</span>
                  <span className="topic-item-blocks">
                    {t.topics_blocks.replace("{n}", String(topic.block_count))}
                  </span>
                </div>
                <div className="topic-item-right">
                  {masteryBar(topic.mastery)}
                  <span className="topic-item-pct">{Math.round(topic.mastery * 100)}%</span>
                </div>
              </li>
            ))}
          </ul>
        )}

        <div className="topic-add-row">
          <input
            ref={inputRef}
            className="textarea-input topic-add-input"
            placeholder={t.topics_placeholder}
            value={newName}
            onChange={e => setNewName(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleCreate()}
          />
          <button
            className="btn btn-gradient"
            onClick={handleCreate}
            disabled={!newName.trim() || creating}
          >
            {creating ? "..." : t.topics_add}
          </button>
        </div>
      </div>
    </div>
  );
}
