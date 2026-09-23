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
  archived?: boolean;
}): Promise<PatientList> {
  const query = new URLSearchParams({ limit: "100" });
  if (params?.q) {
    query.set("q", params.q);
  }
  if (params?.clinical_status) {
    query.set("clinical_status", params.clinical_status);
  }
  query.set("archived", params?.archived ? "true" : "false");
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

/** S51 archive client (T9): admin-only, If-Match + Idempotency-Key. */
async function setArchived(
  patientUuid: string,
  revision: number,
  archived: boolean,
): Promise<Patient> {
  const csrf = csrfToken();
  const action = archived ? "archive" : "unarchive";
  const response = await fetch(`/api/v1/patients/${patientUuid}/${action}`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRF-Token": csrf } : {}),
      "If-Match": String(revision),
      "Idempotency-Key": idempotencyKey(),
    },
    body: JSON.stringify({}),
  });
  if (response.status === 412) {
    throw Object.assign(new Error("The patient changed. Reload and reconcile."), {
      status: 412,
    });
  }
  if (response.status === 403) {
    throw Object.assign(new Error("Administrator access required."), {
      status: 403,
    });
  }
  if (!response.ok) {
    throw Object.assign(
      new Error(archived ? "Could not archive the patient." : "Could not unarchive the patient."),
      { status: response.status },
    );
  }
  const payload = (await response.json()) as { patient: Patient };
  return payload.patient;
}

export async function archivePatient(
  patientUuid: string,
  revision: number,
): Promise<Patient> {
  return setArchived(patientUuid, revision, true);
}

export async function unarchivePatient(
  patientUuid: string,
  revision: number,
): Promise<Patient> {
  return setArchived(patientUuid, revision, false);
}

export interface DeactivationDraft {
  id: string;
  encounter_id: string;
  kind: string;
  state: string;
  revision: number;
}

export interface DeactivationReview {
  schema_version: number;
  physician_id: string;
  account_revision: number;
  drafts: DeactivationDraft[];
  draft_set_revision: string;
}

/** S51 deactivation review (T9): real non-terminal draft set + content hash. */
export async function getDeactivationReview(
  physicianId: string,
): Promise<DeactivationReview> {
  const response = await fetch(
    `/api/v1/physicians/${physicianId}/deactivation-review`,
    { credentials: "include" },
  );
  if (response.status === 403) {
    throw statusError("Access denied.", 403);
  }
  if (!response.ok) {
    throw statusError("Could not load the draft review.", response.status);
  }
  return (await response.json()) as DeactivationReview;
}

/** S51 deactivate (T9): explicit retain/discard + draft_set_revision + If-Match. */
export async function deactivatePhysician(
  physicianId: string,
  body: {
    draft_action: "retain" | "discard";
    draft_set_revision: string;
    confirm_discard: boolean;
  },
  revision: number,
): Promise<PhysicianAccount> {
  const response = await fetch(`/api/v1/physicians/${physicianId}/deactivate`, {
    method: "POST",
    credentials: "include",
    headers: {
      ...csrfHeaders(),
      "If-Match": String(revision),
      "Idempotency-Key": idempotencyKey(),
    },
    body: JSON.stringify(body),
  });
  if (
    response.status === 403 ||
    response.status === 409 ||
    response.status === 412 ||
    response.status === 422
  ) {
    let detail = "Could not deactivate the physician.";
    try {
      const payload = (await response.clone().json()) as {
        detail?: unknown;
      };
      if (typeof payload.detail === "string" && payload.detail.trim() !== "") {
        detail = payload.detail;
      }
    } catch {
      /* keep fallback */
    }
    throw statusError(detail, response.status);
  }
  if (!response.ok) {
    throw statusError("Could not deactivate the physician.", response.status);
  }
  return (await response.json()) as PhysicianAccount;
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

/** S24 admin networks client. XML is not secret; errors stay generic. */
export interface NetworkItem {
  id: string;
  network_id: string;
  key: string;
}

export interface NetworkVersionItem {
  version_id: string;
  id: string;
  version_number: number;
  version: number;
  sha256: string;
  source_sha256: string;
  byte_count: number;
  xsd_valid: boolean;
}

export interface NetworkGraph {
  version_id: string;
  network_id: string;
  version_number: number;
  version: number;
  sha256: string;
  byte_count: number;
  nodes: string[];
  edges: string[][];
  states: Record<string, string[]>;
  xsd_valid: boolean;
  executable: boolean;
  admitted: boolean;
  validation_status: string;
  xsd_report: Record<string, unknown>;
  semantic_report: Record<string, unknown>;
  admission_report: Record<string, unknown>;
}

export interface NetworkValidation {
  version_id: string;
  network_id: string;
  xsd_report: Record<string, unknown>;
  semantic_report: Record<string, unknown>;
  admission_report: Record<string, unknown>;
  xsd_valid: boolean;
  executable: boolean;
  admitted: boolean;
}

export interface ModelBundle {
  workflow: string;
  revision: number;
  bundle_hash: string | null;
  pins: Record<string, unknown>[];
}

export interface BundlePinInput {
  question_key: string;
  network_version_id: string;
  review: { decision: string; reviewer: string; date: string };
}

function networkError(status: number, fallback: string): Error {
  if (status === 401) {
    return statusError("Log in to continue.", 401);
  }
  if (status === 403) {
    return statusError("Access denied.", 403);
  }
  return statusError(fallback, status);
}

export async function listNetworks(): Promise<NetworkItem[]> {
  const response = await fetch("/api/v1/networks", { credentials: "include" });
  if (!response.ok) {
    throw networkError(response.status, "Could not load networks.");
  }
  const payload = (await response.json()) as { items: NetworkItem[] };
  return payload.items ?? [];
}

export async function importNetwork(xml: string): Promise<{
  network_id: string;
  version_id: string;
  version_number: number;
  sha256: string;
  byte_count: number;
}> {
  const response = await fetch("/api/v1/networks", {
    method: "POST",
    credentials: "include",
    headers: csrfHeaders({ "Idempotency-Key": idempotencyKey() }),
    body: JSON.stringify({ xml }),
  });
  if (response.status === 422) {
    throw statusError("Invalid network XML.", 422);
  }
  if (!response.ok) {
    throw networkError(response.status, "Could not import the network.");
  }
  const body = (await response.json()) as Record<string, unknown>;
  return {
    network_id: String(body.network_id ?? body.id ?? ""),
    version_id: String(body.version_id ?? ""),
    version_number: Number(body.version_number ?? 1),
    sha256: String(body.sha256 ?? body.source_sha256 ?? ""),
    byte_count: Number(body.byte_count ?? 0),
  };
}

export async function listNetworkVersions(
  networkId: string,
): Promise<NetworkVersionItem[]> {
  const response = await fetch(`/api/v1/networks/${networkId}/versions`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw networkError(response.status, "Could not load versions.");
  }
  const payload = (await response.json()) as {
    items?: Record<string, unknown>[];
    versions?: Record<string, unknown>[];
  };
  const raw = payload.items ?? payload.versions ?? [];
  return raw.map((entry) => {
    const versionId = String(entry.version_id ?? entry.id ?? "");
    const versionNumber = Number(entry.version_number ?? entry.version ?? 0);
    const sha = String(entry.sha256 ?? entry.source_sha256 ?? "");
    return {
      version_id: versionId,
      id: versionId,
      version_number: versionNumber,
      version: versionNumber,
      sha256: sha,
      source_sha256: sha,
      byte_count: Number(entry.byte_count ?? 0),
      xsd_valid: Boolean(entry.xsd_valid === true),
    };
  });
}

export async function addNetworkVersion(
  networkId: string,
  xml: string,
): Promise<{ version_id: string; version_number: number; sha256: string }> {
  const response = await fetch(`/api/v1/networks/${networkId}/versions`, {
    method: "POST",
    credentials: "include",
    headers: csrfHeaders({ "Idempotency-Key": idempotencyKey() }),
    body: JSON.stringify({ xml }),
  });
  if (response.status === 422) {
    throw statusError("Invalid network XML.", 422);
  }
  if (!response.ok) {
    throw networkError(response.status, "Could not add the version.");
  }
  const body = (await response.json()) as Record<string, unknown>;
  return {
    version_id: String(body.version_id ?? ""),
    version_number: Number(body.version_number ?? 0),
    sha256: String(body.sha256 ?? body.source_sha256 ?? ""),
  };
}

export async function getNetworkGraph(versionId: string): Promise<NetworkGraph> {
  const response = await fetch(`/api/v1/network-versions/${versionId}/graph`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw networkError(response.status, "Could not load the graph.");
  }
  return (await response.json()) as NetworkGraph;
}

export async function validateNetworkVersion(
  versionId: string,
): Promise<NetworkValidation> {
  const response = await fetch(
    `/api/v1/network-versions/${versionId}/validate`,
    {
      method: "POST",
      credentials: "include",
      headers: csrfHeaders(),
      body: JSON.stringify({}),
    },
  );
  if (!response.ok) {
    throw networkError(response.status, "Could not validate the version.");
  }
  return (await response.json()) as NetworkValidation;
}

export function networkVersionXmlUrl(versionId: string): string {
  return `/api/v1/network-versions/${versionId}/xml`;
}

export async function getModelBundle(workflow: string): Promise<ModelBundle> {
  const response = await fetch(`/api/v1/model-bundles/${workflow}`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw networkError(response.status, "Could not load the bundle.");
  }
  return (await response.json()) as ModelBundle;
}

export async function activateModelBundle(body: {
  workflow: string;
  pins: BundlePinInput[];
  expected_revision: number;
}): Promise<ModelBundle> {
  const response = await fetch("/api/v1/model-bundles/activate", {
    method: "POST",
    credentials: "include",
    headers: csrfHeaders({ "Idempotency-Key": idempotencyKey() }),
    body: JSON.stringify(body),
  });
  if (response.status === 412) {
    throw statusError(
      "Bundle changed. Reload and reconcile your edits.",
      412,
    );
  }
  if (response.status === 422) {
    let detail = "Invalid bundle.";
    try {
      const payload = (await response.clone().text()) as string;
      if (payload) {
        detail = payload.slice(0, 500);
      }
    } catch {
      /* keep generic message */
    }
    throw statusError(detail, 422);
  }
  if (!response.ok) {
    throw networkError(response.status, "Could not activate the bundle.");
  }
  return (await response.json()) as ModelBundle;
}

export async function rollbackModelBundle(body: {
  workflow: string;
  target_revision: number;
  expected_revision: number;
}): Promise<ModelBundle> {
  const response = await fetch("/api/v1/model-bundles/rollback", {
    method: "POST",
    credentials: "include",
    headers: csrfHeaders({ "Idempotency-Key": idempotencyKey() }),
    body: JSON.stringify(body),
  });
  if (response.status === 412) {
    throw statusError(
      "Bundle changed. Reload and reconcile your edits.",
      412,
    );
  }
  if (!response.ok) {
    throw networkError(response.status, "Could not roll back the bundle.");
  }
  return (await response.json()) as ModelBundle;
}
/** S48 run client: proposal-review entry, read, and precise retry (T1 routes).
 * Errors carry server detail for 403/409/412/422 (author-only and revision
 * messages); 401 maps to a login prompt. No secrets ever enter state/errors.
 */
export interface RunStartResult {
  schema_version: number;
  run_id: string;
  revision: number;
  status: string;
  questions: string[];
}

export interface RunProjection {
  question_key: string;
  projection_hash: string;
  projection: Record<string, unknown>;
  applicability: string;
  applicability_reason: string;
}

export interface RunJob {
  question_key: string;
  ordinal: number;
  stage: string;
  status: string;
  attempt_count: number;
  fencing_generation: number;
  failure_details: Record<string, unknown> | null;
}

export interface RunSection {
  question_key: string;
  network_version: unknown;
  patient_inputs: unknown;
  cpt_percentages: unknown;
  result: unknown;
  prompt: unknown;
  model: unknown;
  effective_hash: unknown;
  query: unknown;
  rendered_text: string;
  engine: unknown;
  template_version: unknown;
  source_paths: unknown;
  missingness: unknown;
  status: string;
}

export interface RunInfo {
  id: string;
  encounter_id: string;
  encounter_revision: number;
  workflow: string;
  status: string;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface RunDetail {
  schema_version: number;
  run: RunInfo;
  snapshot_hash: string;
  fingerprint: string;
  stale: boolean;
  projections: RunProjection[];
  pinned: Record<string, unknown>;
  jobs: RunJob[];
  sections: RunSection[];
  proposal: Record<string, unknown> | null;
}

export interface RunRetryBody {
  question_key: string;
  failed_stage: string;
  expected_run_revision: number;
}

export function newIdempotencyKey(): string {
  return idempotencyKey();
}

async function runResponseOrThrow(
  response: Response,
  fallback: string,
): Promise<unknown> {
  if (response.status === 401) {
    throw statusError("Log in to continue.", 401);
  }
  if (
    response.status === 403 ||
    response.status === 409 ||
    response.status === 412 ||
    response.status === 422
  ) {
    let detail = fallback;
    try {
      const payload = (await response.clone().json()) as {
        detail?: unknown;
      };
      if (typeof payload.detail === "string" && payload.detail.trim() !== "") {
        detail = payload.detail;
      }
    } catch {
      /* keep fallback; never leak transport internals */
    }
    throw statusError(detail, response.status);
  }
  if (!response.ok) {
    throw statusError(fallback, response.status);
  }
  return response.json();
}

/** S48 entry: flush first (caller-owned), then POST once with live revision. */
export async function startRun(
  encounterId: string,
  revision: number,
  key: string,
): Promise<RunStartResult> {
  const response = await fetch(`/api/v1/encounters/${encounterId}/runs`, {
    method: "POST",
    credentials: "include",
    headers: {
      ...csrfHeaders(),
      "If-Match": String(revision),
      "Idempotency-Key": key,
    },
    body: JSON.stringify({ encounter_revision: revision }),
  });
  return (await runResponseOrThrow(
    response,
    "Could not start the run.",
  )) as RunStartResult;
}

/** S48 read: persisted run detail (projections/jobs/sections/proposal). */
export async function getRun(runId: string): Promise<RunDetail> {
  const response = await fetch(`/api/v1/runs/${runId}`, {
    credentials: "include",
  });
  if (response.status === 401) {
    throw statusError("Log in to continue.", 401);
  }
  if (response.status === 403) {
    let detail = "Only the run author may read it.";
    try {
      const payload = (await response.clone().json()) as {
        detail?: unknown;
      };
      if (typeof payload.detail === "string" && payload.detail.trim() !== "") {
        detail = payload.detail;
      }
    } catch {
      /* keep fallback */
    }
    throw statusError(detail, 403);
  }
  if (!response.ok) {
    throw statusError("Could not load the run.", response.status);
  }
  return (await response.json()) as RunDetail;
}

/** S48 precise retry: one failed question, live run revision, failed stage. */
export async function retryRun(
  runId: string,
  body: RunRetryBody,
): Promise<unknown> {
  const response = await fetch(`/api/v1/runs/${runId}/retry`, {
    method: "POST",
    credentials: "include",
    headers: csrfHeaders(),
    body: JSON.stringify(body),
  });
  return runResponseOrThrow(response, "Could not retry the question.");
}
/** S50 signing client (T1 routes): secondary plan, sign, snapshot, addenda.
 * Errors carry server detail for 403/409/412/422; 401 maps to a login
 * prompt. No secrets ever enter state/errors.
 */
export interface SecondaryPlanState {
  revision: number;
  text: string;
}

export async function getSecondaryPlan(
  encounterId: string,
): Promise<SecondaryPlanState | null> {
  const response = await fetch(`/api/v1/encounters/${encounterId}/secondary-plan`, {
    credentials: "include",
  });
  if (response.status === 401) {
    throw statusError("Log in to continue.", 401);
  }
  if (!response.ok) {
    throw statusError("Could not load the secondary plan.", response.status);
  }
  const payload = (await response.json()) as {
    secondary_plan?: { revision: number; text: string } | null;
    current?: { revision: number; text: string } | null;
  };
  const current = payload.secondary_plan ?? payload.current ?? null;
  if (current === null) {
    return null;
  }
  return { revision: current.revision ?? 0, text: current.text ?? "" };
}

export async function saveSecondaryPlan(
  encounterId: string,
  text: string,
  revision: number,
  key: string,
): Promise<SecondaryPlanState> {
  const response = await fetch(`/api/v1/encounters/${encounterId}/secondary-plan`, {
    method: "PATCH",
    credentials: "include",
    headers: {
      ...csrfHeaders(),
      "If-Match": String(revision),
      "Idempotency-Key": key,
    },
    body: JSON.stringify({ text }),
  });
  const payload = (await runResponseOrThrow(
    response,
    "Could not save the secondary plan.",
  )) as { secondary_plan?: { revision: number; text: string } };
  const plan = payload.secondary_plan;
  if (plan === undefined || typeof plan.revision !== "number") {
    throw statusError("Could not save the secondary plan.", 500);
  }
  return { revision: plan.revision, text: plan.text ?? "" };
}

export interface SignBody {
  encounter_revision: number;
  run_id: string;
  secondary_plan_revision: number;
  review_acknowledgments: string[];
  baseline_acknowledgment: boolean;
}

export interface SignResult {
  encounter: {
    id: string;
    kind: string;
    state: string;
    revision: number;
    author_id: string | null;
  };
  signed_snapshot: Record<string, unknown>;
  signature?: string;
  snapshot_hash?: string;
}

export async function signEncounter(
  encounterId: string,
  body: SignBody,
  encounterRevision: number,
  key: string,
): Promise<SignResult> {
  const response = await fetch(`/api/v1/encounters/${encounterId}/sign`, {
    method: "POST",
    credentials: "include",
    headers: {
      ...csrfHeaders(),
      "If-Match": String(encounterRevision),
      "Idempotency-Key": key,
    },
    body: JSON.stringify(body),
  });
  return (await runResponseOrThrow(
    response,
    "Could not sign the plan.",
  )) as SignResult;
}

export async function getSignedSnapshot(
  encounterId: string,
): Promise<Record<string, unknown> | null> {
  const response = await fetch(`/api/v1/encounters/${encounterId}/signed-snapshot`, {
    credentials: "include",
  });
  if (response.status === 401) {
    throw statusError("Log in to continue.", 401);
  }
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw statusError("Could not load the signed record.", response.status);
  }
  const payload = (await response.json()) as {
    signed_snapshot?: Record<string, unknown>;
  };
  return payload.signed_snapshot ?? null;
}

export interface Addendum {
  id: string;
  reason: string;
  correction_text: string;
  author_id: string | null;
  created_at: string;
}

export async function listAddenda(encounterId: string): Promise<Addendum[]> {
  const response = await fetch(`/api/v1/encounters/${encounterId}/addenda`, {
    credentials: "include",
  });
  if (response.status === 401) {
    throw statusError("Log in to continue.", 401);
  }
  if (!response.ok) {
    throw statusError("Could not load addenda.", response.status);
  }
  const payload = (await response.json()) as { items: Addendum[] };
  return payload.items ?? [];
}

export async function addAddendum(
  encounterId: string,
  reason: string,
  correctionText: string,
  key: string,
): Promise<Addendum> {
  const response = await fetch(`/api/v1/encounters/${encounterId}/addenda`, {
    method: "POST",
    credentials: "include",
    headers: {
      ...csrfHeaders(),
      "Idempotency-Key": key,
    },
    body: JSON.stringify({ reason, correction_text: correctionText }),
  });
  const payload = (await runResponseOrThrow(
    response,
    "Could not save the addendum.",
  )) as { addendum: Addendum };
  return payload.addendum;
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

/** S20 medications/DDI client: catalog search + pinned versioned check. */
export interface DrugSearchResult {
  concept_id: string;
  canonical_name: string;
}

export async function searchDrugs(
  query: string,
): Promise<{ catalog_version: string; results: DrugSearchResult[] }> {
  const params = new URLSearchParams({ query, limit: "25" });
  const response = await fetch(`/api/v1/drugs?${params}`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw Object.assign(new Error("Catalog unavailable."), {
      status: response.status,
    });
  }
  return (await response.json()) as {
    catalog_version: string;
    results: DrugSearchResult[];
  };
}

export async function getDdiCurrent(): Promise<{
  dataset_version: string;
  catalog_version: string;
  dataset_hash: string;
}> {
  const response = await fetch("/api/v1/ddi/current", {
    credentials: "include",
  });
  if (!response.ok) {
    throw Object.assign(new Error("DDI dataset unavailable."), {
      status: response.status,
    });
  }
  return (await response.json()) as {
    dataset_version: string;
    catalog_version: string;
    dataset_hash: string;
  };
}

export interface DdiReport {
  dataset_version: string;
  catalog_version?: string;
  dataset_hash?: string;
  medication_fingerprint: string;
  generated_at?: string;
  resolved_medications?: unknown[];
  unresolved_medications?: unknown[];
  pairs?: Array<{
    pair_key: string;
    drug_a: string;
    drug_b: string;
    status: string;
    highest_known_severity: string | null;
    has_unknown_severity: boolean;
    conflicts?: Array<{ source_severity: string; source_path?: string }>;
    evidence?: Array<{
      source_severity?: string;
      direction?: unknown;
      raw_text?: string;
      management?: string | null;
      source_path?: string;
      span?: unknown;
    }>;
    coverage_basis?: string;
  }>;
  limitations?: string[];
}

/** S52 audit trail client (T9): admin-only, references only, never bodies.
 * List items carry id, occurred_at (UTC-Z), actor_id, actor_display,
 * operation, result_reference, target_display, details, request_id plus
 * next_cursor. Detail adds result_status + truncated (never result_payload).
 */
export interface AuditEvent {
  id: string;
  occurred_at: string;
  actor_id: string | null;
  actor_display: string;
  operation: string;
  result_reference: string | null;
  target_display: string | null;
  details: unknown;
  request_id: string;
}

export interface AuditEventDetail extends AuditEvent {
  result_status: number | null;
  truncated: boolean;
}

export interface AuditList {
  schema_version: number;
  items: AuditEvent[];
  next_cursor: string | null;
}

export async function listAuditEvents(params?: {
  actor_id?: string;
  operation?: string;
  since?: string;
  until?: string;
  target?: string;
  cursor?: string;
  limit?: number;
}): Promise<AuditList> {
  const query = new URLSearchParams({
    limit: String(params?.limit ?? 25),
  });
  if (params?.actor_id) {
    query.set("actor_id", params.actor_id);
  }
  if (params?.operation) {
    query.set("operation", params.operation);
  }
  if (params?.since) {
    query.set("since", params.since);
  }
  if (params?.until) {
    query.set("until", params.until);
  }
  if (params?.target) {
    query.set("target", params.target);
  }
  if (params?.cursor) {
    query.set("cursor", params.cursor);
  }
  const response = await fetch(`/api/v1/audit-events?${query}`, {
    credentials: "include",
  });
  if (response.status === 403) {
    throw statusError("Access denied.", 403);
  }
  if (!response.ok) {
    throw statusError("Could not load audit events.", response.status);
  }
  return (await response.json()) as AuditList;
}

export async function getAuditEvent(id: string): Promise<AuditEventDetail> {
  const response = await fetch(`/api/v1/audit-events/${id}`, {
    credentials: "include",
  });
  if (response.status === 403) {
    throw statusError("Access denied.", 403);
  }
  if (!response.ok) {
    throw statusError("Could not load the audit event.", response.status);
  }
  return (await response.json()) as AuditEventDetail;
}
/** S53 printable report + CSV exports (T9): escaped server HTML + admin CSVs.
 * The report body is server-escaped HTML; the caller must embed it sandboxed
 * (iframe srcdoc) and never via dangerouslySetInnerHTML.
 */
export async function fetchPatientReportHtml(
  patientUuid: string,
): Promise<string> {
  const response = await fetch(`/api/v1/patients/${patientUuid}/report`, {
    credentials: "include",
  });
  if (response.status === 401) {
    throw statusError("Log in to continue.", 401);
  }
  if (response.status === 403) {
    throw statusError("Access denied.", 403);
  }
  if (!response.ok) {
    throw statusError("Could not load the report.", response.status);
  }
  return response.text();
}

export function patientsCsvUrl(): string {
  return "/api/v1/exports/patients.csv";
}

export function physiciansCsvUrl(): string {
  return "/api/v1/exports/physicians.csv";
}

/** Authenticated CSV download via a blob anchor (cookies ride the fetch). */
export async function downloadCsv(url: string, filename: string): Promise<string> {
  const response = await fetch(url, { credentials: "include" });
  if (response.status === 401) {
    throw statusError("Log in to continue.", 401);
  }
  if (response.status === 403) {
    throw statusError("Access denied.", 403);
  }
  if (!response.ok) {
    throw statusError("Could not export the list.", response.status);
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    setTimeout(() => URL.revokeObjectURL(objectUrl), 5000);
  }
  return filename;
}
export async function checkDdi(
  dataset_version: string,
  medications: Array<Record<string, string>>,
): Promise<DdiReport> {
  const csrf = csrfToken();
  const response = await fetch("/api/v1/ddi/check", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRF-Token": csrf } : {}),
    },
    body: JSON.stringify({ dataset_version, medications }),
  });
  if (!response.ok) {
    throw Object.assign(new Error("DDI check failed."), {
      status: response.status,
    });
  }
  return (await response.json()) as DdiReport;
}

/** S54 admin backup client (T9): create, poll, download.
 * The manifest carries inventory/checksums only — no secret values.
 */
export interface BackupJob {
  schema_version: number;
  job_id: string;
  status: string;
  error: string | null;
  manifest: Record<string, unknown> | null;
}

export async function createBackup(): Promise<{
  job_id: string;
  status: string;
}> {
  const response = await fetch("/api/v1/backups", {
    method: "POST",
    credentials: "include",
    headers: csrfHeaders({ "Idempotency-Key": idempotencyKey() }),
    body: JSON.stringify({}),
  });
  if (response.status === 403) {
    throw statusError("Access denied.", 403);
  }
  if (response.status === 429) {
    throw statusError("A backup build is already running.", 429);
  }
  if (!response.ok) {
    throw statusError("Could not start the backup.", response.status);
  }
  return (await response.json()) as { job_id: string; status: string };
}

export async function getBackup(jobId: string): Promise<BackupJob> {
  const response = await fetch(`/api/v1/backups/${jobId}`, {
    credentials: "include",
  });
  if (response.status === 403) {
    throw statusError("Access denied.", 403);
  }
  if (!response.ok) {
    throw statusError("Could not load the backup.", response.status);
  }
  return (await response.json()) as BackupJob;
}

export function backupDownloadUrl(jobId: string): string {
  return `/api/v1/backups/${jobId}/download`;
}

/** S55 staged-restore validation client (T1 routes): validate + read.
 * Payloads carry inventory/checksums only — no secret values. Errors carry
 * safe server text; 403 maps to the shared guard message. There is no commit
 * route (S56 owns it); the UI never fires one. */
export interface RestoreReport {
  schema_version: number;
  backup_id: string;
  backup_timestamp: string | null;
  db_schema_revision: string;
  app_version: string;
  archive_sha256: string;
  tables: Record<string, number>;
  files: Array<{ path: string; sha256: string; bytes: number }>;
  coverage?: unknown;
  impact: {
    live: Record<string, number>;
    staged: Record<string, number>;
  };
  key_reentry_note: string;
  staged_at: string;
  expires_at: string;
}

export interface RestoreValidation {
  schema_version: number;
  restore_id: string;
  status: string;
  confirmation_digest: string;
  report: RestoreReport;
}

export interface RestoreStatus {
  schema_version: number;
  restore_id: string;
  status: string;
  confirmation_digest: string | null;
  expired: boolean;
  superseded: boolean;
  report: RestoreReport | null;
  error: string | null;
}

export async function validateRestore(file: File): Promise<RestoreValidation> {
  const form = new FormData();
  form.append("archive", file, file.name);
  const csrf = csrfToken();
  const response = await fetch("/api/v1/restores/validate", {
    method: "POST",
    credentials: "include",
    headers: {
      ...(csrf ? { "X-CSRF-Token": csrf } : {}),
      "Idempotency-Key": idempotencyKey(),
    },
    body: form,
  });
  if (response.status === 403) {
    throw statusError("Access denied.", 403);
  }
  if (response.status === 409) {
    let detail = "Idempotency key was used for another request.";
    try {
      const payload = (await response.clone().json()) as { detail?: unknown };
      if (typeof payload.detail === "string" && payload.detail.trim() !== "") {
        detail = payload.detail;
      }
    } catch {
      /* keep fallback */
    }
    throw statusError(detail, 409);
  }
  if (response.status === 422) {
    let detail = "Backup archive failed validation.";
    let fieldCode = "";
    try {
      const payload = (await response.clone().json()) as {
        message?: unknown;
        field_errors?: unknown;
      };
      if (typeof payload.message === "string" && payload.message.trim() !== "") {
        detail = payload.message;
      }
      const fields = payload.field_errors as Record<string, unknown> | undefined;
      if (fields !== undefined && typeof fields.archive === "string") {
        fieldCode = fields.archive;
      }
    } catch {
      /* keep fallback */
    }
    throw statusError(
      fieldCode !== "" ? `${detail} (archive: ${fieldCode})` : detail,
      422,
    );
  }
  if (!response.ok) {
    throw statusError("Could not validate the archive.", response.status);
  }
  return (await response.json()) as RestoreValidation;
}

export async function getRestore(restoreId: string): Promise<RestoreStatus> {
  const response = await fetch(`/api/v1/restores/${restoreId}`, {
    credentials: "include",
  });
  if (response.status === 403) {
    throw statusError("Access denied.", 403);
  }
  if (!response.ok) {
    throw statusError("Could not load the staged restore.", response.status);
  }
  return (await response.json()) as RestoreStatus;
}
