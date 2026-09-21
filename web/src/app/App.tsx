import { useCallback, useEffect, useState } from "react";
import "../shared/theme.css";
import {
  RESEARCH_NOTICE,
  changeOwnPassword,
  createPhysician,
  fetchSession,
  listPhysicians,
  login,
  logout,
  updateTheme,
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
      <PasswordForm />
    </>
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
