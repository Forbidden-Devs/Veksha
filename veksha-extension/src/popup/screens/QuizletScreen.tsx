import { useEffect, useState } from "react";
import * as api from "../../shared/api";
import { useT } from "../../shared/i18n";
import { useApp } from "../App";

type QuizletError = "status" | "export" | "export_all" | "csv" | "import";

export function QuizletScreen() {
  const { username } = useApp();
  const t = useT();
  const [status, setStatus] = useState<api.QuizletExportStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<QuizletError | null>(null);
  const [success, setSuccess] = useState(false);
  const [importResult, setImportResult] = useState<{ imported: number; skipped: number; errors: string[] } | null>(null);

  useEffect(() => {
    loadStatus();
  }, [username]);

  async function loadStatus() {
    try {
      setLoading(true);
      const result = await api.quizletExportStatus(username);
      setStatus(result);
      setError(null);
    } catch (err) {
      setError("status");
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  async function handleExportUnexported() {
    try {
      setExporting(true);
      setError(null);
      setSuccess(false);
      const token = await api.getAuthToken();
      const response = await fetch(`${api.BACKEND_URL}/api/quizlet/export`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}` },
      });
      if (!response.ok) throw new Error("Export failed");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "quizlet_export.csv";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      setSuccess(true);
      await loadStatus();
    } catch (err) {
      setError("export");
      console.error(err);
    } finally {
      setExporting(false);
    }
  }

  async function handleExportAll() {
    try {
      setExporting(true);
      setError(null);
      setSuccess(false);
      const token = await api.getAuthToken();
      const response = await fetch(`${api.BACKEND_URL}/api/quizlet/export-all`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}` },
      });
      if (!response.ok) throw new Error("Export failed");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "quizlet_export_all.csv";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      setSuccess(true);
      await loadStatus();
    } catch (err) {
      setError("export_all");
      console.error(err);
    } finally {
      setExporting(false);
    }
  }

  async function handleImport(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    if (!file.name.endsWith('.csv')) {
      setError("csv");
      return;
    }

    try {
      setImporting(true);
      setError(null);
      setSuccess(false);
      setImportResult(null);

      const formData = new FormData();
      formData.append("file", file);

      const token = await api.getAuthToken();
      const response = await fetch(`${api.BACKEND_URL}/api/quizlet/import`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}` },
        body: formData,
      });

      if (!response.ok) {
        throw new Error("Import failed");
      }

      const result = await response.json();
      setImportResult({
        imported: result.imported_count,
        skipped: result.skipped_count,
        errors: result.errors || [],
      });
      setSuccess(true);
      await loadStatus();
    } catch (err) {
      setError("import");
      console.error(err);
    } finally {
      setImporting(false);
      // Reset file input
      event.target.value = "";
    }
  }

  const errorCopy: Record<QuizletError, string> = {
    status: t.quizlet_error_status,
    export: t.quizlet_error_export,
    export_all: t.quizlet_error_export_all,
    csv: t.quizlet_error_csv,
    import: t.quizlet_error_import,
  };

  return (
    <section className="screen quizlet-screen">
      <div className="quizlet-content">
        {loading ? (
          <p className="quizlet-placeholder">{t.quizlet_loading}</p>
        ) : status ? (
          <>
            <section className="quizlet-card">
              <h2>{t.quizlet_status_title}</h2>
              <div className="quizlet-stats">
                <div><strong>{status.total_words}</strong><span>{t.quizlet_total_words}</span></div>
                <div><strong>{status.exported_words}</strong><span>{t.quizlet_exported}</span></div>
                <div><strong>{status.unexported_words}</strong><span>{t.quizlet_not_exported}</span></div>
              </div>
            </section>

            <section className="quizlet-card">
              <h2>{t.quizlet_export_options}</h2>
              <div className="quizlet-actions">
                <div>
                  <button className="btn btn-block" disabled={exporting || status.unexported_words === 0} onClick={handleExportUnexported}>
                    {exporting ? t.quizlet_exporting : t.quizlet_export_new.replace("{n}", String(status.unexported_words))}
                  </button>
                  <p className="quizlet-hint">{t.quizlet_export_new_hint}</p>
                </div>
                <div>
                  <button className="btn btn-block" disabled={exporting || status.total_words === 0} onClick={handleExportAll}>
                    {exporting ? t.quizlet_exporting : t.quizlet_export_all.replace("{n}", String(status.total_words))}
                  </button>
                  <p className="quizlet-hint">{t.quizlet_export_all_hint}</p>
                </div>
              </div>
              <p className="quizlet-format-hint">{t.quizlet_format_hint}</p>
            </section>

            <section className="quizlet-card">
              <h2>{t.quizlet_import_title}</h2>
              <p className="quizlet-hint quizlet-import-copy">
                {t.quizlet_import_desc}
              </p>

              <label className={`btn btn-block quizlet-file-button${importing ? " is-disabled" : ""}`} htmlFor="quizlet-file-input">
                {importing ? t.quizlet_importing : t.quizlet_select_csv}
              </label>
              <input
                id="quizlet-file-input"
                type="file"
                accept=".csv"
                onChange={handleImport}
                disabled={importing}
                style={{ display: "none" }}
              />

              {importResult && (
                <div className="quizlet-import-result">
                  <p>✓ <strong>{t.quizlet_imported}:</strong> {importResult.imported}</p>
                  <p>⊘ <strong>{t.quizlet_skipped}:</strong> {importResult.skipped}</p>
                  {importResult.errors.length > 0 && (
                    <details>
                      <summary>{t.quizlet_errors.replace("{n}", String(importResult.errors.length))}</summary>
                      <p>{t.quizlet_error_import}</p>
                    </details>
                  )}
                </div>
              )}
            </section>

            {error && <p className="onboarding-error">{errorCopy[error]}</p>}
            {success && !importResult && <p className="quizlet-success">✓ {t.quizlet_export_success}</p>}

            <aside className="quizlet-import-hint">
              <p><strong>{t.quizlet_export_steps_title}:</strong></p>
              <ol>
                <li>{t.quizlet_export_step_1}</li>
                <li>{t.quizlet_export_step_2}</li>
                <li>{t.quizlet_export_step_3}</li>
                <li>{t.quizlet_export_step_4}</li>
              </ol>
            </aside>
          </>
        ) : (
          <p className="onboarding-error">{t.quizlet_error_status}</p>
        )}
      </div>
    </section>
  );
}
