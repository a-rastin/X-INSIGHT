/** Minimal same-origin API client (S05 slice 1). Cookies carry the session. */
export interface SessionUser {
  id: string;
  username: string;
  role: string;
  theme: string;
}

export const RESEARCH_NOTICE =
  "This is a research app and is not intended to be used as the sole basis for treating patients.";

function readCookie(name: string): string | null {
  const parts = document.cookie.split(";").map((p) => p.trim());
  for (const part of parts) {
    if (part.startsWith(`${name}=`)) {
      return decodeURIComponent(part.slice(name.length + 1));
    }
  }
  return null;
}

export function csrfToken(): string | null {
  return readCookie("xinsight_csrf");
}

async function jsonOrThrow(response: Response): Promise<unknown> {
  const text = await response.text();
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    throw new Error("Unexpected server response.");
  }
}

async function mutating(path: string, body: unknown): Promise<Response> {
  const csrf = csrfToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (csrf) {
    headers["X-CSRF-Token"] = csrf;
  }
  return fetch(path, {
    method: "POST",
    credentials: "include",
    headers,
    body: JSON.stringify(body),
  });
}

export async function logout(): Promise<void> {
  const response = await mutating("/api/v1/auth/logout", {});
  if (!response.ok && response.status !== 401) {
    throw new Error("Could not sign out. Retry later.");
  }
}

export async function changeOwnPassword(
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  const response = await mutating("/api/v1/me/password", {
    current_password: currentPassword,
    new_password: newPassword,
  });
  if (!response.ok) {
    throw new Error("Could not change the password.");
  }
}

export interface PhysicianAccount {
  id: string;
  username: string;
  role: string;
  active: boolean;
  revision: number;
}

function idempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `web-${Date.now()}-${Math.floor(Math.random() * 1e9)}`;
}

export async function listPhysicians(): Promise<PhysicianAccount[]> {
  // Prototype holds fewer than ten physicians; one page covers the table.
  const response = await fetch("/api/v1/physicians?limit=100", {
    credentials: "include",
  });
  if (response.status === 403) {
    throw new Error("Access denied.");
  }
  if (!response.ok) {
    throw new Error("Could not load physicians.");
  }
  const payload = (await response.json()) as { items: PhysicianAccount[] };
  return payload.items;
}

export async function createPhysician(
  username: string,
  password: string,
): Promise<PhysicianAccount> {
  const csrf = csrfToken();
  const response = await fetch("/api/v1/physicians", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRF-Token": csrf } : {}),
      "Idempotency-Key": idempotencyKey(),
    },
    body: JSON.stringify({ username, password }),
  });
  if (response.status === 403) {
    throw new Error("Access denied.");
  }
  if (!response.ok) {
    throw new Error("Could not create the physician.");
  }
  return (await response.json()) as PhysicianAccount;
}

export interface Patient {
  id: string;
  patient_id: string;
  first_name: string;
  last_name: string;
  sex: string;
  age: number;
  clinical_status: string;
  phone: string | null;
  archived: boolean;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface PatientList {
  schema_version: 1;
  items: Patient[];
  next_cursor: string | null;
}

export interface PatientCreate {
  first_name: string;
  last_name: string;
  sex: string;
  age: number;
  patient_id: string;
  clinical_status: string;
  phone?: string;
}

export async function listPatients(params?: {
  q?: string;
  clinical_status?: string;
}): Promise<PatientList> {
  const query = new URLSearchParams({ limit: "100" });
  if (params?.q) {
    query.set("q", params.q);
  }
  if (params?.clinical_status) {
    query.set("clinical_status", params.clinical_status);
  }
  const response = await fetch(`/api/v1/patients?${query}`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error("Could not load patients.");
  }
  return (await response.json()) as PatientList;
}

export async function createPatient(body: PatientCreate): Promise<Patient> {
  const csrf = csrfToken();
  const response = await fetch("/api/v1/patients", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRF-Token": csrf } : {}),
      "Idempotency-Key": idempotencyKey(),
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error("Could not register the patient.");
  }
  const payload = (await response.json()) as { patient: Patient };
  return payload.patient;
}

export interface Encounter {
  id: string;
  patient_id: string;
  kind: string;
  author_id: string | null;
  state: string;
  revision: number;
  draft_data: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export async function listEncounters(patientUuid: string): Promise<Encounter[]> {
  const response = await fetch(`/api/v1/patients/${patientUuid}/encounters`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error("Could not load drafts.");
  }
  const payload = (await response.json()) as { items: Encounter[] };
  return payload.items;
}

export async function getEncounter(encounterId: string): Promise<Encounter> {
  const response = await fetch(`/api/v1/encounters/${encounterId}`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error("Could not load the draft.");
  }
  const payload = (await response.json()) as { encounter: Encounter };
  return payload.encounter;
}

export async function patchEncounter(
  encounterId: string,
  draftData: Record<string, unknown>,
  revision: number,
): Promise<Encounter> {
  const csrf = csrfToken();
  const response = await fetch(`/api/v1/encounters/${encounterId}`, {
    method: "PATCH",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRF-Token": csrf } : {}),
      "If-Match": String(revision),
    },
    body: JSON.stringify({ draft_data: draftData }),
  });
  if (response.status === 412) {
    throw Object.assign(new Error("Stale revision."), { status: 412 });
  }
  if (response.status === 403) {
    throw Object.assign(new Error("Only the author may edit."), { status: 403 });
  }
  if (!response.ok) {
    throw Object.assign(new Error("Could not save the draft."), {
      status: response.status,
    });
  }
  const payload = (await response.json()) as { encounter: Encounter };
  return payload.encounter;
}

export async function discardEncounter(
  encounterId: string,
  revision: number,
): Promise<Encounter> {
  const csrf = csrfToken();
  const response = await fetch(`/api/v1/encounters/${encounterId}/discard`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRF-Token": csrf } : {}),
      "If-Match": String(revision),
    },
    body: JSON.stringify({ confirm: true }),
  });
  if (response.status === 412) {
    throw Object.assign(new Error("Stale revision."), { status: 412 });
  }
  if (response.status === 403) {
    throw Object.assign(new Error("Only the author may discard."), { status: 403 });
  }
  if (!response.ok) {
    throw Object.assign(new Error("Could not discard the draft."), {
      status: response.status,
    });
  }
  const payload = (await response.json()) as { encounter: Encounter };
  return payload.encounter;
}

export async function fetchSession(): Promise<SessionUser | null> {
  const response = await fetch("/api/v1/me", { credentials: "include" });
  if (response.status === 401) {
    return null;
  }
  if (!response.ok) {
    throw new Error("Could not load the session.");
  }
  return (await response.json()) as SessionUser;
}

export type ThemeName = "light" | "dark";

export async function updateTheme(theme: ThemeName): Promise<SessionUser> {
  const csrf = csrfToken();
  const response = await fetch("/api/v1/me/preferences", {
    method: "PATCH",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRF-Token": csrf } : {}),
    },
    body: JSON.stringify({ theme }),
  });
  if (!response.ok) {
    throw new Error("Could not save the theme.");
  }
  return (await response.json()) as SessionUser;
}

export async function login(
  username: string,
  password: string,
  role: string,
): Promise<{ user: SessionUser; researchNotice: string | null }> {
  const response = await fetch("/api/v1/auth/login", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password, role }),
  });
  if (response.status === 401 || response.status === 429) {
    // Generic failure: never disclose which field was wrong.
    throw new Error("Invalid username, password, or role.");
  }
  if (!response.ok) {
    throw new Error("Could not log in. Retry later.");
  }
  const payload = (await jsonOrThrow(response)) as {
    user: SessionUser;
    research_notice?: string;
  };
  return { user: payload.user, researchNotice: payload.research_notice ?? null };
}
