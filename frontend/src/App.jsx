// Destination: frontend/src/App.jsx
import { useEffect, useState } from "react";
import {
  Activity, AlertCircle, ArrowRight, BarChart3, Bell, Building2, CheckCircle2,
  ChevronDown, ClipboardList, FileSearch, FileText, GitBranch, History,
  LayoutDashboard, Link2, LoaderCircle, LockKeyhole, LogOut, Mail, Plus,
  RefreshCw, Search, ShieldCheck, Users, X,
} from "lucide-react";
import { api, clearAccessToken, getAccessToken, saveAccessToken } from "./services/api";
import "./App.css";
import "./Modules.css";
import AssignmentsPage from "./AssignmentsPage";
import MonitoringDashboard from "./MonitoringDashboard";
import OverlapDetectionPage from "./OverlapDetectionPage";
import RelatedCasesPage from "./RelatedCasesPage";
import WorkflowHistoryPage from "./WorkflowHistoryPage";

const moduleRoadmap = [
  { number: "01", title: "Authentication & Role-Based Access", description: "Secure accounts and role-aware access.", icon: ShieldCheck, status: "Active", page: "overview" },
  { number: "02", title: "Institution Profiles", description: "Create, search and update institution records.", icon: Building2, status: "Active", page: "institutions" },
  { number: "03", title: "Complaint & Case Management", description: "Register cases and track status, priority and deadlines.", icon: ClipboardList, status: "Active", page: "cases" },
  { number: "04", title: "Bureau & Case Assignment", description: "Manage Bureaus, officers and assignments.", icon: Users, status: "Active", page: "assignments" },
  { number: "05", title: "Integrated Monitoring Dashboard", description: "Monitor cases, workload and pending actions.", icon: LayoutDashboard, status: "Active", page: "monitoring" },
  { number: "06", title: "AI-Assisted Overlap Detection", description: "Flag potentially related or duplicate complaints.", icon: FileSearch, status: "Active", page: "overlap" },
  { number: "07", title: "Related Cases & Coordination", description: "Link cases and coordinate between Bureaus.", icon: Link2, status: "Active", page: "coordination" },
  { number: "08", title: "Workflow & Action History", description: "Track status changes, remarks and decisions.", icon: History, status: "Active", page: "workflow" },
  { number: "09", title: "SLA Alerts & Escalation", description: "Identify approaching deadlines and overdue cases.", icon: Bell, status: "Planned", page: "planned" },
  { number: "10", title: "Smart Search & Filters", description: "Search cases by institution, status and priority.", icon: Search, status: "Planned", page: "planned" },
  { number: "11", title: "Reports & Performance Analytics", description: "Review case ageing and resolution trends.", icon: BarChart3, status: "Planned", page: "planned" },
  { number: "12", title: "Administration, Audit & Documents", description: "Manage audit history, settings and attachments.", icon: FileText, status: "Planned", page: "planned" },
];

const pageLabels = {
  overview: "Overview",
  monitoring: "Integrated Monitoring Dashboard",
  overlap: "AI-Assisted Overlap Detection",
  coordination: "Related Cases & Inter-Bureau Coordination",
  workflow: "Workflow & Action History",
  institutions: "Institutions",
  cases: "Complaint & Case Management",
  assignments: "Bureau & Case Assignment",
  planned: "Module roadmap",
};

function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const isRegister = mode === "register";

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    const cleanEmail = email.trim().toLowerCase();
    if (isRegister && !name.trim()) return setError("Enter your full name.");
    if (isRegister && password !== confirmPassword) return setError("Passwords do not match.");
    if (isRegister && password.length < 8) return setError("Use at least 8 characters for your password.");
    setBusy(true);
    try {
      const response = await api.post(isRegister ? "/api/auth/register" : "/api/auth/login", isRegister
        ? { name: name.trim(), email: cleanEmail, password }
        : { email: cleanEmail, password });
      const result = response.data?.data;
      if (!response.data?.success || !result?.user || !result?.access_token) {
        throw new Error("The server returned an unexpected authentication response.");
      }
      onAuthenticated(result);
    } catch (requestError) {
      setError(requestError.response?.data?.message || (requestError.code === "ERR_NETWORK"
        ? "Cannot connect to the API. Check that Flask is running on port 5000."
        : requestError.message) || "Unable to connect to the server.");
    } finally {
      setBusy(false);
    }
  }

  function switchMode(nextMode) {
    setMode(nextMode);
    setError("");
    setPassword("");
    setConfirmPassword("");
  }

  return (
    <main className="auth-page">
      <section className="auth-story" aria-label="Application introduction">
        <div className="brand brand-on-dark"><img className="brand-mark" src="/aikyatrace-mark.png" alt="AikyaTrace logo" /><div><div className="brand-name">AikyaTrace</div><div className="brand-subtitle">COMPLAINT CASE INTELLIGENCE</div></div></div>
        <div className="story-copy"><div className="eyebrow"><span className="eyebrow-dot" /> INTEGRATED CASE MONITORING</div><h1>Better visibility.<br /><span>Better coordination.</span></h1><p>A unified workspace for tracking institution-related complaints, coordinating case activity and helping teams identify work that needs attention.</p></div>
        <div className="story-footer"><div className="story-line" /><span>Every case connected. Every action accounted for.</span></div><div className="story-orb story-orb-one" /><div className="story-orb story-orb-two" />
      </section>
      <section className="auth-panel"><div className="auth-form-wrap">
        <div className="mobile-brand brand"><img className="brand-mark" src="/aikyatrace-mark.png" alt="AikyaTrace logo" /><div><div className="brand-name">AikyaTrace</div><div className="brand-subtitle">COMPLAINT CASE INTELLIGENCE</div></div></div>
        <div className="form-heading"><div className="form-kicker">SECURE WORKSPACE</div><h2>{isRegister ? "Create your account" : "Welcome back"}</h2><p>{isRegister ? "Register to access the complaint monitoring prototype." : "Sign in to continue to your monitoring workspace."}</p></div>
        <div className="auth-switch" role="tablist" aria-label="Authentication mode"><button className={mode === "login" ? "switch-option active" : "switch-option"} type="button" role="tab" aria-selected={mode === "login"} onClick={() => switchMode("login")}>Sign in</button><button className={mode === "register" ? "switch-option active" : "switch-option"} type="button" role="tab" aria-selected={mode === "register"} onClick={() => switchMode("register")}>Create account</button></div>
        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          {isRegister && <label className="field-label">Full name<span className="input-wrap"><Users size={17} /><input autoComplete="name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Enter your full name" maxLength={150} required /></span></label>}
          <label className="field-label">Email address<span className="input-wrap"><Mail size={17} /><input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@institution.edu" maxLength={255} required /></span></label>
          <label className="field-label">Password<span className="input-wrap"><LockKeyhole size={17} /><input type={showPassword ? "text" : "password"} autoComplete={isRegister ? "new-password" : "current-password"} value={password} onChange={(event) => setPassword(event.target.value)} placeholder={isRegister ? "At least 8 characters" : "Enter your password"} required minLength={isRegister ? 8 : undefined} /><button type="button" className="visibility-button" onClick={() => setShowPassword((current) => !current)} aria-label={showPassword ? "Hide password" : "Show password"}><Activity size={17} /></button></span></label>
          {isRegister && <label className="field-label">Confirm password<span className="input-wrap"><LockKeyhole size={17} /><input type={showPassword ? "text" : "password"} autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} placeholder="Re-enter your password" required /></span></label>}
          {error && <div className="form-alert" role="alert"><AlertCircle size={17} /><span>{error}</span></div>}
          <button className="primary-button" type="submit" disabled={busy}>{busy ? <><LoaderCircle size={18} className="spin" /> Please wait…</> : <>{isRegister ? "Create account" : "Sign in to workspace"}<ArrowRight size={18} /></>}</button>
        </form>
        <p className="auth-footnote"><LockKeyhole size={14} /> Passwords are securely hashed by the backend.</p><p className="prototype-note">SIH 2026 student prototype. Use synthetic demonstration data only.</p>
      </div></section>
    </main>
  );
}

function StatCard({ label, value, foot, icon: Icon }) {
  return <article className="summary-card"><div className="summary-label">{label}</div><div className="summary-value">{value}</div><div className="summary-foot"><Icon size={15} />{foot}</div></article>;
}

function OverviewPage({ user, apiStatus, onNavigate }) {
  const [counts, setCounts] = useState({ institutions: null, cases: null });
  const [recentCases, setRecentCases] = useState([]);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([
      api.get("/api/institutions?page=1&page_size=5"),
      api.get("/api/complaints?page=1&page_size=5"),
    ]).then(([institutionResponse, complaintResponse]) => {
      if (!active) return;
      setCounts({ institutions: institutionResponse.data?.data?.total ?? 0, cases: complaintResponse.data?.data?.total ?? 0 });
      setRecentCases(complaintResponse.data?.data?.items ?? []);
      setLoadError("");
    }).catch((error) => {
      if (active) setLoadError(error.response?.data?.message || "Could not load live summary data. Check the API and database connection.");
    });
    return () => { active = false; };
  }, []);

  return <>
    <div className="page-title-row"><div><div className="eyebrow light-eyebrow">MONITORING WORKSPACE</div><h1>Good to see you, {user?.name?.split(/\s+/)[0] || "there"}.</h1><p>Your unified workspace for institution-related complaint monitoring.</p></div><div className="prototype-badge"><span /> Connected prototype</div></div>
    <div className="welcome-banner"><div className="welcome-icon"><CheckCircle2 size={23} /></div><div className="welcome-copy"><strong>Foundation and core case modules are available</strong><p>Institution profiles and complaint records now use the Flask API and MySQL database.</p></div><div className="banner-version">PHASE 02 <span>·</span> CORE MODULES</div></div>
    {loadError && <div className="inline-alert" role="alert"><AlertCircle size={17} />{loadError}</div>}
    <div className="summary-grid">
      <StatCard label="Institutions" value={counts.institutions === null ? "…" : counts.institutions} foot="Stored institution profiles" icon={Building2} />
      <StatCard label="Complaint cases" value={counts.cases === null ? "…" : counts.cases} foot="Tracked case records" icon={ClipboardList} />
      <StatCard label="API connectivity" value={apiStatus === "online" ? "Online" : apiStatus === "offline" ? "Offline" : "Checking"} foot="Flask health endpoint" icon={Activity} />
    </div>
    <div className="quick-actions"><button className="primary-button compact-button" onClick={() => onNavigate("institutions")}><Plus size={16} /> Add institution</button><button className="secondary-button" onClick={() => onNavigate("cases")}><Plus size={16} /> Register complaint</button></div>
    <div className="section-heading"><div><div className="eyebrow light-eyebrow">RECENT ACTIVITY</div><h2>Latest complaint cases</h2><p>Recent records from the connected database.</p></div><button className="text-button" onClick={() => onNavigate("cases")}>View all cases <ArrowRight size={15} /></button></div>
    <div className="table-card">
      {recentCases.length === 0 ? <div className="empty-state"><ClipboardList size={28} /><strong>No complaint cases yet</strong><span>Create an institution first, then register your first complaint.</span><button className="secondary-button" onClick={() => onNavigate("cases")}>Open case management</button></div> : <div className="table-scroll"><table className="data-table"><thead><tr><th>Case</th><th>Institution</th><th>Priority</th><th>Status</th><th>Reported</th></tr></thead><tbody>{recentCases.map((item) => <tr key={item.id}><td><strong>{item.case_number}</strong><span className="sub-cell">{item.title}</span></td><td>{item.institution_name}</td><td><span className={`priority-pill priority-${String(item.priority).toLowerCase()}`}>{item.priority}</span></td><td><span className={`status-pill status-${String(item.status).toLowerCase()}`}>{item.status.replaceAll("_", " ")}</span></td><td>{formatDate(item.reported_at || item.created_at)}</td></tr>)}</tbody></table></div>}
    </div>
    <div className="section-heading roadmap-heading" id="modules"><div><div className="eyebrow light-eyebrow">PRODUCT ROADMAP</div><h2>12 application modules</h2><p>Core modules are connected to the API; remaining modules are planned.</p></div><div className="module-count">12 MODULES</div></div>
    <div className="module-grid">{moduleRoadmap.map((item) => { const Icon = item.icon; return <button className="module-card module-card-button" key={item.number} onClick={() => onNavigate(item.page)}><div className="module-card-top"><div className="module-icon"><Icon size={20} /></div><span className={`module-status ${item.status === "Active" ? "foundation-status" : ""}`}>{item.status}</span></div><div className="module-number">MODULE {item.number}</div><h3>{item.title}</h3><p>{item.description}</p></button>; })}</div>
  </>;
}

const emptyInstitution = { institution_code: "", name: "", institution_type: "", state: "", district: "", official_email: "", phone: "", address: "" };

function InstitutionsPage() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [form, setForm] = useState(emptyInstitution);
  const [editingId, setEditingId] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function loadInstitutions(searchValue = search) {
    setLoading(true);
    setError("");
    try {
      const response = await api.get("/api/institutions", { params: { search: searchValue, page: 1, page_size: 100 } });
      setItems(response.data?.data?.items ?? []);
      setTotal(response.data?.data?.total ?? 0);
    } catch (requestError) {
      setError(requestError.response?.data?.message || "Could not load institutions.");
    } finally {
      setLoading(false);
    }
  }

  // Fetch initial institution data asynchronously. State updates happen only
  // after the request settles, avoiding synchronous state updates in an effect.
  useEffect(() => {
    let active = true;

    api.get("/api/institutions", {
      params: { search: "", page: 1, page_size: 100 },
    })
      .then((response) => {
        if (!active) return;
        setItems(response.data?.data?.items ?? []);
        setTotal(response.data?.data?.total ?? 0);
      })
      .catch((requestError) => {
        if (active) {
          setError(requestError.response?.data?.message || "Could not load institutions.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  function startCreate() {
    setEditingId(null);
    setForm(emptyInstitution);
    setError("");
    setNotice("");
    setFormOpen(true);
  }

  function startEdit(item) {
    setEditingId(item.id);
    setForm({ institution_code: item.institution_code || "", name: item.name || "", institution_type: item.institution_type || "", state: item.state || "", district: item.district || "", official_email: item.official_email || "", phone: item.phone || "", address: item.address || "" });
    setError("");
    setNotice("");
    setFormOpen(true);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const response = editingId
        ? await api.put(`/api/institutions/${editingId}`, form)
        : await api.post("/api/institutions", form);
      setNotice(response.data?.message || (editingId ? "Institution updated." : "Institution created."));
      setFormOpen(false);
      setForm(emptyInstitution);
      setEditingId(null);
      await loadInstitutions(search);
    } catch (requestError) {
      setError(requestError.response?.data?.message || "Unable to save institution.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleStatus(item) {
    const nextStatus = item.status === "INACTIVE" ? "ACTIVE" : "INACTIVE";
    setError("");
    setNotice("");
    try {
      await api.put(`/api/institutions/${item.id}`, { status: nextStatus });
      setNotice(`${item.name} marked ${nextStatus.toLowerCase()}.`);
      await loadInstitutions(search);
    } catch (requestError) {
      setError(requestError.response?.data?.message || "Could not update institution status.");
    }
  }

  function changeField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  return <>
    <div className="page-title-row"><div><div className="eyebrow light-eyebrow">MODULE 02</div><h1>Institution profiles</h1><p>Manage the centralized institution directory used by complaint cases.</p></div><button className="primary-button compact-button" onClick={startCreate}><Plus size={16} /> Add institution</button></div>
    {error && <div className="inline-alert" role="alert"><AlertCircle size={17} />{error}</div>}{notice && <div className="inline-success" role="status"><CheckCircle2 size={17} />{notice}</div>}
    {formOpen && <section className="form-card"><div className="form-card-heading"><div><h2>{editingId ? "Update institution" : "Create institution"}</h2><p>Fields marked with * are required.</p></div><button className="icon-button" type="button" onClick={() => setFormOpen(false)} aria-label="Close form"><X size={18} /></button></div>
      <form className="entity-form" onSubmit={handleSubmit}>
        <label>Institution name *<input required maxLength={255} value={form.name} onChange={(event) => changeField("name", event.target.value)} placeholder="e.g. Example Institute of Technology" /></label>
        <label>Institution code<input maxLength={60} value={form.institution_code} onChange={(event) => changeField("institution_code", event.target.value)} placeholder="Optional unique code" /></label>
        <label>Institution type<input maxLength={100} value={form.institution_type} onChange={(event) => changeField("institution_type", event.target.value)} placeholder="Engineering, Polytechnic, etc." /></label>
        <label>State<input maxLength={100} value={form.state} onChange={(event) => changeField("state", event.target.value)} placeholder="State" /></label>
        <label>District<input maxLength={100} value={form.district} onChange={(event) => changeField("district", event.target.value)} placeholder="District" /></label>
        <label>Official email<input type="email" maxLength={255} value={form.official_email} onChange={(event) => changeField("official_email", event.target.value)} placeholder="office@example.edu" /></label>
        <label>Phone<input maxLength={25} value={form.phone} onChange={(event) => changeField("phone", event.target.value)} placeholder="Contact number" /></label>
        <label className="wide-field">Address<textarea rows={2} value={form.address} onChange={(event) => changeField("address", event.target.value)} placeholder="Postal address" /></label>
        <div className="form-actions wide-field"><button className="secondary-button" type="button" onClick={() => setFormOpen(false)}>Cancel</button><button className="primary-button compact-button" type="submit" disabled={saving}>{saving ? <><LoaderCircle size={16} className="spin" /> Saving…</> : editingId ? "Save changes" : "Create institution"}</button></div>
      </form>
    </section>}
    <section className="table-card"><div className="table-toolbar"><div><h2>Institution directory</h2><p>{total} record{total === 1 ? "" : "s"}</p></div><form className="search-form" onSubmit={(event) => { event.preventDefault(); loadInstitutions(search); }}><span className="search-input"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name, code, district…" /></span><button className="secondary-button" type="submit">Search</button><button className="icon-button" type="button" onClick={() => loadInstitutions(search)} aria-label="Refresh institutions"><RefreshCw size={16} /></button></form></div>
      {loading ? <div className="loading-inline"><LoaderCircle className="spin" size={20} />Loading institutions…</div> : items.length === 0 ? <div className="empty-state"><Building2 size={28} /><strong>No institutions found</strong><span>Add an institution to begin registering complaint cases.</span><button className="secondary-button" onClick={startCreate}><Plus size={15} /> Add institution</button></div> : <div className="table-scroll"><table className="data-table"><thead><tr><th>Institution</th><th>Location</th><th>Type</th><th>Status</th><th>Actions</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><strong>{item.name}</strong><span className="sub-cell">{item.institution_code || `ID ${item.id}`}{item.official_email ? ` · ${item.official_email}` : ""}</span></td><td>{[item.district, item.state].filter(Boolean).join(", ") || "—"}</td><td>{item.institution_type || "—"}</td><td><span className={`status-pill status-${String(item.status).toLowerCase()}`}>{item.status.replaceAll("_", " ")}</span></td><td><div className="row-actions"><button className="small-action" onClick={() => startEdit(item)}>Edit</button><button className="small-action" onClick={() => toggleStatus(item)}>{item.status === "INACTIVE" ? "Activate" : "Deactivate"}</button></div></td></tr>)}</tbody></table></div>}
    </section>
  </>;
}

const statusOptions = {
  SUBMITTED: ["UNDER_REVIEW", "ASSIGNED"],
  UNDER_REVIEW: ["ASSIGNED", "AWAITING_INFORMATION", "RESOLVED"],
  ASSIGNED: ["UNDER_REVIEW", "AWAITING_INFORMATION", "RESOLVED"],
  AWAITING_INFORMATION: ["UNDER_REVIEW", "ASSIGNED"],
  RESOLVED: ["CLOSED", "REOPENED"],
  CLOSED: ["REOPENED"],
  REOPENED: ["UNDER_REVIEW", "ASSIGNED"],
};
const emptyComplaint = { institution_id: "", title: "", description: "", category: "Academic compliance", priority: "MEDIUM" };

function ComplaintsPage() {
  const [items, setItems] = useState([]);
  const [institutions, setInstitutions] = useState([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("");
  const [form, setForm] = useState(emptyComplaint);
  const [formOpen, setFormOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function loadCases(overrides = {}) {
    setLoading(true);
    setError("");
    const params = { page: 1, page_size: 100, search, status: statusFilter, priority: priorityFilter, ...overrides };
    Object.keys(params).forEach((key) => { if (params[key] === "") delete params[key]; });
    try {
      const response = await api.get("/api/complaints", { params });
      setItems(response.data?.data?.items ?? []);
      setTotal(response.data?.data?.total ?? 0);
    } catch (requestError) {
      setError(requestError.response?.data?.message || "Could not load complaint cases.");
    } finally {
      setLoading(false);
    }
  }

  // Load initial cases and institution choices asynchronously. Keep state updates
  // inside request callbacks instead of calling state-updating helpers directly
  // in the effect body.
  useEffect(() => {
    let active = true;

    Promise.all([
      api.get("/api/complaints", {
        params: { page: 1, page_size: 100 },
      }),
      api.get("/api/institutions", {
        params: { status: "ACTIVE", page: 1, page_size: 100 },
      }),
    ])
      .then(([casesResponse, institutionsResponse]) => {
        if (!active) return;
        setItems(casesResponse.data?.data?.items ?? []);
        setTotal(casesResponse.data?.data?.total ?? 0);
        setInstitutions(institutionsResponse.data?.data?.items ?? []);
      })
      .catch((requestError) => {
        if (active) {
          setError(
            requestError.response?.data?.message ||
            "Could not load initial complaint and institution data."
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  async function handleCreate(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const response = await api.post("/api/complaints", { ...form, institution_id: Number(form.institution_id) });
      setNotice(`Complaint registered: ${response.data?.data?.complaint?.case_number || "case created"}.`);
      setForm(emptyComplaint);
      setFormOpen(false);
      setSearch("");
      setStatusFilter("");
      setPriorityFilter("");
      await loadCases({ search: "", status: "", priority: "" });
    } catch (requestError) {
      setError(requestError.response?.data?.message || "Unable to register complaint.");
    } finally {
      setSaving(false);
    }
  }

  async function changeStatus(item, nextStatus) {
    if (!nextStatus || nextStatus === item.status) return;
    setError("");
    setNotice("");
    try {
      await api.patch(`/api/complaints/${item.id}/status`, { status: nextStatus, comment: "Status updated from the monitoring dashboard." });
      setNotice(`${item.case_number} moved to ${nextStatus.replaceAll("_", " ")}.`);
      await loadCases();
    } catch (requestError) {
      setError(requestError.response?.data?.message || "Unable to update case status.");
      await loadCases();
    }
  }

  return <>
    <div className="page-title-row"><div><div className="eyebrow light-eyebrow">MODULE 03</div><h1>Complaint & case management</h1><p>Register complaints, prioritize work and record valid status transitions.</p></div><button className="primary-button compact-button" onClick={() => { setFormOpen((value) => !value); setError(""); }}><Plus size={16} /> Register complaint</button></div>
    {error && <div className="inline-alert" role="alert"><AlertCircle size={17} />{error}</div>}{notice && <div className="inline-success" role="status"><CheckCircle2 size={17} />{notice}</div>}
    {formOpen && <section className="form-card"><div className="form-card-heading"><div><h2>Register a complaint</h2><p>A case number and SLA target will be generated by the backend.</p></div><button className="icon-button" type="button" onClick={() => setFormOpen(false)} aria-label="Close form"><X size={18} /></button></div>
      {institutions.length === 0 && <div className="inline-alert"><AlertCircle size={17} />Create or activate an institution in Module 02 before registering a complaint.</div>}
      <form className="entity-form" onSubmit={handleCreate}>
        <label>Institution *<select required value={form.institution_id} onChange={(event) => setForm((current) => ({ ...current, institution_id: event.target.value }))}><option value="">Select institution</option>{institutions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label>Complaint category *<select required value={form.category} onChange={(event) => setForm((current) => ({ ...current, category: event.target.value }))}><option>Academic compliance</option><option>Infrastructure</option><option>Faculty and staffing</option><option>Student grievance</option><option>Approval and affiliation</option><option>Other</option></select></label>
        <label className="wide-field">Case title *<input required maxLength={255} value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} placeholder="Briefly describe the complaint" /></label>
        <label>Priority *<select value={form.priority} onChange={(event) => setForm((current) => ({ ...current, priority: event.target.value }))}><option value="LOW">Low</option><option value="MEDIUM">Medium</option><option value="HIGH">High</option><option value="CRITICAL">Critical</option></select></label>
        <label className="wide-field">Description *<textarea required rows={4} value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} placeholder="Add relevant details. Use synthetic demonstration data." /></label>
        <div className="form-actions wide-field"><button className="secondary-button" type="button" onClick={() => setFormOpen(false)}>Cancel</button><button className="primary-button compact-button" type="submit" disabled={saving || institutions.length === 0}>{saving ? <><LoaderCircle size={16} className="spin" /> Registering…</> : "Create case"}</button></div>
      </form>
    </section>}
    <section className="table-card"><div className="table-toolbar"><div><h2>Case register</h2><p>{total} case{total === 1 ? "" : "s"} matching these filters</p></div><form className="case-filters" onSubmit={(event) => { event.preventDefault(); loadCases(); }}><span className="search-input"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search case, title, institution" /></span><select aria-label="Filter by status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">All statuses</option>{["SUBMITTED", "UNDER_REVIEW", "ASSIGNED", "AWAITING_INFORMATION", "RESOLVED", "CLOSED", "REOPENED"].map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select><select aria-label="Filter by priority" value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value)}><option value="">All priorities</option>{["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((value) => <option key={value} value={value}>{value}</option>)}</select><button className="secondary-button" type="submit">Filter</button></form></div>
      {loading ? <div className="loading-inline"><LoaderCircle className="spin" size={20} />Loading cases…</div> : items.length === 0 ? <div className="empty-state"><ClipboardList size={28} /><strong>No cases found</strong><span>Register a complaint or change the current filters.</span><button className="secondary-button" onClick={() => { setSearch(""); setStatusFilter(""); setPriorityFilter(""); loadCases({ search: "", status: "", priority: "" }); }}>Clear filters</button></div> : <div className="table-scroll"><table className="data-table"><thead><tr><th>Case / title</th><th>Institution</th><th>Priority</th><th>Status</th><th>SLA due</th><th>Update status</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><strong>{item.case_number}</strong><span className="sub-cell">{item.title}</span></td><td>{item.institution_name}</td><td><span className={`priority-pill priority-${String(item.priority).toLowerCase()}`}>{item.priority}</span></td><td><span className={`status-pill status-${String(item.status).toLowerCase()}`}>{item.status.replaceAll("_", " ")}</span></td><td>{formatDate(item.sla_due_at)}</td><td><label className="status-select-label"><span className="sr-only">Change status for {item.case_number}</span><select value={item.status} onChange={(event) => changeStatus(item, event.target.value)}><option value={item.status}>{item.status.replaceAll("_", " ")}</option>{(statusOptions[item.status] || []).map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select><ChevronDown size={13} /></label></td></tr>)}</tbody></table></div>}
    </section>
  </>;
}

function PlannedPage({ onNavigate }) {
  const planned = moduleRoadmap.filter((item) => item.status === "Planned");
  return <>
    <div className="page-title-row"><div><div className="eyebrow light-eyebrow">IMPLEMENTATION ROADMAP</div><h1>Module roadmap</h1><p>The remaining modules will be connected to the same API and database as development continues.</p></div></div>
    <div className="roadmap-notice"><ShieldCheck size={21} /><div><strong>Core data foundation is in place</strong><p>Institution and complaint records are now stored in MySQL. Upcoming modules will build on these shared records and audit-friendly workflows.</p></div></div>
    <div className="module-grid">{planned.map((item) => { const Icon = item.icon; return <article className="module-card" key={item.number}><div className="module-card-top"><div className="module-icon"><Icon size={20} /></div><span className="module-status">Planned</span></div><div className="module-number">MODULE {item.number}</div><h3>{item.title}</h3><p>{item.description}</p></article>; })}</div>
    <div className="quick-actions"><button className="secondary-button" onClick={() => onNavigate("institutions")}>Open institutions</button><button className="primary-button compact-button" onClick={() => onNavigate("cases")}>Open case management <ArrowRight size={16} /></button></div>
  </>;
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 16).replace("T", " ");
  return date.toLocaleString(undefined, { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function Dashboard({ user, onLogout }) {
  const [apiStatus, setApiStatus] = useState("checking");
  const [activePage, setActivePage] = useState("overview");

  useEffect(() => {
    let active = true;
    api.get("/api/health").then(() => { if (active) setApiStatus("online"); }).catch(() => { if (active) setApiStatus("offline"); });
    return () => { active = false; };
  }, []);

  const initials = (user?.name || "User").trim().split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase();
  const navigate = (page) => { setActivePage(page); window.scrollTo({ top: 0, behavior: "smooth" }); };

  return <div className="app-shell">
    <aside className="sidebar"><div className="brand sidebar-brand"><img className="brand-mark" src="/aikyatrace-mark.png" alt="AikyaTrace logo" /><div><div className="brand-name">AikyaTrace</div><div className="brand-subtitle">COMPLAINT CASE INTELLIGENCE</div></div></div>
      <div className="sidebar-label">WORKSPACE</div>
      <nav className="side-nav" aria-label="Main navigation">
        <button type="button" className={`side-link ${activePage === "overview" ? "active" : ""}`} onClick={() => navigate("overview")}><LayoutDashboard size={18} />Overview{activePage === "overview" && <span className="nav-active-dot" />}</button>
        <button type="button" className={`side-link ${activePage === "monitoring" ? "active" : ""}`} onClick={() => navigate("monitoring")}><Activity size={18} />Monitoring dashboard{activePage === "monitoring" && <span className="nav-active-dot" />}</button>
        <button type="button" className={`side-link ${activePage === "overlap" ? "active" : ""}`} onClick={() => navigate("overlap")}><FileSearch size={18} />Overlap detection{activePage === "overlap" && <span className="nav-active-dot" />}</button>
        <button type="button" className={`side-link ${activePage === "coordination" ? "active" : ""}`} onClick={() => navigate("coordination")}><Link2 size={18} />Related cases{activePage === "coordination" && <span className="nav-active-dot" />}</button>
        <button type="button" className={`side-link ${activePage === "workflow" ? "active" : ""}`} onClick={() => navigate("workflow")}><History size={18} />Workflow &amp; action history{activePage === "workflow" && <span className="nav-active-dot" />}</button>
        <button type="button" className={`side-link ${activePage === "institutions" ? "active" : ""}`} onClick={() => navigate("institutions")}><Building2 size={18} />Institutions{activePage === "institutions" && <span className="nav-active-dot" />}</button>
        <button type="button" className={`side-link ${activePage === "cases" ? "active" : ""}`} onClick={() => navigate("cases")}><ClipboardList size={18} />Complaint cases{activePage === "cases" && <span className="nav-active-dot" />}</button>
        <button type="button" className={`side-link ${activePage === "assignments" ? "active" : ""}`} onClick={() => navigate("assignments")}><Users size={18} />Bureau assignments{activePage === "assignments" && <span className="nav-active-dot" />}</button>
        <button type="button" className={`side-link ${activePage === "planned" ? "active" : ""}`} onClick={() => navigate("planned")}><GitBranch size={18} />All modules{activePage === "planned" && <span className="nav-active-dot" />}</button>
      </nav>
      <div className="sidebar-bottom"><div className="sidebar-status"><span className={apiStatus === "online" ? "status-dot online" : apiStatus === "offline" ? "status-dot offline" : "status-dot"} /><div><strong>API service</strong><small>{apiStatus === "online" ? "Connected" : apiStatus === "offline" ? "Unavailable" : "Checking connection…"}</small></div></div><button className="logout-button" type="button" onClick={onLogout}><LogOut size={17} />Sign out</button></div>
    </aside>
    <main className="dashboard-main"><header className="topbar"><div className="breadcrumb">Workspace <span>/</span> {pageLabels[activePage]}</div><div className="topbar-user"><div className="avatar">{initials}</div><div className="user-meta"><strong>{user?.name || "User"}</strong><span>{(user?.role || "CASE_OFFICER").replaceAll("_", " ")}</span></div><button type="button" className="top-logout" onClick={onLogout} aria-label="Sign out"><LogOut size={17} /></button></div></header>
      <section className="page-content">
        {activePage === "overview" && <OverviewPage user={user} apiStatus={apiStatus} onNavigate={navigate} />}
        {activePage === "monitoring" && <MonitoringDashboard apiStatus={apiStatus} onNavigate={navigate} />}
        {activePage === "overlap" && <OverlapDetectionPage />}
        {activePage === "coordination" && <RelatedCasesPage user={user} />}
        {activePage === "workflow" && <WorkflowHistoryPage user={user} onNavigate={navigate} />}
        {activePage === "institutions" && <InstitutionsPage />}
        {activePage === "cases" && <ComplaintsPage />}
        {activePage === "assignments" && <AssignmentsPage user={user} />}
        {activePage === "planned" && <PlannedPage onNavigate={navigate} />}
        <footer className="page-footer"><span>AikyaTrace · SIH 2026 student prototype</span><span>Prototype · Use synthetic demonstration data</span></footer>
      </section>
    </main>
  </div>;
}

export default function App() {
  const [user, setUser] = useState(null);
  const [checkingSession, setCheckingSession] = useState(() => Boolean(getAccessToken()));

  useEffect(() => {
    const token = getAccessToken();
    if (!token) return undefined;
    let active = true;
    api.get("/api/auth/me").then((response) => {
      if (active) setUser(response.data?.data?.user || null);
    }).catch(() => {
      clearAccessToken();
      if (active) setUser(null);
    }).finally(() => {
      if (active) setCheckingSession(false);
    });
    return () => { active = false; };
  }, []);

  function handleAuthenticated(result) {
    saveAccessToken(result.access_token);
    setUser(result.user);
  }

  function handleLogout() {
    clearAccessToken();
    setUser(null);
  }

  if (checkingSession) return <div className="loading-screen"><LoaderCircle size={28} className="spin" /><p>Restoring secure session…</p></div>;
  return user ? <Dashboard user={user} onLogout={handleLogout} /> : <AuthScreen onAuthenticated={handleAuthenticated} />;
}
