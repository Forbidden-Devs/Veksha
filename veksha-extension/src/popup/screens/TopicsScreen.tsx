import { useEffect, useRef, useState } from "react";
import * as api from "../../shared/api";
import { useT } from "../../shared/i18n";
import type { LessonTopicSummary } from "../../shared/types";
import { useApp } from "../App";

/** Topics live in the popup now; clicking one opens the floating lesson
 *  window on the page (same size/mechanics as before). */
export function TopicsScreen() {
  const { username, openLesson } = useApp();
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
      openLesson(name);
    } catch {
      setCreating(false);
    }
  }

  return (
    <section className="screen">
      <div className="topics-body">
        {topics === null ? (
          <p className="topic-picker-status">{t.topics_loading}</p>
        ) : topics.length === 0 ? (
          <div className="topic-empty">
            <div className="topic-empty-icon">🎓</div>
            <h3 className="topic-empty-title">{t.topics_empty_title}</h3>
            <p className="topic-empty-hint">{t.topics_empty_hint}</p>
          </div>
        ) : (
          <div className="topics-grid">
            {topics.map((topic, i) => {
              const pct = Math.round(topic.mastery * 100);
              return (
                <div key={topic.name} className="topic-card2" onClick={() => openLesson(topic.name)}>
                  <div className="topic-card2-top">
                    <span className={`topic-chip${i % 2 ? " chip-blue" : ""}`}>
                      {t.topics_blocks.replace("{n}", String(topic.block_count))}
                    </span>
                    <span className="topic-card2-pct">{pct}%</span>
                  </div>
                  <div className="topic-card2-name">{topic.name}</div>
                  <div className="topic-card2-progress">
                    <div className="tbar"><i style={{ width: `${pct}%` }} /></div>
                  </div>
                </div>
              );
            })}
          </div>
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
    </section>
  );
}
