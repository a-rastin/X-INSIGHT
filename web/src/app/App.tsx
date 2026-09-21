import { useCallback, useEffect, useRef, useState } from "react";
import "../shared/theme.css";
import {
  RESEARCH_NOTICE,
  changeOwnPassword,
  createPhysician,
  createPatient,
  discardEncounter,
  fetchSession,
  getEncounter,
  listEncounters,
  listPhysicians,
  login,
  logout,
  listPatients,
  patchEncounter,
  updateTheme,
  type Encounter,
  type Patient,
  type PhysicianAccount,
  type SessionUser,
  type ThemeName,
} from "./api";

type Route = "/" | "/register" | "/physicians";

/** S09 diagnosis preview (mirrors backend evaluate_diagnosis, no I/O). */
type DiagAnswers = {
  active_phase_domains: string[];
  shared_one_month_active_phase: boolean | null;
  active_phase_abbreviated_by_intervention: boolean | null;
  functional_decline: boolean | null;
  continuous_months: number | null;
  active_phase_included: boolean | null;
  concurrent_mood_episode_with_psychosis: boolean | null;
  mood_episodes_minority_of_course: boolean | null;
  substance_or_medical_cause: boolean | null;
  autism_or_childhood_communication_history: boolean | null;
};

const DIAG_DEFAULTS: DiagAnswers = {
  active_phase_domains: [],
  shared_one_month_active_phase: false,
  active_phase_abbreviated_by_intervention: false,
  functional_decline: false,
  continuous_months: null,
  active_phase_included: false,
  concurrent_mood_episode_with_psychosis: false,
  mood_episodes_minority_of_course: false,
  substance_or_medical_cause: false,
  autism_or_childhood_communication_history: false,
};

const DIAG_DOMAINS = [
  "delusions",
  "hallucinations",
  "disorganized_speech",
  "disorganized_behavior",
  "negative_symptoms",
] as const;

const DIAG_CORE = new Set(["delusions", "hallucinations", "disorganized_speech"]);

function previewDiagnosis(answers: DiagAnswers): {
  status: "partial" | "complete";
  threshold_met: boolean;
  missing: string[];
  criteria: Record<string, boolean>;
} {
  const missing: string[] = [];
  if (answers.shared_one_month_active_phase === null || answers.shared_one_month_active_phase === undefined) {
    missing.push("shared_one_month_active_phase");
  }
  if (
    answers.active_phase_abbreviated_by_intervention === null ||
    answers.active_phase_abbreviated_by_intervention === undefined
  ) {
    missing.push("active_phase_abbreviated_by_intervention");
  }
  if (answers.functional_decline === null || answers.functional_decline === undefined) {
    missing.push("functional_decline");
  }
  if (answers.continuous_months === null || answers.continuous_months === undefined) {
    missing.push("continuous_months");
  }
  if (answers.active_phase_included === null || answers.active_phase_included === undefined) {
    missing.push("active_phase_included");
  }
  if (
    answers.concurrent_mood_episode_with_psychosis === null ||
    answers.concurrent_mood_episode_with_psychosis === undefined
  ) {
    missing.push("concurrent_mood_episode_with_psychosis");
  }
  if (
    answers.mood_episodes_minority_of_course === null ||
    answers.mood_episodes_minority_of_course === undefined
  ) {
    missing.push("mood_episodes_minority_of_course");
  }
  if (answers.substance_or_medical_cause === null || answers.substance_or_medical_cause === undefined) {
    missing.push("substance_or_medical_cause");
  }
  if (
    answers.autism_or_childhood_communication_history === null ||
    answers.autism_or_childhood_communication_history === undefined
  ) {
    missing.push("autism_or_childhood_communication_history");
  }
  if (answers.active_phase_domains === null || answers.active_phase_domains === undefined) {
    missing.push("active_phase_domains");
  }
  const months = answers.continuous_months;
  if (
    missing.length === 0 &&
    (typeof months !== "number" || !Number.isInteger(months) || months < 0)
  ) {
    missing.push("continuous_months");
  }
  if (missing.length > 0) {
    return {
      status: "partial",
      threshold_met: false,
      missing,
      criteria: { A: false, B: false, C: false, D: false, E: false, F: false },
    };
  }
  const distinct = new Set(answers.active_phase_domains);
  const shared = answers.shared_one_month_active_phase === true;
  const abbreviated = answers.active_phase_abbreviated_by_intervention === true;
  const critA =
    distinct.size >= 2 &&
    (shared || abbreviated) &&
    [...distinct].some((d) => DIAG_CORE.has(d));
  const critB = answers.functional_decline === true;
  const critC = (months as number) >= 6 && answers.active_phase_included === true;
  const critD =
    answers.concurrent_mood_episode_with_psychosis !== true ||
    answers.mood_episodes_minority_of_course === true;
  const critE = answers.substance_or_medical_cause !== true;
  const critF =
    answers.autism_or_childhood_communication_history !== true ||
    distinct.has("delusions") ||
    distinct.has("hallucinations");
  const criteria = { A: critA, B: critB, C: critC, D: critD, E: critE, F: critF };
  return {
    status: "complete",
    threshold_met: Object.values(criteria).every(Boolean),
    missing: [],
    criteria,
  };
}

function diagAnswersFromStored(stored: unknown): DiagAnswers {
  const base = { ...DIAG_DEFAULTS, active_phase_domains: [...DIAG_DEFAULTS.active_phase_domains] };
  if (typeof stored !== "object" || stored === null) {
    return base;
  }
  const raw = stored as Record<string, unknown>;
  if (Array.isArray(raw.active_phase_domains)) {
    base.active_phase_domains = (raw.active_phase_domains as unknown[]).filter(
      (d): d is string => typeof d === "string" && (DIAG_DOMAINS as readonly string[]).includes(d),
    );
  }
  const boolKeys: (keyof DiagAnswers)[] = [
    "shared_one_month_active_phase",
    "active_phase_abbreviated_by_intervention",
    "functional_decline",
    "active_phase_included",
    "concurrent_mood_episode_with_psychosis",
    "mood_episodes_minority_of_course",
    "substance_or_medical_cause",
    "autism_or_childhood_communication_history",
  ];
  for (const key of boolKeys) {
    const value = raw[key];
    if (value === true || value === false) {
      (base[key] as boolean | null) = value;
    } else if (value === null || value === undefined) {
      // Checkbox UI defaults unchecked to false; keep stored null as false
      // so empty drafts stay answerable without tri-state widgets.
      (base[key] as boolean | null) = false;
    }
  }
  const months = raw.continuous_months;
  if (typeof months === "number" && Number.isInteger(months) && months >= 0) {
    base.continuous_months = months;
  } else {
    base.continuous_months = null;
  }
  return base;
}

/**
 * S09 diagnosis gate reusing the S07 autosave path (revisionRef/timer/saveState
 * live in DraftEditor; this section only edits answers + requests ack/bypass).
 */
function DiagnosisSection({
  encounterId,
  answers,
  ackStamp,
  bypassStamp,
  ackChecked,
  readOnly,
  onDomainsChange,
  onBoolChange,
  onMonthsChange,
  onAckChange,
  onBypass,
  onComplete,
}: {
  encounterId: string;
  answers: DiagAnswers;
  ackStamp: Record<string, unknown> | null;
  bypassStamp: Record<string, unknown> | null;
  ackChecked: boolean;
  readOnly: boolean;
  onDomainsChange: (domains: string[]) => void;
  onBoolChange: (key: keyof DiagAnswers, value: boolean) => void;
  onMonthsChange: (value: number | null) => void;
  onAckChange: (checked: boolean) => void;
  onBypass: () => void;
  onComplete: () => void;
}) {
  const preview = previewDiagnosis(answers);
  const isBypassed =
    bypassStamp !== null && bypassStamp.status === "bypassed";
  const isComplete = preview.status === "complete";
  const isMet = isComplete && preview.threshold_met;
  const isBelow = isComplete && !preview.threshold_met;
  const showWarning = isBelow && !isBypassed;
  const continueDisabled = readOnly || (!isBypassed && !isMet && !ackChecked);
  const completeDisabled = readOnly || !isComplete;

  function toggleDomain(domain: string, checked: boolean): void {
    const current = new Set(answers.active_phase_domains);
    if (checked) {
      current.add(domain);
    } else {
      current.delete(domain);
    }
    onDomainsChange([...current]);
  }

  const boolFields: { key: keyof DiagAnswers; label: string }[] = [
    { key: "shared_one_month_active_phase", label: "Shared one month active phase" },
    { key: "active_phase_abbreviated_by_intervention", label: "Active phase abbreviated by intervention" },
    { key: "functional_decline", label: "Functional decline" },
    { key: "active_phase_included", label: "Active phase included" },
    { key: "concurrent_mood_episode_with_psychosis", label: "Concurrent mood episode with psychosis" },
    { key: "mood_episodes_minority_of_course", label: "Mood episodes minority of course" },
    { key: "substance_or_medical_cause", label: "Substance or medical cause" },
    { key: "autism_or_childhood_communication_history", label: "Autism or childhood communication history" },
  ];

  return (
    <section aria-labelledby="diagnosis-heading">
      <h3 id="diagnosis-heading">Diagnosis</h3>
      <p>
        partial answers need all fields. A below threshold result needs
        acknowledgement before Continue.
      </p>
      <fieldset>
        <legend>Active phase domains</legend>
        {DIAG_DOMAINS.map((domain) => (
          <div className="x-field" key={domain}>
            <label htmlFor={`diag-domain-${encounterId}-${domain}`}>
              <input
                id={`diag-domain-${encounterId}-${domain}`}
                type="checkbox"
                checked={answers.active_phase_domains.includes(domain)}
                disabled={readOnly}
                onChange={(event) => toggleDomain(domain, event.target.checked)}
              />{" "}
              {domain}
            </label>
          </div>
        ))}
      </fieldset>
      {boolFields.map((field) => (
        <div className="x-field" key={field.key}>
          <label htmlFor={`diag-${encounterId}-${field.key}`}>
            <input
              id={`diag-${encounterId}-${field.key}`}
              type="checkbox"
              checked={answers[field.key] === true}
              disabled={readOnly}
              onChange={(event) => onBoolChange(field.key, event.target.checked)}
            />{" "}
            {field.label}
          </label>
        </div>
      ))}
      <div className="x-field">
        <label htmlFor={`diag-${encounterId}-continuous_months`}>Continuous months</label>
        <input
          id={`diag-${encounterId}-continuous_months`}
          type="number"
          min={0}
          step={1}
          disabled={readOnly}
          value={answers.continuous_months === null ? "" : String(answers.continuous_months)}
          onChange={(event) => {
            const raw = event.target.value;
            if (raw === "") {
              onMonthsChange(null);
              return;
            }
            const parsed = Number.parseInt(raw, 10);
            onMonthsChange(Number.isNaN(parsed) ? null : parsed);
          }}
        />
      </div>
      {isBypassed ? (
        <p>
          Bypassed by {String(bypassStamp?.actor_id ?? "unknown")} at{" "}
          {String(bypassStamp?.bypassed_at ?? "unknown")} (rev{" "}
          {String(bypassStamp?.assessed_revision ?? "unknown")}).
        </p>
      ) : preview.status === "partial" ? (
        <p>partial — answer all fields</p>
      ) : isMet ? (
        <p>Threshold met</p>
      ) : (
        <p>below threshold</p>
      )}
      <p>
        Criteria A: {preview.criteria.A ? "met" : "not met"}; B:{" "}
        {preview.criteria.B ? "met" : "not met"}; C:{" "}
        {preview.criteria.C ? "met" : "not met"}; D:{" "}
        {preview.criteria.D ? "met" : "not met"}; E:{" "}
        {preview.criteria.E ? "met" : "not met"}; F:{" "}
        {preview.criteria.F ? "met" : "not met"}.
      </p>
      {showWarning ? (
        <p role="alert" className="x-error">
          Warning: below threshold. Acknowledgement is required before Continue.
        </p>
      ) : null}
      {ackStamp !== null && !isBypassed ? (
        <p>
          Acknowledged by {String(ackStamp.actor_id ?? "unknown")} at{" "}
          {String(ackStamp.acknowledged_at ?? "unknown")} (rev{" "}
          {String(ackStamp.assessed_revision ?? "unknown")}).
        </p>
      ) : null}
      <div className="x-field">
        <label htmlFor={`diag-${encounterId}-ack`}>
          <input
            id={`diag-${encounterId}-ack`}
            type="checkbox"
            checked={ackChecked}
            disabled={readOnly}
            onChange={(event) => onAckChange(event.target.checked)}
          />{" "}
          Acknowledge warning
        </label>
      </div>
      <button
        type="button"
        className="x-button"
        disabled={completeDisabled}
        onClick={onComplete}
      >
        Complete
      </button>{" "}
      <button
        type="button"
        className="x-button"
        disabled={continueDisabled}
        onClick={() => undefined}
      >
        Continue
      </button>{" "}
      <button
        type="button"
        className="x-button"
        disabled={readOnly || isBypassed}
        onClick={onBypass}
      >
        Bypass diagnosis
      </button>
    </section>
  );
}

function currentRoute(): Route {
  if (window.location.pathname === "/register") {
    return "/register";
  }
  if (window.location.pathname === "/physicians") {
    return "/physicians";
  }
  return "/";
}

function navigate(route: Route): void {
  window.history.pushState(null, "", route);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function App() {
  const [route, setRoute] = useState<Route>(currentRoute);
  const [user, setUser] = useState<SessionUser | null>(null);
  const [theme, setTheme] = useState<ThemeName>("light");
  const [notice, setNotice] = useState<string | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  useEffect(() => {
    const onPop = () => setRoute(currentRoute());
    window.addEventListener("popstate", onPop);
    fetchSession()
      .then((session) => {
        setUser(session);
        if (session && (session.theme === "light" || session.theme === "dark")) {
          setTheme(session.theme);
        }
      })
      .catch(() => setUser(null))
      .finally(() => setChecking(false));
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const handleLoggedIn = useCallback(
    (next: SessionUser, researchNotice: string | null) => {
      setUser(next);
      if (next.theme === "light" || next.theme === "dark") {
        setTheme(next.theme);
      }
      // Every physician login shows the exact research warning first.
      setNotice(next.role === "physician" ? (researchNotice ?? RESEARCH_NOTICE) : null);
      navigate("/");
    },
    [],
  );

  const handleSignedOut = useCallback(() => {
    setUser(null);
    setNotice(null);
    navigate("/");
  }, []);

  if (checking) {
    return (
      <main className="x-shell">
        <p>Loading…</p>
      </main>
    );
  }

  // The research warning gates the physician dashboard until acknowledged.
  if (user?.role === "physician" && notice !== null) {
    return (
      <main className="x-shell">
        <h1>X-INSIGHT</h1>
        <p>{notice}</p>
        <button type="button" className="x-button" onClick={() => setNotice(null)}>
          Continue
        </button>
      </main>
    );
  }

  return (
    <main className="x-shell">
      <nav className="x-nav" aria-label="Primary">
        <strong>X-INSIGHT</strong>
        <NavLink route="/" current={route}>
          Home
        </NavLink>
        {user?.role === "admin" ? (
          <NavLink route="/physicians" current={route}>
            Physicians
          </NavLink>
        ) : null}
        {!user ? (
          <NavLink route="/register" current={route}>
            Register
          </NavLink>
        ) : null}
        {user ? (
          <>
            <span>
              Signed in as {user.username} ({user.role}).
            </span>
            <ThemeToggle theme={theme} onChanged={setTheme} />
            <SignOutButton onSignedOut={handleSignedOut} />
          </>
        ) : null}
      </nav>
      {route === "/register" && !user ? (
        <Register />
      ) : route === "/physicians" ? (
        <PhysiciansGate user={user} />
      ) : user ? (
        <Dashboard user={user} />
      ) : (
        <LoginForm onLoggedIn={handleLoggedIn} />
      )}
    </main>
  );
}

function NavLink({
  route,
  current,
  children,
}: {
  route: Route;
  current: Route;
  children: React.ReactNode;
}) {
  return (
    <a
      href={route}
      aria-current={current === route ? "page" : undefined}
      onClick={(event) => {
        event.preventDefault();
        navigate(route);
      }}
    >
      {children}
    </a>
  );
}

function Register() {
  return (
    <>
      <h1>Register</h1>
      <p>Contact administrator</p>
    </>
  );
}

function Dashboard({ user }: { user: SessionUser }) {
  return (
    <>
      <h1>{user.role === "admin" ? "Admin dashboard" : "Physician dashboard"}</h1>
      <p>Signed in as {user.username}.</p>
      <PatientsSection role={user.role} userId={user.id} />
      <PasswordForm />
    </>
  );
}

const PATIENT_NAME_RE = /^\p{L}+$/u;
const PATIENT_ID_RE = /^[0-9]{10}$/;

function PatientsSection({ role, userId }: { role: string; userId: string }) {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [items, setItems] = useState<Patient[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Restart recovery: remember the open draft across reload/restart.
  const [openPatient, setOpenPatient] = useState<Patient | null>(() => {
    try {
      const raw = localStorage.getItem("xinsight.openPatient");
      return raw ? (JSON.parse(raw) as Patient) : null;
    } catch {
      return null;
    }
  });

  function openDraft(item: Patient): void {
    // Warn when switching drafts with pending local edits.
    if (
      (window as unknown as { __xinsight_dirty?: boolean }).__xinsight_dirty &&
      !window.confirm("You have unsaved edits. Leave without saving?")
    ) {
      return;
    }
    setOpenPatient(item);
    try {
      localStorage.setItem("xinsight.openPatient", JSON.stringify(item));
    } catch {
      /* storage unavailable; editor still opens for this session */
    }
  }

  function closeDraft(): void {
    setOpenPatient(null);
    try {
      localStorage.removeItem("xinsight.openPatient");
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      listPatients({
        q: q || undefined,
        clinical_status: status || undefined,
      })
        .then((payload) => {
          if (!cancelled) {
            setItems(payload.items);
            setError(null);
          }
        })
        .catch((failure: unknown) => {
          if (!cancelled) {
            setError(
              failure instanceof Error ? failure.message : "Could not load patients.",
            );
          }
        });
    }, 150);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [q, status, refresh]);

  return (
    <section aria-labelledby="patients-heading">
      <h2 id="patients-heading">Patients</h2>
      {role === "physician" ? (
        <PatientForm
          onCreated={() => {
            setQ("");
            setStatus("");
            setRefresh((n) => n + 1);
          }}
        />
      ) : null}
      <div className="x-field">
        <label htmlFor="patient-search">Search patients</label>
        <input
          id="patient-search"
          name="patient-search"
          autoComplete="off"
          value={q}
          onChange={(event) => setQ(event.target.value)}
        />
      </div>
      <div className="x-field">
        <label htmlFor="patient-status-filter">Filter by clinical status</label>
        <select
          id="patient-status-filter"
          value={status}
          onChange={(event) => setStatus(event.target.value)}
        >
          <option value="">All</option>
          <option value="first_time">first_time</option>
          <option value="established">established</option>
        </select>
      </div>
      {error ? (
        <p role="alert" className="x-error">
          {error}
        </p>
      ) : items === null ? (
        <p>Loading…</p>
      ) : items.length === 0 ? (
        <p>No patients found.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Patient ID</th>
              <th scope="col">First name</th>
              <th scope="col">Last name</th>
              <th scope="col">Draft</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{item.patient_id}</td>
                <td>{item.first_name}</td>
                <td>{item.last_name}</td>
                <td>
                  <button
                    type="button"
                    className="x-button"
                    onClick={() => openDraft(item)}
                  >
                    Open draft {item.patient_id}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {openPatient ? (
        <DraftEditor
          patient={openPatient}
          userId={userId}
          onClose={closeDraft}
        />
      ) : null}
    </section>
  );
}

/**
 * Single autosave path for all draft pages (S07 handoff).
 * Revision ownership: the encounter revision is the only write precondition
 * (If-Match); every assessment page must reuse getEncounter/patchEncounter,
 * never a separate persistence mechanism.
 */
function DraftEditor({
  patient,
  userId,
  onClose,
}: {
  patient: Patient;
  userId: string;
  onClose: () => void;
}) {
  const [encounter, setEncounter] = useState<Encounter | null>(null);
  const [note, setNote] = useState("");
  const [saveState, setSaveState] = useState("Loading…");
  const [serverNote, setServerNote] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [diagAnswers, setDiagAnswers] = useState<DiagAnswers>(DIAG_DEFAULTS);
  const [diagAck, setDiagAck] = useState<Record<string, unknown> | null>(null);
  const [diagBypass, setDiagBypass] = useState<Record<string, unknown> | null>(null);
  const [ackChecked, setAckChecked] = useState(false);
  const revisionRef = useRef(0);
  const savedNoteRef = useRef("");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const noteRef = useRef("");
  const staleRef = useRef(false);
  const diagAnswersRef = useRef<DiagAnswers>(DIAG_DEFAULTS);
  const savedDiagRef = useRef(JSON.stringify(DIAG_DEFAULTS));
  const ackCheckedRef = useRef(false);

  function isDiagDirty(): boolean {
    return JSON.stringify(diagAnswersRef.current) !== savedDiagRef.current;
  }

  async function reloadPreservingEdits(): Promise<void> {
    if (!encounter) {
      return;
    }
    try {
      const fresh = await getEncounter(encounter.id);
      const freshNote =
        typeof fresh.draft_data?.note === "string"
          ? (fresh.draft_data.note as string)
          : "";
      // Preserve unsaved edits; only refresh the server preview.
      setServerNote(freshNote);
      setSaveState("Stale revision");
    } catch {
      setSaveState("Stale revision");
    }
  }

  useEffect(() => {
    let cancelled = false;
    setSaveState("Loading…");
    setLoadError(null);
    listEncounters(patient.id)
      .then((all) => {
        const resumable = all.find((e) => e.state === "draft") ?? all[0];
        if (!resumable) {
          throw new Error("No resumable draft.");
        }
        return getEncounter(resumable.id);
      })
      .then((full) => {
        if (cancelled) {
          return;
        }
        setEncounter(full);
        revisionRef.current = full.revision;
        const initial =
          typeof full.draft_data?.note === "string"
            ? (full.draft_data.note as string)
            : "";
        setNote(initial);
        noteRef.current = initial;
        savedNoteRef.current = initial;
        const storedDiag =
          typeof full.draft_data?.diagnosis === "object" && full.draft_data?.diagnosis !== null
            ? (full.draft_data.diagnosis as Record<string, unknown>)
            : null;
        const initialDiag = diagAnswersFromStored(
          storedDiag !== null ? storedDiag.answers : null,
        );
        setDiagAnswers(initialDiag);
        diagAnswersRef.current = initialDiag;
        savedDiagRef.current = JSON.stringify(initialDiag);
        const storedAck =
          storedDiag !== null && typeof storedDiag.warning_ack === "object" && storedDiag.warning_ack !== null
            ? (storedDiag.warning_ack as Record<string, unknown>)
            : null;
        const storedBypass =
          storedDiag !== null && typeof storedDiag.bypass === "object" && storedDiag.bypass !== null
            ? (storedDiag.bypass as Record<string, unknown>)
            : null;
        setDiagAck(storedAck);
        setDiagBypass(storedBypass);
        const stampedAck =
          storedAck !== null && typeof storedAck.actor_id === "string";
        setAckChecked(stampedAck);
        ackCheckedRef.current = stampedAck;
        staleRef.current = false;
        setServerNote(null);
        setSaveState("Saved");
      })
      .catch((failure: unknown) => {
        if (!cancelled) {
          setLoadError(
            failure instanceof Error ? failure.message : "Could not load the draft.",
          );
          setSaveState("Save failed");
        }
      });
    return () => {
      cancelled = true;
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patient.id]);

  // Page-transition flush: attempt a final save when leaving.
  useEffect(() => {
    function onBeforeUnload(event: BeforeUnloadEvent): void {
      if (
        (noteRef.current !== savedNoteRef.current || isDiagDirty()) &&
        encounter !== null
      ) {
        event.preventDefault();
      }
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [encounter]);

  // Shared dirty flag so in-app navigation (open another draft) can warn.
  useEffect(() => {
    (window as unknown as { __xinsight_dirty?: boolean }).__xinsight_dirty =
      (noteRef.current !== savedNoteRef.current || isDiagDirty()) &&
      encounter !== null;
  });

  function handleClose(): void {
    if (
      (noteRef.current !== savedNoteRef.current || isDiagDirty()) &&
      encounter !== null
    ) {
      // Warn while local edits remain; dismiss keeps the editor + edits.
      if (!window.confirm("You have unsaved edits. Leave without saving?")) {
        return;
      }
    }
    onClose();
  }

  type DiagExtra = { warning_ack?: { confirm: true }; bypass?: { confirm: true } };

  function buildDraftPayload(
    noteValue: string,
    diagValue: DiagAnswers,
    extra?: DiagExtra,
  ): Record<string, unknown> {
    const answers: Record<string, unknown> = {
      active_phase_domains: [...diagValue.active_phase_domains],
      shared_one_month_active_phase: diagValue.shared_one_month_active_phase,
      active_phase_abbreviated_by_intervention:
        diagValue.active_phase_abbreviated_by_intervention,
      functional_decline: diagValue.functional_decline,
      continuous_months: diagValue.continuous_months,
      active_phase_included: diagValue.active_phase_included,
      concurrent_mood_episode_with_psychosis:
        diagValue.concurrent_mood_episode_with_psychosis,
      mood_episodes_minority_of_course: diagValue.mood_episodes_minority_of_course,
      substance_or_medical_cause: diagValue.substance_or_medical_cause,
      autism_or_childhood_communication_history:
        diagValue.autism_or_childhood_communication_history,
    };
    const diagBlock: Record<string, unknown> = { answers };
    if (extra?.warning_ack) {
      diagBlock.warning_ack = extra.warning_ack;
    }
    if (extra?.bypass) {
      diagBlock.bypass = extra.bypass;
    }
    return { note: noteValue, diagnosis: diagBlock };
  }

  async function saveNow(
    value: string,
    diagValue: DiagAnswers,
    extra: DiagExtra | undefined,
    revision: number,
  ): Promise<void> {
    if (!encounter) {
      return;
    }
    setSaveState("Saving…");
    try {
      const updated = await patchEncounter(
        encounter.id,
        buildDraftPayload(value, diagValue, extra),
        revision,
      );
      revisionRef.current = updated.revision;
      savedNoteRef.current = value;
      savedDiagRef.current = JSON.stringify(diagValue);
      setEncounter(updated);
      const storedDiag =
        typeof updated.draft_data?.diagnosis === "object" &&
        updated.draft_data?.diagnosis !== null
          ? (updated.draft_data.diagnosis as Record<string, unknown>)
          : null;
      setDiagAck(
        storedDiag !== null && typeof storedDiag.warning_ack === "object" && storedDiag.warning_ack !== null
          ? (storedDiag.warning_ack as Record<string, unknown>)
          : null,
      );
      setDiagBypass(
        storedDiag !== null && typeof storedDiag.bypass === "object" && storedDiag.bypass !== null
          ? (storedDiag.bypass as Record<string, unknown>)
          : null,
      );
      // Only advertise Saved after the write is acknowledged.
      if (noteRef.current === value && JSON.stringify(diagAnswersRef.current) === JSON.stringify(diagValue)) {
        setSaveState(`Saved (rev ${updated.revision})`);
      }
    } catch (failure: unknown) {
      const status = (failure as { status?: number }).status;
      if (status === 412) {
        staleRef.current = true;
        setSaveState("Stale revision");
        try {
          const fresh = await getEncounter(encounter.id);
          const freshNote =
            typeof fresh.draft_data?.note === "string"
              ? (fresh.draft_data.note as string)
              : "";
          setServerNote(freshNote);
        } catch {
          /* keep edits; server preview stays empty */
        }
      } else if (status === 403) {
        setSaveState("Read-only draft.");
      } else {
        // Failed network/database save never shows Saved; keep edits.
        // 422 (e.g. forged ack/bypass) never shows Saved; keep edits.
        setSaveState("Save failed");
      }
    }
  }

  function scheduleSave(
    value: string,
    diagValue: DiagAnswers,
    extra?: DiagExtra,
  ): void {
    if (encounter?.state !== "draft") {
      return;
    }
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    setSaveState("Saving…");
    const snapshotExtra = extra ? { ...extra } : undefined;
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      if (!staleRef.current) {
        // Read latest refs at fire time so concurrent note+diagnosis edits merge.
        void saveNow(noteRef.current, diagAnswersRef.current, snapshotExtra, revisionRef.current);
      }
    }, 1000);
  }

  function handleDiagAnswers(next: DiagAnswers): void {
    if (encounter?.state !== "draft" || readOnly) {
      return;
    }
    // Relevant edits clear a prior ack preview; bypass persists server-side.
    setDiagAnswers(next);
    diagAnswersRef.current = next;
    setAckChecked(false);
    ackCheckedRef.current = false;
    setDiagAck(null);
    if (staleRef.current) {
      setSaveState("Stale revision");
      return;
    }
    scheduleSave(noteRef.current, next);
  }

  function handleDiagBool(key: keyof DiagAnswers, value: boolean): void {
    handleDiagAnswers({ ...diagAnswersRef.current, [key]: value });
  }

  function handleDiagDomains(domains: string[]): void {
    handleDiagAnswers({ ...diagAnswersRef.current, active_phase_domains: domains });
  }

  function handleDiagMonths(value: number | null): void {
    handleDiagAnswers({ ...diagAnswersRef.current, continuous_months: value });
  }

  function handleDiagAck(checked: boolean): void {
    if (encounter?.state !== "draft" || readOnly) {
      return;
    }
    setAckChecked(checked);
    ackCheckedRef.current = checked;
    if (!checked) {
      // Unchecking gates Continue locally; the stamped server ack clears on
      // the next answers edit (backend preserves same-answers acks).
      return;
    }
    if (staleRef.current) {
      setSaveState("Stale revision");
      return;
    }
    const preview = previewDiagnosis(diagAnswersRef.current);
    const completeBelow = preview.status === "complete" && !preview.threshold_met;
    // Below-threshold complete requests a stamped ack; partial answers save
    // normally (200) so the shared Saving…/Saved (rev N) contract holds and
    // Continue unlocks locally. The S49 sign gate still requires a stamped ack.
    scheduleSave(
      noteRef.current,
      diagAnswersRef.current,
      completeBelow ? { warning_ack: { confirm: true } } : undefined,
    );
  }

  function handleDiagBypass(): void {
    if (encounter?.state !== "draft" || readOnly) {
      return;
    }
    if (staleRef.current) {
      setSaveState("Stale revision");
      return;
    }
    scheduleSave(noteRef.current, diagAnswersRef.current, { bypass: { confirm: true } });
  }

  function handleDiagComplete(): void {
    if (encounter?.state !== "draft" || readOnly) {
      return;
    }
    if (staleRef.current) {
      setSaveState("Stale revision");
      return;
    }
    scheduleSave(noteRef.current, diagAnswersRef.current);
  }

  async function handleDiscard(): Promise<void> {
    if (!encounter || encounter.state !== "draft" || readOnly) {
      return;
    }
    if (!window.confirm("Discard this draft? This cannot be undone.")) {
      return;
    }
    // Explicit confirmation + current revision; tombstone retained server-side.
    // No jobs exist yet, so jobs cancellation is a no-op (S51 integrates it).
    try {
      const discarded = await discardEncounter(encounter.id, revisionRef.current);
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      revisionRef.current = discarded.revision;
      savedNoteRef.current = noteRef.current;
      savedDiagRef.current = JSON.stringify(diagAnswersRef.current);
      staleRef.current = false;
      setEncounter(discarded);
      setSaveState("Draft discarded.");
    } catch {
      setSaveState("Save failed");
    }
  }

  const readOnly =
    encounter !== null && encounter.author_id !== null && encounter.author_id !== userId;
  const discarded = encounter !== null && encounter.state !== "draft";

  return (
    <section aria-labelledby="draft-heading">
      <h3 id="draft-heading">Draft</h3>
      <p>
        Patient {patient.patient_id} ·{" "}
        <button type="button" className="x-button" onClick={handleClose}>
          Close
        </button>
      </p>
      {loadError ? (
        <p role="alert" className="x-error">
          {loadError}
        </p>
      ) : encounter === null ? (
        <p role="status">Loading…</p>
      ) : discarded ? (
        <>
          <div className="x-field">
            <label htmlFor={`draft-note-${encounter.id}`}>Draft note</label>
            <textarea
              id={`draft-note-${encounter.id}`}
              value={note}
              disabled
              readOnly
            />
          </div>
          <p role="status">Draft discarded.</p>
        </>
      ) : (
        <>
          <div className="x-field">
            <label htmlFor={`draft-note-${encounter.id}`}>Draft note</label>
            <textarea
              id={`draft-note-${encounter.id}`}
              value={note}
              disabled={readOnly}
              onChange={(event) => {
                const value = event.target.value;
                setNote(value);
                noteRef.current = value;
                if (staleRef.current) {
                  setSaveState("Stale revision");
                  return;
                }
                scheduleSave(value, diagAnswersRef.current);
              }}
            />
          </div>
          <DiagnosisSection
            encounterId={encounter.id}
            answers={diagAnswers}
            ackStamp={diagAck}
            bypassStamp={diagBypass}
            ackChecked={ackChecked}
            readOnly={readOnly}
            onDomainsChange={handleDiagDomains}
            onBoolChange={handleDiagBool}
            onMonthsChange={handleDiagMonths}
            onAckChange={handleDiagAck}
            onBypass={handleDiagBypass}
            onComplete={handleDiagComplete}
          />
          <p role="status">{saveState}</p>
          {readOnly ? <p>Read-only draft.</p> : null}
          {!readOnly ? (
            <button type="button" className="x-button" onClick={() => void handleDiscard()}>
              Discard draft
            </button>
          ) : null}
          {saveState === "Stale revision" ? (
            <>
              {serverNote !== null ? <p>Server value: {serverNote}</p> : null}
              <button
                type="button"
                className="x-button"
                onClick={() => void reloadPreservingEdits()}
              >
                Reload draft
              </button>
            </>
          ) : null}
        </>
      )}
    </section>
  );
}

function PatientForm({ onCreated }: { onCreated: () => void }) {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [sex, setSex] = useState("");
  const [age, setAge] = useState("");
  const [patientId, setPatientId] = useState("");
  const [clinicalStatus, setClinicalStatus] = useState("");
  const [phone, setPhone] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const ageNumber = /^\d+$/.test(age) ? parseInt(age, 10) : Number.NaN;
  const valid =
    PATIENT_NAME_RE.test(firstName.normalize("NFC")) &&
    PATIENT_NAME_RE.test(lastName.normalize("NFC")) &&
    (sex === "M" || sex === "F") &&
    Number.isInteger(ageNumber) &&
    ageNumber >= 18 &&
    ageNumber <= 99 &&
    PATIENT_ID_RE.test(patientId) &&
    (clinicalStatus === "first_time" || clinicalStatus === "established");

  async function submit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    if (!valid || pending) {
      return;
    }
    setError(null);
    setPending(true);
    try {
      await createPatient({
        first_name: firstName.normalize("NFC"),
        last_name: lastName.normalize("NFC"),
        sex,
        age: ageNumber,
        patient_id: patientId,
        clinical_status: clinicalStatus,
        ...(phone ? { phone } : {}),
      });
      setFirstName("");
      setLastName("");
      setSex("");
      setAge("");
      setPatientId("");
      setClinicalStatus("");
      setPhone("");
      onCreated();
    } catch {
      setError("Could not register the patient.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="x-form" onSubmit={submit} aria-label="Register patient">
      <div className="x-field">
        <label htmlFor="patient-first-name">First name</label>
        <input
          id="patient-first-name"
          name="first-name"
          autoComplete="off"
          value={firstName}
          onChange={(event) => setFirstName(event.target.value)}
        />
      </div>
      <div className="x-field">
        <label htmlFor="patient-last-name">Last name</label>
        <input
          id="patient-last-name"
          name="last-name"
          autoComplete="off"
          value={lastName}
          onChange={(event) => setLastName(event.target.value)}
        />
      </div>
      <div className="x-field">
        <label htmlFor="patient-sex">Sex</label>
        <select
          id="patient-sex"
          value={sex}
          onChange={(event) => setSex(event.target.value)}
        >
          <option value="">Select…</option>
          <option value="F">F</option>
          <option value="M">M</option>
        </select>
      </div>
      <div className="x-field">
        <label htmlFor="patient-age">Age</label>
        <input
          id="patient-age"
          name="age"
          inputMode="numeric"
          autoComplete="off"
          value={age}
          onChange={(event) => setAge(event.target.value)}
        />
      </div>
      <div className="x-field">
        <label htmlFor="patient-patient-id">Patient ID</label>
        <input
          id="patient-patient-id"
          name="patient-id"
          inputMode="numeric"
          autoComplete="off"
          value={patientId}
          onChange={(event) => setPatientId(event.target.value)}
        />
      </div>
      <div className="x-field">
        <label htmlFor="patient-clinical-status">Clinical status</label>
        <select
          id="patient-clinical-status"
          value={clinicalStatus}
          onChange={(event) => setClinicalStatus(event.target.value)}
        >
          <option value="">Select…</option>
          <option value="first_time">first_time</option>
          <option value="established">established</option>
        </select>
      </div>
      <div className="x-field">
        <label htmlFor="patient-phone">Phone</label>
        <input
          id="patient-phone"
          name="phone"
          autoComplete="off"
          value={phone}
          onChange={(event) => setPhone(event.target.value)}
        />
      </div>
      {error ? (
        <p role="alert" className="x-error">
          {error}
        </p>
      ) : null}
      <button type="submit" className="x-button" disabled={!valid || pending}>
        {pending ? "Registering…" : "Register patient"}
      </button>
    </form>
  );
}

/** Route guard complements the server check; the server still enforces admin. */
function PhysiciansGate({ user }: { user: SessionUser | null }) {
  if (!user) {
    return <LoginHint />;
  }
  if (user.role !== "admin") {
    return <p role="alert">Access denied.</p>;
  }
  return <PhysiciansPage />;
}

function LoginHint() {
  return <p>Log in to continue.</p>;
}

function ThemeToggle({
  theme,
  onChanged,
}: {
  theme: ThemeName;
  onChanged: (theme: ThemeName) => void;
}) {
  const [failed, setFailed] = useState(false);
  const next: ThemeName = theme === "dark" ? "light" : "dark";
  return (
    <>
      <button
        type="button"
        className="x-button"
        onClick={() => {
          setFailed(false);
          const previous = theme;
          onChanged(next);
          updateTheme(next).catch(() => {
            onChanged(previous);
            setFailed(true);
          });
        }}
      >
        {theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
      </button>
      {failed ? (
        <p role="alert" className="x-error">
          Could not save the theme.
        </p>
      ) : null}
    </>
  );
}

function SignOutButton({ onSignedOut }: { onSignedOut: () => void }) {
  const [failed, setFailed] = useState(false);
  return (
    <>
      <button
        type="button"
        className="x-button"
        onClick={() => {
          setFailed(false);
          logout()
            .then(onSignedOut)
            .catch(() => setFailed(true));
        }}
      >
        Sign out
      </button>
      {failed ? (
        <p role="alert" className="x-error">
          Could not sign out. Retry later.
        </p>
      ) : null}
    </>
  );
}

function PasswordForm() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    setError(null);
    setDone(false);
    setPending(true);
    try {
      await changeOwnPassword(current, next);
      setDone(true);
      setCurrent("");
      setNext("");
    } catch {
      setError("Could not change the password.");
    } finally {
      setPending(false);
    }
  }

  return (
    <section aria-labelledby="password-heading">
      <h2 id="password-heading">Change password</h2>
      <form className="x-form" onSubmit={submit}>
        <div className="x-field">
          <label htmlFor="current-password">Current password</label>
          <input
            id="current-password"
            name="current-password"
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
            aria-describedby={error ? "password-error" : undefined}
          />
        </div>
        <div className="x-field">
          <label htmlFor="new-password">New password</label>
          <input
            id="new-password"
            name="new-password"
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(event) => setNext(event.target.value)}
            aria-describedby={error ? "password-error" : undefined}
          />
        </div>
        {error ? (
          <p id="password-error" role="alert" className="x-error">
            {error}
          </p>
        ) : null}
        {done ? <p role="status">Password changed.</p> : null}
        <button type="submit" className="x-button" disabled={pending}>
          {pending ? "Changing…" : "Change password"}
        </button>
      </form>
    </section>
  );
}

function PhysiciansPage() {
  const [items, setItems] = useState<PhysicianAccount[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    setError(null);
    listPhysicians()
      .then(setItems)
      .catch((failure: unknown) =>
        setError(failure instanceof Error ? failure.message : "Could not load physicians."),
      );
  }, []);

  useEffect(reload, [reload]);

  return (
    <>
      <h1>Physicians</h1>
      <CreatePhysicianForm onCreated={reload} />
      {error ? (
        <p role="alert" className="x-error">
          {error}
        </p>
      ) : items === null ? (
        <p>Loading…</p>
      ) : items.length === 0 ? (
        <p>No physicians yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Username</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{item.username}</td>
                <td>{item.active ? "Active" : "Inactive"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function CreatePhysicianForm({ onCreated }: { onCreated: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      await createPhysician(username, password);
      setUsername("");
      setPassword("");
      onCreated();
    } catch {
      setError("Could not create the physician.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="x-form" onSubmit={submit} aria-label="Create physician">
      <div className="x-field">
        <label htmlFor="new-physician-username">Username</label>
        <input
          id="new-physician-username"
          name="username"
          autoComplete="off"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          aria-describedby={error ? "create-physician-error" : undefined}
        />
      </div>
      <div className="x-field">
        <label htmlFor="new-physician-password">Password</label>
        <input
          id="new-physician-password"
          name="password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          aria-describedby={error ? "create-physician-error" : undefined}
        />
      </div>
      {error ? (
        <p id="create-physician-error" role="alert" className="x-error">
          {error}
        </p>
      ) : null}
      <button type="submit" className="x-button" disabled={pending}>
        {pending ? "Creating…" : "Create physician"}
      </button>
    </form>
  );
}

function LoginForm({
  onLoggedIn,
}: {
  onLoggedIn: (user: SessionUser, notice: string | null) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("physician");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      const result = await login(username, password, role);
      onLoggedIn(result.user, result.researchNotice);
    } catch {
      setError("Invalid username, password, or role.");
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <h1>X-INSIGHT</h1>
      <form className="x-form" onSubmit={submit}>
        <div className="x-field">
          <label htmlFor="username">Username</label>
          <input
            id="username"
            name="username"
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            aria-describedby={error ? "login-error" : undefined}
          />
        </div>
        <div className="x-field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            aria-describedby={error ? "login-error" : undefined}
          />
        </div>
        <div className="x-field">
          <label htmlFor="role">Role</label>
          <select
            id="role"
            name="role"
            value={role}
            onChange={(event) => setRole(event.target.value)}
          >
            <option value="physician">physician</option>
            <option value="admin">admin</option>
          </select>
        </div>
        {error ? (
          <p id="login-error" role="alert" className="x-error">
            {error}
          </p>
        ) : null}
        <button type="submit" className="x-button" disabled={pending}>
          {pending ? "Logging in…" : "Log in"}
        </button>
      </form>
    </>
  );
}
