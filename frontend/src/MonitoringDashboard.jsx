// Destination: frontend/src/MonitoringDashboard.jsx
import { useEffect, useState } from "react";
import {
  Activity, AlertTriangle, ArrowDownRight, ArrowRight,
  BarChart3, BellRing, Building2, CalendarClock, CheckCircle2,
  ClipboardList, Clock3, RefreshCw, ShieldAlert, Users,
} from "lucide-react";
import { api } from "./services/api";
import "./MonitoringDashboard.css";

const STATUS_ORDER = [
  "SUBMITTED", "UNDER_REVIEW", "ASSIGNED", "AWAITING_INFORMATION",
  "REOPENED", "RESOLVED", "CLOSED",
];
const PRIORITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

function number(value) {
  return Number(value || 0).toLocaleString();
}

function readable(value) {
  return String(value || "—").replaceAll("_", " ").toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString(undefined, {
    month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

function MetricCard({ label, value, helper, icon: Icon, tone = "blue", onClick }) {
  return <button type="button" className={`monitor-metric monitor-tone-${tone}`} onClick={onClick}>
    <span className="monitor-metric-icon"><Icon size={19} /></span>
    <span className="monitor-metric-label">{label}</span>
    <strong className="monitor-metric-value">{value}</strong>
    <span className="monitor-metric-helper">{helper}</span>
  </button>;
}

function Distribution({ title, subtitle, items, order, type }) {
  const mapped = order.map((label) => ({
    label,
    count: Number(items.find((item) => item.label === label)?.count || 0),
  }));
  const max = Math.max(1, ...mapped.map((item) => item.count));

  return <section className="monitor-panel">
    <div className="monitor-panel-header"><div><h2>{title}</h2><p>{subtitle}</p></div><BarChart3 size={19} /></div>
    <div className="monitor-distribution">
      {mapped.map((item) => <div className="monitor-bar-row" key={item.label}>
        <div className="monitor-bar-label"><span>{readable(item.label)}</span><strong>{number(item.count)}</strong></div>
        <div className={`monitor-bar-track monitor-bar-${type}`}><span style={{ width: `${item.count === 0 ? 0 : Math.max(4, (item.count / max) * 100)}%` }} /></div>
      </div>)}
    </div>
  </section>;
}

export default function MonitoringDashboard({ apiStatus, onNavigate }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api.get("/api/dashboard/summary")
      .then((response) => {
        if (!active) return;
        setSummary(response.data?.data || null);
        setError("");
      })
      .catch((requestError) => {
        if (!active) return;
        setError(requestError.response?.data?.message || "Could not load monitoring data. Check the API and database connection.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [refreshKey]);

  const metrics = summary?.metrics || {};
  const statusItems = summary?.status_breakdown || [];
  const priorityItems = summary?.priority_breakdown || [];
  const bureauItems = summary?.bureau_workload || [];
  const recentCases = summary?.recent_cases || [];
  const recentActivity = summary?.recent_activity || [];

  return <main className="monitor-dashboard">
    <section className="monitor-hero">
      <div className="monitor-hero-copy">
        <div className="monitor-eyebrow"><span className="monitor-live-dot" /> MODULE 05 · LIVE MONITORING</div>
        <h1>Integrated monitoring dashboard</h1>
        <p>One operational view of institution records, complaint status, urgency, deadlines and cross-Bureau workload.</p>
        <div className="monitor-context"><span><Activity size={15} /> API {apiStatus === "online" ? "connected" : apiStatus === "offline" ? "offline" : "checking"}</span><span><ShieldAlert size={15} /> Scope: {summary?.role_scope === "GLOBAL" ? "Global oversight" : "Your assigned and created cases"}</span></div>
      </div>
      <button className="monitor-refresh" type="button" onClick={() => { setLoading(true); setRefreshKey((current) => current + 1); }} disabled={loading}>
        <RefreshCw size={16} className={loading ? "monitor-refresh-spin" : ""} /> {loading ? "Refreshing…" : "Refresh data"}
      </button>
      <div className="monitor-hero-orb monitor-hero-orb-one" /><div className="monitor-hero-orb monitor-hero-orb-two" />
    </section>

    {error && <div className="monitor-error" role="alert"><AlertTriangle size={18} /><span>{error}</span><button type="button" onClick={() => { setLoading(true); setRefreshKey((current) => current + 1); }}>Try again</button></div>}

    <div className="monitor-section-title"><div><span className="monitor-section-kicker">CURRENT POSITION</span><h2>Operational snapshot</h2></div><span className="monitor-updated">{summary?.generated_at ? `Updated ${formatDate(summary.generated_at)}` : "Live data from MySQL"}</span></div>
    <section className="monitor-metrics-grid" aria-label="Current metrics">
      <MetricCard label="Institutions" value={loading && !summary ? "—" : number(metrics.total_institutions)} helper={`${number(metrics.active_institutions)} active profiles`} icon={Building2} tone="blue" onClick={() => onNavigate("institutions")} />
      <MetricCard label="Open cases" value={loading && !summary ? "—" : number(metrics.open_cases)} helper={`${number(metrics.total_cases)} total cases tracked`} icon={ClipboardList} tone="teal" onClick={() => onNavigate("cases")} />
      <MetricCard label="Critical open" value={loading && !summary ? "—" : number(metrics.critical_open_cases)} helper="Needs prioritized review" icon={ShieldAlert} tone="red" onClick={() => onNavigate("cases")} />
      <MetricCard label="Overdue cases" value={loading && !summary ? "—" : number(metrics.overdue_cases)} helper="Open cases past SLA due time" icon={AlertTriangle} tone="amber" onClick={() => onNavigate("cases")} />
      <MetricCard label="Due in 24 hours" value={loading && !summary ? "—" : number(metrics.due_within_24h)} helper="Upcoming deadline window" icon={CalendarClock} tone="purple" onClick={() => onNavigate("cases")} />
      <MetricCard label="Resolved / closed" value={loading && !summary ? "—" : number(metrics.resolved_cases)} helper="Cases no longer active" icon={CheckCircle2} tone="green" onClick={() => onNavigate("cases")} />
    </section>

    <section className="monitor-distribution-grid">
      <Distribution title="Case status" subtitle="Where work currently sits in the workflow." items={statusItems} order={STATUS_ORDER} type="status" />
      <Distribution title="Priority distribution" subtitle="Understand the urgency mix across visible cases." items={priorityItems} order={PRIORITY_ORDER} type="priority" />
    </section>

    <section className="monitor-bottom-grid">
      <section className="monitor-panel monitor-wide-panel">
        <div className="monitor-panel-header"><div><h2>Recent complaint cases</h2><p>Latest records available in your current access scope.</p></div><button className="monitor-link-button" type="button" onClick={() => onNavigate("cases")}>View all <ArrowRight size={15} /></button></div>
        {loading && !summary ? <div className="monitor-loading"><RefreshCw size={18} className="monitor-refresh-spin" /> Loading recent cases…</div> : recentCases.length === 0 ? <div className="monitor-empty"><ClipboardList size={24} /><strong>No complaint cases in this view</strong><span>Create a test institution and complaint to populate this panel.</span><button type="button" onClick={() => onNavigate("cases")}>Open case management</button></div> : <div className="monitor-table-wrap"><table className="monitor-table"><thead><tr><th>Case / institution</th><th>Priority</th><th>Status</th><th>Bureau</th><th>SLA due</th></tr></thead><tbody>{recentCases.map((item) => <tr key={item.id}><td><strong>{item.case_number}</strong><span>{item.title}</span><small>{item.institution_name}</small></td><td><span className={`monitor-pill monitor-priority-${String(item.priority).toLowerCase()}`}>{item.priority}</span></td><td><span className={`monitor-pill monitor-status-${String(item.status).toLowerCase()}`}>{readable(item.status)}</span></td><td>{item.bureau_name || "Unassigned"}</td><td>{formatDate(item.sla_due_at)}</td></tr>)}</tbody></table></div>}
      </section>

      <section className="monitor-panel">
        <div className="monitor-panel-header"><div><h2>Bureau workload</h2><p>Open cases by active assignment.</p></div><Users size={19} /></div>
        {bureauItems.length === 0 ? <div className="monitor-empty compact"><Users size={23} /><strong>No Bureau workload</strong><span>Create a Bureau and assign a case to view workload.</span><button type="button" onClick={() => onNavigate("assignments")}>Manage assignments</button></div> : <div className="monitor-workload-list">{bureauItems.map((item) => <div className="monitor-workload-item" key={item.id}><div className="monitor-workload-top"><div><strong>{item.name}</strong><span>{item.code}</span></div><b>{number(item.active_cases)}</b></div><div className="monitor-workload-track"><span style={{ width: `${Math.max(0, Math.min(100, Number(item.active_cases || 0) / Math.max(1, ...bureauItems.map((entry) => Number(entry.active_cases || 0))) * 100))}%` }} /></div></div>)}<button className="monitor-link-button full-width" type="button" onClick={() => onNavigate("assignments")}>Open Bureau assignments <ArrowRight size={15} /></button></div>}
      </section>
    </section>

    <section className="monitor-panel monitor-activity-panel">
      <div className="monitor-panel-header"><div><h2>Latest case activity</h2><p>Recent action-history events from the database.</p></div><Clock3 size={19} /></div>
      {recentActivity.length === 0 ? <div className="monitor-empty compact"><Activity size={22} /><strong>No recent actions</strong><span>Case registration and assignment events will appear here.</span></div> : <div className="monitor-activity-list">{recentActivity.map((item) => <article className="monitor-activity-item" key={item.id}><div className="monitor-activity-mark"><Activity size={16} /></div><div className="monitor-activity-copy"><strong>{readable(item.action_type)} <span>· {item.case_number}</span></strong><p>{item.comment || (item.to_status ? `Status moved to ${readable(item.to_status)}` : "Case activity recorded.")}</p><small>{item.actor_name || "System"} · {formatDate(item.created_at)}</small></div><span className="monitor-activity-arrow"><ArrowDownRight size={17} /></span></article>)}</div>}
    </section>
    <p className="monitor-disclaimer"><BellRing size={14} /> Overdue and due-soon counts use the configured prototype SLA timestamps. These values are not represented as official AICTE deadlines.</p>
  </main>;
}
