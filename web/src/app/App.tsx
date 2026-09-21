import { useCallback, useEffect, useState } from "react";
import "../shared/theme.css";
import {
  RESEARCH_NOTICE,
  changeOwnPassword,
  createPhysician,
  createPatient,
  fetchSession,
  listPhysicians,
  login,
  logout,
  listPatients,
  updateTheme,
  type Patient,
  type PhysicianAccount,
  type SessionUser,
  type ThemeName,
} from "./api";

type Route = "/" | "/register" | "/physicians";

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
      <PatientsSection role={user.role} />
      <PasswordForm />
    </>
  );
}

const PATIENT_NAME_RE = /^\p{L}+$/u;
const PATIENT_ID_RE = /^[0-9]{10}$/;

function PatientsSection({ role }: { role: string }) {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [items, setItems] = useState<Patient[] | null>(null);
  const [error, setError] = useState<string | null>(null);

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
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{item.patient_id}</td>
                <td>{item.first_name}</td>
                <td>{item.last_name}</td>
              </tr>
            ))}
          </tbody>
        </table>
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
