import { useEffect, useState } from "react";
import * as api from "../../shared/api";
import { useT } from "../../shared/i18n";
import { useApp } from "../App";

export function QuizletScreen() {
  const { username } = useApp();
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
    <section className="screen quizlet-screen">
      <div className="quizlet-content">
        {loading ? (
          <p className="quizlet-placeholder">Loading...</p>
        ) : status ? (
          <>
            <section className="quizlet-card">
              <h2>Export status</h2>
              <div className="quizlet-stats">
                <div><strong>{status.total_words}</strong><span>Total words</span></div>
                <div><strong>{status.exported_words}</strong><span>Exported</span></div>
                <div><strong>{status.unexported_words}</strong><span>Not exported</span></div>
              </div>
            </section>

            <section className="quizlet-card">
              <h2>Export options</h2>
              <div className="quizlet-actions">
                <div>
                  <button className="btn btn-block" disabled={exporting || status.unexported_words === 0} onClick={handleExportUnexported}>
                    {exporting ? "Exporting..." : `Export New (${status.unexported_words})`}
                  </button>
                  <p className="quizlet-hint">Only words you haven't exported yet.</p>
                </div>
                <div>
                  <button className="btn btn-block" disabled={exporting || status.total_words === 0} onClick={handleExportAll}>
                    {exporting ? "Exporting..." : `Export All (${status.total_words})`}
                  </button>
                  <p className="quizlet-hint">All words in your vocabulary.</p>
                </div>
              </div>
              <p className="quizlet-format-hint">Both options download a CSV file ready for Quizlet.</p>
            </section>

            <section className="quizlet-card">
              <h2>Import from Quizlet</h2>
              <p className="quizlet-hint quizlet-import-copy">
                Upload a CSV file from Quizlet to add words to your vocabulary. Columns: Word, Translation, Context
              </p>

              <label className={`btn btn-block quizlet-file-button${importing ? " is-disabled" : ""}`} htmlFor="quizlet-file-input">
                {importing ? "Importing..." : "Select CSV File"}
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
                  <p>✓ <strong>Imported:</strong> {importResult.imported} words</p>
                  <p>⊘ <strong>Skipped:</strong> {importResult.skipped} words</p>
                  {importResult.errors.length > 0 && (
                    <details>
                      <summary>Errors ({importResult.errors.length})</summary>
                      <ul>
                        {importResult.errors.map((err, i) => <li key={i}>{err}</li>)}
                      </ul>
                    </details>
                  )}
                </div>
              )}
            </section>

            {error && <p className="onboarding-error">{error}</p>}
            {success && !importResult && <p className="quizlet-success">✓ Export successful! File downloaded.</p>}

            <aside className="quizlet-import-hint">
              <p><strong>How to export from Quizlet:</strong></p>
              <ol>
                <li>Go to your Quizlet study set</li>
                <li>Click the three dots menu (⋮)</li>
                <li>Select "Download as..." → CSV</li>
                <li>Upload the CSV file here</li>
              </ol>
            </aside>
          </>
        ) : (
          <p className="onboarding-error">Failed to load status</p>
        )}
      </div>
    </section>
  );
}
