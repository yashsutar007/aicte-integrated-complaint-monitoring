// Destination: frontend/src/WorkflowHistoryPage.jsx
import { useEffect, useMemo, useState } from "react";
import {
  Activity, AlertCircle, ArrowRight, CheckCircle2, Clock3, FileClock,
  Filter, History, LoaderCircle, MessageSquareText, RefreshCw, Search,
  ShieldCheck, UserRound, XCircle,
} from "lucide-react";
import { api } from "./services/api";
import "./WorkflowHistory.css";

const STATUSES = ["SUBMITTED", "UNDER_REVIEW", "ASSIGNED", "AWAITING_INFORMATION", "RESOLVED", "CLOSED", "REOPENED"];
const PRIORITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const TRANSITIONS = {
  SUBMITTED: ["UNDER_REVIEW", "ASSIGNED"],
  UNDER_REVIEW: ["ASSIGNED", "AWAITING_INFORMATION", "RESOLVED"],
  ASSIGNED: ["UNDER_REVIEW", "AWAITING_INFORMATION", "RESOLVED"],
  AWAITING_INFORMATION: ["UNDER_REVIEW", "ASSIGNED"],
  RESOLVED: ["CLOSED", "REOPENED"],
  CLOSED: ["REOPENED"],
  REOPENED: ["UNDER_REVIEW", "ASSIGNED"],
};

function pretty(value) {
  return String(value || "—").replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).replace("T", " ").slice(0, 19);
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function errorMessage(error, fallback) {
  return error?.response?.data?.message || error?.message || fallback;
}

function actionLabel(action) {
  const labels = {
    CASE_CREATED: "Case registered",
    STATUS_CHANGED: "Status changed",
    CASE_ASSIGNED: "Case assigned",
    CASE_REMARK_ADDED: "Case remark added",
    CASE_REOPENED: "Case reopened",
    RELATED_CASE_LINK_SUGGESTED: "Related-case link suggested",
    RELATED_CASE_LINK_CONFIRMED: "Related-case link confirmed",
    RELATED_CASE_LINK_REJECTED: "Related-case link rejected",
    INTER_BUREAU_NOTE: "Coordination note added",
  };
  return labels[action] || pretty(action);
}

function actionIcon(action) {
  if (action === "STATUS_CHANGED") return CheckCircle2;
  if (action === "CASE_REMARK_ADDED" || action === "INTER_BUREAU_NOTE") return MessageSquareText;
  if (action === "CASE_CREATED") return FileClock;
  return Activity;
}

export default function WorkflowHistoryPage({ user, onNavigate }) {
  const [cases, setCases] = useState([]);
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [caseDetail, setCaseDetail] = useState(null);
  const [actions, setActions] = useState([]);
  const [listBusy, setListBusy] = useState(true);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [savingStatus, setSavingStatus] = useState(false);
  const [savingRemark, setSavingRemark] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [priorityFilter, setPriorityFilter] = useState("ALL");
  const [nextStatus, setNextStatus] = useState("");
  const [statusComment, setStatusComment] = useState("");
  const [remark, setRemark] = useState("");
  const [reloadCases, setReloadCases] = useState(0);
  const [reloadHistory, setReloadHistory] = useState(0);

  const role = String(user?.role || "CASE_OFFICER").toUpperCase();
  const canWrite = role !== "VIEWER";

  useEffect(() => {
    let active = true;
    api.get("/api/workflow/cases?page=1&page_size=100")
      .then((response) => {
        if (!active) return;
        const items = response.data?.data?.items || [];
        setCases(items);
        setHistoryBusy(items.length > 0);
        if (!items.length) {
          setCaseDetail(null);
          setActions([]);
        }
        setSelectedCaseId((current) => current && items.some((item) => String(item.id) === String(current))
          ? String(current) : (items[0] ? String(items[0].id) : ""));
      })
      .catch((requestError) => {
        if (active) setError(errorMessage(requestError, "Unable to load workflow cases."));
      })
      .finally(() => { if (active) setListBusy(false); });
    return () => { active = false; };
  }, [reloadCases]);

  useEffect(() => {
    if (!selectedCaseId) return undefined;
    let active = true;
    api.get(`/api/workflow/cases/${selectedCaseId}/history`)
      .then((response) => {
        if (!active) return;
        const data = response.data?.data || {};
        setCaseDetail(data.case || null);
        setActions(data.actions || []);
        setNextStatus("");
      })
      .catch((requestError) => {
        if (active) {
          setCaseDetail(null);
          setActions([]);
          setError(errorMessage(requestError, "Unable to load case history."));
        }
      })
      .finally(() => { if (active) setHistoryBusy(false); });
    return () => { active = false; };
  }, [selectedCaseId, reloadHistory]);

  const filteredCases = useMemo(() => {
    const term = search.trim().toLowerCase();
    return cases.filter((item) => {
      const matchesSearch = !term || [item.case_number, item.title, item.institution_name]
        .some((value) => String(value || "").toLowerCase().includes(term));
      const matchesStatus = statusFilter === "ALL" || item.status === statusFilter;
      const matchesPriority = priorityFilter === "ALL" || item.priority === priorityFilter;
      return matchesSearch && matchesStatus && matchesPriority;
    });
  }, [cases, search, statusFilter, priorityFilter]);

  const nextStatuses = TRANSITIONS[caseDetail?.status] || [];

  async function handleStatusChange(event) {
    event.preventDefault();
    if (!caseDetail || !nextStatus) {
      setError("Select a valid next status.");
      return;
    }
    setSavingStatus(true);
    setError("");
    setSuccess("");
    try {
      const response = await api.patch(`/api/workflow/cases/${caseDetail.id}/status`, {
        status: nextStatus,
        comment: statusComment.trim(),
      });
      setSuccess(response.data?.message || "Case status updated.");
      setHistoryBusy(true);
      setStatusComment("");
      setNextStatus("");
      setReloadCases((value) => value + 1);
      setReloadHistory((value) => value + 1);
    } catch (requestError) {
      setError(errorMessage(requestError, "Unable to update case status."));
    } finally {
      setSavingStatus(false);
    }
  }

  async function handleAddRemark(event) {
    event.preventDefault();
    if (!caseDetail || !remark.trim()) {
      setError("Enter a remark before submitting.");
      return;
    }
    setSavingRemark(true);
    setError("");
    setSuccess("");
    try {
      const response = await api.post(`/api/workflow/cases/${caseDetail.id}/remarks`, { comment: remark.trim() });
      setSuccess(response.data?.message || "Case remark added.");
      setHistoryBusy(true);
      setRemark("");
      setReloadHistory((value) => value + 1);
    } catch (requestError) {
      setError(errorMessage(requestError, "Unable to add case remark."));
    } finally {
      setSavingRemark(false);
    }
  }

  function refresh() {
    setError("");
    setSuccess("");
    setListBusy(true);
    if (selectedCaseId) setHistoryBusy(true);
    setReloadCases((value) => value + 1);
    if (selectedCaseId) setReloadHistory((value) => value + 1);
  }

  return (
    <div className="workflow-page">
      <div className="workflow-heading-row">
        <div>
          <div className="eyebrow light-eyebrow">MODULE 08 · CASE GOVERNANCE</div>
          <h1>Workflow &amp; action history</h1>
          <p>Track every decision, status change and remark attached to a complaint.</p>
        </div>
        <button type="button" className="secondary-button workflow-refresh" onClick={refresh} disabled={listBusy || historyBusy}>
          <RefreshCw size={16} className={listBusy || historyBusy ? "workflow-spin" : ""} /> Refresh history
        </button>
      </div>

      {(error || success) && <div className={`workflow-alert ${error ? "is-error" : "is-success"}`} role="status">
        {error ? <AlertCircle size={18} /> : <CheckCircle2 size={18} />}
        <span>{error || success}</span>
        <button type="button" onClick={() => { setError(""); setSuccess(""); }} aria-label="Dismiss message"><XCircle size={16} /></button>
      </div>}

      <div className="workflow-layout">
        <section className="workflow-panel workflow-case-panel">
          <div className="workflow-panel-heading">
            <div><span className="workflow-kicker">CASE REGISTER</span><h2>Choose a case</h2></div>
            <span className="workflow-count">{filteredCases.length} visible</span>
          </div>
          <label className="workflow-search"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search case, title or institution" /></label>
          <div className="workflow-filters">
            <label><Filter size={14} /><select aria-label="Filter by status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="ALL">All statuses</option>{STATUSES.map((status) => <option key={status} value={status}>{pretty(status)}</option>)}</select></label>
            <select aria-label="Filter by priority" value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value)}><option value="ALL">All priorities</option>{PRIORITIES.map((priority) => <option key={priority} value={priority}>{pretty(priority)}</option>)}</select>
          </div>
          {listBusy ? <div className="workflow-empty"><LoaderCircle className="workflow-spin" size={22} /><span>Loading cases…</span></div> : filteredCases.length === 0 ? <div className="workflow-empty"><FileClock size={25} /><strong>No cases found</strong><span>Change the filters or register a complaint first.</span>{onNavigate && <button type="button" className="secondary-button" onClick={() => onNavigate("cases")}>Open case management <ArrowRight size={15} /></button>}</div> : <div className="workflow-case-list">{filteredCases.map((item) => <button type="button" key={item.id} className={`workflow-case-item ${String(item.id) === String(selectedCaseId) ? "selected" : ""}`} onClick={() => { setHistoryBusy(true); setSelectedCaseId(String(item.id)); setError(""); setSuccess(""); }}>
            <div className="workflow-case-item-top"><span>{item.case_number}</span><span className={`workflow-priority priority-${String(item.priority).toLowerCase()}`}>{pretty(item.priority)}</span></div>
            <strong>{item.title}</strong><span className="workflow-case-institution">{item.institution_name}</span>
            <div className="workflow-case-item-bottom"><span className={`workflow-status status-${String(item.status).toLowerCase()}`}>{pretty(item.status)}</span><span>{formatDate(item.updated_at || item.created_at)}</span></div>
          </button>)}</div>}
        </section>

        <div className="workflow-detail-column">
          <section className="workflow-panel workflow-detail-panel">
            <div className="workflow-panel-heading"><div><span className="workflow-kicker">CASE OVERVIEW</span><h2>{caseDetail?.case_number || "Workflow details"}</h2></div>{caseDetail && <span className={`workflow-status status-${String(caseDetail.status).toLowerCase()}`}>{pretty(caseDetail.status)}</span>}</div>
            {historyBusy ? <div className="workflow-empty"><LoaderCircle className="workflow-spin" size={22} /><span>Loading case history…</span></div> : !caseDetail ? <div className="workflow-empty"><History size={26} /><strong>Select a case to view its history</strong><span>Every logged action will appear as a timeline entry.</span></div> : <>
              <h3 className="workflow-case-title">{caseDetail.title}</h3>
              <div className="workflow-case-facts"><div><span>Institution</span><strong>{caseDetail.institution_name}</strong></div><div><span>Priority</span><strong>{pretty(caseDetail.priority)}</strong></div><div><span>Current Bureau</span><strong>{caseDetail.bureau_name || "Not assigned"}</strong></div><div><span>SLA due</span><strong>{formatDate(caseDetail.sla_due_at)}</strong></div></div>
              <div className="workflow-description">{caseDetail.description}</div>
            </>}
          </section>

          {caseDetail && canWrite && <section className="workflow-panel workflow-update-panel">
            <div className="workflow-panel-heading"><div><span className="workflow-kicker">CONTROLLED WORKFLOW</span><h2>Update case status</h2></div><ShieldCheck size={22} /></div>
            {nextStatuses.length === 0 ? <p className="workflow-muted">No further status transitions are available from this state.</p> : <form onSubmit={handleStatusChange} className="workflow-form">
              <label>Next status<select required value={nextStatus} onChange={(event) => setNextStatus(event.target.value)}><option value="">Select allowed transition</option>{nextStatuses.map((status) => <option key={status} value={status}>{pretty(status)}</option>)}</select></label>
              <label>Reason / decision note <span className="workflow-optional">Optional</span><textarea value={statusComment} onChange={(event) => setStatusComment(event.target.value)} maxLength={2000} rows={2} placeholder="Explain why this status change is being made…" /></label>
              <button type="submit" className="primary-button compact-button" disabled={savingStatus || !nextStatus}>{savingStatus ? <><LoaderCircle size={16} className="workflow-spin" /> Saving…</> : <>Save status change <ArrowRight size={16} /></>}</button>
            </form>}
          </section>}

          {caseDetail && canWrite && <section className="workflow-panel workflow-update-panel">
            <div className="workflow-panel-heading"><div><span className="workflow-kicker">CASE NOTES</span><h2>Add a remark</h2></div><MessageSquareText size={21} /></div>
            <form onSubmit={handleAddRemark} className="workflow-form">
              <label>Internal case remark<textarea required value={remark} onChange={(event) => setRemark(event.target.value)} maxLength={2000} rows={3} placeholder="Record an observation, decision or follow-up requirement…" /></label>
              <div className="workflow-form-footer"><span>{remark.length}/2000</span><button type="submit" className="secondary-button" disabled={savingRemark || !remark.trim()}>{savingRemark ? "Saving…" : "Add remark"}</button></div>
            </form>
          </section>}

          <section className="workflow-panel workflow-timeline-panel">
            <div className="workflow-panel-heading"><div><span className="workflow-kicker">AUDITABLE TIMELINE</span><h2>Action history</h2></div><span className="workflow-count">{actions.length} events</span></div>
            {!caseDetail ? <div className="workflow-empty"><History size={25} /><span>Select a case to see its event timeline.</span></div> : actions.length === 0 ? <div className="workflow-empty"><Clock3 size={25} /><span>No actions have been recorded yet.</span></div> : <div className="workflow-timeline">{actions.map((action) => { const Icon = actionIcon(action.action_type); return <article className="workflow-event" key={action.id}><div className="workflow-event-marker"><Icon size={16} /></div><div className="workflow-event-body"><div className="workflow-event-top"><strong>{actionLabel(action.action_type)}</strong><time>{formatDate(action.created_at)}</time></div><div className="workflow-event-meta"><UserRound size={14} />{action.actor_name || `User #${action.actor_id}`}{action.from_status && action.to_status && action.from_status !== action.to_status && <><span className="workflow-event-arrow">{pretty(action.from_status)} <ArrowRight size={13} /> {pretty(action.to_status)}</span></>}</div>{action.comment && <p>{action.comment}</p>}</div></article>; })}</div>}
          </section>
        </div>
      </div>
    </div>
  );
}
