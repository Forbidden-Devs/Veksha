import { useEffect, useState } from "react";
import * as api from "../../shared/api";
import { useT } from "../../shared/i18n";
import { useApp } from "../App";

export function QuizletScreen() {
  const { username, navigateTo } = useApp();
  const t = useT();
  const [status, setStatus] = useState<api.QuizletExportStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
      setError("Failed to load export status");
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
      setError("Failed to export words");
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
      setError("Failed to export all words");
      console.error(err);
    } finally {
      setExporting(false);
    }
  }

  async function handleImport(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    if (!file.name.endsWith('.csv')) {
      setError("Please select a CSV file");
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
        const errorData = await response.json().catch(() => ({ detail: "Import failed" }));
        throw new Error(errorData.detail || "Import failed");
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
      setError(err instanceof Error ? err.message : "Failed to import words");
      console.error(err);
    } finally {
      setImporting(false);
      // Reset file input
      event.target.value = "";
    }
  }

  return (
    <section className="screen">
      <button className="screen-header-back" onClick={() => navigateTo("home")} />
      <h1 className="screen-title">Quizlet Export</h1>

      <div className="screen-content">
        {loading ? (
          <p className="settings-toggle-desc">Loading...</p>
        ) : status ? (
          <>
            <div className="settings-section">
              <label className="field-label">Export Status</label>
              <div className="quizlet-stats">
                <p><strong>Total words:</strong> {status.total_words}</p>
                <p><strong>Exported:</strong> {status.exported_words}</p>
                <p><strong>Not exported:</strong> {status.unexported_words}</p>
              </div>
            </div>

            <div className="settings-section">
              <label className="field-label">Export Options</label>
              <button
                className="btn btn-block"
                disabled={exporting || status.unexported_words === 0}
                onClick={handleExportUnexported}
              >
                {exporting ? "Exporting..." : `Export New (${status.unexported_words})`}
              </button>
              <p className="quizlet-hint">
                Exports only words you haven't exported yet. Downloads as CSV file.
              </p>

              <button
                className="btn btn-block"
                disabled={exporting || status.total_words === 0}
                onClick={handleExportAll}
                style={{ marginTop: "1rem" }}
              >
                {exporting ? "Exporting..." : `Export All (${status.total_words})`}
              </button>
              <p className="quizlet-hint">
                Exports all your words. Downloads as CSV file.
              </p>
            </div>

            <div className="settings-section" style={{ marginTop: "2rem", borderTop: "1px solid var(--color-border)" }}>
              <label className="field-label">Import from Quizlet</label>
              <p className="quizlet-hint">
                Upload a CSV file from Quizlet to add words to your vocabulary. Columns: Word, Translation, Context
              </p>

              <label className="field-label" htmlFor="quizlet-file-input">
                <div className="btn btn-block" style={{ cursor: "pointer" }}>
                  {importing ? "Importing..." : "Select CSV File"}
                </div>
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
                <div className="quizlet-import-result" style={{ marginTop: "1rem", padding: "1rem", backgroundColor: "var(--color-bg-alt)", borderRadius: "4px" }}>
                  <p>✓ <strong>Imported:</strong> {importResult.imported} words</p>
                  <p>⊘ <strong>Skipped:</strong> {importResult.skipped} words</p>
                  {importResult.errors.length > 0 && (
                    <details style={{ marginTop: "0.5rem" }}>
                      <summary>Errors ({importResult.errors.length})</summary>
                      <ul style={{ fontSize: "0.85em", color: "var(--color-error)", marginTop: "0.5rem" }}>
                        {importResult.errors.map((err, i) => <li key={i}>{err}</li>)}
                      </ul>
                    </details>
                  )}
                </div>
              )}
            </div>

            {error && <p className="onboarding-error">{error}</p>}
            {success && !importResult && <p className="settings-toggle-desc">✓ Export successful! File downloaded.</p>}

            <div className="quizlet-import-hint" style={{ marginTop: "2rem" }}>
              <p><strong>How to export from Quizlet:</strong></p>
              <ol>
                <li>Go to your Quizlet study set</li>
                <li>Click the three dots menu (⋮)</li>
                <li>Select "Download as..." → CSV</li>
                <li>Upload the CSV file here</li>
              </ol>
            </div>
          </>
        ) : (
          <p className="onboarding-error">Failed to load status</p>
        )}
      </div>
    </section>
  );
}
