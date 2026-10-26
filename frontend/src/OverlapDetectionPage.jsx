// Destination: frontend/src/OverlapDetectionPage.jsx
import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle, ArrowLeftRight, BadgeCheck, Check, CircleHelp,
  FileSearch, LoaderCircle, RefreshCw, ScanSearch, ShieldAlert, X,
} from "lucide-react";
import { api } from "./services/api";
import "./OverlapDetection.css";

const REVIEW_FILTERS = [
  { value: "SUGGESTED", label: "Needs review" },
  { value: "CONFIRMED", label: "Confirmed" },
  { value: "REJECTED", label: "Rejected" },
  { value: "ALL", label: "All suggestions" },
];

function titleCase(value) {
  return String(value || "").toLowerCase().replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function ConfidenceMeter({ value }) {
  const confidence = Math.max(0, Math.min(100, Number(value) || 0));
  const level = confidence >= 75 ? "high" : confidence >= 60 ? "medium" : "low";
  return <div className={`overlap-confidence ${level}`}>
    <div className="overlap-confidence-top"><span>Similarity score</span><strong>{confidence.toFixed(1)}%</strong></div>
    <div className="overlap-meter"><span style={{ width: `${confidence}%` }} /></div>
    <small>Heuristic score, not a probability of duplication.</small>
  </div>;
}

function CaseSummary({ prefix, caseNumber, title, institution, status, priority }) {
  return <div className="overlap-case-summary">
    <span className="overlap-case-label">{prefix}</span>
    <strong>{caseNumber || "Case record"}</strong>
    <h3>{title || "Untitled complaint"}</h3>
    <p>{institution || "Institution unavailable"}</p>
    <div className="overlap-tags"><span>{titleCase(status)}</span><span className={`priority-pill priority-${String(priority || "medium").toLowerCase()}`}>{titleCase(priority)}</span></div>
  </div>;
}

export default function OverlapDetectionPage() {
  const [suggestions, setSuggestions] = useState([]);
  const [filter, setFilter] = useState("SUGGESTED");
  const [minConfidence, setMinConfidence] = useState("50");
  const [refreshKey, setRefreshKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [reviewingId, setReviewingId] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    api.get("/api/overlap/suggestions", {
      params: { review_status: filter, page: 1, page_size: 100 },
    }).then((response) => {
      if (!active) return;
      setSuggestions(response.data?.data?.items ?? []);
      setError("");
    }).catch((requestError) => {
      if (active) {
        setError(requestError.response?.data?.message || "Could not load overlap suggestions.");
        setSuggestions([]);
      }
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [filter, refreshKey]);

  const counts = useMemo(() => ({
    suggestions: suggestions.filter((item) => item.review_status === "SUGGESTED").length,
    confirmed: suggestions.filter((item) => item.review_status === "CONFIRMED").length,
    rejected: suggestions.filter((item) => item.review_status === "REJECTED").length,
  }), [suggestions]);

  async function runScan() {
    setScanning(true);
    setError("");
    setNotice("");
    try {
      const response = await api.post("/api/overlap/detect", { min_confidence: Number(minConfidence) });
      const data = response.data?.data || {};
      setNotice(`Scan complete: compared ${data.pairs_compared ?? 0} pairs; ${data.new_suggestions ?? 0} new suggestions and ${data.updated_suggestions ?? 0} refreshed suggestions. Review all matches before treating them as duplicates.`);
      setFilter("SUGGESTED");
      setRefreshKey((value) => value + 1);
    } catch (requestError) {
      setError(requestError.response?.data?.message || "Overlap scan failed. Check your API connection.");
    } finally {
      setScanning(false);
    }
  }

  async function reviewSuggestion(item, reviewStatus) {
    setReviewingId(item.id);
    setError("");
    setNotice("");
    try {
      const response = await api.patch(`/api/overlap/suggestions/${item.id}/review`, { review_status: reviewStatus });
      setNotice(response.data?.message || `Suggestion ${reviewStatus.toLowerCase()}.`);
      setRefreshKey((value) => value + 1);
    } catch (requestError) {
      setError(requestError.response?.data?.message || "Could not save the review decision.");
    } finally {
      setReviewingId(null);
    }
  }

  return <div className="overlap-page">
    <div className="page-title-row overlap-title-row">
      <div><div className="eyebrow light-eyebrow">MODULE 06 · EXPLAINABLE MATCHING</div><h1>AI-assisted overlap detection</h1><p>Find potentially related complaints using case text, category and institution signals.</p></div>
      <button type="button" className="primary-button overlap-scan-button" onClick={runScan} disabled={scanning}>
        {scanning ? <LoaderCircle size={17} className="spin" /> : <ScanSearch size={17} />}
        {scanning ? "Scanning accessible cases…" : "Run overlap scan"}
      </button>
    </div>

    <div className="overlap-explainer"><div className="overlap-explainer-icon"><ShieldAlert size={22} /></div><div><strong>Decision support, not automatic judgement</strong><p>The system ranks likely overlaps and explains the signals. An authorized user must confirm or reject each suggestion; a similarity score alone does not establish duplication or misconduct.</p></div></div>

    <div className="overlap-metrics">
      <article><span>Visible suggestions</span><strong>{suggestions.length}</strong><small>For the current review filter</small></article>
      <article><span>Needs review</span><strong>{counts.suggestions}</strong><small>Awaiting a human decision</small></article>
      <article><span>Confirmed / rejected</span><strong>{counts.confirmed} / {counts.rejected}</strong><small>Within the currently visible results</small></article>
    </div>

    {error && <div className="overlap-alert error" role="alert"><AlertCircle size={17} />{error}</div>}
    {notice && <div className="overlap-alert success" role="status"><BadgeCheck size={17} />{notice}</div>}

    <section className="overlap-list-panel">
      <div className="overlap-list-toolbar"><div><h2>Potentially related cases</h2><p>Review the evidence before accepting a match.</p></div><div className="overlap-controls"><label>Minimum score<select value={minConfidence} onChange={(event) => setMinConfidence(event.target.value)}><option value="40">40% · broad</option><option value="50">50% · balanced</option><option value="60">60% · stricter</option><option value="70">70% · high similarity</option></select></label><label>Review status<select value={filter} onChange={(event) => setFilter(event.target.value)}>{REVIEW_FILTERS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label><button type="button" className="secondary-button" onClick={() => setRefreshKey((value) => value + 1)}><RefreshCw size={15} /> Refresh</button></div></div>

      {loading ? <div className="overlap-empty"><LoaderCircle size={22} className="spin" /><span>Loading suggestions…</span></div>
        : suggestions.length === 0 ? <div className="overlap-empty"><FileSearch size={30} /><strong>No suggestions in this view</strong><span>Run an overlap scan after creating a second complaint with similar subject matter. The current dataset has one test complaint, so it cannot form a pair yet.</span><button type="button" className="primary-button compact-button" onClick={runScan} disabled={scanning}>{scanning ? "Scanning…" : "Run overlap scan"}</button></div>
          : <div className="overlap-suggestion-list">{suggestions.map((item) => <article className="overlap-suggestion-card" key={item.id}>
            <div className="overlap-suggestion-top"><div><span className={`overlap-review-pill ${String(item.review_status).toLowerCase()}`}>{titleCase(item.review_status)}</span><span className="overlap-link-id">Suggestion #{item.id}</span></div><ConfidenceMeter value={item.confidence} /></div>
            <div className="overlap-case-pair"><CaseSummary prefix="CASE A" caseNumber={item.case_number_a} title={item.title_a} institution={item.institution_a} status={item.status_a} priority={item.priority_a} /><div className="overlap-pair-icon"><ArrowLeftRight size={20} /></div><CaseSummary prefix="CASE B" caseNumber={item.case_number_b} title={item.title_b} institution={item.institution_b} status={item.status_b} priority={item.priority_b} /></div>
            <div className="overlap-evidence"><CircleHelp size={17} /><div><strong>Why this was suggested</strong><p>{item.explanation || "Combined similarity signals exceeded the selected threshold."}</p></div></div>
            {item.review_status === "SUGGESTED" && <div className="overlap-review-actions"><span>Confirm only after reviewing both records.</span><div><button type="button" className="secondary-button reject-button" onClick={() => reviewSuggestion(item, "REJECTED")} disabled={reviewingId === item.id}>{reviewingId === item.id ? <LoaderCircle size={15} className="spin" /> : <X size={15} />} Reject</button><button type="button" className="primary-button compact-button" onClick={() => reviewSuggestion(item, "CONFIRMED")} disabled={reviewingId === item.id}>{reviewingId === item.id ? <LoaderCircle size={15} className="spin" /> : <Check size={15} />} Confirm duplicate</button></div></div>}
          </article>)}</div>}
    </section>
  </div>;
}
