import { useEffect, useState } from "react";
import { CONFIG } from "../../shared/config";
import { useT } from "../../shared/i18n";
import { storageGet, storageSet } from "../../shared/platform";

export function ImmersionScreen() {
  const t = useT();
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    storageGet([CONFIG.STORAGE_KEY_IMMERSION]).then((result) => {
      setEnabled(Boolean(result[CONFIG.STORAGE_KEY_IMMERSION]));
    });
  }, []);

  async function toggle() {
    const next = !enabled;
    setEnabled(next);
    await storageSet({ [CONFIG.STORAGE_KEY_IMMERSION]: next });
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab?.id) {
        await chrome.tabs.sendMessage(tab.id, { type: "VEKSHA_TOGGLE_IMMERSION", enabled: next });
      }
    } catch {
      // Restricted pages cannot receive content-script messages; the saved
      // preference will still be applied on the next regular page.
    }
  }

  return (
    <section className="screen screen-settings immersion-screen">
      <div className="imm-modal-icon" aria-hidden="true">✨</div>
      <h2 className="lang-pick-title">{enabled ? t.imm_modal_title : t.nav_immersion}</h2>
      <p className="imm-modal-sub">{t.imm_modal_sub}</p>

      <div className="imm-card pink">
        <div className="imm-card-ic" aria-hidden="true">🔎</div>
        <div className="imm-card-body">
          <div className="imm-card-title">{t.imm_card1_title}</div>
          <div className="imm-card-desc">{t.imm_card1_desc}</div>
        </div>
      </div>
      <div className="imm-card blue">
        <div className="imm-card-ic" aria-hidden="true">💡</div>
        <div className="imm-card-body">
          <div className="imm-card-title">{t.imm_card2_title}</div>
          <div className="imm-card-desc">{t.imm_card2_desc}</div>
        </div>
      </div>
      <div className="imm-card pink">
        <div className="imm-card-ic" aria-hidden="true">📈</div>
        <div className="imm-card-body">
          <div className="imm-card-title">{t.imm_card3_title} <span className="imm-badge">i + 1</span></div>
          <div className="imm-card-desc">{t.imm_card3_desc}</div>
        </div>
      </div>

      <button className="btn btn-gradient btn-block" type="button" onClick={toggle}>
        {enabled ? t.immersion_on : t.immersion_off}
      </button>
    </section>
  );
}
