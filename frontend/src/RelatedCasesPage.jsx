// Destination: frontend/src/RelatedCasesPage.jsx
import { useEffect, useState } from "react";
import {
  AlertCircle, ArrowUpRight, CheckCircle2, ClipboardList, LoaderCircle,
  MessageSquare, Plus, RefreshCw, Send, XCircle,
} from "lucide-react";
import { api } from "./services/api";
import "./RelatedCases.css";

const blankForm = { complaint_id: "", related_complaint_id: "", relationship: "RELATED", explanation: "" };
const writeRoles = new Set(["ADMIN", "SUPER_ADMIN", "BUREAU_OFFICER", "CASE_OFFICER"]);

function displayDate(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString();
}

function statusClass(value) {
  return `coord-status coord-status-${String(value || "suggested").toLowerCase()}`;
}

export default function RelatedCasesPage({ user }) {
  const canWrite = writeRoles.has(String(user?.role || "CASE_OFFICER").toUpperCase());
  const [cases, setCases] = useState([]);
  const [links, setLinks] = useState([]);
  const [form, setForm] = useState(blankForm);
  const [reviewStatus, setReviewStatus] = useState("ALL");
  const [relationshipFilter, setRelationshipFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [reviewingId, setReviewingId] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [activeNotesLink, setActiveNotesLink] = useState(null);
  const [notesByLink, setNotesByLink] = useState({});
  const [noteDrafts, setNoteDrafts] = useState({});
  const [notesLoadingId, setNotesLoadingId] = useState(null);
  const [noteSavingId, setNoteSavingId] = useState(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [caseResponse, linkResponse] = await Promise.all([
          api.get("/api/complaints", { params: { page: 1, page_size: 100 } }),
          api.get("/api/coordination/links", { params: { review_status: reviewStatus, relationship: relationshipFilter, search, page: 1, page_size: 100 } }),
        ]);
        if (!active) return;
        setCases(caseResponse.data?.data?.items ?? []);
        setLinks(linkResponse.data?.data?.items ?? []);
        setError("");
      } catch (requestError) {
        if (active) setError(requestError.response?.data?.message || "Could not load related cases. Check your connection and permissions.");
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => { active = false; };
  }, [reviewStatus, relationshipFilter, search, reloadKey]);

  function setFilter(setter, value) {
    setLoading(true);
    setError("");
    setter(value);
  }

  async function handleCreate(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    if (!form.complaint_id || !form.related_complaint_id) {
      setError("Select both complaint cases.");
      return;
    }
    if (form.complaint_id === form.related_complaint_id) {
      setError("Choose two different cases.");
      return;
    }
    setSaving(true);
    try {
      const response = await api.post("/api/coordination/links", {
        complaint_id: Number(form.complaint_id),
        related_complaint_id: Number(form.related_complaint_id),
        relationship: form.relationship,
        explanation: form.explanation.trim(),
      });
      setNotice(response.data?.message || "Relationship suggested for review.");
      setForm(blankForm);
      setLoading(true);
      setReloadKey((value) => value + 1);
    } catch (requestError) {
      setError(requestError.response?.data?.message || "Could not create related-case link.");
    } finally {
      setSaving(false);
    }
  }

  async function handleReview(link, decision) {
    setReviewingId(link.id);
    setError("");
    setNotice("");
    try {
      const response = await api.patch(`/api/coordination/links/${link.id}/review`, { review_status: decision });
      setNotice(response.data?.message || `Relationship ${decision.toLowerCase()}.`);
      setLoading(true);
      setReloadKey((value) => value + 1);
    } catch (requestError) {
      setError(requestError.response?.data?.message || "Could not save the review decision.");
    } finally {
      setReviewingId(null);
    }
  }

  async function toggleNotes(link) {
    if (activeNotesLink === link.id) {
      setActiveNotesLink(null);
      return;
    }
    setActiveNotesLink(link.id);
    if (notesByLink[link.id]) return;
    setNotesLoadingId(link.id);
    setError("");
    try {
      const response = await api.get(`/api/coordination/links/${link.id}/notes`);
      setNotesByLink((current) => ({ ...current, [link.id]: response.data?.data?.items ?? [] }));
    } catch (requestError) {
      setError(requestError.response?.data?.message || "Could not load coordination notes.");
    } finally {
      setNotesLoadingId(null);
    }
  }

  async function handleAddNote(event, link) {
    event.preventDefault();
    const note = String(noteDrafts[link.id] || "").trim();
    if (!note) {
      setError("Enter a coordination note before sending.");
      return;
    }
    setNoteSavingId(link.id);
    setError("");
    setNotice("");
    try {
      const response = await api.post(`/api/coordination/links/${link.id}/notes`, { note });
      setNotesByLink((current) => ({ ...current, [link.id]: [...(current[link.id] || []), response.data?.data].filter(Boolean) }));
      setNoteDrafts((current) => ({ ...current, [link.id]: "" }));
      setNotice("Coordination note added.");
    } catch (requestError) {
      setError(requestError.response?.data?.message || "Could not add coordination note.");
    } finally {
      setNoteSavingId(null);
    }
  }

  return <div className="coord-page">
    <header className="coord-hero">
      <div className="coord-hero-copy"><span className="coord-eyebrow">MODULE 07 · INTER-BUREAU WORKSPACE</span><h1>Related cases & coordination</h1><p>Connect related complaints, review case relationships, and share coordination notes with authorized teams.</p></div>
      <div className="coord-hero-mark"><MessageSquare size={28} /><span>Shared context</span></div>
    </header>

    {error && <div className="coord-alert coord-alert-error" role="alert"><AlertCircle size={18} />{error}</div>}
    {notice && <div className="coord-alert coord-alert-success" role="status"><CheckCircle2 size={18} />{notice}</div>}

    {canWrite && <section className="coord-panel coord-create-panel">
      <div className="coord-section-title"><div><span className="coord-eyebrow">CREATE A RELATIONSHIP</span><h2>Link two cases</h2><p>New links remain suggested until reviewed. Duplicate detection stays in Module 6.</p></div><div className="coord-title-icon"><Plus size={21} /></div></div>
      <form className="coord-link-form" onSubmit={handleCreate}>
        <label>Primary case<select value={form.complaint_id} onChange={(event) => setForm((current) => ({ ...current, complaint_id: event.target.value }))} required><option value="">Select a case</option>{cases.map((item) => <option key={item.id} value={item.id}>{item.case_number} · {item.title}</option>)}</select></label>
        <label>Related case<select value={form.related_complaint_id} onChange={(event) => setForm((current) => ({ ...current, related_complaint_id: event.target.value }))} required><option value="">Select another case</option>{cases.map((item) => <option key={item.id} value={item.id} disabled={String(item.id) === form.complaint_id}>{item.case_number} · {item.title}</option>)}</select></label>
        <label>Relationship type<select value={form.relationship} onChange={(event) => setForm((current) => ({ ...current, relationship: event.target.value }))}><option value="RELATED">Related cases</option><option value="FOLLOW_UP">Follow-up case</option></select></label>
        <label className="coord-explanation-field">Reason for linking<textarea value={form.explanation} onChange={(event) => setForm((current) => ({ ...current, explanation: event.target.value }))} rows={2} maxLength={1000} placeholder="Explain why these cases should be coordinated (optional)." /></label>
        <div className="coord-form-actions"><button className="coord-primary-btn" type="submit" disabled={saving}>{saving ? <LoaderCircle size={17} className="coord-spin" /> : <Plus size={17} />}Suggest relationship</button></div>
      </form>
    </section>}

    <section className="coord-panel">
      <div className="coord-section-title"><div><span className="coord-eyebrow">COORDINATION REGISTER</span><h2>Related-case links</h2><p>Review status, Bureau ownership and cross-case notes.</p></div><button className="coord-outline-btn" type="button" onClick={() => { setLoading(true); setReloadKey((value) => value + 1); }}><RefreshCw size={16} /> Refresh</button></div>
      <div className="coord-filters">
        <label>Search cases<input value={search} onChange={(event) => setFilter(setSearch, event.target.value)} placeholder="Case number or title" /></label>
        <label>Review status<select value={reviewStatus} onChange={(event) => setFilter(setReviewStatus, event.target.value)}><option value="ALL">All statuses</option><option value="SUGGESTED">Suggested</option><option value="CONFIRMED">Confirmed</option><option value="REJECTED">Rejected</option></select></label>
        <label>Relationship<select value={relationshipFilter} onChange={(event) => setFilter(setRelationshipFilter, event.target.value)}><option value="ALL">All relationships</option><option value="RELATED">Related</option><option value="FOLLOW_UP">Follow-up</option><option value="POTENTIAL_DUPLICATE">Potential duplicate</option></select></label>
      </div>
      {loading ? <div className="coord-empty"><LoaderCircle size={24} className="coord-spin" /><span>Loading case relationships…</span></div> : links.length === 0 ? <div className="coord-empty"><ClipboardList size={29} /><strong>No linked cases found</strong><span>Run overlap detection in Module 6 or suggest a relationship above.</span></div> : <div className="coord-link-list">{links.map((link) => <article className="coord-link-card" key={link.id}>
        <div className="coord-link-card-head"><div className="coord-link-kind"><span className="coord-link-icon"><ArrowUpRight size={18} /></span><div><strong>{link.relationship === "POTENTIAL_DUPLICATE" ? "Potential duplicate" : link.relationship === "FOLLOW_UP" ? "Follow-up case" : "Related cases"}</strong><span>Link #{link.id} · Created {displayDate(link.created_at)}</span></div></div><span className={statusClass(link.review_status)}>{String(link.review_status).replaceAll("_", " ")}</span></div>
        <div className="coord-case-pair"><div className="coord-case-side"><span className="coord-case-kicker">CASE A · {link.bureau_a || "Unassigned Bureau"}</span><strong>{link.case_number_a}</strong><p>{link.title_a}</p><span>{link.institution_a}</span><div className="coord-case-tags"><span>{link.priority_a}</span><span>{String(link.status_a || "").replaceAll("_", " ")}</span></div></div><div className="coord-pair-connector"><span><ArrowUpRight size={17} /></span><small>{link.relationship === "FOLLOW_UP" ? "Follows" : "Linked"}</small></div><div className="coord-case-side"><span className="coord-case-kicker">CASE B · {link.bureau_b || "Unassigned Bureau"}</span><strong>{link.case_number_b}</strong><p>{link.title_b}</p><span>{link.institution_b}</span><div className="coord-case-tags"><span>{link.priority_b}</span><span>{String(link.status_b || "").replaceAll("_", " ")}</span></div></div></div>
        {link.explanation && <div className="coord-link-reason"><strong>Reason</strong><p>{link.explanation}</p></div>}
        {link.relationship === "POTENTIAL_DUPLICATE" && <p className="coord-review-hint">Duplicate suggestions should be reviewed in Module 6: Overlap Detection.</p>}
        <div className="coord-link-actions"><button className="coord-outline-btn" type="button" onClick={() => toggleNotes(link)}><MessageSquare size={16} />{activeNotesLink === link.id ? "Hide notes" : "Coordination notes"}</button>{canWrite && link.relationship !== "POTENTIAL_DUPLICATE" && link.review_status === "SUGGESTED" && <><button className="coord-confirm-btn" type="button" disabled={reviewingId === link.id} onClick={() => handleReview(link, "CONFIRMED")}><CheckCircle2 size={16} />Confirm</button><button className="coord-reject-btn" type="button" disabled={reviewingId === link.id} onClick={() => handleReview(link, "REJECTED")}><XCircle size={16} />Reject</button></>}</div>
        {activeNotesLink === link.id && <div className="coord-notes-panel"><h3>Inter-Bureau coordination notes</h3>{notesLoadingId === link.id ? <p className="coord-muted">Loading notes…</p> : (notesByLink[link.id] || []).length === 0 ? <p className="coord-muted">No coordination notes yet.</p> : <div className="coord-note-list">{(notesByLink[link.id] || []).map((note) => <div className="coord-note" key={note.id}><div><strong>{note.author_name || "Authorized user"}</strong><time>{displayDate(note.created_at)}</time></div><p>{note.note}</p></div>)}</div>}{canWrite && <form className="coord-note-form" onSubmit={(event) => handleAddNote(event, link)}><textarea rows={2} maxLength={2000} value={noteDrafts[link.id] || ""} onChange={(event) => setNoteDrafts((current) => ({ ...current, [link.id]: event.target.value }))} placeholder="Add a coordination note for authorized teams…" /><button className="coord-primary-btn" type="submit" disabled={noteSavingId === link.id}>{noteSavingId === link.id ? <LoaderCircle size={16} className="coord-spin" /> : <Send size={16} />}Send note</button></form>}</div>}
      </article>)}</div>}
      <div className="coord-footnote">Linking records a relationship, not a finding that two complaints are identical. Confirm only after human review.</div>
    </section>
  </div>;
}
