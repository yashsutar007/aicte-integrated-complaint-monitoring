import { useEffect, useState } from "react";
import {
  AlertCircle, ArrowLeftRight, Building2, CheckCircle2, ClipboardList,
  LoaderCircle, Plus, RefreshCw, ShieldCheck, Users, X,
} from "lucide-react";
import { api } from "./services/api";
import "./Assignments.css";

const emptyBureau = { name: "", code: "", description: "" };
const emptyAssignment = { complaint_id: "", bureau_id: "", assigned_to: "", note: "" };
const ADMIN_ROLES = ["ADMIN", "SUPER_ADMIN"];
const ASSIGNMENT_ROLES = ["ADMIN", "SUPER_ADMIN", "BUREAU_OFFICER"];

function humanize(value) {
  return String(value || "").replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 16).replace("T", " ");
  return date.toLocaleString(undefined, { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function errorMessage(error, fallback) {
  return error.response?.data?.message || (error.code === "ERR_NETWORK" ? "Cannot reach the Flask API. Keep the backend terminal running." : fallback);
}

export default function AssignmentsPage({ user }) {
  const role = String(user?.role || "CASE_OFFICER").toUpperCase();
  const canManageBureaus = ADMIN_ROLES.includes(role);
  const canAssignCases = ASSIGNMENT_ROLES.includes(role);
  const [bureaus, setBureaus] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [caseOptions, setCaseOptions] = useState([]);
  const [eligibleOfficers, setEligibleOfficers] = useState([]);
  const [members, setMembers] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("");
  const [bureauFilter, setBureauFilter] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [bureauFormOpen, setBureauFormOpen] = useState(false);
  const [bureauEditingId, setBureauEditingId] = useState(null);
  const [bureauForm, setBureauForm] = useState(emptyBureau);
  const [selectedManageBureau, setSelectedManageBureau] = useState(null);
  const [memberCandidate, setMemberCandidate] = useState("");
  const [assignmentFormOpen, setAssignmentFormOpen] = useState(false);
  const [assignmentForm, setAssignmentForm] = useState(emptyAssignment);
  const [membersLoading, setMembersLoading] = useState(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const requests = [
          api.get("/api/bureaus"),
          api.get("/api/assignments", { params: { page: 1, page_size: 100 } }),
        ];
        if (canManageBureaus) requests.push(api.get("/api/bureaus/eligible-officers"));
        const results = await Promise.all(requests);
        if (!active) return;
        setBureaus(results[0].data?.data?.items ?? []);
        setAssignments(results[1].data?.data?.items ?? []);
        setTotal(results[1].data?.data?.total ?? 0);
        if (canManageBureaus) setEligibleOfficers(results[2].data?.data?.items ?? []);
        setError("");
      } catch (requestError) {
        if (active) setError(errorMessage(requestError, "Could not load Bureau and assignment data."));
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [canManageBureaus]);

  async function refreshAssignments(overrides = {}) {
    setLoading(true);
    setError("");
    const params = {
      page: 1,
      page_size: 100,
      search,
      status: statusFilter,
      priority: priorityFilter,
      bureau_id: bureauFilter,
      ...overrides,
    };
    Object.keys(params).forEach((key) => { if (params[key] === "") delete params[key]; });
    try {
      const response = await api.get("/api/assignments", { params });
      setAssignments(response.data?.data?.items ?? []);
      setTotal(response.data?.data?.total ?? 0);
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not load case assignments."));
    } finally {
      setLoading(false);
    }
  }

  async function refreshBureaus() {
    try {
      const response = await api.get("/api/bureaus");
      setBureaus(response.data?.data?.items ?? []);
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not refresh Bureaus."));
    }
  }

  function startCreateBureau() {
    setBureauEditingId(null);
    setBureauForm(emptyBureau);
    setBureauFormOpen(true);
    setError("");
    setNotice("");
  }

  function startEditBureau(bureau) {
    setBureauEditingId(bureau.id);
    setBureauForm({ name: bureau.name || "", code: bureau.code || "", description: bureau.description || "" });
    setBureauFormOpen(true);
    setError("");
    setNotice("");
  }

  async function saveBureau(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const response = bureauEditingId
        ? await api.put(`/api/bureaus/${bureauEditingId}`, bureauForm)
        : await api.post("/api/bureaus", bureauForm);
      setNotice(response.data?.message || "Bureau saved.");
      setBureauFormOpen(false);
      setBureauForm(emptyBureau);
      setBureauEditingId(null);
      await refreshBureaus();
    } catch (requestError) {
      setError(errorMessage(requestError, "Unable to save Bureau or Cell."));
    } finally {
      setSaving(false);
    }
  }

  async function toggleBureau(bureau) {
    setError("");
    setNotice("");
    try {
      const response = await api.patch(`/api/bureaus/${bureau.id}/status`, { is_active: !bureau.is_active });
      setNotice(response.data?.message || "Bureau status updated.");
      await refreshBureaus();
    } catch (requestError) {
      setError(errorMessage(requestError, "Unable to update Bureau status."));
    }
  }

  async function openMembers(bureau) {
    setAssignmentFormOpen(false);
    setSelectedManageBureau(bureau);
    setMembers([]);
    setMemberCandidate("");
    setMembersLoading(true);
    setError("");
    try {
      const [memberResponse, eligibleResponse] = await Promise.all([
        api.get(`/api/bureaus/${bureau.id}/members`),
        canManageBureaus ? api.get("/api/bureaus/eligible-officers") : Promise.resolve({ data: { data: { items: [] } } }),
      ]);
      const nextMembers = memberResponse.data?.data?.items ?? [];
      const nextEligible = eligibleResponse.data?.data?.items ?? [];
      setMembers(nextMembers);
      if (canManageBureaus) setEligibleOfficers(nextEligible.filter((officer) => !nextMembers.some((member) => member.id === officer.id)));
    } catch (requestError) {
      setError(errorMessage(requestError, "Unable to load Bureau members."));
    } finally {
      setMembersLoading(false);
    }
  }

  async function addMember(event) {
    event.preventDefault();
    if (!selectedManageBureau || !memberCandidate) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const response = await api.post(`/api/bureaus/${selectedManageBureau.id}/members`, { user_id: Number(memberCandidate) });
      setNotice(response.data?.message || "Officer added to Bureau.");
      await openMembers(selectedManageBureau);
      await refreshBureaus();
    } catch (requestError) {
      setError(errorMessage(requestError, "Unable to add officer."));
    } finally {
      setSaving(false);
    }
  }

  async function removeMember(member) {
    if (!selectedManageBureau) return;
    setError("");
    setNotice("");
    try {
      const response = await api.delete(`/api/bureaus/${selectedManageBureau.id}/members/${member.id}`);
      setNotice(response.data?.message || "Officer removed from Bureau.");
      await openMembers(selectedManageBureau);
      await refreshBureaus();
    } catch (requestError) {
      setError(errorMessage(requestError, "Unable to remove officer."));
    }
  }

  async function openAssignment(item = null) {
    setSelectedManageBureau(null);
    setError("");
    setNotice("");
    setAssignmentForm({
      complaint_id: String(item?.complaint_id ?? ""),
      bureau_id: String(item?.bureau_id ?? ""),
      assigned_to: String(item?.assigned_to ?? ""),
      note: "",
    });
    setAssignmentFormOpen(true);
    try {
      const response = await api.get("/api/complaints", { params: { page: 1, page_size: 100 } });
      setCaseOptions(response.data?.data?.items ?? []);
      const bureauId = item?.bureau_id ? String(item.bureau_id) : "";
      if (bureauId) {
        const membersResponse = await api.get(`/api/bureaus/${bureauId}/members`);
        setMembers(membersResponse.data?.data?.items ?? []);
      } else {
        setMembers([]);
      }
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not load cases or Bureau members for assignment."));
    }
  }

  async function changeAssignmentBureau(value) {
    setAssignmentForm((current) => ({ ...current, bureau_id: value, assigned_to: "" }));
    if (!value) {
      setMembers([]);
      return;
    }
    try {
      const response = await api.get(`/api/bureaus/${value}/members`);
      setMembers(response.data?.data?.items ?? []);
    } catch (requestError) {
      setMembers([]);
      setError(errorMessage(requestError, "Could not load members for this Bureau."));
    }
  }

  async function submitAssignment(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setNotice("");
    const payload = {
      complaint_id: Number(assignmentForm.complaint_id),
      bureau_id: Number(assignmentForm.bureau_id),
      assigned_to: assignmentForm.assigned_to ? Number(assignmentForm.assigned_to) : null,
      note: assignmentForm.note.trim(),
    };
    try {
      const response = await api.post("/api/assignments", payload);
      setNotice(response.data?.message || "Case assigned successfully.");
      setAssignmentFormOpen(false);
      await Promise.all([refreshAssignments(), refreshBureaus()]);
    } catch (requestError) {
      setError(errorMessage(requestError, "Unable to assign case."));
    } finally {
      setSaving(false);
    }
  }

  const activeBureaus = bureaus.filter((item) => Boolean(item.is_active));
  const selectedOfficerIds = new Set(members.map((member) => Number(member.id)));
  const memberOptions = members.filter((member) => selectedOfficerIds.has(Number(member.id)) && Boolean(member.is_active));

  return <>
    <div className="page-title-row assignment-page-title">
      <div><div className="eyebrow light-eyebrow">MODULE 04</div><h1>Bureau & case assignment</h1><p>Route complaint cases to the responsible Bureau or Cell and assign an officer.</p></div>
      <div className="assignment-title-actions"><button type="button" className="secondary-button" onClick={() => { void refreshAssignments(); void refreshBureaus(); }}><RefreshCw size={15} /> Refresh</button>{canAssignCases && <button type="button" className="primary-button compact-button" onClick={() => openAssignment()}><ArrowLeftRight size={16} /> Assign case</button>}</div>
    </div>
    {error && <div className="inline-alert" role="alert"><AlertCircle size={17} />{error}</div>}
    {notice && <div className="inline-success" role="status"><CheckCircle2 size={17} />{notice}</div>}
    {!canAssignCases && <div className="assignment-permission-note"><ShieldCheck size={18} /><span>Your role can review cases visible to you. Assignment changes require a Bureau Officer or administrator.</span></div>}

    <div className="assignment-summary-grid">
      <article className="assignment-summary-card"><div><span>Bureaus / Cells</span><Building2 size={17} /></div><strong>{bureaus.length}</strong><small>Available to your role</small></article>
      <article className="assignment-summary-card"><div><span>Case records</span><ClipboardList size={17} /></div><strong>{total}</strong><small>Matching assignment filters</small></article>
      <article className="assignment-summary-card"><div><span>Unassigned cases</span><Users size={17} /></div><strong>{assignments.filter((item) => !item.assignment_id).length}</strong><small>Need Bureau routing</small></article>
    </div>

    <section className="assignment-section">
      <div className="section-heading"><div><div className="eyebrow light-eyebrow">ORGANIZATION DIRECTORY</div><h2>Bureaus & Cells</h2><p>Create the routing structure and maintain officer membership.</p></div>{canManageBureaus && <button type="button" className="primary-button compact-button" onClick={() => bureauFormOpen ? setBureauFormOpen(false) : startCreateBureau()}><Plus size={16} /> Add Bureau</button>}</div>
      {bureauFormOpen && canManageBureaus && <section className="form-card"><div className="form-card-heading"><div><h2>{bureauEditingId ? "Edit Bureau or Cell" : "Create Bureau or Cell"}</h2><p>Codes must be unique. Use a recognizable internal code.</p></div><button type="button" className="icon-button" onClick={() => setBureauFormOpen(false)} aria-label="Close Bureau form"><X size={17} /></button></div><form className="entity-form" onSubmit={saveBureau}>
        <label>Bureau / Cell name *<input required maxLength={150} value={bureauForm.name} onChange={(event) => setBureauForm((current) => ({ ...current, name: event.target.value }))} placeholder="e.g. Academic Compliance Cell" /></label>
        <label>Unique code *<input required minLength={2} maxLength={40} pattern="[A-Za-z0-9][A-Za-z0-9_-]{1,39}" value={bureauForm.code} onChange={(event) => setBureauForm((current) => ({ ...current, code: event.target.value.toUpperCase() }))} placeholder="e.g. ACADEMIC-01" /></label>
        <label className="wide-field">Description<textarea rows={3} maxLength={2000} value={bureauForm.description} onChange={(event) => setBureauForm((current) => ({ ...current, description: event.target.value }))} placeholder="Describe the Bureau's responsibilities" /></label>
        <div className="form-actions wide-field"><button type="button" className="secondary-button" onClick={() => setBureauFormOpen(false)}>Cancel</button><button type="submit" className="primary-button compact-button" disabled={saving}>{saving ? <><LoaderCircle size={15} className="spin" /> Saving…</> : bureauEditingId ? "Save changes" : "Create Bureau"}</button></div>
      </form></section>}
      {loading && bureaus.length === 0 ? <div className="loading-inline"><LoaderCircle size={20} className="spin" />Loading Bureaus…</div> : bureaus.length === 0 ? <div className="empty-state assignment-empty"><Building2 size={27} /><strong>No Bureaus or Cells available</strong><span>{canManageBureaus ? "Create the first Bureau to start routing complaint cases." : "Ask an administrator to add you to a Bureau or Cell."}</span></div> : <div className="assignment-bureau-grid">{bureaus.map((bureau) => <article className={`assignment-bureau-card ${!bureau.is_active ? "is-inactive" : ""}`} key={bureau.id}><div className="assignment-bureau-card-head"><div className="assignment-bureau-icon"><Building2 size={20} /></div><span className={`status-pill ${bureau.is_active ? "status-active" : "status-inactive"}`}>{bureau.is_active ? "Active" : "Inactive"}</span></div><div className="assignment-bureau-code">{bureau.code}</div><h3>{bureau.name}</h3><p>{bureau.description || "No description supplied."}</p><div className="assignment-bureau-metrics"><span><Users size={14} />{bureau.member_count ?? 0} officers</span><span><ClipboardList size={14} />{bureau.active_assignment_count ?? 0} current cases</span></div><div className="assignment-bureau-actions"><button type="button" className="secondary-button" onClick={() => openMembers(bureau)}><Users size={14} /> Members</button>{canManageBureaus && <><button type="button" className="secondary-button" onClick={() => startEditBureau(bureau)}>Edit</button><button type="button" className="small-action" onClick={() => toggleBureau(bureau)}>{bureau.is_active ? "Deactivate" : "Activate"}</button></>}</div></article>)}</div>}
    </section>

    {selectedManageBureau && <section className="form-card assignment-members-card"><div className="form-card-heading"><div><h2>Members · {selectedManageBureau.name}</h2><p>Only active users assigned to this Bureau are eligible for case assignment.</p></div><button type="button" className="icon-button" onClick={() => setSelectedManageBureau(null)} aria-label="Close members"><X size={17} /></button></div>
      {membersLoading ? <div className="loading-inline"><LoaderCircle size={19} className="spin" />Loading members…</div> : <>
        {canManageBureaus && <form className="assignment-member-add" onSubmit={addMember}><label>Add an officer<select value={memberCandidate} onChange={(event) => setMemberCandidate(event.target.value)} required><option value="">Select an officer</option>{eligibleOfficers.map((officer) => <option key={officer.id} value={officer.id}>{officer.full_name} · {officer.email}</option>)}</select></label><button type="submit" className="primary-button compact-button" disabled={saving || !memberCandidate}><Plus size={15} /> Add member</button></form>}
        {members.length === 0 ? <div className="empty-state"><Users size={24} /><strong>No members yet</strong><span>Use the officer selector to add active users to this Bureau.</span></div> : <div className="assignment-member-list">{members.map((member) => <div className="assignment-member-row" key={member.id}><div className="assignment-member-avatar">{member.full_name.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase()}</div><div className="assignment-member-info"><strong>{member.full_name}</strong><span>{member.email} · {humanize(member.role)}</span></div>{canManageBureaus && <button type="button" className="small-action danger-action" onClick={() => removeMember(member)}>Remove</button>}</div>)}</div>}
      </>}
    </section>}

    {assignmentFormOpen && canAssignCases && <section className="form-card assignment-case-form-card"><div className="form-card-heading"><div><h2>Assign or reassign a case</h2><p>Assignment updates the case status, writes an action-history record and notifies the selected officer.</p></div><button type="button" className="icon-button" onClick={() => setAssignmentFormOpen(false)} aria-label="Close assignment form"><X size={17} /></button></div>
      <form className="entity-form" onSubmit={submitAssignment}>
        <label>Complaint case *<select required value={assignmentForm.complaint_id} onChange={(event) => setAssignmentForm((current) => ({ ...current, complaint_id: event.target.value }))}><option value="">Select a case</option>{caseOptions.map((item) => <option key={item.id} value={item.id}>{item.case_number} · {item.title} ({humanize(item.status)})</option>)}</select></label>
        <label>Bureau / Cell *<select required value={assignmentForm.bureau_id} onChange={(event) => changeAssignmentBureau(event.target.value)}><option value="">Select a Bureau</option>{activeBureaus.map((bureau) => <option key={bureau.id} value={bureau.id}>{bureau.name} · {bureau.code}</option>)}</select></label>
        <label>Assign to officer<select value={assignmentForm.assigned_to} onChange={(event) => setAssignmentForm((current) => ({ ...current, assigned_to: event.target.value }))}><option value="">Assign to Bureau only</option>{memberOptions.map((member) => <option key={member.id} value={member.id}>{member.full_name} · {member.email}</option>)}</select></label>
        <label>Assignment note<input maxLength={1000} value={assignmentForm.note} onChange={(event) => setAssignmentForm((current) => ({ ...current, note: event.target.value }))} placeholder="Optional reason or handover note" /></label>
        {caseOptions.length === 0 && <div className="inline-alert wide-field"><AlertCircle size={16} />Create a complaint case in Module 03 before assigning work.</div>}
        <div className="form-actions wide-field"><button type="button" className="secondary-button" onClick={() => setAssignmentFormOpen(false)}>Cancel</button><button type="submit" className="primary-button compact-button" disabled={saving || caseOptions.length === 0 || activeBureaus.length === 0}>{saving ? <><LoaderCircle size={15} className="spin" /> Assigning…</> : "Save assignment"}</button></div>
      </form>
    </section>}

    <section className="table-card assignment-table-card"><div className="table-toolbar"><div><h2>Case assignment register</h2><p>{total} case{total === 1 ? "" : "s"} matching these filters</p></div><form className="case-filters assignment-filters" onSubmit={(event) => { event.preventDefault(); void refreshAssignments(); }}><span className="search-input"><ClipboardList size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search case, title, institution" /></span><select aria-label="Filter by case status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">All statuses</option>{["SUBMITTED", "UNDER_REVIEW", "ASSIGNED", "AWAITING_INFORMATION", "RESOLVED", "CLOSED", "REOPENED"].map((value) => <option key={value} value={value}>{humanize(value)}</option>)}</select><select aria-label="Filter by priority" value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value)}><option value="">All priorities</option>{["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((value) => <option key={value} value={value}>{humanize(value)}</option>)}</select><select aria-label="Filter by Bureau" value={bureauFilter} onChange={(event) => setBureauFilter(event.target.value)}><option value="">All Bureaus</option>{bureaus.map((bureau) => <option key={bureau.id} value={bureau.id}>{bureau.name}</option>)}</select><button type="submit" className="secondary-button">Filter</button></form></div>
      {loading ? <div className="loading-inline"><LoaderCircle size={20} className="spin" />Loading assignments…</div> : assignments.length === 0 ? <div className="empty-state"><ClipboardList size={28} /><strong>No cases found</strong><span>{total === 0 ? "Register a complaint in Module 03, then route it to a Bureau or Cell." : "Change your filters and try again."}</span><button type="button" className="secondary-button" onClick={() => { setSearch(""); setStatusFilter(""); setPriorityFilter(""); setBureauFilter(""); void refreshAssignments({ search: "", status: "", priority: "", bureau_id: "" }); }}>Clear filters</button></div> : <div className="table-scroll"><table className="data-table"><thead><tr><th>Case / title</th><th>Institution</th><th>Priority / status</th><th>Bureau / Cell</th><th>Assigned officer</th><th>SLA due</th><th>Action</th></tr></thead><tbody>{assignments.map((item) => <tr key={item.complaint_id}><td><strong>{item.case_number}</strong><span className="sub-cell">{item.title}</span></td><td>{item.institution_name}</td><td><span className={`priority-pill priority-${String(item.priority).toLowerCase()}`}>{item.priority}</span><span className={`assignment-case-status status-pill status-${String(item.status).toLowerCase()}`}>{humanize(item.status)}</span></td><td>{item.bureau_name || <span className="muted-value">Not assigned</span>}</td><td>{item.assigned_to_name || <span className="muted-value">Unassigned</span>}</td><td>{formatDate(item.sla_due_at)}</td><td>{canAssignCases && !["CLOSED", "RESOLVED"].includes(item.status) ? <button type="button" className="small-action" onClick={() => openAssignment(item)}>{item.assignment_id ? "Reassign" : "Assign"}</button> : <span className="muted-value">View only</span>}</td></tr>)}</tbody></table></div>}
    </section>
  </>;
}
