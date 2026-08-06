interface OverlayHeaderProps {
  title: string;
  titleClass: string;
  headerClass: string;
  closeLabel: string;
  onClose: () => void;
}

export function OverlayHeader(props: OverlayHeaderProps) {
  return (
    <header className={props.headerClass} data-drag-handle>
      <span className="logo-badge logo-badge-sm" aria-hidden="true">Ve</span>
      <strong className={props.titleClass}>{props.title}</strong>
      <button
        type="button"
        className="icon-btn"
        style={{ marginInlineStart: "auto" }}
        aria-label={props.closeLabel}
        onClick={props.onClose}
      >
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path d="m6 6 12 12M18 6 6 18" fill="none" stroke="currentColor" strokeWidth="2" />
        </svg>
      </button>
    </header>
  );
}
