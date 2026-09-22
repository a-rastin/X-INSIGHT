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
  baseline_encounter_id: string | null;
  baseline_changed: boolean;
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

/** S14 follow-up: open a follow_up draft copied from a signed baseline. */
export async function createFollowup(
  patientUuid: string,
  baselineId: string,
): Promise<Encounter> {
  const csrf = csrfToken();
  const response = await fetch(`/api/v1/patients/${patientUuid}/encounters`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRF-Token": csrf } : {}),
      "Idempotency-Key": idempotencyKey(),
    },
    body: JSON.stringify({ baseline_encounter_id: baselineId }),
  });
  if (response.status === 403) {
    throw Object.assign(new Error("Only physicians may start a follow-up."), {
      status: 403,
    });
  }
  if (response.status === 409) {
    throw Object.assign(new Error("The baseline must be signed first."), {
      status: 409,
    });
  }
  if (response.status === 422) {
    throw Object.assign(new Error("Could not start the follow-up."), {
      status: 422,
    });
  }
  if (!response.ok) {
    throw Object.assign(new Error("Could not start the follow-up."), {
      status: response.status,
    });
  }
  const payload = (await response.json()) as { encounter: Encounter };
  return payload.encounter;
}

export interface HistoryContentField {
  id: string;
}

export interface HistoryContentEffect {
  id: string;
  severity_values: string[];
}

export interface HistoryContent {
  definition_version: string;
  fields: HistoryContentField[];
  effects: HistoryContentEffect[];
}

/** Released-only structured-history definition (S12). 404 = draft unreleased. */
export async function getHistoryContent(): Promise<HistoryContent> {
  const response = await fetch("/api/v1/content/history", {
    credentials: "include",
  });
  if (!response.ok) {
    throw Object.assign(new Error("History content unavailable."), {
      status: response.status,
    });
  }
  const payload = (await response.json()) as {
    definition_version: string;
    definition: {
      fields: HistoryContentField[];
      effects: HistoryContentEffect[];
    };
  };
  return {
    definition_version: payload.definition_version,
    fields: payload.definition.fields ?? [],
    effects: payload.definition.effects ?? [],
  };
}

export async function patchPatientPhone(
  patientUuid: string,
  phone: string | null,
  revision: number,
): Promise<Patient> {
  const csrf = csrfToken();
  const response = await fetch(`/api/v1/patients/${patientUuid}`, {
    method: "PATCH",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRF-Token": csrf } : {}),
      "If-Match": String(revision),
    },
    body: JSON.stringify({ phone }),
  });
  if (response.status === 412) {
    throw Object.assign(new Error("Stale revision."), { status: 412 });
  }
  if (response.status === 403) {
    throw Object.assign(new Error("Physician access required."), {
      status: 403,
    });
  }
  if (!response.ok) {
    throw Object.assign(new Error("Could not save the phone."), {
      status: response.status,
    });
  }
  const payload = (await response.json()) as { patient: Patient };
  return payload.patient;
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

export interface PageNote {
  id: string;
  encounter_id: string;
  page: string;
  text: string;
  author_id: string;
  author_display: string;
  created_at: string;
}

/** S13 attributed page notes: append-only, server-stamped, separate table. */
export async function listNotes(encounterId: string): Promise<PageNote[]> {
  const response = await fetch(`/api/v1/encounters/${encounterId}/notes`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error("Could not load notes.");
  }
  const payload = (await response.json()) as { items: PageNote[] };
  return payload.items;
}

export async function addNote(
  encounterId: string,
  page: string,
  text: string,
): Promise<PageNote> {
  const csrf = csrfToken();
  const response = await fetch(`/api/v1/encounters/${encounterId}/notes`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRF-Token": csrf } : {}),
      "Idempotency-Key": idempotencyKey(),
    },
    body: JSON.stringify({ page, text }),
  });
  if (!response.ok) {
    throw Object.assign(new Error("Could not save the note."), {
      status: response.status,
    });
  }
  const payload = (await response.json()) as { note: PageNote };
  return payload.note;
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

export interface ProviderSettings {
  schema_version: 1;
  base_url: string;
  model: string;
  revision: number;
  key_configured: boolean;
  test_status: string;
  last_test: string | null;
}

export interface ProviderCapabilityResult {
  schema_version: 1;
  credential_ok: boolean;
  model_ok: boolean;
  tool_ok: boolean;
  json_ok: boolean;
  diagnostic: string;
}

function csrfHeaders(extra?: Record<string, string>): Record<string, string> {
  const csrf = csrfToken();
  return {
    "Content-Type": "application/json",
    ...(csrf ? { "X-CSRF-Token": csrf } : {}),
    ...(extra ?? {}),
  };
}

function statusError(message: string, status: number): Error {
  return Object.assign(new Error(message), { status });
}

/** S42 masked provider settings (T9). Never carries a key; 404 = unconfigured. */
export async function getProviderSettings(): Promise<{
  settings: ProviderSettings;
  etag: string;
}> {
  const response = await fetch("/api/v1/api-settings", {
    credentials: "include",
  });
  if (response.status === 403) {
    throw statusError("Access denied.", 403);
  }
  if (response.status === 404) {
    throw statusError("Provider settings are not configured.", 404);
  }
  if (!response.ok) {
    throw statusError("Could not load provider settings.", response.status);
  }
  const settings = (await response.json()) as ProviderSettings;
  const etag = (response.headers.get("etag") ?? "").replace(/"/g, "");
  return { settings, etag: etag || String(settings.revision) };
}

export async function saveProviderSettings(
  body: {
    base_url?: string;
    model?: string;
    key_action: "replace" | "unchanged" | "clear";
    api_key?: string;
  },
  ifMatch?: string,
): Promise<{ settings: ProviderSettings; etag: string }> {
  const response = await fetch("/api/v1/api-settings", {
    method: "PUT",
    credentials: "include",
    headers: csrfHeaders(ifMatch ? { "If-Match": ifMatch } : undefined),
    body: JSON.stringify(body),
  });
  if (response.status === 403) {
    throw statusError("Access denied.", 403);
  }
  if (response.status === 412) {
    throw statusError(
      "Provider settings changed. Reload and reconcile.",
      412,
    );
  }
  if (response.status === 422) {
    let detail = "Invalid provider settings.";
    try {
      const payload = (await response.clone().json()) as { detail?: unknown };
      if (typeof payload.detail === "string" && payload.detail) {
        detail = payload.detail;
      }
    } catch {
      /* keep generic message */
    }
    throw statusError(detail, 422);
  }
  if (!response.ok) {
    throw statusError("Could not save provider settings.", response.status);
  }
  const settings = (await response.json()) as ProviderSettings;
  const etag = (response.headers.get("etag") ?? "").replace(/"/g, "");
  return { settings, etag: etag || String(settings.revision) };
}

/** S42 explicit capability probe (T9): one synthetic exchange, no secret echo. */
export async function testProviderSettings(): Promise<ProviderCapabilityResult> {
  const response = await fetch("/api/v1/api-settings/test", {
    method: "POST",
    credentials: "include",
    headers: csrfHeaders(),
    body: JSON.stringify({}),
  });
  if (response.status === 403) {
    throw statusError("Access denied.", 403);
  }
  if (response.status === 404) {
    throw statusError("Provider settings are not configured.", 404);
  }
  if (response.status === 422) {
    let detail = "Provider destination is not allowed.";
    try {
      const payload = (await response.clone().json()) as { detail?: unknown };
      if (typeof payload.detail === "string" && payload.detail) {
        detail = payload.detail;
      }
    } catch {
      /* keep generic message */
    }
    throw statusError(detail, 422);
  }
  if (!response.ok) {
    throw statusError("Provider test failed.", response.status);
  }
  return (await response.json()) as ProviderCapabilityResult;
}

/** S42 revision retention list (masked, key never present). */
export async function listProviderVersions(): Promise<ProviderSettings[]> {
  const response = await fetch("/api/v1/api-settings/versions", {
    credentials: "include",
  });
  if (response.status === 403) {
    throw statusError("Access denied.", 403);
  }
  if (!response.ok) {
    throw statusError("Could not load provider revisions.", response.status);
  }
  const payload = (await response.json()) as { items: ProviderSettings[] };
  return payload.items ?? [];
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
