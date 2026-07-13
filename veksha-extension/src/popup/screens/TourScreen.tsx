import { useEffect, useRef, useState } from "react";
import { useT } from "../../shared/i18n";
import type { Strings } from "../../shared/i18n/strings";

/**
 * TourScreen — the post-registration tour. Eight scenes: copy on the left,
 * an animated visualization on the right (article selection, smart pick,
 * YouTube subtitles, PDF context menu, image region, training, intro/finish).
 * A React port of the veksha-tour-final prototype.
 */

const TOTAL = 8;

// ---------------------------------------------------------------------------
// Small shared pieces
// ---------------------------------------------------------------------------

/** Timer bag: schedule with `at(ms, fn)`, everything auto-cleans on unmount. */
function useTimeline() {
  const timers = useRef<number[]>([]);
  useEffect(() => () => { timers.current.forEach(clearTimeout); }, []);
  return (ms: number, fn: () => void) => timers.current.push(window.setTimeout(fn, ms));
}

/** Fly a word chip from `from` into the knowledge-base card. Imperative on
 *  purpose — it needs live rects and outlives no state. */
function flyWord(viz: HTMLElement | null, from: HTMLElement | null, kb: HTMLElement | null, text: string, after?: () => void) {
  if (!viz || !from || !kb) { after?.(); return; }
  const vr = viz.getBoundingClientRect();
  const ar = from.getBoundingClientRect();
  const kr = kb.getBoundingClientRect();
  const el = document.createElement("div");
  el.className = "tour-fly";
  el.textContent = text;
  el.style.left = `${ar.left - vr.left}px`;
  el.style.top = `${ar.top - vr.top}px`;
  el.style.setProperty("--fx", `${kr.left - ar.left + 10}px`);
  el.style.setProperty("--fy", `${kr.top - ar.top + 6}px`);
  viz.appendChild(el);
  requestAnimationFrame(() => el.classList.add("go"));
  window.setTimeout(() => { el.remove(); after?.(); }, 850);
}

function KbCard({ t, count, pulse, kbRef }: { t: Strings; count: number; pulse: boolean; kbRef: React.RefObject<HTMLDivElement> }) {
  return (
    <div className={`tour-kb${pulse ? " pulse" : ""}`} ref={kbRef}>
      <div className="tour-kb-ic">📚</div>
      <div className="tour-kb-txt">{t.tour_kb}<br /><b>{count}</b></div>
    </div>
  );
}

/** Dark frosted popup — the YouTube subtitle translator. `tail` points at the
 *  anchor: "t" (popup below the word) or "b" (popup above the word). */
function AvPop({ t, src, tgt, show, style, tail = "t" }: { t: Strings; src: string; tgt: string; show: boolean; style?: React.CSSProperties; tail?: "t" | "b" }) {
  return (
    <div className={`tour-avpop${show ? " show" : ""}${tail === "b" ? " tail-b" : ""}`} style={style}>
      <div className="tour-avpop-langs">EN → ES</div>
      <div className="tour-avpop-src">{src}</div>
      <div className="tour-avpop-tgt">{tgt}</div>
      <div className="tour-avpop-row">
        <div className="tour-avpop-spk">🔊</div>
        <div className="tour-avpop-more">Más</div>
      </div>
      <div className="tour-avpop-saved">{t.tour_saved}</div>
    </div>
  );
}

/** White popup — the regular in-page contextual translator (like the real
 *  .veksha-popup): language row, big translation, listen + more buttons. */
function WhitePop({ t, tgt, show, style }: { t: Strings; tgt: string; show: boolean; style?: React.CSSProperties }) {
  return (
    <div className={`tour-wpop${show ? " show" : ""}`} style={style}>
      <div className="tour-wpop-head">
        <span className="tour-wpop-langs">EN → ES</span>
        <span className="tour-wpop-x">×</span>
      </div>
      <div className="tour-wpop-tr">{tgt}</div>
      <div className="tour-wpop-row">
        <span className="tour-wpop-spk">🔊</span>
        <span className="tour-wpop-more">Más</span>
      </div>
      <div className="tour-wpop-saved">{t.tour_saved}</div>
    </div>
  );
}

const BrowserBar = () => (
  <div className="tour-winbar">
    <span className="tour-windot" style={{ background: "#ff5f57" }} />
    <span className="tour-windot" style={{ background: "#febc2e" }} />
    <span className="tour-windot" style={{ background: "#28c840" }} />
    <div className="tour-winurl" />
  </div>
);

// ---------------------------------------------------------------------------
// Scenes (each mounts fresh — the parent keys them — and runs its timeline)
// ---------------------------------------------------------------------------

function PlainScene({ badge, title, text, underline }: { badge: string; title: string; text: string; underline?: boolean }) {
  const [a, b] = title.split("|");
  return (
    <div className="tour-scene tour-plain">
      <div className="tour-badge">{badge}</div>
      <h2>{a}<br /><em className={underline ? "u" : ""}>{b}</em></h2>
      <p>{text}</p>
    </div>
  );
}

function ArticleScene({ t, vizRef }: { t: Strings; vizRef: React.RefObject<HTMLDivElement> }) {
  const at = useTimeline();
  const [sel, setSel] = useState(false);
  const [pop, setPop] = useState(false);
  const [count, setCount] = useState(142);
  const [pulse, setPulse] = useState(false);
  const selRef = useRef<HTMLSpanElement>(null);
  const kbRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    at(500, () => setSel(true));
    at(1000, () => setPop(true));
    at(2200, () => flyWord(vizRef.current, selRef.current, kbRef.current, "sustain momentum", () => {
      setCount((c) => c + 1);
      setPulse(true);
      at(500, () => setPulse(false));
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="tour-scene">
      <div className="tour-win">
        <BrowserBar />
        <div className="tour-art">
          <div className="tour-art-k">Essay</div>
          <div className="tour-art-h">Why momentum is the hardest thing to keep</div>
          <p>
            Many products fail not because the idea is weak, but because teams cannot{" "}
            <span className={`tour-selm${sel ? " on" : ""}`} ref={selRef}>sustain momentum</span>{" "}
            after the first launch.
          </p>
        </div>
      </div>
      <WhitePop t={t} tgt="mantener el impulso" show={pop} style={{ left: "26%", top: "56%" }} />
      <KbCard t={t} count={count} pulse={pulse} kbRef={kbRef} />
    </div>
  );
}

const SMART_WORDS: Array<[string, string]> = [
  ["impasse", "punto muerto"],
  ["ambiguous", "ambiguo"],
  ["exacerbate", "agravar"],
  ["underlying", "subyacente"],
];

function SmartScene({ t }: { t: Strings }) {
  const at = useTimeline();
  const [hl, setHl] = useState(false);
  const [chips, setChips] = useState(0);

  useEffect(() => {
    at(500, () => setHl(true));
    SMART_WORDS.forEach((_, i) => at(1300 + i * 280, () => setChips(i + 1)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="tour-scene">
      <div className="tour-win">
        <BrowserBar />
        <div className="tour-art">
          <div className="tour-art-k">Essay</div>
          <p className={`tour-para2${hl ? " hl" : ""}`}>
            The negotiation reached an impasse, and the ambiguous clauses in the contract
            only exacerbated the underlying tension between the two parties involved in the deal.
          </p>
        </div>
      </div>
      <div className="tour-extract">
        {SMART_WORDS.slice(0, chips).map(([w, tr]) => (
          <div key={w} className="tour-exchip on">{w} <small>{tr}</small></div>
        ))}
      </div>
      <KbCard t={t} count={142} pulse={false} kbRef={useRef<HTMLDivElement>(null)} />
    </div>
  );
}

function YouTubeScene({ t, vizRef }: { t: Strings; vizRef: React.RefObject<HTMLDivElement> }) {
  const at = useTimeline();
  const [wOn, setWOn] = useState(false);
  const [pop, setPop] = useState(false);
  const [count, setCount] = useState(143);
  const [pulse, setPulse] = useState(false);
  const wRef = useRef<HTMLSpanElement>(null);
  const kbRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    at(600, () => setWOn(true));
    at(1100, () => setPop(true));
    at(2300, () => flyWord(vizRef.current, wRef.current, kbRef.current, "majestic", () => {
      setCount((c) => c + 1);
      setPulse(true);
      at(500, () => setPulse(false));
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="tour-scene">
      <div className="tour-yt">
        <div className="tour-yt-video">
          <div className="tour-yt-grad" />
          <div className="tour-yt-sub">
            <span className="tour-yt-line">
              Imagine sailing through <span className={`tour-yt-w${wOn ? " on" : ""}`} ref={wRef}>majestic</span> fjords and quiet villages
            </span>
          </div>
        </div>
        <div className="tour-yt-ctrl">
          <i>▶</i>
          <div className="tour-yt-track" />
          <span className="tour-yt-time">0:03 / 32:47</span>
        </div>
      </div>
      <AvPop t={t} src="majestic" tgt="majestuoso" show={pop} tail="b" style={{ left: "30%", bottom: "38%" }} />
      <KbCard t={t} count={count} pulse={pulse} kbRef={kbRef} />
    </div>
  );
}

function PdfScene({ t, vizRef }: { t: Strings; vizRef: React.RefObject<HTMLDivElement> }) {
  const at = useTimeline();
  const [ctx, setCtx] = useState(false);
  const [avHl, setAvHl] = useState(false);
  const [pop, setPop] = useState(false);
  const [count, setCount] = useState(144);
  const [pulse, setPulse] = useState(false);
  const popRef = useRef<HTMLDivElement>(null);
  const kbRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    at(700, () => setCtx(true));
    at(1800, () => setAvHl(true));
    at(2400, () => { setCtx(false); setPop(true); });
    at(3400, () => flyWord(vizRef.current, popRef.current, kbRef.current, "southeast", () => {
      setCount((c) => c + 1);
      setPulse(true);
      at(500, () => setPulse(false));
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="tour-scene">
      <div className="tour-pdf">
        <div className="tour-pdf-bar"><span>≡</span><span style={{ flex: 1 }}>Greece.pdf</span><span className="tour-pdf-pg">3 / 100</span></div>
        <div className="tour-pdf-scroll">
          <div className="tour-pdf-page">
            <h4>A Short Description</h4>
            <p>
              Greece, officially the Hellenic Republic, is a country in Europe. Although geographically
              located at the continent's <span className="tour-pdf-selm">southeast</span>, it is generally
              included in Western Europe.
            </p>
            <div className="tour-pdf-img">🏛️</div>
            <div className={`tour-ctx${ctx ? " show" : ""}`} style={{ left: "40%", top: "22%" }}>
              <div className="tour-ctx-i">Copy <span className="k">Ctrl+C</span></div>
              <div className="tour-ctx-i">Search Google</div>
              <div className="tour-ctx-i">Print… <span className="k">Ctrl+P</span></div>
              <div className="tour-ctx-sep" />
              <div className={`tour-ctx-i av${avHl ? " hl" : ""}`}>
                <span><span className="tour-ctx-avic">VE</span>Translate in Veksha</span>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div ref={popRef} style={{ position: "absolute", left: "16%", top: "42%", width: 0, height: 0 }} />
      <WhitePop t={t} tgt="sureste" show={pop} style={{ left: "16%", top: "42%" }} />
      <KbCard t={t} count={count} pulse={pulse} kbRef={kbRef} />
    </div>
  );
}

function ImageScene({ t, vizRef }: { t: Strings; vizRef: React.RefObject<HTMLDivElement> }) {
  const at = useTimeline();
  const [grown, setGrown] = useState(false);
  const [replaced, setReplaced] = useState(false);
  const [regionGone, setRegionGone] = useState(false);
  const [count, setCount] = useState(145);
  const [pulse, setPulse] = useState(false);
  const txtRef = useRef<HTMLDivElement>(null);
  const kbRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    at(600, () => setGrown(true));
    // The region is captured and the original text gets replaced in place with
    // the translated patch (that's what the real image-region feature does).
    at(1800, () => setReplaced(true));
    at(2600, () => setRegionGone(true));
    at(2900, () => flyWord(vizRef.current, txtRef.current, kbRef.current, "empower", () => {
      setCount((c) => c + 1);
      setPulse(true);
      at(500, () => setPulse(false));
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="tour-scene">
      <div className="tour-imgscene">
        <div className="tour-poster">
          <div className="tour-poster-h">Bent Ginsburg<br />Psychologist</div>
          <div className="tour-poster-photo">🧑🏾‍⚕️</div>
          <div className="tour-poster-txtwrap" ref={txtRef}>
            <div className="tour-poster-txt">As a psychologist, I empower individuals to navigate life's challenges with resilience.</div>
            <div className={`tour-inpaint${replaced ? " show" : ""}`}>
              Como psicóloga, empodero a las personas para afrontar los desafíos de la vida con resiliencia.
            </div>
          </div>
          <div className={`tour-region${grown && !regionGone ? " show" : ""}${grown ? " grown" : ""}`}>
            <div className="tour-region-tag">{t.tour_region_tag}</div>
            <div className="hnd h1" /><div className="hnd h2" /><div className="hnd h3" /><div className="hnd h4" />
          </div>
        </div>
      </div>
      <KbCard t={t} count={count} pulse={pulse} kbRef={kbRef} />
    </div>
  );
}

function TrainScene({ t }: { t: Strings }) {
  const at = useTimeline();
  const [toast, setToast] = useState(false);
  const [card, setCard] = useState(false);
  const [typed, setTyped] = useState("");
  const [fb, setFb] = useState(false);
  const word = "majestuoso";

  useEffect(() => {
    at(400, () => setToast(true));
    at(1100, () => setCard(true));
    for (let i = 1; i <= word.length; i++) {
      at(2000 + i * 70, () => {
        setTyped(word.slice(0, i));
        if (i === word.length) at(500, () => setFb(true));
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="tour-scene">
      <div className="tour-train">
        <div className={`tour-tt${toast ? " show" : ""}`}>
          <i>🔔</i>
          <div><b>{t.tour_tt_title}</b><br /><span>{t.tour_tt_sub}</span></div>
        </div>
        <div className={`tour-qc${card ? " show" : ""}`}>
          <div className="tour-qb">{t.tour_q_badge}</div>
          <div className="tour-qw">majestic <div className="tour-qspk">🔊</div></div>
          <div className="tour-qctx">{t.tour_q_ctx}</div>
          <div className="tour-qir">
            <div className="tour-qi"><span>{typed}</span><span className="tour-qcur" /></div>
          </div>
          <div className={`tour-qfb${fb ? " show" : ""}`}>{t.tour_q_fb}</div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main tour
// ---------------------------------------------------------------------------

export function TourScreen({ onFinish }: { onFinish: () => void }) {
  const t = useT();
  const [cur, setCur] = useState(0);
  const [animKey, setAnimKey] = useState(0); // bump to replay the scene
  const vizRef = useRef<HTMLDivElement>(null);

  const copy = [
    { step: t.tour_s0_step, title: t.tour_s0_title, text: t.tour_s0_text, tag: "" },
    { step: t.tour_s1_step, title: t.tour_s1_title, text: t.tour_s1_text, tag: t.tour_s1_tag },
    { step: t.tour_s2_step, title: t.tour_s2_title, text: t.tour_s2_text, tag: t.tour_s2_tag },
    { step: t.tour_s3_step, title: t.tour_s3_title, text: t.tour_s3_text, tag: t.tour_s3_tag },
    { step: t.tour_s4_step, title: t.tour_s4_title, text: t.tour_s4_text, tag: t.tour_s4_tag },
    { step: t.tour_s5_step, title: t.tour_s5_title, text: t.tour_s5_text, tag: t.tour_s5_tag },
    { step: t.tour_s6_step, title: t.tour_s6_title, text: t.tour_s6_text, tag: t.tour_s6_tag },
    { step: t.tour_s7_step, title: t.tour_s7_title, text: t.tour_s7_text, tag: "" },
  ];
  const c = copy[cur];
  const [titleA, titleB] = c.title.split("|");
  const isLast = cur === TOTAL - 1;

  const go = (n: number) => { setCur(n); setAnimKey((k) => k + 1); };
  const next = () => (isLast ? onFinish() : go(cur + 1));

  const key = `${cur}-${animKey}`;

  return (
    <div className="tour">
      <div className="tour-head">
        <div className="tour-brand">
          <div className="shell-brand-mark">VE</div>
          <div className="shell-brand-name">Veksha</div>
        </div>
        <div className="tour-head-spacer" />
        <div className="tour-dots">
          {Array.from({ length: TOTAL }, (_, i) => (
            <div key={i} className={`tour-dot${i === cur ? " active" : i < cur ? " done" : ""}`} />
          ))}
        </div>
        {!isLast && <div className="tour-skip" onClick={() => go(TOTAL - 1)}>{t.tour_skip}</div>}
      </div>

      <div className={`tour-body${cur === 0 || cur === TOTAL - 1 ? " solo" : ""}`}>
        {cur !== 0 && cur !== TOTAL - 1 && (
          <div className="tour-copy">
            <div className="tour-step">{c.step}</div>
            <h1>{titleA}<br /><em>{titleB}</em></h1>
            <p>{c.text}</p>
            {c.tag && <div className="tour-tag">{c.tag}</div>}
          </div>
        )}

        <div className="tour-viz" ref={vizRef}>
          {cur === 0 && <PlainScene badge="🧠" title={c.title} text={c.text} />}
          {cur === 1 && <ArticleScene key={key} t={t} vizRef={vizRef} />}
          {cur === 2 && <SmartScene key={key} t={t} />}
          {cur === 3 && <YouTubeScene key={key} t={t} vizRef={vizRef} />}
          {cur === 4 && <PdfScene key={key} t={t} vizRef={vizRef} />}
          {cur === 5 && <ImageScene key={key} t={t} vizRef={vizRef} />}
          {cur === 6 && <TrainScene key={key} t={t} />}
          {cur === 7 && <PlainScene badge="🎉" title={c.title} text={c.text} underline />}
        </div>
      </div>

      <div className="tour-foot">
        {cur >= 1 && cur <= 6 ? (
          <div className="tour-replay" onClick={() => setAnimKey((k) => k + 1)}>{t.tour_replay}</div>
        ) : (
          <div className="tour-replay-spacer" />
        )}
        <button className="tour-btn ghost" style={{ visibility: cur === 0 ? "hidden" : "visible" }} onClick={() => go(cur - 1)}>
          {t.tour_back}
        </button>
        <button className="tour-btn" onClick={next}>
          {cur === 0 ? t.tour_next_first : isLast ? t.tour_start : t.tour_next}
        </button>
      </div>
    </div>
  );
}
