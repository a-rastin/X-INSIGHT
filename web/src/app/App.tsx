import { useCallback, useEffect, useRef, useState } from "react";
import "../shared/theme.css";
import {
  RESEARCH_NOTICE,
  activateModelBundle,
  addAddendum,
  addNetworkVersion,
  archivePatient,
  changeOwnPassword,
  checkDdi,
  createFollowup,
  createPhysician,
  createPatient,
  deactivatePhysician,
  discardEncounter,
  fetchSession,
  addNote,
  getDdiCurrent,
  getDeactivationReview,
  getEncounter,
  getHistoryContent,
  getModelBundle,
  getNetworkGraph,
  getProviderSettings,
  getRun,
  getSecondaryPlan,
  getSignedSnapshot,
  importNetwork,
  listAddenda,
  listNetworks,
  listNetworkVersions,
  listNotes,
  listEncounters,
  listPhysicians,
  listProviderVersions,
  login,
  logout,
  listPatients,
  networkVersionXmlUrl,
  newIdempotencyKey,
  patchEncounter,
  patchPatientPhone,
  retryRun,
  rollbackModelBundle,
  saveProviderSettings,
  saveSecondaryPlan,
  searchDrugs,
  signEncounter,
  startRun,
  testProviderSettings,
  unarchivePatient,
  updateTheme,
  validateNetworkVersion,
  type Addendum,
  type BundlePinInput,
  type DdiReport,
  type DeactivationReview,
  type DrugSearchResult,
  type Encounter,
  type HistoryContent,
  type ModelBundle,
  type NetworkGraph,
  type NetworkValidation,
  type NetworkVersionItem,
  type PageNote,
  type Patient,
  type PhysicianAccount,
  type ProviderSettings,
  type RunDetail,
  type SessionUser,
  type ThemeName,
} from "./api";

type Route = "/" | "/register" | "/physicians" | "/provider-settings" | "/networks";

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

/** S10 PANSS preview (mirrors backend evaluate_panss sums, no I/O). */
const PANSS_POSITIVE_IDS = ["P1", "P2", "P3", "P4", "P5", "P6", "P7"];
const PANSS_NEGATIVE_IDS = ["N1", "N2", "N3", "N4", "N5", "N6", "N7"];
const PANSS_GENERAL_IDS = [
  "G1",
  "G2",
  "G3",
  "G4",
  "G5",
  "G6",
  "G7",
  "G8",
  "G9",
  "G10",
  "G11",
  "G12",
  "G13",
  "G14",
  "G15",
  "G16",
];
const PANSS_ALL_IDS = [
  ...PANSS_POSITIVE_IDS,
  ...PANSS_NEGATIVE_IDS,
  ...PANSS_GENERAL_IDS,
];

const PANSS_PROMPTS: Record<string, string> = {
  P1: "Does the person hold fixed, implausible beliefs that are not shared by the person’s cultural or social context and are resistant to evidence?",
  P2: "Is the person’s thinking or speech difficult to follow because of loose associations, tangentiality, incoherence, or derailment?",
  P3: "Does the person report or appear to respond to perceptual experiences without an external stimulus?",
  P4: "Is there unusually increased activation, energy, motor activity, or emotional intensity?",
  P5: "Does the person express an exaggerated sense of power, importance, ability, identity, or status?",
  P6: "Does the person show suspiciousness or beliefs that others intend to harm, exploit, monitor, or persecute them?",
  P7: "Does the person show verbal or physical hostility, anger, resentment, or aggression toward others?",
  N1: "Is the person’s emotional expression noticeably reduced in facial expression, voice, gestures, or emotional responsiveness?",
  N2: "Does the person show reduced involvement in relationships and limited emotional contact with others?",
  N3: "Is it difficult to establish a natural, cooperative, and empathetic interpersonal relationship with the person?",
  N4: "Does the person show reduced interest, initiative, or participation in social interaction?",
  N5: "Does the person have difficulty moving beyond concrete or literal thinking when asked to interpret concepts, similarities, or proverbs?",
  N6: "Is the person’s conversation reduced in spontaneous initiation, productivity, or conversational flow?",
  N7: "Is the person’s thinking repetitive, rigid, simplistic, or stereotyped?",
  G1: "Is the person excessively concerned about physical health, bodily symptoms, or illness?",
  G2: "Does the person show excessive fear, worry, apprehension, or nervousness?",
  G3: "Does the person experience excessive or inappropriate guilt, self-blame, or remorse?",
  G4: "Does the person show observable or reported physical and psychological tension, restlessness, or agitation?",
  G5: "Are there unusual, odd, artificial, or socially inappropriate movements, gestures, poses, or mannerisms?",
  G6: "Does the person show a depressed mood, hopelessness, sadness, or reduced interest and pleasure?",
  G7: "Is there a noticeable slowing of movement, speech, or activity?",
  G8: "Does the person resist the interview, treatment, or reasonable requests without adequate explanation?",
  G9: "Does the person express unusual, implausible, or bizarre ideas that do not meet the threshold for a fixed delusion?",
  G10: "Is the person confused about time, place, person, or the current situation?",
  G11: "Does the person have difficulty sustaining, shifting, or directing attention during the interview?",
  G12: "Does the person have impaired understanding of their condition, symptoms, consequences, or need for help?",
  G13: "Is there reduced ability to initiate, sustain, or direct purposeful activity?",
  G14: "Does the person have difficulty controlling urges or behavior, with risk of sudden or poorly considered actions?",
  G15: "Is the person excessively absorbed in internal thoughts, feelings, or ideas in a way that interferes with the interview or functioning?",
  G16: "Does the person deliberately avoid social contact because of fear, distrust, hostility, or unusual beliefs?",
};

type PanssAnswers = Record<string, number | null>;

function emptyPanssAnswers(): PanssAnswers {
  const out: PanssAnswers = {};
  for (const id of PANSS_ALL_IDS) {
    out[id] = null;
  }
  return out;
}

function panssFromStored(stored: unknown): {
  answers: PanssAnswers;
  notAssessed: boolean;
} {
  const base = emptyPanssAnswers();
  if (typeof stored !== "object" || stored === null) {
    return { answers: base, notAssessed: false };
  }
  const raw = stored as Record<string, unknown>;
  if (raw.not_assessed === true) {
    return { answers: base, notAssessed: true };
  }
  const answersRaw =
    typeof raw.answers === "object" && raw.answers !== null
      ? (raw.answers as Record<string, unknown>)
      : null;
  if (answersRaw === null) {
    return { answers: base, notAssessed: false };
  }
  for (const id of PANSS_ALL_IDS) {
    const value = answersRaw[id];
    if (typeof value === "number" && Number.isInteger(value) && value >= 1 && value <= 7) {
      base[id] = value;
    } else {
      base[id] = null;
    }
  }
  return { answers: base, notAssessed: false };
}

function previewPanss(
  answers: PanssAnswers,
  notAssessed: boolean,
): {
  status: "skipped" | "unanswered" | "partial" | "complete";
  positive: number | null;
  negative: number | null;
  general: number | null;
  total: number | null;
  answered: number;
  missing: number;
} {
  if (notAssessed) {
    return {
      status: "skipped",
      positive: null,
      negative: null,
      general: null,
      total: null,
      answered: 0,
      missing: PANSS_ALL_IDS.length,
    };
  }
  const missingIds = PANSS_ALL_IDS.filter((id) => answers[id] === null || answers[id] === undefined);
  const answered = PANSS_ALL_IDS.length - missingIds.length;
  if (missingIds.length === PANSS_ALL_IDS.length) {
    return {
      status: "unanswered",
      positive: null,
      negative: null,
      general: null,
      total: null,
      answered,
      missing: missingIds.length,
    };
  }
  if (missingIds.length > 0) {
    return {
      status: "partial",
      positive: null,
      negative: null,
      general: null,
      total: null,
      answered,
      missing: missingIds.length,
    };
  }
  let positive = 0;
  for (const id of PANSS_POSITIVE_IDS) {
    positive += answers[id] as number;
  }
  let negative = 0;
  for (const id of PANSS_NEGATIVE_IDS) {
    negative += answers[id] as number;
  }
  let general = 0;
  for (const id of PANSS_GENERAL_IDS) {
    general += answers[id] as number;
  }
  return {
    status: "complete",
    positive,
    negative,
    general,
    total: positive + negative + general,
    answered,
    missing: 0,
  };
}

function serializePanss(
  answers: PanssAnswers,
  notAssessed: boolean,
): Record<string, unknown> | undefined {
  if (notAssessed) {
    return { not_assessed: true };
  }
  const out: Record<string, unknown> = {};
  for (const id of PANSS_ALL_IDS) {
    const value = answers[id];
    if (typeof value === "number" && Number.isInteger(value) && value >= 1 && value <= 7) {
      out[id] = value;
    }
  }
  if (Object.keys(out).length === 0) {
    return undefined;
  }
  return { answers: out };
}

function panssDirtyKey(answers: PanssAnswers, notAssessed: boolean): string {
  const ordered: Record<string, unknown> = {};
  for (const id of PANSS_ALL_IDS) {
    ordered[id] = answers[id] ?? null;
  }
  return JSON.stringify({ answers: ordered, notAssessed });
}

/** S11 slice 4 C-SSRS ideation helpers (mirror backend evaluate_cssrs, no I/O). */
type CssrsLevelId = "L1" | "L2" | "L3" | "L4" | "L5";
type CssrsPeriod = "current" | "historical";
type CssrsLevel = { endorsed: boolean | null; period: CssrsPeriod | null };
type CssrsLevels = Record<CssrsLevelId, CssrsLevel>;

const CSSRS_IDS: CssrsLevelId[] = ["L1", "L2", "L3", "L4", "L5"];

const CSSRS_PROMPTS: Record<CssrsLevelId, { construct: string; question: string }> = {
  L1: {
    construct: "Wish to be dead",
    question: "Have you wished you were dead, or wished you could go to sleep and not wake up?",
  },
  L2: {
    construct: "Nonspecific active thoughts",
    question: "Have you had thoughts of killing yourself, without thinking about a method, intent, or plan?",
  },
  L3: {
    construct: "Method, without intent",
    question: "Have you thought about how you might kill yourself, without intending to act on those thoughts?",
  },
  L4: {
    construct: "Some intent, no specific plan",
    question: "Have you had suicidal thoughts and some intention of acting on them, but without a specific plan?",
  },
  L5: {
    construct: "Specific plan and intent",
    question: "Have you worked out a method or plan for killing yourself, and do you intend to carry it out?",
  },
};

function emptyCssrs(): CssrsLevels {
  return {
    L1: { endorsed: null, period: null },
    L2: { endorsed: null, period: null },
    L3: { endorsed: null, period: null },
    L4: { endorsed: null, period: null },
    L5: { endorsed: null, period: null },
  };
}

function cssrsFromStored(stored: unknown): {
  levels: CssrsLevels;
  notAssessed: boolean;
  extra: Record<string, unknown>;
} {
  const base = emptyCssrs();
  if (typeof stored !== "object" || stored === null) {
    return { levels: base, notAssessed: false, extra: {} };
  }
  const raw = stored as Record<string, unknown>;
  if (raw.not_assessed === true) {
    return { levels: base, notAssessed: true, extra: {} };
  }
  const answersRaw =
    typeof raw.answers === "object" && raw.answers !== null
      ? (raw.answers as Record<string, unknown>)
      : null;
  if (answersRaw === null) {
    return { levels: base, notAssessed: false, extra: {} };
  }
  const extra: Record<string, unknown> = {};
  for (const key of ["intensity", "behavior", "lethality"]) {
    if (key in answersRaw) {
      extra[key] = answersRaw[key];
    } else if (key in raw) {
      extra[key] = raw[key];
    }
  }
  for (const id of CSSRS_IDS) {
    const entry = answersRaw[id];
    if (typeof entry !== "object" || entry === null) {
      base[id] = { endorsed: null, period: null };
      continue;
    }
    const rec = entry as Record<string, unknown>;
    const endorsed = rec.endorsed === true ? true : rec.endorsed === false ? false : null;
    const period =
      rec.period === "current" || rec.period === "historical" ? rec.period : null;
    base[id] = { endorsed, period: endorsed === true ? period : null };
  }
  return { levels: base, notAssessed: false, extra };
}

function previewCssrs(
  levels: CssrsLevels,
  notAssessed: boolean,
): {
  status: "skipped" | "unanswered" | "partial" | "complete";
  severity: number | null;
  missing: CssrsLevelId[];
  flags: { no_ideation: boolean; clinical_review: boolean; high_risk: boolean };
} {
  const noFlags = { no_ideation: false, clinical_review: false, high_risk: false };
  if (notAssessed) {
    return { status: "skipped", severity: null, missing: [...CSSRS_IDS], flags: { ...noFlags } };
  }
  const missing = CSSRS_IDS.filter((id) => levels[id]?.endorsed === null || levels[id]?.endorsed === undefined);
  if (missing.length === CSSRS_IDS.length) {
    return { status: "unanswered", severity: null, missing, flags: { ...noFlags } };
  }
  let severity = 0;
  CSSRS_IDS.forEach((id, index) => {
    if (levels[id]?.endorsed === true) {
      severity = index + 1;
    }
  });
  const clinical_review =
    levels.L1?.endorsed === true || levels.L2?.endorsed === true || levels.L3?.endorsed === true;
  const high_risk =
    (levels.L4?.endorsed === true && levels.L4?.period === "current") ||
    (levels.L5?.endorsed === true && levels.L5?.period === "current");
  const no_ideation = CSSRS_IDS.every((id) => levels[id]?.endorsed === false);
  const flags = { no_ideation, clinical_review, high_risk };
  if (missing.length > 0) {
    return { status: "partial", severity, missing, flags };
  }
  return { status: "complete", severity, missing, flags };
}

function serializeCssrs(
  levels: CssrsLevels,
  notAssessed: boolean,
  extra?: Record<string, unknown>,
): Record<string, unknown> | undefined {
  if (notAssessed) {
    return { not_assessed: true };
  }
  const entries: Record<string, unknown> = {};
  CSSRS_IDS.forEach((id) => {
    const level = levels[id];
    if (level?.endorsed === true) {
      // Autosave-safe: a Yes without a period is kept locally (preview +
      // dirty tracking) but withheld from the wire until the period is set,
      // so an intermediate select never trips the backend period rule (422).
      if (level.period === "current" || level.period === "historical") {
        entries[id] = { endorsed: true, period: level.period };
      }
    } else if (level?.endorsed === false) {
      entries[id] = { endorsed: false };
    }
  });
  const preserved = extra ?? {};
  if (Object.keys(entries).length === 0) {
    if (Object.keys(preserved).length === 0) {
      return undefined;
    }
    return { answers: { ...preserved } };
  }
  return { answers: { ...preserved, ...entries } };
}

function cssrsDirtyKey(levels: CssrsLevels, notAssessed: boolean): string {
  const ordered: Record<string, unknown> = {};
  for (const id of CSSRS_IDS) {
    ordered[id] = {
      endorsed: levels[id]?.endorsed ?? null,
      period: levels[id]?.period ?? null,
    };
  }
  return JSON.stringify({ answers: ordered, notAssessed });
}

/**
 * S12 structured history + adverse effects (FR-14/FR-20–21), reusing the S07
 * autosave path (revisionRef/timer/saveState live in DraftEditor; these
 * sections only edit values). Generic over the released definition: field ids
 * and severity enums come from GET /content/history, never hardcoded clinical
 * content. Absent-only effects round-trip without unreleased severity ids.
 * No BARS/SAS/AIMS full questionnaires (FR-21: supporting sources only).
 */
const EFFECT_IDS = [
  "tardive_dyskinesia",
  "akathisia",
  "parkinsonism",
  "acute_dystonia",
] as const;

type EffectId = (typeof EFFECT_IDS)[number];

const EFFECT_LABELS: Record<EffectId, string> = {
  tardive_dyskinesia: "Tardive dyskinesia",
  akathisia: "Akathisia",
  parkinsonism: "Parkinsonism",
  acute_dystonia: "Acute dystonia",
};

type EffectStatus = "present" | "absent" | "not_assessed";
type EffectEntry = { status: EffectStatus | null; severity: string | null };
type EffectsState = Record<EffectId, EffectEntry>;

type HistoryStatus = "known" | "unknown" | "not_assessed";
type HistoryEntry = { status: HistoryStatus; value: boolean | null };
type HistoryState = Record<string, HistoryEntry>;

function emptyEffects(): EffectsState {
  return {
    tardive_dyskinesia: { status: null, severity: null },
    akathisia: { status: null, severity: null },
    parkinsonism: { status: null, severity: null },
    acute_dystonia: { status: null, severity: null },
  };
}

function effectsFromStored(stored: unknown): EffectsState {
  const base = emptyEffects();
  if (typeof stored !== "object" || stored === null) {
    return base;
  }
  const raw = stored as Record<string, unknown>;
  const values =
    typeof raw.values === "object" && raw.values !== null
      ? (raw.values as Record<string, unknown>)
      : null;
  if (values === null) {
    return base;
  }
  for (const id of EFFECT_IDS) {
    const entry = values[id];
    if (typeof entry !== "object" || entry === null) {
      continue;
    }
    const rec = entry as Record<string, unknown>;
    if (rec.status === "present" || rec.status === "absent" || rec.status === "not_assessed") {
      base[id] = {
        status: rec.status,
        severity: typeof rec.severity === "string" ? rec.severity : null,
      };
    }
  }
  return base;
}

function serializeEffects(
  state: EffectsState,
  version: string | null,
): Record<string, unknown> | undefined {
  if (version === null) {
    return undefined;
  }
  for (const id of EFFECT_IDS) {
    const entry = state[id];
    if (entry?.status === null || entry?.status === undefined) {
      return undefined;
    }
    // Autosave-safe: present without a severity is kept locally but withheld
    // from the wire until a reviewed severity is chosen (never 422s a draft).
    if (entry.status === "present" && (entry.severity === null || entry.severity === "")) {
      return undefined;
    }
  }
  const values: Record<string, unknown> = {};
  for (const id of EFFECT_IDS) {
    const entry = state[id];
    values[id] = {
      status: entry.status,
      severity: entry.status === "present" ? entry.severity : null,
    };
  }
  return { definition_version: version, values };
}

function effectsDirtyKey(state: EffectsState): string {
  const ordered: Record<string, unknown> = {};
  for (const id of EFFECT_IDS) {
    ordered[id] = {
      status: state[id]?.status ?? null,
      severity: state[id]?.severity ?? null,
    };
  }
  return JSON.stringify(ordered);
}

function historyFromStored(stored: unknown): HistoryState {
  const out: HistoryState = {};
  if (typeof stored !== "object" || stored === null) {
    return out;
  }
  const raw = stored as Record<string, unknown>;
  const values =
    typeof raw.values === "object" && raw.values !== null
      ? (raw.values as Record<string, unknown>)
      : null;
  if (values === null) {
    return out;
  }
  for (const [id, entry] of Object.entries(values)) {
    if (typeof entry !== "object" || entry === null) {
      continue;
    }
    const rec = entry as Record<string, unknown>;
    if (rec.status === "known" && typeof rec.value === "boolean") {
      out[id] = { status: "known", value: rec.value };
    } else if (
      (rec.status === "unknown" || rec.status === "not_assessed") &&
      rec.value === null
    ) {
      out[id] = { status: rec.status, value: null };
    }
  }
  return out;
}

function serializeHistory(
  state: HistoryState,
  version: string | null,
): Record<string, unknown> | undefined {
  if (version === null) {
    return undefined;
  }
  const values: Record<string, unknown> = {};
  for (const [id, entry] of Object.entries(state)) {
    values[id] = { status: entry.status, value: entry.value };
  }
  if (Object.keys(values).length === 0) {
    return undefined;
  }
  return { definition_version: version, values };
}

function historyDirtyKey(state: HistoryState): string {
  const ordered: Record<string, unknown> = {};
  for (const id of Object.keys(state).sort()) {
    ordered[id] = state[id];
  }
  return JSON.stringify(ordered);
}

function reconFromStored(stored: unknown): Record<string, unknown> | null {
  if (typeof stored === "object" && stored !== null && !Array.isArray(stored)) {
    return stored as Record<string, unknown>;
  }
  return null;
}

/**
 * S12 history section: analysis-visible structured history, rendered
 * distinctly from page notes (notes are never relabeled as history). Generic
 * over the released definition; when no definition is released the section
 * stays visible with an honest unavailable state and sends no history block.
 * Reconciliation is explicit object state, never auto-confirmed (S14 owns
 * copy semantics).
 */
function HistorySection({
  encounterId,
  definition,
  definitionLoaded,
  values,
  reconciliation,
  readOnly,
  onFieldChange,
  onReconChange,
}: {
  encounterId: string;
  definition: HistoryContent | null;
  definitionLoaded: boolean;
  values: HistoryState;
  reconciliation: Record<string, unknown> | null;
  readOnly: boolean;
  onFieldChange: (id: string, raw: string) => void;
  onReconChange: (raw: string) => void;
}) {
  function selectValue(id: string): string {
    const entry = values[id];
    if (!entry) {
      return "";
    }
    if (entry.status === "known") {
      return entry.value === true ? "known_true" : "known_false";
    }
    return entry.status;
  }
  const reconStatus =
    typeof reconciliation?.status === "string" ? String(reconciliation.status) : "";
  const reconSelect =
    reconStatus === "pending" || reconStatus === "confirmed" ? reconStatus : "";
  return (
    <section data-testid="history-section" aria-label="History">
      <h3>History</h3>
      <p>
        Structured history used for analysis. Draft notes are separate and
        never used for analysis.
      </p>
      {!definitionLoaded ? <p>Loading history content…</p> : null}
      {definitionLoaded && definition === null ? (
        <p>Structured history content is pending review — unavailable.</p>
      ) : null}
      {definition !== null
        ? definition.fields.map((field) => (
            <div className="x-field" key={field.id}>
              <label htmlFor={`history-${encounterId}-${field.id}`}>
                {field.id} (analysis-visible)
              </label>
              <select
                id={`history-${encounterId}-${field.id}`}
                data-testid={`history-item-${field.id}`}
                disabled={readOnly}
                value={selectValue(field.id)}
                onChange={(event) => onFieldChange(field.id, event.target.value)}
              >
                <option value="">Select…</option>
                <option value="known_true">Known — yes</option>
                <option value="known_false">Known — no</option>
                <option value="unknown">Unknown</option>
                <option value="not_assessed">Not assessed</option>
              </select>
            </div>
          ))
        : null}
      <div className="x-field">
        <label htmlFor={`recon-${encounterId}`}>History reconciliation</label>
        <select
          id={`recon-${encounterId}`}
          data-testid="history-reconciliation-status"
          disabled={readOnly}
          value={reconSelect}
          onChange={(event) => onReconChange(event.target.value)}
        >
          <option value="">Select…</option>
          <option value="pending">pending</option>
          <option value="confirmed">confirmed</option>
        </select>
        {reconciliation !== null ? (
          <p>Current: {JSON.stringify(reconciliation)}</p>
        ) : (
          <p>No reconciliation recorded.</p>
        )}
      </div>
    </section>
  );
}

/**
 * S12 adverse-effects section: the four FR-21 effects, each with a status
 * select and a severity select. Severity is enabled only when present and is
 * explicitly cleared client-side on status change (absent/not_assessed always
 * send severity null).
 */
/**
 * S13 page notes: attributed, append-only entries rendered separately from
 * structured history. React escapes note text by default; literal markup
 * renders as text, never as HTML. Server derives author/time; corrections
 * are new notes. Notes never enter analysis projections (see backend
 * ANALYSIS_EXCLUDED_TOP_LEVEL_KEYS; S40/S41/S59 prove noninterference).
 */
const NOTE_PAGES = [
  "demographics",
  "diagnosis",
  "severity",
  "suicide",
  "history",
  "review",
  "plan",
] as const;

function NotesSection({
  encounterId,
  readOnly,
}: {
  encounterId: string;
  readOnly: boolean;
}) {
  const [items, setItems] = useState<PageNote[]>([]);
  const [page, setPage] = useState<string>("demographics");
  const [text, setText] = useState("");
  const [status, setStatus] = useState("");
  useEffect(() => {
    let cancelled = false;
    setStatus("");
    listNotes(encounterId)
      .then((loaded) => {
        if (cancelled) return;
        setItems(loaded);
        setStatus("");
      })
      .catch(() => {
        if (!cancelled) setStatus("Could not load notes.");
      });
    return () => {
      cancelled = true;
    };
  }, [encounterId]);
  async function handleAdd(): Promise<void> {
    const trimmed = text.trim();
    if (!trimmed || readOnly) return;
    setStatus("Saving note…");
    try {
      const created = await addNote(encounterId, page, trimmed);
      setItems((prev) => [...prev, created]);
      setText("");
      setStatus("Note saved.");
    } catch {
      setStatus("Could not save the note.");
    }
  }
  return (
    <section data-testid="notes-section" aria-label="Notes">
      <h3>Notes</h3>
      <p>Page notes are separate from structured history and never used for analysis.</p>
      <div className="x-field">
        <label htmlFor={`notes-page-${encounterId}`}>Page</label>
        <select
          id={`notes-page-${encounterId}`}
          data-testid="notes-page"
          value={page}
          disabled={readOnly}
          onChange={(event) => setPage(event.target.value)}
        >
          {NOTE_PAGES.map((id) => (
            <option key={id} value={id}>
              {id}
            </option>
          ))}
        </select>
        <label htmlFor={`notes-text-${encounterId}`}>Note</label>
        <textarea
          id={`notes-text-${encounterId}`}
          data-testid="notes-text"
          value={text}
          disabled={readOnly}
          onChange={(event) => setText(event.target.value)}
        />
        <button
          type="button"
          className="x-button"
          data-testid="notes-add"
          disabled={readOnly || text.trim() === ""}
          onClick={() => void handleAdd()}
        >
          Add note
        </button>
      </div>
      {status ? <p role="status" data-testid="notes-status">{status}</p> : null}
      <div data-testid="notes-list">
        {items.map((note) => (
          <article key={note.id} data-testid="notes-item">
            <p>
              {note.page} · {note.author_display} · {note.created_at}
            </p>
            <p>{note.text}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function EffectsSection({
  encounterId,
  definition,
  definitionLoaded,
  values,
  readOnly,
  onStatusChange,
  onSeverityChange,
}: {
  encounterId: string;
  definition: HistoryContent | null;
  definitionLoaded: boolean;
  values: EffectsState;
  readOnly: boolean;
  onStatusChange: (id: EffectId, value: EffectStatus | null) => void;
  onSeverityChange: (id: EffectId, value: string | null) => void;
}) {
  function severitiesFor(id: EffectId): string[] {
    const found = definition?.effects.find((effect) => effect.id === id);
    return found?.severity_values ?? [];
  }
  return (
    <section data-testid="effects-section" aria-label="Adverse effects">
      <h3>Adverse effects</h3>
      <p>
        Severity is required only when present. Supporting sources only —
        full BARS, SAS, or AIMS questionnaires are not required.
      </p>
      {!definitionLoaded ? <p>Loading effect content…</p> : null}
      {definitionLoaded && definition === null ? (
        <p>Severity definitions are pending review — severities unavailable.</p>
      ) : null}
      {EFFECT_IDS.map((id) => {
        const entry = values[id] ?? { status: null, severity: null };
        const severities = severitiesFor(id);
        const present = entry.status === "present";
        return (
          <div className="x-field" key={id}>
            <label htmlFor={`effects-status-${encounterId}-${id}`}>
              {EFFECT_LABELS[id]} status
            </label>
            <select
              id={`effects-status-${encounterId}-${id}`}
              data-testid={`effects-status-${id}`}
              disabled={readOnly}
              value={entry.status ?? ""}
              onChange={(event) => {
                const raw = event.target.value;
                if (raw === "present" || raw === "absent" || raw === "not_assessed") {
                  onStatusChange(id, raw);
                  return;
                }
                onStatusChange(id, null);
              }}
            >
              <option value="">Select…</option>
              <option value="present">present</option>
              <option value="absent">absent</option>
              <option value="not_assessed">not_assessed</option>
            </select>
            <label htmlFor={`effects-severity-${encounterId}-${id}`}>
              {EFFECT_LABELS[id]} severity
            </label>
            <select
              id={`effects-severity-${encounterId}-${id}`}
              data-testid={`effects-severity-${id}`}
              disabled={readOnly || !present || severities.length === 0}
              value={present ? (entry.severity ?? "") : ""}
              onChange={(event) => {
                const raw = event.target.value;
                onSeverityChange(id, raw === "" ? null : raw);
              }}
            >
              <option value="">Select…</option>
              {severities.map((severity) => (
                <option key={severity} value={severity}>
                  {severity}
                </option>
              ))}
            </select>
          </div>
        );
      })}
    </section>
  );
}

/**
 * S20 medications + DDI (FR-14/FR-20): drug-only list plus a versioned
 * coverage-aware interaction report, reusing the S07 autosave path
 * (revisionRef/timer/saveState live in DraftEditor; these sections only edit
 * values and request a check). No regimen detail is ever stored: entries
 * carry exactly one of catalog_drug_id|unknown_label. Unknown labels and
 * source evidence render as plain JSX text (React escapes by default; never
 * dangerouslySetInnerHTML).
 */
type MedEntry = { catalog_drug_id?: string; unknown_label?: string };

function medsFromStored(stored: unknown): MedEntry[] {
  if (!Array.isArray(stored)) {
    return [];
  }
  const out: MedEntry[] = [];
  for (const entry of stored) {
    if (typeof entry !== "object" || entry === null || Array.isArray(entry)) {
      continue;
    }
    const rec = entry as Record<string, unknown>;
    const keys = Object.keys(rec);
    if (
      keys.length === 1 &&
      keys[0] === "catalog_drug_id" &&
      typeof rec.catalog_drug_id === "string" &&
      rec.catalog_drug_id.trim() !== ""
    ) {
      out.push({ catalog_drug_id: rec.catalog_drug_id });
    } else if (
      keys.length === 1 &&
      keys[0] === "unknown_label" &&
      typeof rec.unknown_label === "string" &&
      rec.unknown_label.trim() !== ""
    ) {
      out.push({ unknown_label: rec.unknown_label });
    }
  }
  return out;
}

function ddiFromStored(stored: unknown): DdiReport | null {
  if (typeof stored !== "object" || stored === null || Array.isArray(stored)) {
    return null;
  }
  const rec = stored as Record<string, unknown>;
  if (typeof rec.dataset_version !== "string" || rec.dataset_version.trim() === "") {
    return null;
  }
  if (
    typeof rec.medication_fingerprint !== "string" ||
    rec.medication_fingerprint.trim() === ""
  ) {
    return null;
  }
  return rec as unknown as DdiReport;
}

function medsDirtyKey(meds: MedEntry[]): string {
  const normalized = meds.map((entry) =>
    entry.catalog_drug_id !== undefined
      ? { catalog_drug_id: entry.catalog_drug_id }
      : { unknown_label: entry.unknown_label as string },
  );
  normalized.sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b)));
  return JSON.stringify(normalized);
}

function MedicationsSection({
  encounterId,
  meds,
  readOnly,
  onRemove,
  onAddCatalog,
  onAddUnknown,
}: {
  encounterId: string;
  meds: MedEntry[];
  readOnly: boolean;
  onRemove: (index: number) => void;
  onAddCatalog: (conceptId: string) => void;
  onAddUnknown: (label: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<DrugSearchResult[]>([]);
  const [searchNotice, setSearchNotice] = useState("Searching…");
  const [unknown, setUnknown] = useState("");

  useEffect(() => {
    let cancelled = false;
    setSearchNotice("Searching…");
    const timer = setTimeout(() => {
      searchDrugs(query)
        .then((payload) => {
          if (cancelled) {
            return;
          }
          const items = Array.isArray(payload.results) ? payload.results : [];
          setResults(items);
          setSearchNotice(items.length === 0 ? "No catalog matches." : "");
        })
        .catch(() => {
          if (cancelled) {
            return;
          }
          setResults([]);
          setSearchNotice("Catalog unavailable.");
        });
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query]);

  function handleAddUnknown(): void {
    const trimmed = unknown.trim();
    if (trimmed === "" || readOnly) {
      return;
    }
    onAddUnknown(trimmed);
    setUnknown("");
  }

  return (
    <section data-testid="medications-section" aria-label="Medications">
      <h3>Medications</h3>
      <p>Drug names only — doses, routes, and schedules are never stored.</p>
      <div className="x-field">
        <label htmlFor={`medications-search-${encounterId}`}>Search catalog</label>
        <input
          id={`medications-search-${encounterId}`}
          data-testid="medications-search"
          autoComplete="off"
          value={query}
          disabled={readOnly}
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>
      <div data-testid="medications-search-results">
        {searchNotice !== "" ? (
          <p>{searchNotice}</p>
        ) : (
          results.map((item) => (
            <div key={item.concept_id}>
              <span>{item.concept_id}</span>{" "}
              <button
                type="button"
                className="x-button"
                data-testid={`medications-add-${item.concept_id}`}
                disabled={readOnly}
                onClick={() => onAddCatalog(item.concept_id)}
              >
                Add {item.concept_id}
              </button>
            </div>
          ))
        )}
      </div>
      <div className="x-field">
        <label htmlFor={`medications-unknown-${encounterId}`}>Unknown medication</label>
        <input
          id={`medications-unknown-${encounterId}`}
          data-testid="medications-unknown-input"
          autoComplete="off"
          value={unknown}
          disabled={readOnly}
          onChange={(event) => setUnknown(event.target.value)}
        />
        <button
          type="button"
          className="x-button"
          data-testid="medications-unknown-add"
          disabled={readOnly}
          onClick={handleAddUnknown}
        >
          Add unknown
        </button>
      </div>
      <ul data-testid="medications-list">
        {meds.map((entry, index) => (
          <li key={index}>
            {entry.catalog_drug_id !== undefined ? (
              <span>{entry.catalog_drug_id}</span>
            ) : (
              <span>Unknown: {entry.unknown_label as string} (coverage unavailable)</span>
            )}{" "}
            <button
              type="button"
              className="x-button"
              data-testid={`medications-remove-${index}`}
              disabled={readOnly}
              onClick={() => onRemove(index)}
            >
              Remove
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function DdiSection({
  encounterId,
  encounterKind,
  report,
  status,
  errorDetail,
  reconciliationStatus,
  readOnly,
  onCheck,
}: {
  encounterId: string;
  encounterKind: string;
  report: DdiReport | null;
  status: "idle" | "pending" | "current" | "error";
  errorDetail: string | null;
  reconciliationStatus: string;
  readOnly: boolean;
  onCheck: () => void;
}) {
  const rawPairs = report?.pairs;
  const pairs: NonNullable<DdiReport["pairs"]> = Array.isArray(rawPairs)
    ? rawPairs
    : [];
  const rawLimitations = report?.limitations;
  const limitations: string[] = Array.isArray(rawLimitations) ? rawLimitations : [];
  const conflicts: Array<{ source_severity: string; source_path?: string }> = [];
  for (const pair of pairs) {
    for (const conflict of pair.conflicts ?? []) {
      conflicts.push(conflict);
    }
  }
  let statusText = "No DDI report yet.";
  if (status === "pending") {
    statusText = "DDI report pending — medications changed.";
  } else if (status === "current" && report !== null) {
    statusText = `DDI report current (dataset ${report.dataset_version}).`;
  } else if (status === "error") {
    statusText =
      errorDetail !== null && errorDetail !== ""
        ? `DDI check failed. ${errorDetail}`
        : "DDI check failed.";
  }
  return (
    <section data-testid="ddi-section" aria-label="Drug interactions">
      <h3>Drug interactions</h3>
      {encounterKind === "follow_up" && reconciliationStatus !== "confirmed" ? (
        <p data-testid="medications-reconcile-notice">
          Copied medications need reconciliation before relying on DDI.
        </p>
      ) : null}
      <button
        type="button"
        className="x-button"
        id={`ddi-check-${encounterId}`}
        data-testid="ddi-check"
        disabled={readOnly}
        onClick={onCheck}
      >
        Check interactions
      </button>
      {/*
        No role="status" here: DraftEditor keeps a single live status
        (the shared saveState). A second role would trip strict-mode
        getByRole("status") Saved assertions across the suite; ddi-status
        remains addressable via its testid.
      */}
      <p data-testid="ddi-status">
        {statusText}
      </p>
      {status === "current" && report !== null ? (
        <div data-testid="ddi-report">
          {pairs.length === 0 ? <p>No pairs to evaluate.</p> : null}
          {pairs.map((pair) => (
            <article key={pair.pair_key} data-testid={`ddi-pair-${pair.pair_key}`}>
              <p>
                {pair.pair_key}: {pair.drug_a} + {pair.drug_b}
              </p>
              <p data-testid={`ddi-severity-${pair.pair_key}`}>
                Severity: {pair.highest_known_severity ?? "unknown"}
              </p>
              <p data-testid={`ddi-status-${pair.pair_key}`}>Status: {pair.status}</p>
              {pair.coverage_basis ? <p>Coverage: {pair.coverage_basis}</p> : null}
              {pair.evidence !== undefined && pair.evidence.length > 0 ? (
                <ul>
                  {pair.evidence.map((item, index) => (
                    <li key={index}>
                      {item.source_severity ?? "unknown"}: {item.raw_text ?? ""} (
                      {item.source_path ?? ""})
                    </li>
                  ))}
                </ul>
              ) : (
                <p>No listed evidence.</p>
              )}
            </article>
          ))}
          <div data-testid="ddi-conflicts">
            {conflicts.length === 0 ? (
              <p>No conflicts.</p>
            ) : (
              <ul>
                {conflicts.map((conflict, index) => (
                  <li key={index}>
                    {conflict.source_severity} ({conflict.source_path ?? ""})
                  </li>
                ))}
              </ul>
            )}
          </div>
          <ul data-testid="ddi-limitations">
            {limitations.length === 0 ? (
              <li>None</li>
            ) : (
              limitations.map((item, index) => <li key={index}>{item}</li>)
            )}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

/**
 * S11 slice 4 C-SSRS section reusing the S07 autosave path (revisionRef/timer/
 * saveState live in DraftEditor; this section only edits levels + requests skip).
 * Ideation L1-L5 only; intensity/behavior/lethality are never edited here and
 * are preserved verbatim by DraftEditor on save. No composite score.
 */
function CssrsSection({
  encounterId,
  levels,
  notAssessed,
  readOnly,
  onLevelChange,
  onPeriodChange,
  onSkip,
}: {
  encounterId: string;
  levels: CssrsLevels;
  notAssessed: boolean;
  readOnly: boolean;
  onLevelChange: (id: CssrsLevelId, value: boolean | null) => void;
  onPeriodChange: (id: CssrsLevelId, value: CssrsPeriod | null) => void;
  onSkip: () => void;
}) {
  const preview = previewCssrs(levels, notAssessed);
  const dash = "—";
  return (
    <section data-testid="cssrs-section" aria-label="C-SSRS">
      <h3>C-SSRS</h3>
      <p>Paraphrase — use authorized form for exact wording.</p>
      <p>
        Time window: current = recent, historical = lifetime/history. Record the
        period for each endorsed level.
      </p>
      {preview.status === "skipped" ? <p>Not assessed — skipped.</p> : null}
      {preview.status === "unanswered" ? <p>Unanswered — select Yes or No for each level.</p> : null}
      {preview.status === "partial" ? (
        <p>
          Partial — {preview.missing.length} missing ({preview.missing.join(", ")}).
        </p>
      ) : null}
      {preview.status === "complete" ? <p>Complete.</p> : null}
      <p>
        Severity: <span data-testid="cssrs-severity">{preview.severity === null ? dash : String(preview.severity)}</span>
      </p>
      {preview.flags.clinical_review ? (
        <p data-testid="cssrs-review-flag" role="alert" tabIndex={0}>
          Clinical review required — documentation and review by the treating clinician.
        </p>
      ) : null}
      {preview.flags.high_risk ? (
        <p data-testid="cssrs-urgent-flag" role="alert" tabIndex={0}>
          Urgent — recent level 4/5 requires immediate assessment under local protocol.
        </p>
      ) : null}
      {preview.flags.no_ideation ? <p>No ideation endorsed — continue routine assessment.</p> : null}
      <p>
        If current intent/plan, attempt in progress, or inability to stay safe:
        emergency intervention per local policy — do not wait.
      </p>
      {CSSRS_IDS.map((id) => (
        <div className="x-field" key={id}>
          <label htmlFor={`cssrs-${encounterId}-${id}`}>
            {id} — {CSSRS_PROMPTS[id].construct}: {CSSRS_PROMPTS[id].question}
          </label>
          <select
            id={`cssrs-${encounterId}-${id}`}
            data-testid={`cssrs-item-${id}`}
            disabled={readOnly}
            value={
              levels[id]?.endorsed === true ? "yes" : levels[id]?.endorsed === false ? "no" : ""
            }
            onChange={(event) => {
              const raw = event.target.value;
              if (raw === "") {
                onLevelChange(id, null);
                return;
              }
              if (raw === "yes") {
                onLevelChange(id, true);
                return;
              }
              if (raw === "no") {
                onLevelChange(id, false);
                return;
              }
            }}
          >
            <option value="">Select…</option>
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>
          <label htmlFor={`cssrs-period-${encounterId}-${id}`}>{id} period</label>
          <select
            id={`cssrs-period-${encounterId}-${id}`}
            data-testid={`cssrs-period-${id}`}
            disabled={readOnly || levels[id]?.endorsed !== true}
            value={levels[id]?.endorsed === true ? (levels[id]?.period ?? "") : ""}
            onChange={(event) => {
              const raw = event.target.value;
              if (raw === "current" || raw === "historical") {
                onPeriodChange(id, raw);
                return;
              }
              onPeriodChange(id, null);
            }}
          >
            <option value="">Select…</option>
            <option value="current">current</option>
            <option value="historical">historical</option>
          </select>
        </div>
      ))}
      <button
        type="button"
        className="x-button"
        data-testid="cssrs-skip"
        disabled={readOnly}
        onClick={onSkip}
      >
        Skip
      </button>
    </section>
  );
}

/**
 * S10 PANSS section reusing the S07 autosave path (revisionRef/timer/saveState
 * live in DraftEditor; this section only edits items + requests skip).
 * No treatment gates; prior scores are historical text only, never prefilled.
 */
function PanssSection({
  encounterId,
  answers,
  notAssessed,
  readOnly,
  onItemChange,
  onSkip,
}: {
  encounterId: string;
  answers: PanssAnswers;
  notAssessed: boolean;
  readOnly: boolean;
  onItemChange: (id: string, value: number | null) => void;
  onSkip: () => void;
}) {
  const preview = previewPanss(answers, notAssessed);
  const dash = "—";
  return (
    <section data-testid="panss-section" aria-label="PANSS">
      <h3>PANSS</h3>
      <p>Rate each item for the previous 7 days (1–7).</p>
      <p>No prior PANSS score — prior: none (historical only; never prefilled as answers).</p>
      {preview.status === "skipped" ? <p>Not assessed — skipped.</p> : null}
      {preview.status === "unanswered" ? <p>Unanswered — select a rating for each item.</p> : null}
      {preview.status === "partial" ? (
        <p>
          Partial — {preview.missing} missing ({preview.answered} of 30 answered).
        </p>
      ) : null}
      {preview.status === "complete" ? <p>Complete.</p> : null}
      <p>
        Positive subscale: <span data-testid="panss-positive">{preview.positive === null ? dash : String(preview.positive)}</span>
      </p>
      <p>
        Negative subscale: <span data-testid="panss-negative">{preview.negative === null ? dash : String(preview.negative)}</span>
      </p>
      <p>
        General subscale: <span data-testid="panss-general">{preview.general === null ? dash : String(preview.general)}</span>
      </p>
      <p>
        Total: <span data-testid="panss-total">{preview.total === null ? dash : String(preview.total)}</span>
      </p>
      {PANSS_ALL_IDS.map((id) => (
        <div className="x-field" key={id}>
          <label htmlFor={`panss-${encounterId}-${id}`}>
            {id} — {PANSS_PROMPTS[id] ?? id}
          </label>
          <select
            id={`panss-${encounterId}-${id}`}
            data-testid={`panss-item-${id}`}
            disabled={readOnly}
            value={answers[id] === null || answers[id] === undefined ? "" : String(answers[id])}
            onChange={(event) => {
              const raw = event.target.value;
              if (raw === "") {
                onItemChange(id, null);
                return;
              }
              const parsed = Number.parseInt(raw, 10);
              if (!Number.isInteger(parsed) || parsed < 1 || parsed > 7) {
                return;
              }
              onItemChange(id, parsed);
            }}
          >
            <option value="">Select…</option>
            <option value="1">1</option>
            <option value="2">2</option>
            <option value="3">3</option>
            <option value="4">4</option>
            <option value="5">5</option>
            <option value="6">6</option>
            <option value="7">7</option>
          </select>
        </div>
      ))}
      <button
        type="button"
        className="x-button"
        data-testid="panss-skip"
        disabled={readOnly}
        onClick={onSkip}
      >
        Skip
      </button>
    </section>
  );
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
  if (window.location.pathname === "/provider-settings") {
    return "/provider-settings";
  }
  if (window.location.pathname === "/networks") {
    return "/networks";
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
        {user?.role === "admin" ? (
          <NavLink route="/provider-settings" current={route}>
            Provider settings
          </NavLink>
        ) : null}
        {user?.role === "admin" ? (
          <NavLink route="/networks" current={route}>
            Networks
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
      ) : route === "/provider-settings" ? (
        <ProviderSettingsGate user={user} />
      ) : route === "/networks" ? (
        <NetworksGate user={user} />
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

/**
 * S14 patient chart: shared encounter list with per-encounter open and
 * physician-only follow-up start. Read-only for non-authors (DraftEditor owns
 * the author gate); the chart itself persists nothing.
 */
function PatientChart({
  patient,
  role,
  onOpenEncounter,
  onPatientChanged,
}: {
  patient: Patient;
  userId: string;
  role: string;
  onOpenEncounter: (encounterId: string) => void;
  onPatientChanged: (patient: Patient) => void;
}) {
  const [items, setItems] = useState<Encounter[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [archiveDialog, setArchiveDialog] = useState(false);
  const [archivePending, setArchivePending] = useState(false);
  const [archiveError, setArchiveError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setItems(null);
    setError(null);
    listEncounters(patient.id)
      .then((all) => {
        if (!cancelled) {
          setItems(all);
        }
      })
      .catch((failure: unknown) => {
        if (!cancelled) {
          setError(
            failure instanceof Error ? failure.message : "Could not load the chart.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [patient.id]);

  async function handleStartFollowup(baselineId: string): Promise<void> {
    setStarting(baselineId);
    setStartError(null);
    try {
      const created = await createFollowup(patient.id, baselineId);
      setItems((prev) => (prev === null ? [created] : [...prev, created]));
      onOpenEncounter(created.id);
    } catch (failure: unknown) {
      setStartError(
        failure instanceof Error ? failure.message : "Could not start the follow-up.",
      );
    } finally {
      setStarting(null);
    }
  }

  const baselineChanged =
    items !== null &&
    items.some((item) => item.kind === "follow_up" && item.baseline_changed);
  const openDraftCount =
    items === null
      ? 0
      : items.filter((item) => item.state === "draft" || item.state === "review_ready")
          .length;

  async function handleArchiveConfirm(): Promise<void> {
    setArchivePending(true);
    setArchiveError(null);
    try {
      const updated = await archivePatient(patient.id, patient.revision);
      setArchiveDialog(false);
      onPatientChanged(updated);
    } catch (failure: unknown) {
      setArchiveError(
        failure instanceof Error ? failure.message : "Could not archive the patient.",
      );
    } finally {
      setArchivePending(false);
    }
  }

  async function handleUnarchive(): Promise<void> {
    setArchivePending(true);
    setArchiveError(null);
    try {
      const updated = await unarchivePatient(patient.id, patient.revision);
      onPatientChanged(updated);
    } catch (failure: unknown) {
      setArchiveError(
        failure instanceof Error ? failure.message : "Could not unarchive the patient.",
      );
    } finally {
      setArchivePending(false);
    }
  }

  return (
    <section data-testid="chart-section" aria-label="Chart">
      <h3>Chart</h3>
      <p>Patient {patient.patient_id}</p>
      {patient.archived ? (
        <p data-testid="patient-archived-badge">Archived</p>
      ) : null}
      {role === "admin" && !patient.archived ? (
        <button
          type="button"
          className="x-button"
          data-testid="patient-archive-button"
          onClick={() => {
            setArchiveError(null);
            setArchiveDialog(true);
          }}
        >
          Archive
        </button>
      ) : null}
      {role === "admin" && patient.archived ? (
        <button
          type="button"
          className="x-button"
          data-testid="patient-unarchive-button"
          disabled={archivePending}
          onClick={() => void handleUnarchive()}
        >
          {archivePending ? "Unarchiving…" : "Unarchive"}
        </button>
      ) : null}
      {archiveDialog && !patient.archived ? (
        <div data-testid="patient-archive-dialog" role="dialog" aria-label="Archive patient">
          <p data-testid="patient-archive-dialog-draft-count">
            {openDraftCount} open draft{openDraftCount === 1 ? "" : "s"}
          </p>
          <p>Archived patient drafts become read-only until unarchived.</p>
          {archiveError ? (
            <p role="alert" className="x-error">
              {archiveError}
            </p>
          ) : null}
          <button
            type="button"
            className="x-button"
            data-testid="patient-archive-confirm-button"
            disabled={archivePending}
            onClick={() => void handleArchiveConfirm()}
          >
            {archivePending ? "Archiving…" : "Confirm archive"}
          </button>{" "}
          <button
            type="button"
            className="x-button"
            data-testid="patient-archive-cancel"
            disabled={archivePending}
            onClick={() => setArchiveDialog(false)}
          >
            Cancel
          </button>
        </div>
      ) : null}
      {archiveError && patient.archived ? (
        <p role="alert" className="x-error">
          {archiveError}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="x-error">
          {error}
        </p>
      ) : items === null ? (
        <p>Loading…</p>
      ) : (
        <>
          {baselineChanged ? (
            <p data-testid="chart-baseline-changed">
              Baseline changed — reconcile against the newer signed record before signing.
            </p>
          ) : null}
          <ul data-testid="chart-encounters">
            {items.map((item) => (
              <li key={item.id} data-testid={`chart-encounter-${item.id}`}>
                <span data-testid={`chart-badge-${item.id}`}>
                  {item.kind} · {item.state}
                </span>{" "}
                <button
                  type="button"
                  className="x-button"
                  data-testid={`open-encounter-${item.id}`}
                  onClick={() => onOpenEncounter(item.id)}
                >
                  Open encounter {item.kind}
                </button>
                {item.state === "signed" && role === "physician" ? (
                  <button
                    type="button"
                    className="x-button"
                    data-testid={`start-followup-${item.id}`}
                    disabled={starting !== null}
                    onClick={() => void handleStartFollowup(item.id)}
                  >
                    Start follow-up
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
          {starting !== null ? <p role="status">Starting follow-up…</p> : null}
          {startError ? (
            <p role="alert" className="x-error">
              {startError}
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}

const PATIENT_NAME_RE = /^\p{L}+$/u;
const PATIENT_ID_RE = /^[0-9]{10}$/;
function PatientsSection({ role, userId }: { role: string; userId: string }) {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [archivedFilter, setArchivedFilter] = useState<"active" | "archived">("active");
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
  const [selectedEncounterId, setSelectedEncounterId] = useState<string | null>(null);

  function openDraft(item: Patient): void {
    // Warn when switching drafts with pending local edits.
    if (
      (window as unknown as { __xinsight_dirty?: boolean }).__xinsight_dirty &&
      !window.confirm("You have unsaved edits. Leave without saving?")
    ) {
      return;
    }
    setSelectedEncounterId(null);
    setOpenPatient(item);
    try {
      localStorage.setItem("xinsight.openPatient", JSON.stringify(item));
    } catch {
      /* storage unavailable; editor still opens for this session */
    }
  }

  function closeDraft(): void {
    setSelectedEncounterId(null);
    setOpenPatient(null);
    try {
      localStorage.removeItem("xinsight.openPatient");
    } catch {
      /* ignore */
    }
  }

  function handlePatientChanged(next: Patient): void {
    setOpenPatient(next);
    try {
      localStorage.setItem("xinsight.openPatient", JSON.stringify(next));
    } catch {
      /* storage unavailable; chart still reflects the change this session */
    }
    // The directory hides/shows archived rows by filter; refresh the list.
    setRefresh((n) => n + 1);
  }

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      listPatients({
        q: q || undefined,
        clinical_status: status || undefined,
        archived: archivedFilter === "archived",
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
  }, [q, status, refresh, archivedFilter]);

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
      <div className="x-field">
        <label htmlFor="patient-directory-archived-filter">Show archived patients</label>
        <select
          id="patient-directory-archived-filter"
          data-testid="patient-directory-archived-filter"
          value={archivedFilter}
          onChange={(event) =>
            setArchivedFilter(event.target.value === "archived" ? "archived" : "active")
          }
        >
          <option value="active">Active</option>
          <option value="archived">Archived</option>
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
        <>
          <PatientChart
            patient={openPatient}
            userId={userId}
            role={role}
            onOpenEncounter={setSelectedEncounterId}
            onPatientChanged={handlePatientChanged}
          />
          <DraftEditor
            patient={openPatient}
            userId={userId}
            role={role}
            onClose={closeDraft}
            initialEncounterId={selectedEncounterId}
          />
        </>
      ) : null}
    </section>
  );
}

/**
 * S14 follow-up extras: baseline-copy notice, historical prior scores, and
 * the honest generation-status pin. Prior scores render as history only —
 * the editor never prefills PANSS/C-SSRS answers from the baseline.
 */
function FollowupExtras({
  encounter,
  baseline,
}: {
  encounter: Encounter;
  baseline: Encounter | null;
}) {
  const baselineId =
    typeof encounter.baseline_encounter_id === "string"
      ? encounter.baseline_encounter_id
      : "record";
  let panssText =
    "No prior PANSS score — prior: none (historical only; never scored as new answers).";
  let cssrsText =
    "No prior C-SSRS score — prior: none (historical only; never scored as new answers).";
  if (baseline !== null) {
    const stored = baseline.draft_data;
    const parsedPanss = panssFromStored(stored.panss);
    const panssPreview = previewPanss(parsedPanss.answers, parsedPanss.notAssessed);
    if (panssPreview.total !== null) {
      panssText =
        `Prior PANSS total ${panssPreview.total} ` +
        `(positive ${panssPreview.positive}, negative ${panssPreview.negative}, ` +
        `general ${panssPreview.general}) (historical).`;
    }
    const parsedCssrs = cssrsFromStored(stored.cssrs);
    const cssrsPreview = previewCssrs(parsedCssrs.levels, parsedCssrs.notAssessed);
    if (cssrsPreview.severity !== null) {
      cssrsText = `Prior C-SSRS severity ${cssrsPreview.severity} (historical).`;
    }
  }
  return (
    <>
      <p data-testid="followup-baseline-note">
        Copied from baseline {baselineId} — reconcile history and medications before
        signing.
      </p>
      <section data-testid="prior-scores" aria-label="Prior scores">
        <h4>Prior scores</h4>
        <p>{panssText}</p>
        <p>{cssrsText}</p>
        {baseline !== null ? (
          <p>
            Baseline recorded {baseline.created_at} (historical).
          </p>
        ) : (
          <p>Baseline scores pending — prior: none (historical only).</p>
        )}
      </section>
      <p data-testid="generation-status">Proposal generation unavailable.</p>
    </>
  );
}
/**
 * S48 proposal review: automatic run entry + run status (slice 1).
 * States/retry/polling (slice 2), transparency (slice 3), and proposal +
 * secondary plan + sign gate (slice 4) extend this section.
 *
 * Entry contract: flush the shared autosave first, then POST start once per
 * mount when prerequisites hold (author-owned draft, no unsaved edits, save
 * state clean). Never POSTs per keystroke: the effect below fires on mount /
 * encounter change and on save completion only, never on edits. Same
 * fingerprint re-entry reuses the run server-side (same run_id). A
 * remembered terminal run is shown as-is with no new POST. There is no
 * Generate button: entry is automatic when prerequisites hold.
 *
 * No role="status" here: DraftEditor keeps the single live saveState node
 * (S13/S20 precedent); run status stays addressable via its testid.
 * Everything renders as plain JSX text (React escapes by default; never
 * dangerouslySetInnerHTML), and notes state is never read here.
 */
const PROPOSAL_TERMINAL_STATUSES = new Set([
  "succeeded",
  "failed",
  "needs_clarification",
  "cancelled",
]);

function isProposalRunTerminal(detail: RunDetail): boolean {
  if (PROPOSAL_TERMINAL_STATUSES.has(detail.run.status)) {
    return true;
  }
  if (detail.stale) {
    const active = detail.jobs.some(
      (job) => job.status === "queued" || job.status === "claimed" || job.status === "running",
    );
    if (!active) {
      return true;
    }
  }
  return false;
}

function rememberedRunStorageKey(encounterId: string): string {
  return `xinsight.proposalRun:${encounterId}`;
}

function readRememberedRunId(encounterId: string): string | null {
  try {
    const raw = sessionStorage.getItem(rememberedRunStorageKey(encounterId));
    return raw !== null && /^[0-9a-f-]{36}$/i.test(raw) ? raw : null;
  } catch {
    return null;
  }
}

function rememberRunId(encounterId: string, runId: string): void {
  try {
    sessionStorage.setItem(rememberedRunStorageKey(encounterId), runId);
  } catch {
    /* storage unavailable; entry still works for this mount */
  }
}

function proposalPrereqMessage(state: {
  saveState: string;
  dirty: boolean;
  readOnly: boolean;
}): string | null {  if (state.readOnly) {
    return "Only the draft author may start a run.";
  }
  if (state.dirty) {
    return "Unsaved edits pending — waiting for save before starting the run.";
  }
  if (state.saveState === "Saving…" || state.saveState === "Loading…") {
    return "Run prerequisites pending — waiting for the draft to save.";
  }  if (
    state.saveState === "Stale revision" ||
    state.saveState === "Save failed" ||
    state.saveState === "Read-only draft." ||
    state.saveState === "Draft discarded."
  ) {
    return `Run prerequisites pending — resolve the save state (${state.saveState}) before starting the run.`;
  }
  return null;
}

/**
 * S48 per-question state label (slice 2): combines the persisted
 * applicability gate with the live job stage/status. Text-only status, never
 * color-only.
 */
function proposalQuestionStateText(
  applicability: string,
  reason: string,
  job: { stage: string; status: string } | undefined,
  hasSucceededSection: boolean,
): string {
  if (job !== undefined) {
    if (job.status === "failed") {
      return `Failed — ${job.stage}`;
    }
    if (job.status === "running") {
      return `Running — ${job.stage}`;
    }
    if (job.status === "queued" || job.status === "claimed") {
      return `Pending — ${job.stage} (${job.status})`;
    }
    if (job.status === "succeeded") {
      return "Completed (succeeded)";
    }
  }
  if (applicability === "not_applicable") {
    return `Skipped — not applicable: ${reason}`;
  }
  if (applicability === "needs_clarification") {
    return `Needs clarification: ${reason}`;
  }
  if (hasSucceededSection) {
    return "Completed (succeeded)";
  }
  return "Pending — awaiting worker";
}

/**
 * S48 transparency details (slice 3): persisted section payload only —
 * network version, exact patient inputs, provider-estimated CPT percentages,
 * deterministic posterior result, and provenance. Rendered from the
 * already-fetched GET payload on expansion; never recomputed from chart
 * state, never notes (only patient_inputs/projection facts, rendered text,
 * and DDI raw text ever render here). Plain JSX text throughout.
 */
function proposalText(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (value === null || value === undefined) {
    return "";
  }
  try {
    return JSON.stringify(value);
  } catch {
    return "";
  }
}

/**
 * S48 proposal/DDI shaping (slice 4): the succeeded proposal lists section
 * keys (+ rendered texts when present) and skipped reasons — patient inputs
 * are never duplicated here. DDI renders from proposal.ddi_report (the only
 * production read path); a missing report renders an honest unavailable
 * message. Plain JSX text throughout.
 */
function proposalSectionEntries(
  sections: unknown,
): Array<{ key: string; text: string }> {
  if (!Array.isArray(sections)) {
    return [];
  }
  const out: Array<{ key: string; text: string }> = [];
  for (const entry of sections) {
    if (typeof entry === "string") {
      if (entry !== "") {
        out.push({ key: entry, text: "" });
      }
    } else if (typeof entry === "object" && entry !== null) {
      const rec = entry as Record<string, unknown>;
      const key =
        typeof rec.question_key === "string" ? rec.question_key : "";
      const text = typeof rec.text === "string" ? rec.text : "";
      if (key !== "") {
        out.push({ key, text });
      }
    }
  }
  return out;
}

function proposalSkippedEntries(skipped: unknown): string[] {
  if (!Array.isArray(skipped)) {
    return [];
  }
  const out: string[] = [];
  for (const entry of skipped) {
    if (typeof entry === "string") {
      if (entry !== "") {
        out.push(entry);
      }
    } else if (typeof entry === "object" && entry !== null) {
      const rec = entry as Record<string, unknown>;
      const key =
        typeof rec.question_key === "string" ? rec.question_key : "";
      const reason =
        typeof rec.reason === "string"
          ? rec.reason
          : typeof rec.applicability_reason === "string"
            ? String(rec.applicability_reason)
            : "";
      const label =
        key !== "" && reason !== "" ? `${key}: ${reason}` : `${key}${reason}`;
      if (label !== "") {
        out.push(label);
      }
    }
  }
  return out;
}

function proposalStringEntries(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter(
    (entry): entry is string => typeof entry === "string" && entry !== "",
  );
}

interface ProposalDdiEvidence {
  source_severity: string;
  raw_text: string;
  source_path: string;
}

interface ProposalDdiPair {
  pair_key: string;
  drug_a: string;
  drug_b: string;
  status: string;
  highest_known_severity: string | null;
  coverage_basis: string;
  evidence: ProposalDdiEvidence[];
  conflicts: ProposalDdiEvidence[];
}

function proposalDdiPairs(ddi: Record<string, unknown>): ProposalDdiPair[] {
  const raw = ddi.pairs;
  if (!Array.isArray(raw)) {
    return [];
  }
  const out: ProposalDdiPair[] = [];
  for (const entry of raw) {
    if (typeof entry !== "object" || entry === null) {
      continue;
    }
    const rec = entry as Record<string, unknown>;
    const evidence: ProposalDdiEvidence[] = [];
    if (Array.isArray(rec.evidence)) {
      for (const item of rec.evidence) {
        if (typeof item !== "object" || item === null) {
          continue;
        }
        const ev = item as Record<string, unknown>;
        evidence.push({
          source_severity:
            typeof ev.source_severity === "string"
              ? ev.source_severity
              : "unknown",
          raw_text: typeof ev.raw_text === "string" ? ev.raw_text : "",
          source_path:
            typeof ev.source_path === "string" ? ev.source_path : "",
        });
      }
    }
    const conflicts: ProposalDdiEvidence[] = [];
    if (Array.isArray(rec.conflicts)) {
      for (const item of rec.conflicts) {
        if (typeof item !== "object" || item === null) {
          continue;
        }
        const ev = item as Record<string, unknown>;
        conflicts.push({
          source_severity:
            typeof ev.source_severity === "string"
              ? ev.source_severity
              : "unknown",
          raw_text: typeof ev.raw_text === "string" ? ev.raw_text : "",
          source_path:
            typeof ev.source_path === "string" ? ev.source_path : "",
        });
      }
    }
    out.push({
      pair_key: typeof rec.pair_key === "string" ? rec.pair_key : "",
      drug_a: typeof rec.drug_a === "string" ? rec.drug_a : "",
      drug_b: typeof rec.drug_b === "string" ? rec.drug_b : "",
      status: typeof rec.status === "string" ? rec.status : "",
      highest_known_severity:
        typeof rec.highest_known_severity === "string"
          ? rec.highest_known_severity
          : null,
      coverage_basis:
        typeof rec.coverage_basis === "string" ? rec.coverage_basis : "",
      evidence,
      conflicts,
    });
  }
  return out;
}

function ProposalReviewSection({
  encounterId,
  readOnly,
  saveState,
  dirty,
  getRevision,
  flushSave,
  secondaryPlan,
  onSecondaryPlanChange,
}: {
  encounterId: string;
  readOnly: boolean;
  saveState: string;
  dirty: boolean;
  getRevision: () => number;
  flushSave: () => Promise<void>;
  secondaryPlan: string;
  onSecondaryPlanChange: (value: string) => void;
}) {
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [entryError, setEntryError] = useState<string | null>(null);
  const [retryError, setRetryError] = useState<{
    key: string;
    message: string;
  } | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const cancelledRef = useRef(false);
  const postedRef = useRef<string | null>(null);
  const postingRef = useRef(false);
  const fallbackRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const entryKeyRef = useRef<string | null>(null);
  const detailRef = useRef<RunDetail | null>(null);
  detailRef.current = detail;
  const liveRef = useRef({ saveState, dirty, readOnly });
  liveRef.current = { saveState, dirty, readOnly };

  function clearFallback(): void {
    if (fallbackRef.current !== null) {
      clearTimeout(fallbackRef.current);
      fallbackRef.current = null;
    }
  }

  async function doEntryPost(): Promise<void> {
    if (postingRef.current || postedRef.current !== null) {
      return;
    }
    const live = liveRef.current;
    if (
      proposalPrereqMessage(live) !== null ||
      (detailRef.current !== null && isProposalRunTerminal(detailRef.current))
    ) {
      return;
    }
    postingRef.current = true;
    setEntryError(null);
    try {
      // Flush first so the POST always carries acknowledged edits.
      await flushSave();
      if (cancelledRef.current) {
        return;
      }
      const afterFlush = liveRef.current;
      if (
        proposalPrereqMessage(afterFlush) !== null ||
        (detailRef.current !== null && isProposalRunTerminal(detailRef.current))
      ) {
        return;
      }
      if (entryKeyRef.current === null) {
        entryKeyRef.current = newIdempotencyKey();
      }
      const started = await startRun(
        encounterId,
        getRevision(),
        entryKeyRef.current,
      );
      if (cancelledRef.current) {
        return;
      }
      postedRef.current = started.run_id;
      rememberRunId(encounterId, started.run_id);
      clearFallback();
      const data = await getRun(started.run_id);
      if (cancelledRef.current) {
        return;
      }
      setDetail(data);
    } catch (failure: unknown) {
      if (!cancelledRef.current) {
        setEntryError(
          failure instanceof Error ? failure.message : "Could not start the run.",
        );
      }
    } finally {
      postingRef.current = false;
    }
  }

  function fireFallback(): void {
    fallbackRef.current = null;
    if (
      cancelledRef.current ||
      postingRef.current ||
      postedRef.current !== null
    ) {
      return;
    }
    if (detailRef.current !== null && isProposalRunTerminal(detailRef.current)) {
      return;
    }
    if (proposalPrereqMessage(liveRef.current) !== null) {
      // Still settling (a save in flight save-triggers instead); rearm.
      fallbackRef.current = setTimeout(fireFallback, 2000);
      return;
    }
    void doEntryPost();
  }

  function armFallback(): void {
    clearFallback();
    fallbackRef.current = setTimeout(fireFallback, 4000);
  }

  // Entry (mount + encounter change): show a remembered run, then POST once
  // when prerequisites hold. Terminal remembered runs never re-POST.
  useEffect(() => {
    cancelledRef.current = false;
    postedRef.current = null;
    postingRef.current = false;
    entryKeyRef.current = null;
    setDetail(null);
    detailRef.current = null;
    setEntryError(null);
    async function enter(): Promise<void> {
      const remembered = readRememberedRunId(encounterId);
      if (remembered !== null) {
        try {
          const data = await getRun(remembered);
          if (cancelledRef.current) {
            return;
          }
          setDetail(data);
          detailRef.current = data;
          if (isProposalRunTerminal(data)) {
            return;
          }
        } catch {
          /* fall through to a fresh entry below */
        }
      }
      if (!cancelledRef.current) {
        armFallback();
      }
    }
    void enter();
    return () => {
      cancelledRef.current = true;
      clearFallback();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [encounterId]);

  // Save completion trigger: the first acknowledged save after mount starts
  // the run (post-edit fingerprint), so re-entry reuses it. Later saves
  // never POST (postedRef set); terminal runs never re-POST.
  useEffect(() => {
    if (
      postedRef.current !== null ||
      postingRef.current ||
      cancelledRef.current
    ) {
      return;
    }
    if (detailRef.current !== null && isProposalRunTerminal(detailRef.current)) {
      return;
    }
    if (readOnly || dirty) {
      return;
    }
    if (!/^Saved \(rev \d+\)$/.test(saveState)) {
      return;
    }
    void doEntryPost();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [encounterId, saveState, dirty, readOnly]);

  // Polling (slice 2): GET every ~2s while the displayed run is
  // non-terminal (~10s backoff while the document is hidden); stops entirely
  // at terminal. Timers are cleared on unmount.
  useEffect(() => {
    if (detail === null || isProposalRunTerminal(detail)) {
      return;
    }
    const runId = detail.run.id;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    function schedule(): void {
      timer = setTimeout(() => {
        timer = null;
        void poll();
      }, document.hidden ? 10000 : 2000);
    }
    async function poll(): Promise<void> {
      try {
        const data = await getRun(runId);
        if (!cancelled) {
          setDetail(data);
        }
      } catch {
        /* transient read failure: keep polling on schedule */
      }
      if (!cancelled) {
        schedule();
      }
    }
    schedule();
    return () => {
      cancelled = true;
      if (timer !== null) {
        clearTimeout(timer);
      }
    };
  }, [detail]);

  // Precise retry (slice 2): one failed question with the failed job's stage
  // and the live run revision. 409/412 surfaces the server message inline;
  // editing stays enabled (nothing here ever disables the editor).
  async function handleRetry(questionKey: string, stage: string): Promise<void> {
    const current = detailRef.current;
    if (current === null) {
      return;
    }
    setRetryError(null);
    try {
      await retryRun(current.run.id, {
        question_key: questionKey,
        failed_stage: stage,
        expected_run_revision: current.run.revision,
      });
      setDetail((prev) => {
        if (prev === null) {
          return prev;
        }
        return {
          ...prev,
          jobs: prev.jobs.map((item) =>
            item.question_key === questionKey
              ? { ...item, status: "queued", failure_details: null }
              : item,
          ),
        };
      });
      const fresh = await getRun(current.run.id);
      if (!cancelledRef.current) {
        setDetail(fresh);
      }
    } catch (failure: unknown) {
      if (!cancelledRef.current) {
        setRetryError({
          key: questionKey,
          message:
            failure instanceof Error
              ? failure.message
              : "Could not retry the question.",
        });
      }
    }
  }

  const blocked = proposalPrereqMessage({ saveState, dirty, readOnly });

  // Slice 4: succeeded proposal + pinned DDI + sign gate. The proposal is
  // immutable (keys/reasons/texts only, inputs never duplicated); the
  // secondary plan is the separate physician-editable control below.
  const proposal =
    detail !== null &&
    typeof detail.proposal === "object" &&
    detail.proposal !== null
      ? (detail.proposal as Record<string, unknown>)
      : null;
  const ddi =
    proposal !== null &&
    typeof proposal.ddi_report === "object" &&
    proposal.ddi_report !== null
      ? (proposal.ddi_report as Record<string, unknown>)
      : null;
  const proposalTitle =
    proposal !== null && typeof proposal.title === "string"
      ? proposal.title
      : "";
  const proposalSections = proposalSectionEntries(
    proposal !== null ? proposal.sections : null,
  );
  const proposalSkipped = proposalSkippedEntries(
    proposal !== null ? proposal.skipped : null,
  );
  const proposalCoverageNote =
    proposal !== null && typeof proposal.coverage_note === "string"
      ? proposal.coverage_note
      : "";
  const proposalLimitations = proposalStringEntries(
    proposal !== null ? proposal.limitations : null,
  );
  const ddiPairs = ddi !== null ? proposalDdiPairs(ddi) : [];
  const ddiLimitations = proposalStringEntries(
    ddi !== null ? ddi.limitations : null,
  );
  const ddiDatasetVersion =
    ddi !== null && typeof ddi.dataset_version === "string"
      ? ddi.dataset_version
      : "";
  const runFailed = detail !== null && detail.run.status === "failed";
  const runNeedsClarification =
    detail !== null &&
    (detail.run.status === "needs_clarification" ||
      detail.projections.some(
        (item) => item.applicability === "needs_clarification",
      ));
  const anyJobFailed =
    detail !== null &&
    detail.jobs.some((item) => item.status === "failed");
  const proposalSucceeded =
    proposal !== null &&
    detail !== null &&
    detail.run.status === "succeeded" &&
    !detail.stale &&
    !anyJobFailed &&
    !runNeedsClarification;
  let signBlocked: string | null = null;
  if (!proposalSucceeded) {
    if (runFailed || anyJobFailed) {
      signBlocked =
        "Signing is blocked — the run failed; no proposal is available to sign.";
    } else if (runNeedsClarification) {
      signBlocked =
        "Signing is blocked — clarification is needed before signing.";
    } else if (detail !== null && detail.stale) {
      signBlocked =
        "Signing is blocked — the run is stale; analytical inputs changed since the snapshot.";
    } else {
      signBlocked =
        "Signing is blocked — the proposal is incomplete; the run is still in progress.";
    }
  }

  let runStatusText: string;
  if (blocked !== null) {
    runStatusText = blocked;
  } else if (entryError !== null) {
    runStatusText = entryError;
  } else if (detail === null) {
    runStatusText =
      "Run prerequisites pending — waiting for a clean save to start the run.";
  } else {
    runStatusText = `Run ${detail.run.status}`;
    if (detail.stale) {
      runStatusText += " (stale — analytical inputs changed since the snapshot)";
    }
  }

  return (
    <section data-testid="proposal-review-section" aria-label="Proposal review">
      <h3>Proposal review</h3>
      <p data-testid="proposal-run-status">{runStatusText}</p>
      {(detail?.projections ?? []).map((proj) => {
        const job = detail?.jobs.find(
          (item) => item.question_key === proj.question_key,
        );
        const section = detail?.sections.find(
          (item) => item.question_key === proj.question_key,
        );
        const failed = job !== undefined && job.status === "failed";
        return (
          <div
            key={proj.question_key}
            data-testid={`proposal-question-${proj.question_key}`}
          >
            <p data-testid={`proposal-question-state-${proj.question_key}`}>
              {proposalQuestionStateText(
                proj.applicability,
                proj.applicability_reason,
                job === undefined
                  ? undefined
                  : { stage: job.stage, status: job.status },
                section !== undefined,
              )}
            </p>
            {failed && job !== undefined ? (
              <button
                type="button"
                className="x-button"
                data-testid={`proposal-retry-${proj.question_key}`}
                onClick={() => void handleRetry(proj.question_key, job.stage)}
              >
                Retry {proj.question_key}
              </button>
            ) : null}
            {retryError !== null && retryError.key === proj.question_key ? (
              <p>{retryError.message}</p>
            ) : null}
          </div>
        );
      })}
      {(detail?.sections ?? []).map((section) => {
        const key = section.question_key;
        const open = expanded[key] === true;
        const detailsId = `proposal-details-${encounterId}-${key}`;
        function toggle(): void {
          setExpanded((prev) => ({ ...prev, [key]: !(prev[key] === true) }));
        }
        return (
          <article
            key={key}
            data-testid={`proposal-section-${key}`}
            onClick={toggle}
          >
            <h4>{key}</h4>
            <p>
              {typeof section.rendered_text === "string"
                ? section.rendered_text
                : ""}
            </p>
            <button
              type="button"
              className="x-button"
              aria-expanded={open}
              aria-controls={detailsId}
              onClick={(event) => {
                event.stopPropagation();
                toggle();
              }}
            >
              {open
                ? `Hide transparency details for ${key}`
                : `Show transparency details for ${key}`}
            </button>
            {open ? (
              <div id={detailsId}>
                <p>Network version: {proposalText(section.network_version)}</p>
                <div data-testid={`proposal-inputs-${key}`}>
                  <p>Patient inputs (persisted snapshot)</p>
                  <pre>{proposalText(section.patient_inputs)}</pre>
                </div>
                <div data-testid={`proposal-cpt-${key}`}>
                  <p>CPT percentages (provider-estimated inputs)</p>
                  <pre>{proposalText(section.cpt_percentages)}</pre>
                </div>
                <div data-testid={`proposal-result-${key}`}>
                  <p>Posterior probabilities (deterministic inference result)</p>
                  <pre>{proposalText(section.result)}</pre>
                </div>
                <p>Prompt: {proposalText(section.prompt)}</p>
                <p>Template version: {proposalText(section.template_version)}</p>
                <p>Engine: {proposalText(section.engine)}</p>
                <p>Source paths: {proposalText(section.source_paths)}</p>
                <p>Missingness: {proposalText(section.missingness)}</p>
                <p>Effective hash: {proposalText(section.effective_hash)}</p>
                <p>Model: {proposalText(section.model)}</p>
                <p>Query: {proposalText(section.query)}</p>
              </div>
            ) : null}
          </article>
        );
      })}
      {proposal !== null ? (
        <section data-testid="proposal-proposal" aria-label="Initial proposal">
          <h4>Initial proposal (immutable)</h4>
          {proposalTitle !== "" ? <p>{proposalTitle}</p> : null}
          {proposalSections.length > 0 ? (
            <ul>
              {proposalSections.map((entry) => (
                <li key={entry.key}>
                  {entry.key}
                  {entry.text !== "" ? `: ${entry.text}` : null}
                </li>
              ))}
            </ul>
          ) : null}
          {proposalSkipped.length > 0 ? (
            <div>
              <p>Skipped questions:</p>
              <ul>
                {proposalSkipped.map((reason, index) => (
                  <li key={index}>{reason}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {proposalCoverageNote !== "" ? <p>{proposalCoverageNote}</p> : null}
          {proposalLimitations.length > 0 ? (
            <div>
              <p>Limitations:</p>
              <ul>
                {proposalLimitations.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      ) : null}
      <section data-testid="proposal-ddi" aria-label="Proposal drug interactions">
        <h4>Drug interactions (pinned to the proposal)</h4>
        {ddi === null ? (
          <p>DDI coverage unavailable for this run (no pinned DDI report).</p>
        ) : (
          <>
            {ddiDatasetVersion !== "" ? (
              <p>Dataset version: {ddiDatasetVersion}</p>
            ) : null}
            {ddiPairs.length === 0 ? <p>No pairs evaluated.</p> : null}
            {ddiPairs.map((pair) => (
              <article key={pair.pair_key || `${pair.drug_a}-${pair.drug_b}`}>
                <p>
                  {pair.pair_key !== ""
                    ? pair.pair_key
                    : `${pair.drug_a} + ${pair.drug_b}`}
                  : {pair.drug_a} + {pair.drug_b}
                </p>
                <p>
                  Severity: {pair.highest_known_severity ?? "unknown"}
                </p>
                <p>Status: {pair.status}</p>
                {pair.coverage_basis !== "" ? (
                  <p>Coverage: {pair.coverage_basis}</p>
                ) : null}
                {pair.evidence.length > 0 ? (
                  <ul>
                    {pair.evidence.map((item, index) => (
                      <li key={index}>
                        {item.source_severity}: {item.raw_text} (
                        {item.source_path})
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>No listed evidence.</p>
                )}
                {pair.conflicts.length > 0 ? (
                  <ul>
                    {pair.conflicts.map((item, index) => (
                      <li key={index}>
                        {item.source_severity} ({item.source_path})
                      </li>
                    ))}
                  </ul>
                ) : null}
              </article>
            ))}
            {ddiLimitations.length > 0 ? (
              <div>
                <p>Limitations:</p>
                <ul>
                  {ddiLimitations.map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        )}
      </section>
      <div className="x-field">
        <label htmlFor={`proposal-secondary-plan-${encounterId}`}>
          Secondary plan (physician edit; the initial proposal above is
          immutable)
        </label>
        <textarea
          id={`proposal-secondary-plan-${encounterId}`}
          data-testid="proposal-secondary-plan"
          value={secondaryPlan}
          disabled={readOnly}
          onChange={(event) => onSecondaryPlanChange(event.target.value)}
        />
      </div>
      {signBlocked !== null ? (
        <p data-testid="proposal-sign-blocked">{signBlocked}</p>
      ) : null}
    </section>
  );
}

/**
 * S50 signing (T9 journey contract): immutable proposal beside a
 * server-backed secondary plan, explicit sign, signed view, addenda.
 *
 * Data sources: run detail comes from the S48 remembered run (same
 * sessionStorage key ProposalReviewSection writes; this section never POSTs
 * a run, so entry stays single-flight). The proposal text, run status, and
 * run_id are read from that detail; the signed record comes from
 * GET signed-snapshot (readable by any role). The secondary plan persists
 * through PATCH/GET secondary-plan only — never draft_data.
 *
 * No role="status" nodes here: DraftEditor keeps the single live saveState
 * node (S13/S20/S48 precedent). Secondary save + sign status stay
 * addressable via their testids; errors use role="alert".
 */
function signerCacheKey(encounterId: string): string {
  return `xinsight.signer:${encounterId}`;
}

function readCachedSigner(encounterId: string): string | null {
  try {
    const raw = localStorage.getItem(signerCacheKey(encounterId));
    return raw !== null && raw !== "" ? raw : null;
  } catch {
    return null;
  }
}

function cacheSigner(encounterId: string, username: string): void {
  try {
    localStorage.setItem(signerCacheKey(encounterId), username);
  } catch {
    /* storage unavailable; signed view still shows the signer id */
  }
}

function snapshotText(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (value === null || value === undefined) {
    return "";
  }
  try {
    return JSON.stringify(value);
  } catch {
    return "";
  }
}

function proposalFullText(proposal: Record<string, unknown> | null): string {
  if (proposal === null) {
    return "";
  }
  const parts: string[] = [];
  if (typeof proposal.title === "string" && proposal.title !== "") {
    parts.push(proposal.title);
  }
  const sections = proposalSectionEntries(proposal.sections);
  for (const entry of sections) {
    parts.push(entry.text !== "" ? `${entry.key}: ${entry.text}` : entry.key);
  }
  const skipped = proposalSkippedEntries(proposal.skipped);
  for (const reason of skipped) {
    parts.push(reason);
  }
  if (typeof proposal.coverage_note === "string" && proposal.coverage_note !== "") {
    parts.push(proposal.coverage_note);
  }
  for (const item of proposalStringEntries(proposal.limitations)) {
    parts.push(item);
  }
  return parts.join("\n");
}

function SigningSection({
  encounter,
  userId,
  getRevision,
  onSigned,
}: {
  encounter: Encounter;
  userId: string;
  getRevision: () => number;
  onSigned: (next: Encounter) => void;
}) {
  const encounterId = encounter.id;
  const isAuthor = encounter.author_id === null || encounter.author_id === userId;
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const runDetailRef = useRef<RunDetail | null>(null);
  runDetailRef.current = runDetail;
  const [snapshot, setSnapshot] = useState<Record<string, unknown> | null>(null);
  const [signedView, setSignedView] = useState(encounter.state === "signed");
  const [secondaryText, setSecondaryText] = useState("");
  const secondaryTextRef = useRef("");
  const [secondaryRev, setSecondaryRev] = useState(0);
  const secondaryRevRef = useRef(0);
  const [secondaryStatus, setSecondaryStatus] = useState("");
  const secondaryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const secondarySavingRef = useRef(false);
  const [reviewAck, setReviewAck] = useState(false);
  const [baselineAck, setBaselineAck] = useState(false);
  const [signStatus, setSignStatus] = useState("");
  const [signing, setSigning] = useState(false);
  const signingRef = useRef(false);
  const [sessionUsername, setSessionUsername] = useState<string | null>(null);
  const [addenda, setAddenda] = useState<Addendum[]>([]);
  const [addReason, setAddReason] = useState("");
  const [addText, setAddText] = useState("");
  const [addStatus, setAddStatus] = useState("");
  const [adding, setAdding] = useState(false);
  const addingRef = useRef(false);

  const draftActive = encounter.state === "draft" && !signedView;
  const secondaryEditable = draftActive && isAuthor;

  useEffect(() => {
    setSignedView(encounter.state === "signed");
  }, [encounter.state]);

  useEffect(() => {
    let cancelled = false;
    fetchSession()
      .then((session) => {
        if (!cancelled && session) {
          setSessionUsername(session.username);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  // Cache the author's username while viewing the own draft so a later
  // cross-physician signed view can attribute the signature without a
  // backend lookup (physician directory is admin-only).
  useEffect(() => {
    if (sessionUsername !== null && isAuthor) {
      cacheSigner(encounterId, sessionUsername);
    }
  }, [sessionUsername, isAuthor, encounterId]);

  // Secondary plan: server truth on mount/encounter change.
  useEffect(() => {
    let cancelled = false;
    setSecondaryStatus("");
    if (secondaryTimerRef.current !== null) {
      clearTimeout(secondaryTimerRef.current);
      secondaryTimerRef.current = null;
    }
    getSecondaryPlan(encounterId)
      .then((plan) => {
        if (cancelled) {
          return;
        }
        if (plan !== null) {
          setSecondaryText(plan.text ?? "");
          secondaryTextRef.current = plan.text ?? "";
          setSecondaryRev(plan.revision ?? 0);
          secondaryRevRef.current = plan.revision ?? 0;
        } else {
          setSecondaryText("");
          secondaryTextRef.current = "";
          setSecondaryRev(0);
          secondaryRevRef.current = 0;
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSecondaryStatus("Could not load the secondary plan.");
        }
      });
    return () => {
      cancelled = true;
      if (secondaryTimerRef.current !== null) {
        clearTimeout(secondaryTimerRef.current);
        secondaryTimerRef.current = null;
      }
    };
  }, [encounterId]);

  // Run detail: observe the S48 remembered run (never POST here). Poll for
  // its appearance and for status while non-terminal; 403 (non-author)
  // falls back to the snapshot below.
  useEffect(() => {
    let cancelled = false;
    async function fetchRemembered(): Promise<void> {
      const remembered = readRememberedRunId(encounterId);
      if (remembered === null) {
        return;
      }
      if (runDetailRef.current !== null && runDetailRef.current.run.id === remembered) {
        return;
      }
      try {
        const data = await getRun(remembered);
        if (!cancelled) {
          setRunDetail(data);
        }
      } catch {
        /* non-author or transient: snapshot covers the signed view */
      }
    }
    async function refresh(): Promise<void> {
      const current = runDetailRef.current;
      if (current === null || isProposalRunTerminal(current)) {
        return;
      }
      try {
        const data = await getRun(current.run.id);
        if (!cancelled) {
          setRunDetail(data);
        }
      } catch {
        /* transient read failure: keep polling on schedule */
      }
    }
    void fetchRemembered();
    const timer = setInterval(() => {
      if (cancelled) {
        return;
      }
      if (runDetailRef.current === null) {
        void fetchRemembered();
      } else {
        void refresh();
      }
    }, 2000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [encounterId]);

  // Signed snapshot: any authenticated role may read; drives the signed
  // view when the encounter is signed or a sign raced to 409.
  useEffect(() => {
    let cancelled = false;
    getSignedSnapshot(encounterId)
      .then((snap) => {
        if (cancelled || snap === null) {
          return;
        }
        setSnapshot(snap);
        setSignedView(true);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [encounterId]);

  // Addenda list: session-only read, shown read-only to non-signers.
  useEffect(() => {
    let cancelled = false;
    if (!signedView) {
      return;
    }
    listAddenda(encounterId)
      .then((items) => {
        if (!cancelled) {
          setAddenda(items);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [encounterId, signedView]);

  async function saveSecondaryNow(): Promise<void> {
    if (secondaryTimerRef.current !== null) {
      clearTimeout(secondaryTimerRef.current);
      secondaryTimerRef.current = null;
    }
    const text = secondaryTextRef.current;
    if (text.trim() === "" || !isAuthor || encounter.state !== "draft" || signedView) {
      return;
    }
    if (secondarySavingRef.current) {
      return;
    }
    secondarySavingRef.current = true;
    setSecondaryStatus("Saving…");
    try {
      const saved = await saveSecondaryPlan(
        encounterId,
        text,
        secondaryRevRef.current,
        newIdempotencyKey(),
      );
      secondaryRevRef.current = saved.revision;
      setSecondaryRev(saved.revision);
      setSecondaryStatus("Saved");
    } catch (failure: unknown) {
      const status = (failure as { status?: number }).status;
      const message =
        failure instanceof Error ? failure.message : "Could not save the secondary plan.";
      if (status === 412) {
        // Reload the server revision but keep the physician's text so an
        // edit is never silently dropped; the next edit saves cleanly.
        try {
          const server = await getSecondaryPlan(encounterId);
          if (server !== null) {
            secondaryRevRef.current = server.revision;
            setSecondaryRev(server.revision);
          } else {
            secondaryRevRef.current = 0;
            setSecondaryRev(0);
          }
        } catch {
          /* keep the local revision; the message still guides reload */
        }
      }
      if (status === 409) {
        try {
          const snap = await getSignedSnapshot(encounterId);
          if (snap !== null) {
            setSnapshot(snap);
            setSignedView(true);
          }
        } catch {
          /* keep the read-only message */
        }
      }
      setSecondaryStatus(message);
    } finally {
      secondarySavingRef.current = false;
    }
  }

  function handleSecondaryChange(value: string): void {
    if (!secondaryEditable) {
      return;
    }
    setSecondaryText(value);
    secondaryTextRef.current = value;
    setSecondaryStatus("Saving…");
    if (secondaryTimerRef.current !== null) {
      clearTimeout(secondaryTimerRef.current);
    }
    secondaryTimerRef.current = setTimeout(() => {
      secondaryTimerRef.current = null;
      void saveSecondaryNow();
    }, 1000);
  }

  const proposalRecord =
    runDetail !== null &&
    typeof runDetail.proposal === "object" &&
    runDetail.proposal !== null
      ? (runDetail.proposal as Record<string, unknown>)
      : null;
  const snapshotProposal =
    snapshot !== null &&
    typeof snapshot.initial_proposal === "object" &&
    snapshot.initial_proposal !== null
      ? (snapshot.initial_proposal as Record<string, unknown>)
      : null;
  // Signed view prefers the frozen snapshot; drafts read the live run.
  const activeProposal = signedView && snapshotProposal !== null ? snapshotProposal : proposalRecord;
  const proposalText = proposalFullText(activeProposal);
  const snapshotSecondary =
    snapshot !== null &&
    typeof snapshot.secondary_plan === "object" &&
    snapshot.secondary_plan !== null
      ? String(
          (snapshot.secondary_plan as Record<string, unknown>).text ?? "",
        )
      : "";
  const displaySecondary = signedView && snapshotSecondary !== "" ? snapshotSecondary : secondaryText;
  const showComparison =
    proposalText !== "" &&
    displaySecondary.trim() !== "" &&
    displaySecondary !== proposalText;

  const runFailed =
    runDetail !== null &&
    (runDetail.run.status === "failed" ||
      runDetail.jobs.some((item) => item.status === "failed"));
  const runNeedsClarification =
    runDetail !== null &&
    (runDetail.run.status === "needs_clarification" ||
      runDetail.projections.some((item) => item.applicability === "needs_clarification"));
  const proposalSucceeded =
    proposalRecord !== null &&
    runDetail !== null &&
    runDetail.run.status === "succeeded" &&
    !runDetail.stale &&
    !runFailed &&
    !runNeedsClarification;

  function blockedMessage(): string {
    if (runDetail === null) {
      return "Signing is blocked — the proposal is incomplete; the run is still in progress.";
    }
    if (runFailed) {
      return "Signing is blocked — the run failed; no proposal is available to sign.";
    }
    if (runNeedsClarification) {
      return "Signing is blocked — clarification is needed before signing.";
    }
    if (runDetail.stale) {
      return "Signing is blocked — the run is stale; analytical inputs changed since the snapshot.";
    }
    return "Signing is blocked — the proposal is incomplete; the run is still in progress.";
  }

  const effectiveSignStatus =
    signStatus !== "" ? signStatus : !proposalSucceeded && !signedView ? blockedMessage() : "";

  async function handleSign(): Promise<void> {
    if (signingRef.current) {
      return;
    }
    const detail = runDetailRef.current;
    if (detail === null || !proposalSucceeded) {
      setSignStatus(blockedMessage());
      return;
    }
    if (!reviewAck) {
      setSignStatus("Review acknowledgment is required before signing.");
      return;
    }
    if (encounter.kind === "follow_up" && !baselineAck) {
      setSignStatus("Baseline reconciliation is required.");
      return;
    }
    signingRef.current = true;
    setSigning(true);
    // One Idempotency-Key per click-attempt: a double-click on the same
    // attempt reuses the guard above, so the server never sees a duplicate.
    const attemptKey = newIdempotencyKey();
    try {
      // Flush any pending secondary autosave first so the sign carries it.
      await saveSecondaryNow();
      const encRev = getRevision();
      const body = {
        encounter_revision: encRev,
        run_id: detail.run.id,
        secondary_plan_revision: secondaryRevRef.current,
        review_acknowledgments: [
          "Physician reviewed the initial proposal and secondary plan.",
        ],
        baseline_acknowledgment: encounter.kind === "follow_up",
      };
      const result = await signEncounter(encounterId, body, encRev, attemptKey);
      if (sessionUsername !== null) {
        cacheSigner(encounterId, sessionUsername);
      }
      onSigned(result.encounter as Encounter);
      try {
        const snap = await getSignedSnapshot(encounterId);
        if (snap !== null) {
          setSnapshot(snap);
        } else if (
          typeof result.signed_snapshot === "object" &&
          result.signed_snapshot !== null
        ) {
          setSnapshot(result.signed_snapshot as Record<string, unknown>);
        }
      } catch {
        if (
          typeof result.signed_snapshot === "object" &&
          result.signed_snapshot !== null
        ) {
          setSnapshot(result.signed_snapshot as Record<string, unknown>);
        }
      }
      try {
        setAddenda(await listAddenda(encounterId));
      } catch {
        /* empty until the first correction */
      }
      setSignedView(true);
      setSignStatus("");
    } catch (failure: unknown) {
      const status = (failure as { status?: number }).status;
      const message = failure instanceof Error ? failure.message : "Could not sign the plan.";
      if (
        status === 409 &&
        /only draft encounters can be signed/i.test(message)
      ) {
        // A retried attempt raced a completed sign: adopt the record.
        try {
          const fresh = await getEncounter(encounterId);
          onSigned(fresh);
        } catch {
          /* snapshot below still drives the view */
        }
        try {
          const snap = await getSignedSnapshot(encounterId);
          if (snap !== null) {
            setSnapshot(snap);
            setSignedView(true);
            setSignStatus("");
            return;
          }
        } catch {
          /* fall through to the message */
        }
      }
      // Edited secondary text is never cleared here.
      setSignStatus(message);
    } finally {
      signingRef.current = false;
      setSigning(false);
    }
  }

  const signerId =
    snapshot !== null && typeof snapshot.signer_id === "string"
      ? String(snapshot.signer_id)
      : null;
  const signedAt =
    snapshot !== null && typeof snapshot.signed_at === "string"
      ? String(snapshot.signed_at)
      : "";
  const snapshotHash =
    snapshot !== null && typeof snapshot.snapshot_hash === "string"
      ? String(snapshot.snapshot_hash)
      : "";
  let signerDisplay = signerId ?? "";
  if (signerId !== null && signerId === userId && sessionUsername !== null) {
    signerDisplay = sessionUsername;
  } else {
    const cached = readCachedSigner(encounterId);
    if (cached !== null) {
      signerDisplay = signerId !== null ? `${cached} (${signerId})` : cached;
    }
  }
  const isOriginalSigner = signerId !== null && signerId === userId;

  async function handleAddendum(): Promise<void> {
    if (addingRef.current) {
      return;
    }
    if (!isOriginalSigner || !signedView) {
      return;
    }
    const reason = addReason.trim();
    const correction = addText.trim();
    if (reason === "" || correction === "") {
      setAddStatus("Reason and correction text are required.");
      return;
    }
    addingRef.current = true;
    setAdding(true);
    setAddStatus("");
    const attemptKey = newIdempotencyKey();
    try {
      const created = await addAddendum(encounterId, reason, correction, attemptKey);
      setAddenda((prev) =>
        prev.some((item) => item.id === created.id) ? prev : [...prev, created],
      );
      setAddReason("");
      setAddText("");
      setAddStatus("Addendum saved.");
    } catch (failure: unknown) {
      setAddStatus(
        failure instanceof Error ? failure.message : "Could not save the addendum.",
      );
    } finally {
      addingRef.current = false;
      setAdding(false);
    }
  }

  return (
    <section data-testid="signing-section" aria-label="Signing">
      <h3>Signing</h3>
      <div data-testid="signing-proposal">
        {proposalText !== "" ? (
          <p>{proposalText}</p>
        ) : (
          <p>No proposal yet — the run has not succeeded.</p>
        )}
      </div>
      <div className="x-field">
        <label htmlFor={`signing-secondary-${encounterId}`}>
          Secondary plan (physician edit; the initial proposal above is immutable)
        </label>
        <textarea
          id={`signing-secondary-${encounterId}`}
          data-testid="signing-secondary-plan"
          value={signedView && snapshotSecondary !== "" ? snapshotSecondary : secondaryText}
          disabled={!secondaryEditable}
          readOnly={!secondaryEditable}
          onChange={(event) => handleSecondaryChange(event.target.value)}
        />
      </div>
      {secondaryStatus !== "" ? <p>{secondaryStatus}</p> : null}
      {showComparison ? (
        <div data-testid="signing-comparison">
          <div>
            <h4>Initial proposal</h4>
            <p>{proposalText.slice(0, 2000)}</p>
          </div>
          <div>
            <h4>Physician edits</h4>
            <p>{displaySecondary.slice(0, 2000)}</p>
          </div>
        </div>
      ) : null}
      {signedView ? (
        <div data-testid="signing-signed-view">
          <p>
            Signer: <span data-testid="signing-signer">{signerDisplay}</span>
          </p>
          <p>
            Signed at: <span data-testid="signing-time">{signedAt}</span>
          </p>
          {snapshotHash !== "" ? <p>Snapshot hash: {snapshotHash}</p> : null}
          {proposalText !== "" ? <p>{proposalText}</p> : null}
          {snapshotSecondary !== "" ? <p>{snapshotSecondary}</p> : null}
          <button
            type="button"
            className="x-button"
            data-testid="signing-print"
            onClick={() => window.print()}
          >
            Print signed record
          </button>
        </div>
      ) : null}
      {!signedView && draftActive && isAuthor ? (
        <div>
          <div className="x-field">
            <label htmlFor={`signing-review-ack-${encounterId}`}>
              <input
                id={`signing-review-ack-${encounterId}`}
                type="checkbox"
                data-testid="signing-review-ack"
                checked={reviewAck}
                onChange={(event) => setReviewAck(event.target.checked)}
              />{" "}
              I reviewed the initial proposal and the secondary plan
            </label>
          </div>
          {encounter.kind === "follow_up" ? (
            <div className="x-field">
              <label htmlFor={`signing-baseline-ack-${encounterId}`}>
                <input
                  id={`signing-baseline-ack-${encounterId}`}
                  type="checkbox"
                  data-testid="signing-baseline-ack"
                  checked={baselineAck}
                  onChange={(event) => setBaselineAck(event.target.checked)}
                />{" "}
                I reconciled against the baseline record
              </label>
            </div>
          ) : null}
          <button
            type="button"
            className="x-button"
            data-testid="signing-sign-button"
            disabled={signing}
            onClick={() => void handleSign()}
          >
            {signing ? "Signing…" : "Sign plan"}
          </button>
        </div>
      ) : null}
      <p data-testid="signing-status" role="alert">
        {effectiveSignStatus}
      </p>
      {signedView ? (
        <div>
          {isOriginalSigner ? (
            <div>
              <div className="x-field">
                <label htmlFor={`signing-addendum-reason-${encounterId}`}>
                  Correction reason
                </label>
                <input
                  id={`signing-addendum-reason-${encounterId}`}
                  data-testid="signing-addendum-reason"
                  autoComplete="off"
                  value={addReason}
                  onChange={(event) => setAddReason(event.target.value)}
                />
              </div>
              <div className="x-field">
                <label htmlFor={`signing-addendum-text-${encounterId}`}>
                  Correction text
                </label>
                <textarea
                  id={`signing-addendum-text-${encounterId}`}
                  data-testid="signing-addendum-text"
                  value={addText}
                  onChange={(event) => setAddText(event.target.value)}
                />
              </div>
              <button
                type="button"
                className="x-button"
                data-testid="signing-addendum-submit"
                disabled={adding}
                onClick={() => void handleAddendum()}
              >
                {adding ? "Saving…" : "Add addendum"}
              </button>
              {addStatus !== "" ? <p>{addStatus}</p> : null}
            </div>
          ) : null}
          <div data-testid="signing-addenda-list">
            {addenda.map((item) => (
              <article key={item.id} data-testid="signing-addendum-item">
                <p>{item.reason}</p>
                <p>{item.correction_text}</p>
                <p>{item.created_at}</p>
              </article>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function DraftEditor({
  patient,
  userId,
  role,
  onClose,
  initialEncounterId,
}: {
  patient: Patient;
  userId: string;
  role: string;
  onClose: () => void;
  initialEncounterId?: string | null;
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
  const [panssAnswers, setPanssAnswers] = useState<PanssAnswers>(() => emptyPanssAnswers());
  const [panssNotAssessed, setPanssNotAssessed] = useState(false);
  const panssAnswersRef = useRef<PanssAnswers>(emptyPanssAnswers());
  const panssNotAssessedRef = useRef(false);
  const savedPanssRef = useRef(panssDirtyKey(emptyPanssAnswers(), false));
  const [cssrsLevels, setCssrsLevels] = useState<CssrsLevels>(() => emptyCssrs());
  const [cssrsNotAssessed, setCssrsNotAssessed] = useState(false);
  const cssrsLevelsRef = useRef<CssrsLevels>(emptyCssrs());
  const cssrsNotAssessedRef = useRef(false);
  const savedCssrsRef = useRef(cssrsDirtyKey(emptyCssrs(), false));
  const cssrsExtraRef = useRef<Record<string, unknown>>({});
  const [historyDef, setHistoryDef] = useState<HistoryContent | null>(null);
  const [historyDefLoaded, setHistoryDefLoaded] = useState(false);
  const historyDefRef = useRef<HistoryContent | null>(null);
  const [historyValues, setHistoryValues] = useState<HistoryState>({});
  const historyRef = useRef<HistoryState>({});
  const savedHistoryRef = useRef(historyDirtyKey({}));
  const [effects, setEffects] = useState<EffectsState>(() => emptyEffects());
  const effectsRef = useRef<EffectsState>(emptyEffects());
  const savedEffectsRef = useRef(effectsDirtyKey(emptyEffects()));
  const [recon, setRecon] = useState<Record<string, unknown> | null>(null);
  const reconRef = useRef<Record<string, unknown> | null>(null);
  const savedReconRef = useRef(JSON.stringify(null));
  const [meds, setMeds] = useState<MedEntry[]>([]);
  const medsRef = useRef<MedEntry[]>([]);
  const savedMedsRef = useRef(medsDirtyKey([]));
  const [ddiReport, setDdiReport] = useState<DdiReport | null>(null);
  const ddiReportRef = useRef<DdiReport | null>(null);
  const savedDdiRef = useRef(JSON.stringify(null));
  const [ddiStatus, setDdiStatus] = useState<"idle" | "pending" | "current" | "error">(
    "idle",
  );
  const [ddiError, setDdiError] = useState<string | null>(null);
  // S48 secondary plan: physician-editable draft text persisted into
  // draft_data.secondary_plan through the shared autosave path. Unknown keys
  // pass through verbatim and stay out of snapshots/fingerprints.
  const [secondaryPlan, setSecondaryPlan] = useState("");
  const secondaryPlanRef = useRef("");
  const savedSecondaryRef = useRef("");
  const [lastCheckedKey, setLastCheckedKey] = useState<string | null>(null);
  const lastCheckedKeyRef = useRef<string | null>(null);
  const [phone, setPhone] = useState("");
  const [phoneState, setPhoneState] = useState("");
  const phoneRevisionRef = useRef(0);
  const [baselineSnapshot, setBaselineSnapshot] = useState<Encounter | null>(null);

  function isDiagDirty(): boolean {
    return JSON.stringify(diagAnswersRef.current) !== savedDiagRef.current;
  }

  function isPanssDirty(): boolean {
    return panssDirtyKey(panssAnswersRef.current, panssNotAssessedRef.current) !== savedPanssRef.current;
  }

  function isCssrsDirty(): boolean {
    return cssrsDirtyKey(cssrsLevelsRef.current, cssrsNotAssessedRef.current) !== savedCssrsRef.current;
  }

  function isHistoryDirty(): boolean {
    return historyDirtyKey(historyRef.current) !== savedHistoryRef.current;
  }

  function isEffectsDirty(): boolean {
    return effectsDirtyKey(effectsRef.current) !== savedEffectsRef.current;
  }

  function isReconDirty(): boolean {
    return JSON.stringify(reconRef.current) !== savedReconRef.current;
  }

  function isMedsDirty(): boolean {
    return medsDirtyKey(medsRef.current) !== savedMedsRef.current;
  }

  function isDdiDirty(): boolean {
    return JSON.stringify(ddiReportRef.current) !== savedDdiRef.current;
  }

  function isSecondaryDirty(): boolean {
    return secondaryPlanRef.current !== savedSecondaryRef.current;
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
        const resumable =
          (initialEncounterId
            ? all.find((e) => e.id === initialEncounterId)
            : undefined) ??
          all.find((e) => e.state === "draft") ??
          all[0];
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
        const storedPanss =
          typeof full.draft_data?.panss === "object" && full.draft_data?.panss !== null
            ? (full.draft_data.panss as unknown)
            : null;
        const initialPanss = panssFromStored(storedPanss);
        setPanssAnswers(initialPanss.answers);
        panssAnswersRef.current = initialPanss.answers;
        setPanssNotAssessed(initialPanss.notAssessed);
        panssNotAssessedRef.current = initialPanss.notAssessed;
        savedPanssRef.current = panssDirtyKey(initialPanss.answers, initialPanss.notAssessed);
        const storedCssrs =
          typeof full.draft_data?.cssrs === "object" && full.draft_data?.cssrs !== null
            ? (full.draft_data.cssrs as unknown)
            : null;
        const initialCssrs = cssrsFromStored(storedCssrs);
        setCssrsLevels(initialCssrs.levels);
        cssrsLevelsRef.current = initialCssrs.levels;
        setCssrsNotAssessed(initialCssrs.notAssessed);
        cssrsNotAssessedRef.current = initialCssrs.notAssessed;
        cssrsExtraRef.current = initialCssrs.extra;
        savedCssrsRef.current = cssrsDirtyKey(initialCssrs.levels, initialCssrs.notAssessed);
        const storedHistory =
          typeof full.draft_data?.history === "object" && full.draft_data?.history !== null
            ? (full.draft_data.history as unknown)
            : null;
        const initialHistory = historyFromStored(storedHistory);
        setHistoryValues(initialHistory);
        historyRef.current = initialHistory;
        savedHistoryRef.current = historyDirtyKey(initialHistory);
        const storedEffects =
          typeof full.draft_data?.effects === "object" && full.draft_data?.effects !== null
            ? (full.draft_data.effects as unknown)
            : null;
        const initialEffects = effectsFromStored(storedEffects);
        setEffects(initialEffects);
        effectsRef.current = initialEffects;
        savedEffectsRef.current = effectsDirtyKey(initialEffects);
        const initialRecon = reconFromStored(full.draft_data?.history_reconciliation);
        setRecon(initialRecon);
        reconRef.current = initialRecon;
        savedReconRef.current = JSON.stringify(initialRecon);
        const initialMeds = medsFromStored(full.draft_data?.medications);
        setMeds(initialMeds);
        medsRef.current = initialMeds;
        savedMedsRef.current = medsDirtyKey(initialMeds);
        const initialDdi = ddiFromStored(full.draft_data?.ddi_report);
        setDdiReport(initialDdi);
        ddiReportRef.current = initialDdi;
        savedDdiRef.current = JSON.stringify(initialDdi);
        const initialSecondary =
          typeof full.draft_data?.secondary_plan === "string"
            ? (full.draft_data.secondary_plan as string)
            : "";
        setSecondaryPlan(initialSecondary);
        secondaryPlanRef.current = initialSecondary;
        savedSecondaryRef.current = initialSecondary;
        lastCheckedKeyRef.current = null;
        setLastCheckedKey(null);
        if (initialDdi === null && initialMeds.length === 0) {
          setDdiStatus("idle");
        } else {
          // Conservative: a persisted report is stale until explicitly
          // re-checked, so it never renders as current after reload.
          setDdiStatus("pending");
        }
        setDdiError(null);
        setPhone(patient.phone ?? "");
        phoneRevisionRef.current = patient.revision;
        setPhoneState("");
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
  }, [patient.id, initialEncounterId]);
  // S14 follow-up baseline snapshot: historical scores only, never prefilled.
  useEffect(() => {
    const baselineId =
      encounter !== null &&
      encounter.kind === "follow_up" &&
      typeof encounter.baseline_encounter_id === "string"
        ? encounter.baseline_encounter_id
        : null;
    if (baselineId === null) {
      setBaselineSnapshot(null);
      return;
    }
    let cancelled = false;
    setBaselineSnapshot(null);
    getEncounter(baselineId)
      .then((baseline) => {
        if (!cancelled) {
          setBaselineSnapshot(baseline);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBaselineSnapshot(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [encounter?.id, encounter?.kind, encounter?.baseline_encounter_id]);


  // S12 released history/effects definition, generic over its content.
  // 404 (draft unreleased) leaves definition null: sections stay visible
  // with an honest unavailable state and send no history/effects block.
  useEffect(() => {
    let cancelled = false;
    // Sole owner of definition state: reset on patient change, then fetch.
    // (Encounter-load success must not reset this; the definition fetch
    // resolves first and a late reset would clobber it.)
    setHistoryDef(null);
    historyDefRef.current = null;
    setHistoryDefLoaded(false);
    getHistoryContent()
      .then((content) => {
        if (cancelled) {
          return;
        }
        setHistoryDef(content);
        historyDefRef.current = content;
        setHistoryDefLoaded(true);
      })
      .catch(() => {
        if (cancelled) {
          return;
        }
        setHistoryDef(null);
        historyDefRef.current = null;
        setHistoryDefLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [patient.id]);

  // If the definition arrives after local history/effects edits, flush them
  // through the shared S07 path once a version is known.
  useEffect(() => {
    if (historyDef === null || encounter?.state !== "draft") {
      return;
    }
    if (encounter.author_id !== null && encounter.author_id !== userId) {
      return;
    }
    if (isHistoryDirty() || isEffectsDirty()) {
      scheduleSave(noteRef.current, diagAnswersRef.current);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyDef]);

  // S20 DDI freshness: any medication change invalidates the last check.
  // The checked report stays hidden while pending so a stale report never
  // renders as current; the user re-checks explicitly (no auto-fetch loop).
  useEffect(() => {
    if (ddiStatus === "error") {
      return;
    }
    const currentKey = medsDirtyKey(meds);
    if (lastCheckedKey === null) {
      if (ddiReport === null && meds.length === 0) {
        if (ddiStatus !== "idle") {
          setDdiStatus("idle");
        }
      } else if (ddiStatus !== "pending") {
        setDdiStatus("pending");
      }
      return;
    }
    let checkedMeds: string | null = null;
    try {
      const parsed = JSON.parse(lastCheckedKey) as { meds?: unknown };
      checkedMeds = typeof parsed.meds === "string" ? parsed.meds : null;
    } catch {
      checkedMeds = null;
    }
    if (ddiReport === null || checkedMeds === null || currentKey !== checkedMeds) {
      if (ddiStatus !== "pending") {
        setDdiStatus("pending");
      }
    } else if (ddiStatus !== "current") {
      setDdiStatus("current");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meds, ddiReport, lastCheckedKey]);

  // Page-transition flush: attempt a final save when leaving.
  useEffect(() => {
    function onBeforeUnload(event: BeforeUnloadEvent): void {
      if (
        (noteRef.current !== savedNoteRef.current || isDiagDirty() || isPanssDirty() || isCssrsDirty() || isHistoryDirty() || isEffectsDirty() || isReconDirty() || isMedsDirty() || isDdiDirty() || isSecondaryDirty()) &&
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
      (noteRef.current !== savedNoteRef.current || isDiagDirty() || isPanssDirty() || isCssrsDirty() || isHistoryDirty() || isEffectsDirty() || isReconDirty() || isMedsDirty() || isDdiDirty() || isSecondaryDirty()) &&
      encounter !== null;
  });

  function handleClose(): void {
    if (
      (noteRef.current !== savedNoteRef.current || isDiagDirty() || isPanssDirty() || isCssrsDirty() || isHistoryDirty() || isEffectsDirty() || isReconDirty() || isMedsDirty() || isDdiDirty() || isSecondaryDirty()) &&
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
    // Snapshot PANSS/C-SSRS at fire time so concurrent edits merge via refs.
    const panssAnsSnapshot: PanssAnswers = { ...panssAnswersRef.current };
    const panssSkipSnapshot = panssNotAssessedRef.current;
    const panssBlock = serializePanss(panssAnsSnapshot, panssSkipSnapshot);
    const cssrsLevelsSnapshot: CssrsLevels = {
      L1: { ...cssrsLevelsRef.current.L1 },
      L2: { ...cssrsLevelsRef.current.L2 },
      L3: { ...cssrsLevelsRef.current.L3 },
      L4: { ...cssrsLevelsRef.current.L4 },
      L5: { ...cssrsLevelsRef.current.L5 },
    };
    const cssrsSkipSnapshot = cssrsNotAssessedRef.current;
    const cssrsExtraSnapshot = { ...cssrsExtraRef.current };
    const cssrsBlock = serializeCssrs(cssrsLevelsSnapshot, cssrsSkipSnapshot, cssrsExtraSnapshot);
    // Snapshot S12 history/effects/reconciliation at fire time the same way.
    const effectsSnapshot: EffectsState = Object.fromEntries(
      EFFECT_IDS.map((id) => [id, { ...(effectsRef.current[id] ?? { status: null, severity: null }) }]),
    ) as EffectsState;
    const historySnapshot: HistoryState = { ...historyRef.current };
    const reconSnapshot = reconRef.current === null ? null : { ...reconRef.current };
    const medsSnapshot: MedEntry[] = medsRef.current.map((entry) =>
      entry.catalog_drug_id !== undefined
        ? { catalog_drug_id: entry.catalog_drug_id }
        : { unknown_label: entry.unknown_label as string },
    );
    const ddiSnapshot = ddiReportRef.current;
    const secondarySnapshot = secondaryPlanRef.current;
    const historyVersionSnapshot = historyDefRef.current?.definition_version ?? null;
    const effectsBlock = serializeEffects(effectsSnapshot, historyVersionSnapshot);
    const historyBlock = serializeHistory(historySnapshot, historyVersionSnapshot);
    try {
      const basePayload = buildDraftPayload(value, diagValue, extra);
      const withPanss =
        panssBlock === undefined ? basePayload : { ...basePayload, panss: panssBlock };
      const withCssrs =
        cssrsBlock === undefined ? withPanss : { ...withPanss, cssrs: cssrsBlock };
      const withEffects =
        effectsBlock === undefined ? withCssrs : { ...withCssrs, effects: effectsBlock };
      const withHistory =
        historyBlock === undefined ? withEffects : { ...withEffects, history: historyBlock };
      const withRecon =
        reconSnapshot === null ? withHistory : { ...withHistory, history_reconciliation: reconSnapshot };
      const withMeds = { ...withRecon, medications: medsSnapshot };
      const payload =
        ddiSnapshot === null
          ? { ...withMeds, secondary_plan: secondarySnapshot }
          : { ...withMeds, ddi_report: ddiSnapshot, secondary_plan: secondarySnapshot };
      const updated = await patchEncounter(
        encounter.id,
        payload,
        revision,
      );
      revisionRef.current = updated.revision;
      savedNoteRef.current = value;
      savedDiagRef.current = JSON.stringify(diagValue);
      savedPanssRef.current = panssDirtyKey(panssAnsSnapshot, panssSkipSnapshot);
      savedCssrsRef.current = cssrsDirtyKey(cssrsLevelsSnapshot, cssrsSkipSnapshot);
      // Withheld blocks (no released version, or incomplete) stay dirty so a
      // later save still flushes them; only acknowledged writes clear.
      if (effectsBlock !== undefined) {
        savedEffectsRef.current = effectsDirtyKey(effectsSnapshot);
      }
      if (historyBlock !== undefined) {
        savedHistoryRef.current = historyDirtyKey(historySnapshot);
      }
      savedMedsRef.current = medsDirtyKey(medsSnapshot);
      savedDdiRef.current = JSON.stringify(ddiSnapshot);
      savedReconRef.current = JSON.stringify(reconSnapshot);
      savedSecondaryRef.current = secondarySnapshot;
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
      if (
        noteRef.current === value &&
        JSON.stringify(diagAnswersRef.current) === JSON.stringify(diagValue) &&
        panssDirtyKey(panssAnswersRef.current, panssNotAssessedRef.current) ===
          panssDirtyKey(panssAnsSnapshot, panssSkipSnapshot) &&
        cssrsDirtyKey(cssrsLevelsRef.current, cssrsNotAssessedRef.current) ===
          cssrsDirtyKey(cssrsLevelsSnapshot, cssrsSkipSnapshot) &&
        effectsDirtyKey(effectsRef.current) === effectsDirtyKey(effectsSnapshot) &&
        historyDirtyKey(historyRef.current) === historyDirtyKey(historySnapshot) &&
        medsDirtyKey(medsRef.current) === medsDirtyKey(medsSnapshot) &&
        JSON.stringify(ddiReportRef.current) === JSON.stringify(ddiSnapshot) &&
        JSON.stringify(reconRef.current) === JSON.stringify(reconSnapshot) &&
        secondaryPlanRef.current === secondarySnapshot
      ) {
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

  function handlePanssItem(id: string, value: number | null): void {
    if (encounter?.state !== "draft" || readOnly) {
      return;
    }
    if (!PANSS_ALL_IDS.includes(id)) {
      return;
    }
    if (value !== null && (!Number.isInteger(value) || value < 1 || value > 7)) {
      return;
    }
    const next = { ...panssAnswersRef.current, [id]: value };
    setPanssAnswers(next);
    panssAnswersRef.current = next;
    // Selecting any item after skip replaces the skip with answers.
    if (panssNotAssessedRef.current) {
      setPanssNotAssessed(false);
      panssNotAssessedRef.current = false;
    }
    if (staleRef.current) {
      setSaveState("Stale revision");
      return;
    }
    scheduleSave(noteRef.current, diagAnswersRef.current);
  }

  function handlePanssSkip(): void {
    if (encounter?.state !== "draft" || readOnly) {
      return;
    }
    const cleared = emptyPanssAnswers();
    setPanssAnswers(cleared);
    panssAnswersRef.current = cleared;
    setPanssNotAssessed(true);
    panssNotAssessedRef.current = true;
    if (staleRef.current) {
      setSaveState("Stale revision");
      return;
    }
    scheduleSave(noteRef.current, diagAnswersRef.current);
  }

  function handleCssrsLevel(id: CssrsLevelId, value: boolean | null): void {
    if (encounter?.state !== "draft" || readOnly) {
      return;
    }
    if (!CSSRS_IDS.includes(id)) {
      return;
    }
    const current = cssrsLevelsRef.current[id];
    const next = {
      ...cssrsLevelsRef.current,
      [id]: value === true ? { endorsed: true, period: current.period } : { endorsed: value, period: null },
    };
    setCssrsLevels(next);
    cssrsLevelsRef.current = next;
    // Selecting any level after skip replaces the skip with answers.
    if (cssrsNotAssessedRef.current) {
      setCssrsNotAssessed(false);
      cssrsNotAssessedRef.current = false;
    }
    if (staleRef.current) {
      setSaveState("Stale revision");
      return;
    }
    scheduleSave(noteRef.current, diagAnswersRef.current);
  }

  function handleCssrsPeriod(id: CssrsLevelId, value: CssrsPeriod | null): void {
    if (encounter?.state !== "draft" || readOnly) {
      return;
    }
    if (!CSSRS_IDS.includes(id)) {
      return;
    }
    if (value !== null && value !== "current" && value !== "historical") {
      return;
    }
    const next = {
      ...cssrsLevelsRef.current,
      [id]: { ...cssrsLevelsRef.current[id], period: value },
    };
    setCssrsLevels(next);
    cssrsLevelsRef.current = next;
    if (cssrsNotAssessedRef.current) {
      setCssrsNotAssessed(false);
      cssrsNotAssessedRef.current = false;
    }
    if (staleRef.current) {
      setSaveState("Stale revision");
      return;
    }
    scheduleSave(noteRef.current, diagAnswersRef.current);
  }

  function handleCssrsSkip(): void {
    if (encounter?.state !== "draft" || readOnly) {
      return;
    }
    const cleared = emptyCssrs();
    setCssrsLevels(cleared);
    cssrsLevelsRef.current = cleared;
    setCssrsNotAssessed(true);
    cssrsNotAssessedRef.current = true;
    if (staleRef.current) {
      setSaveState("Stale revision");
      return;
    }
    scheduleSave(noteRef.current, diagAnswersRef.current);
  }

  function handleEffectStatus(id: EffectId, status: EffectStatus | null): void {
    if (encounter?.state !== "draft" || readOnly) {
      return;
    }
    if (!EFFECT_IDS.includes(id)) {
      return;
    }
    const current = effectsRef.current[id] ?? { status: null, severity: null };
    // Status change explicitly clears obsolete severity client-side: only a
    // present status may carry a severity; absent/not_assessed send null.
    const next = {
      ...effectsRef.current,
      [id]: status === "present"
        ? { status, severity: current.severity }
        : { status, severity: null },
    };
    setEffects(next);
    effectsRef.current = next;
    if (staleRef.current) {
      setSaveState("Stale revision");
      return;
    }
    scheduleSave(noteRef.current, diagAnswersRef.current);
  }

  function handleEffectSeverity(id: EffectId, severity: string | null): void {
    if (encounter?.state !== "draft" || readOnly) {
      return;
    }
    if (!EFFECT_IDS.includes(id)) {
      return;
    }
    const current = effectsRef.current[id];
    if (!current || current.status !== "present") {
      return;
    }
    const next = { ...effectsRef.current, [id]: { status: current.status, severity } };
    setEffects(next);
    effectsRef.current = next;
    if (staleRef.current) {
      setSaveState("Stale revision");
      return;
    }
    scheduleSave(noteRef.current, diagAnswersRef.current);
  }

  function handleHistoryField(id: string, raw: string): void {
    if (encounter?.state !== "draft" || readOnly) {
      return;
    }
    const next = { ...historyRef.current };
    if (raw === "") {
      delete next[id];
    } else if (raw === "known_true") {
      next[id] = { status: "known", value: true };
    } else if (raw === "known_false") {
      next[id] = { status: "known", value: false };
    } else if (raw === "unknown" || raw === "not_assessed") {
      next[id] = { status: raw, value: null };
    } else {
      return;
    }
    setHistoryValues(next);
    historyRef.current = next;
    if (staleRef.current) {
      setSaveState("Stale revision");
      return;
    }
    scheduleSave(noteRef.current, diagAnswersRef.current);
  }

  function handleReconStatus(raw: string): void {
    if (encounter?.state !== "draft" || readOnly) {
      return;
    }
    // Explicit object state only; never auto-confirmed (S14 owns semantics).
    const next = raw === "pending" || raw === "confirmed" ? { status: raw } : null;
    setRecon(next);
    reconRef.current = next;
    if (staleRef.current) {
      setSaveState("Stale revision");
      return;
    }
    scheduleSave(noteRef.current, diagAnswersRef.current);
  }

  function markMedsStale(): void {
    setDdiError(null);
    if (medsRef.current.length === 0 && ddiReportRef.current === null) {
      setDdiStatus("idle");
    } else {
      setDdiStatus("pending");
    }
  }

  function handleAddCatalog(conceptId: string): void {
    if (encounter?.state !== "draft" || readOnly) {
      return;
    }
    const trimmed = conceptId.trim();
    if (trimmed === "") {
      return;
    }
    const next = [...medsRef.current, { catalog_drug_id: trimmed }];
    setMeds(next);
    medsRef.current = next;
    markMedsStale();
    if (staleRef.current) {
      setSaveState("Stale revision");
      return;
    }
    scheduleSave(noteRef.current, diagAnswersRef.current);
  }

  function handleAddUnknown(label: string): void {
    if (encounter?.state !== "draft" || readOnly) {
      return;
    }
    const trimmed = label.trim();
    if (trimmed === "") {
      return;
    }
    const next = [...medsRef.current, { unknown_label: trimmed }];
    setMeds(next);
    medsRef.current = next;
    markMedsStale();
    if (staleRef.current) {
      setSaveState("Stale revision");
      return;
    }
    scheduleSave(noteRef.current, diagAnswersRef.current);
  }

  function handleRemoveMed(index: number): void {
    if (encounter?.state !== "draft" || readOnly) {
      return;
    }
    if (!Number.isInteger(index) || index < 0 || index >= medsRef.current.length) {
      return;
    }
    const next = medsRef.current.filter((_, i) => i !== index);
    setMeds(next);
    medsRef.current = next;
    markMedsStale();
    if (staleRef.current) {
      setSaveState("Stale revision");
      return;
    }
    scheduleSave(noteRef.current, diagAnswersRef.current);
  }

  async function handleDdiCheck(): Promise<void> {
    if (!encounter || encounter.state !== "draft" || readOnly) {
      return;
    }
    if (staleRef.current) {
      setSaveState("Stale revision");
      return;
    }
    setDdiError(null);
    setDdiStatus("pending");
    let datasetVersion: string | null = null;
    try {
      const current = await getDdiCurrent();
      datasetVersion = current.dataset_version;
    } catch {
      const storedVersion = ddiReportRef.current?.dataset_version;
      if (typeof storedVersion === "string" && storedVersion.trim() !== "") {
        datasetVersion = storedVersion;
      }
    }
    if (datasetVersion === null) {
      setDdiError("DDI dataset unavailable.");
      setDdiStatus("error");
      return;
    }
    try {
      const payload: Array<Record<string, string>> = [];
      for (const entry of medsRef.current) {
        if (entry.catalog_drug_id !== undefined) {
          payload.push({ catalog_drug_id: entry.catalog_drug_id });
        } else {
          payload.push({ unknown_label: entry.unknown_label as string });
        }
      }
      const checked = await checkDdi(datasetVersion, payload);
      ddiReportRef.current = checked;
      setDdiReport(checked);
      const key = JSON.stringify({
        meds: medsDirtyKey(medsRef.current),
        dataset_version: datasetVersion,
      });
      lastCheckedKeyRef.current = key;
      setLastCheckedKey(key);
      setDdiStatus("current");
      scheduleSave(noteRef.current, diagAnswersRef.current);
    } catch (failure: unknown) {
      setDdiError(failure instanceof Error ? failure.message : "DDI check failed.");
      setDdiStatus("error");
    }
  }

  // S48 entry flush: await the pending debounced save so a run POST
  // always carries acknowledged edits. No-op while clean (no revision churn).
  async function flushDraftSave(): Promise<void> {
    if (!encounter || encounter.state !== "draft" || staleRef.current) {
      return;
    }
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (
      noteRef.current === savedNoteRef.current &&
      !isDiagDirty() &&
      !isPanssDirty() &&
      !isCssrsDirty() &&
      !isHistoryDirty() &&
      !isEffectsDirty() &&
      !isReconDirty() &&
      !isMedsDirty() &&
      !isDdiDirty() &&
      !isSecondaryDirty()
    ) {
      return;
    }
    await saveNow(noteRef.current, diagAnswersRef.current, undefined, revisionRef.current);
  }

  // S48 secondary plan: physician edit through the shared autosave path.
  function handleSecondaryPlan(value: string): void {
    if (encounter?.state !== "draft" || readOnly) {
      return;
    }
    setSecondaryPlan(value);
    secondaryPlanRef.current = value;
    if (staleRef.current) {
      setSaveState("Stale revision");
      return;
    }
    scheduleSave(noteRef.current, diagAnswersRef.current);
  }

  async function handlePhoneSave(): Promise<void> {
    if (role !== "physician") {
      return;
    }
    setPhoneState("Saving…");
    try {
      // Optional plain text; empty clears to null. No country validation.
      const updated = await patchPatientPhone(
        patient.id,
        phone === "" ? null : phone,
        phoneRevisionRef.current,
      );
      phoneRevisionRef.current = updated.revision;
      setPhone(updated.phone ?? "");
      setPhoneState(`Saved (rev ${updated.revision})`);
    } catch (failure: unknown) {
      const status = (failure as { status?: number }).status;
      setPhoneState(status === 412 ? "Stale revision" : "Save failed");
    }
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
      savedPanssRef.current = panssDirtyKey(panssAnswersRef.current, panssNotAssessedRef.current);
      savedCssrsRef.current = cssrsDirtyKey(cssrsLevelsRef.current, cssrsNotAssessedRef.current);
      savedHistoryRef.current = historyDirtyKey(historyRef.current);
      savedEffectsRef.current = effectsDirtyKey(effectsRef.current);
      savedReconRef.current = JSON.stringify(reconRef.current);
      savedMedsRef.current = medsDirtyKey(medsRef.current);
      savedDdiRef.current = JSON.stringify(ddiReportRef.current);
      savedSecondaryRef.current = secondaryPlanRef.current;
      staleRef.current = false;
      setEncounter(discarded);
      setSaveState("Draft discarded.");
    } catch {
      setSaveState("Save failed");
    }
  }

  const readOnly =
    (encounter !== null && encounter.author_id !== null && encounter.author_id !== userId) ||
    patient.archived;
  const discarded = encounter !== null && encounter.state !== "draft";
  const signed = encounter !== null && encounter.state === "signed";

  function handleSigned(next: Encounter): void {
    revisionRef.current = next.revision;
    setEncounter(next);
  }

  return (
    <section aria-labelledby="draft-heading">
      <h3 id="draft-heading">Draft</h3>
      <p>
        Patient {patient.patient_id} ·{" "}
        <button type="button" className="x-button" onClick={handleClose}>
          Close
        </button>
      </p>
      {patient.archived ? (
        <p data-testid="patient-archived-notice">
          Archived patient — drafts are read-only.
        </p>
      ) : null}
      {loadError ? (
        <p role="alert" className="x-error">
          {loadError}
        </p>
      ) : encounter === null ? (
        <p role="status">Loading…</p>
      ) : discarded ? (
        signed && encounter !== null ? (
          <>
            <p role="status">Signed.</p>
            <SigningSection
              encounter={encounter}
              userId={userId}
              getRevision={() => revisionRef.current}
              onSigned={handleSigned}
            />
          </>
        ) : (
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
        )
      ) : (
        <>
          {encounter.kind === "follow_up" ? (
            <FollowupExtras encounter={encounter} baseline={baselineSnapshot} />
          ) : null}
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
          <PanssSection
            encounterId={encounter.id}
            answers={panssAnswers}
            notAssessed={panssNotAssessed}
            readOnly={readOnly}
            onItemChange={handlePanssItem}
            onSkip={handlePanssSkip}
          />
          <CssrsSection
            encounterId={encounter.id}
            levels={cssrsLevels}
            notAssessed={cssrsNotAssessed}
            readOnly={readOnly}
            onLevelChange={handleCssrsLevel}
            onPeriodChange={handleCssrsPeriod}
            onSkip={handleCssrsSkip}
          />
          <NotesSection encounterId={encounter.id} readOnly={readOnly || discarded} />
          <HistorySection
            encounterId={encounter.id}
            definition={historyDef}
            definitionLoaded={historyDefLoaded}
            values={historyValues}
            reconciliation={recon}
            readOnly={readOnly}
            onFieldChange={handleHistoryField}
            onReconChange={handleReconStatus}
          />
          <EffectsSection
            encounterId={encounter.id}
            definition={historyDef}
            definitionLoaded={historyDefLoaded}
            values={effects}
            readOnly={readOnly}
            onStatusChange={handleEffectStatus}
            onSeverityChange={handleEffectSeverity}
          />
          <MedicationsSection
            encounterId={encounter.id}
            meds={meds}
            readOnly={readOnly}
            onRemove={handleRemoveMed}
            onAddCatalog={handleAddCatalog}
            onAddUnknown={handleAddUnknown}
          />
          <DdiSection
            encounterId={encounter.id}
            encounterKind={encounter.kind}
            report={ddiReport}
            status={ddiStatus}
            errorDetail={ddiError}
            reconciliationStatus={
              typeof recon?.status === "string" ? String(recon?.status) : ""
            }
            readOnly={readOnly}
            onCheck={() => void handleDdiCheck()}
          />
          <ProposalReviewSection
            encounterId={encounter.id}
            readOnly={readOnly}
            saveState={saveState}
            dirty={
              noteRef.current !== savedNoteRef.current ||
              isDiagDirty() ||
              isPanssDirty() ||
              isCssrsDirty() ||
              isHistoryDirty() ||
              isEffectsDirty() ||
              isReconDirty() ||
              isMedsDirty() ||
              isDdiDirty() ||
              isSecondaryDirty()
            }
            getRevision={() => revisionRef.current}
            flushSave={() => flushDraftSave()}
            secondaryPlan={secondaryPlan}
            onSecondaryPlanChange={handleSecondaryPlan}
          />
          <SigningSection
            encounter={encounter}
            userId={userId}
            getRevision={() => revisionRef.current}
            onSigned={handleSigned}
          />
          <div className="x-field">
            <label htmlFor={`draft-phone-${encounter.id}`}>Phone (optional)</label>
            <input
              id={`draft-phone-${encounter.id}`}
              data-testid="patient-phone-input"
              autoComplete="off"
              value={phone}
              disabled={role !== "physician"}
              onChange={(event) => setPhone(event.target.value)}
            />
            <button
              type="button"
              className="x-button"
              data-testid="patient-phone-save"
              disabled={role !== "physician"}
              onClick={() => void handlePhoneSave()}
            >
              Save phone
            </button>
            {phoneState ? (
              <p role="status" data-testid="patient-phone-status">
                {phoneState}
              </p>
            ) : null}
          </div>
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

/**
 * S42 provider settings (T9): masked admin form. The key value is never
 * rendered from the server — only Configured/Missing plus an explicit
 * replace/clear flow. The redacted placeholder "****" is display-only and
 * is never sent back as a key. Test status shows Untested/Verified/Failed.
 */
function ProviderSettingsGate({ user }: { user: SessionUser | null }) {
  if (!user) {
    return <LoginHint />;
  }
  if (user.role !== "admin") {
    return <p role="alert">Access denied.</p>;
  }
  return <ProviderSettingsSection />;
}

const PROVIDER_KEY_PLACEHOLDER = "****";

function ProviderSettingsSection() {
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [revision, setRevision] = useState<string | null>(null);
  const [keyConfigured, setKeyConfigured] = useState(false);
  const [testStatus, setTestStatus] = useState<string | null>(null);
  const [keyValue, setKeyValue] = useState("");
  const [editingKey, setEditingKey] = useState(true);
  const [clearArmed, setClearArmed] = useState(false);
  const [versions, setVersions] = useState<ProviderSettings[] | null>(null);
  const [diagnostic, setDiagnostic] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  function applyLoaded(settings: ProviderSettings, etag: string): void {
    setBaseUrl(settings.base_url);
    setModel(settings.model);
    setRevision(etag || String(settings.revision));
    setKeyConfigured(settings.key_configured);
    setTestStatus(settings.test_status);
    setKeyValue("");
    // A configured key stays hidden until Replace is chosen explicitly.
    setEditingKey(!settings.key_configured);
    setClearArmed(false);
  }

  async function reload(showLoading: boolean): Promise<void> {
    if (showLoading) {
      setLoading(true);
      setError(null);
    }
    try {
      const { settings, etag } = await getProviderSettings();
      applyLoaded(settings, etag);
      try {
        setVersions(await listProviderVersions());
      } catch {
        setVersions(null);
      }
    } catch (failure: unknown) {
      const status = (failure as { status?: number }).status;
      if (status === 404) {
        // Unconfigured: blank form, key entry visible, honest status.
        setRevision(null);
        setKeyConfigured(false);
        setTestStatus(null);
        setKeyValue("");
        setEditingKey(true);
        setVersions([]);
      } else if (status === 403) {
        setError("Access denied.");
      } else {
        setError("Could not load provider settings.");
      }
    } finally {
      if (showLoading) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    void reload(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSave(): Promise<void> {
    setError(null);
    setNotice(null);
    if (editingKey) {
      if (!keyValue || keyValue === PROVIDER_KEY_PLACEHOLDER) {
        setError("Replacing the key requires sending a real API key.");
        return;
      }
    }
    setSaving(true);
    try {
      const { settings, etag } = await saveProviderSettings(
        {
          base_url: baseUrl,
          model,
          key_action: editingKey ? "replace" : "unchanged",
          ...(editingKey ? { api_key: keyValue } : {}),
        },
        revision ?? undefined,
      );
      applyLoaded(settings, etag);
      try {
        setVersions(await listProviderVersions());
      } catch {
        /* versions line is informational only */
      }
      setNotice(`Saved (rev ${settings.revision}).`);
    } catch (failure: unknown) {
      const status = (failure as { status?: number }).status;
      if (status === 412) {
        // Reload first (silent refresh keeps the message), then report the
        // conflict so the message survives the refresh.
        await reload(false);
        setError("Provider settings changed. Reload and reconcile.");
      } else if (status === 403) {
        setError("Access denied.");
      } else if (failure instanceof Error && failure.message) {
        setError(failure.message);
      } else {
        setError("Could not save provider settings.");
      }
    } finally {
      setSaving(false);
    }
  }

  async function handleClear(): Promise<void> {
    if (!clearArmed) {
      // Explicit two-step confirm; the key is never cleared by accident.
      setClearArmed(true);
      return;
    }
    setError(null);
    setNotice(null);
    setSaving(true);
    try {
      const { settings, etag } = await saveProviderSettings(
        { key_action: "clear" },
        revision ?? undefined,
      );
      applyLoaded(settings, etag);
      try {
        setVersions(await listProviderVersions());
      } catch {
        /* versions line is informational only */
      }
      setNotice("Key cleared.");
    } catch (failure: unknown) {
      const status = (failure as { status?: number }).status;
      if (status === 412) {
        await reload(false);
        setError("Provider settings changed. Reload and reconcile.");
      } else if (status === 403) {
        setError("Access denied.");
      } else if (failure instanceof Error && failure.message) {
        setError(failure.message);
      } else {
        setError("Could not clear the key.");
      }
    } finally {
      setSaving(false);
    }
  }

  async function handleTest(): Promise<void> {
    setError(null);
    setNotice(null);
    setDiagnostic(null);
    setTesting(true);
    try {
      const result = await testProviderSettings();
      const passed =
        result.credential_ok && result.model_ok && result.tool_ok && result.json_ok;
      setTestStatus(passed ? "verified" : "failed");
      setDiagnostic(result.diagnostic);
      // Refresh the persisted status line; the probe never echoes the key.
      try {
        const { settings, etag } = await getProviderSettings();
        applyLoaded(settings, etag);
        setTestStatus(passed ? "verified" : "failed");
        setDiagnostic(result.diagnostic);
      } catch {
        /* keep the probe-derived status when the refresh races a save */
      }
    } catch (failure: unknown) {
      const status = (failure as { status?: number }).status;
      if (status === 403) {
        setError("Access denied.");
      } else if (failure instanceof Error && failure.message) {
        setError(failure.message);
      } else {
        setError("Provider test failed.");
      }
    } finally {
      setTesting(false);
    }
  }

  const statusLabel =
    testStatus === null
      ? "Not configured"
      : testStatus === "verified"
        ? "Verified"
        : testStatus === "failed"
          ? "Failed"
          : "Untested";

  if (loading) {
    return (
      <section data-testid="provider-settings-section" aria-label="Provider settings">
        <h1>Provider settings</h1>
        <p>Loading…</p>
      </section>
    );
  }

  return (
    <section data-testid="provider-settings-section" aria-label="Provider settings">
      <h1>Provider settings</h1>
      <p>Admin only. The API key is stored encrypted and never shown.</p>
      <div className="x-field">
        <label htmlFor="provider-base-url">Base URL</label>
        <input
          id="provider-base-url"
          data-testid="provider-base-url"
          autoComplete="off"
          value={baseUrl}
          onChange={(event) => setBaseUrl(event.target.value)}
        />
      </div>
      <div className="x-field">
        <label htmlFor="provider-model">Model</label>
        <input
          id="provider-model"
          data-testid="provider-model"
          autoComplete="off"
          value={model}
          onChange={(event) => setModel(event.target.value)}
        />
      </div>
      <p>
        Key:{" "}
        <span data-testid="provider-key-status">
          {keyConfigured ? "Configured" : "Missing"}
        </span>
      </p>
      <p>
        Status: <span data-testid="provider-status">{statusLabel}</span>
      </p>
      {revision !== null ? <p>Revision {revision}.</p> : null}
      {versions !== null ? (
        <p data-testid="provider-versions">{versions.length} revision(s) retained.</p>
      ) : null}
      {editingKey ? (
        <div className="x-field">
          <label htmlFor="provider-key">API key</label>
          <input
            id="provider-key"
            data-testid="provider-key"
            type="password"
            autoComplete="off"
            placeholder={PROVIDER_KEY_PLACEHOLDER}
            value={keyValue}
            onChange={(event) => setKeyValue(event.target.value)}
          />
        </div>
      ) : (
        <button
          type="button"
          className="x-button"
          data-testid="provider-replace"
          onClick={() => {
            setEditingKey(true);
            setKeyValue("");
          }}
        >
          Replace key
        </button>
      )}{" "}
      <button
        type="button"
        className="x-button"
        data-testid="provider-save"
        disabled={saving}
        onClick={() => void handleSave()}
      >
        {saving ? "Saving…" : "Save provider settings"}
      </button>{" "}
      <button
        type="button"
        className="x-button"
        data-testid="provider-test"
        disabled={testing}
        onClick={() => void handleTest()}
      >
        {testing ? "Testing…" : "Test connection"}
      </button>{" "}
      <button
        type="button"
        className="x-button"
        data-testid="provider-clear"
        disabled={saving}
        onClick={() => void handleClear()}
      >
        {clearArmed ? "Confirm clear" : "Clear key"}
      </button>
      {diagnostic ? (
        <p role="status" data-testid="provider-diagnostic">
          {diagnostic}
        </p>
      ) : null}
      {notice ? (
        <p role="status" data-testid="provider-notice">
          {notice}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="x-error" data-testid="provider-error">
          {error}
        </p>
      ) : null}
    </section>
  );
}

/** S24 model administration (read-only graph, no edit handlers). */
function NetworksGate({ user }: { user: SessionUser | null }) {
  if (!user) {
    return <LoginHint />;
  }
  if (user.role !== "admin") {
    return <p role="alert">Access denied.</p>;
  }
  return <NetworksSection />;
}

const REGISTRATION_ORDER = [
  "hospitalization",
  "pharmacotherapy",
  "involuntary_care",
  "high_suicide_clozapine",
  "lai_indication_choice",
  "aggression_clozapine",
  "established_case_clozapine",
];

const FOLLOWUP_ORDER = [
  "tardive_dyskinesia",
  "akathisia",
  "parkinsonism",
  "acute_dystonia",
  "no_improvement_clozapine",
  "continue_or_adjust",
];

function shortSha(sha: string): string {
  return sha.length > 12 ? sha.slice(0, 12) : sha;
}

/** Plain SVG vertical layout: boxes with states, lines with labels. No drag/edit. */
function NetworkSvg({ graph }: { graph: NetworkGraph }) {
  const nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
  const edges = Array.isArray(graph.edges) ? graph.edges : [];
  const states = (graph.states ?? {}) as Record<string, string[]>;
  const rowH = 84;
  const width = 420;
  const height = Math.max(120, 40 + nodes.length * rowH + 30);
  const yFor = (index: number) => 40 + index * rowH;
  const indexByNode = new Map(nodes.map((name, index) => [name, index]));
  return (
    <svg
      role="img"
      aria-label={`Network graph with ${nodes.length} nodes and ${edges.length} edges`}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
    >
      {edges.map(([from, to], i) => {
        const a = indexByNode.get(String(from));
        const b = indexByNode.get(String(to));
        if (a === undefined || b === undefined) {
          return null;
        }
        const x1 = 210;
        const y1 = yFor(a) + 56;
        const x2 = 210;
        const y2 = yFor(b);
        const midY = (y1 + y2) / 2;
        return (
          <g key={`${from}-${to}-${i}`}>
            <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="currentColor" strokeWidth={2} />
            <text x={x2 + 8} y={midY} fontSize={12} fill="currentColor">
              {`${from} to ${to}`}
            </text>
          </g>
        );
      })}
      {nodes.map((name, i) => {
        const y = yFor(i);
        const list = states[name] ?? [];
        return (
          <g key={name}>
            <rect x={110} y={y} width={200} height={56} fill="none" stroke="currentColor" strokeWidth={2} />
            <text x={120} y={y + 22} fontSize={13} fontWeight={700} fill="currentColor">
              {name}
            </text>
            <text x={120} y={y + 42} fontSize={12} fill="currentColor">
              {list.length > 0 ? list.join(", ") : "no states"}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function VersionInspect({ versionId }: { versionId: string }) {
  const [graph, setGraph] = useState<NetworkGraph | null>(null);
  const [validation, setValidation] = useState<NetworkValidation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleInspect(): Promise<void> {
    setError(null);
    setLoading(true);
    try {
      const [g, v] = await Promise.all([
        getNetworkGraph(versionId),
        validateNetworkVersion(versionId),
      ]);
      setGraph(g);
      setValidation(v);
    } catch {
      setError("Could not inspect the version.");
    } finally {
      setLoading(false);
    }
  }

  async function handleValidate(): Promise<void> {
    setError(null);
    try {
      setValidation(await validateNetworkVersion(versionId));
      if (graph === null) {
        setGraph(await getNetworkGraph(versionId));
      }
    } catch {
      setError("Could not validate the version.");
    }
  }

  const xsd = validation?.xsd_report as Record<string, unknown> | undefined;
  const semantic = validation?.semantic_report as Record<string, unknown> | undefined;
  const admission = validation?.admission_report as Record<string, unknown> | undefined;
  const graphSemantic = graph?.semantic_report as Record<string, unknown> | undefined;
  const graphAdmission = graph?.admission_report as Record<string, unknown> | undefined;
  const semanticView = semantic ?? graphSemantic;
  const admissionView = admission ?? graphAdmission;
  const executable =
    validation !== null
      ? validation.executable
      : (graph !== null ? graph.executable : null);
  const admitted =
    validation !== null
      ? validation.admitted
      : (graph !== null ? graph.admitted : null);

  return (
    <div>
      <button
        type="button"
        className="x-button"
        data-testid={`version-inspect-${versionId}`}
        disabled={loading}
        onClick={() => void handleInspect()}
      >
        {loading ? "Inspecting…" : "Inspect"}
      </button>{" "}
      <a data-testid={`version-export-${versionId}`} href={networkVersionXmlUrl(versionId)} download>
        Export
      </a>
      {error ? (
        <p role="alert" className="x-error">
          {error}
        </p>
      ) : null}
      <div data-testid={`version-graph-${versionId}`}>
        {graph === null ? (
          <p>Graph not loaded.</p>
        ) : (
          <>
            <p>
              Validation status: {graph.validation_status}; XSD{" "}
              {graph.xsd_valid ? "valid" : "invalid"}; semantic{" "}
              {graph.executable ? "executable" : "not executable"}; admission{" "}
              {graph.admitted ? "admitted" : "not admitted"}.
            </p>
            <p>
              Nodes: {graph.nodes.join(", ") || "none"}. Edges:{" "}
              {graph.edges.map(([a, b]) => `${a} to ${b}`).join("; ") || "none"}.
            </p>
            <NetworkSvg graph={graph} />
          </>
        )}
      </div>
      <div data-testid={`version-validate-${versionId}`}>
        <button
          type="button"
          className="x-button"
          onClick={() => void handleValidate()}
        >
          Validate
        </button>
        {validation === null && graph === null ? (
          <p>Validation not loaded.</p>
        ) : (
          <>
            <p>
              XSD: {validation !== null ? (validation.xsd_valid ? "valid" : "invalid") : (graph !== null ? (graph.xsd_valid ? "valid" : "invalid") : "unknown")};{" "}
              semantic executable:{" "}
              {executable === null ? "unknown" : executable ? "true" : "false"};{" "}
              admission admitted:{" "}
              {admitted === null ? "unknown" : admitted ? "true" : "false"}.
            </p>
            <p>XSD report: {JSON.stringify(xsd ?? graph?.xsd_report ?? {})}</p>
            <p>Semantic report: {JSON.stringify(semanticView ?? {})}</p>
            <p>Admission report: {JSON.stringify(admissionView ?? {})}</p>
            {semanticView !== undefined && Array.isArray((semanticView as Record<string, unknown>).errors) ? (
              <p>Semantic errors: {JSON.stringify((semanticView as Record<string, unknown>).errors)}</p>
            ) : null}
            {admissionView !== undefined && typeof (admissionView as Record<string, unknown>).measurements !== "undefined" ? (
              <p>Admission measurements: {JSON.stringify((admissionView as Record<string, unknown>).measurements)}</p>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}

function NetworkCard({
  networkId,
  networkKey,
  onChanged,
}: {
  networkId: string;
  networkKey: string;
  onChanged: () => void;
}) {
  const [versions, setVersions] = useState<NetworkVersionItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newXml, setNewXml] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setVersions(await listNetworkVersions(networkId));
      setError(null);
    } catch {
      setError("Could not load versions.");
    }
  }, [networkId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function handleNewVersion(): Promise<void> {
    setError(null);
    setNotice(null);
    if (!confirm) {
      setError("Confirm the new version before submitting.");
      return;
    }
    if (!newXml.trim()) {
      setError("New version XML is required.");
      return;
    }
    setSaving(true);
    try {
      await addNetworkVersion(networkId, newXml);
      setNewXml("");
      setConfirm(false);
      await reload();
      onChanged();
      setNotice("Version added.");
    } catch {
      setError("Could not add the version.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <article data-testid={`network-${networkId}`}>
      <h3>{networkKey}</h3>
      <div data-testid={`network-versions-${networkId}`}>
        {error ? (
          <p role="alert" className="x-error">
            {error}
          </p>
        ) : null}
        {versions === null ? (
          <p>Loading versions…</p>
        ) : versions.length === 0 ? (
          <p>No versions.</p>
        ) : (
          <ul data-testid="networks-versions-list">
            {versions.map((item) => (
              <li key={item.version_id} data-testid={`network-version-${item.version_id}`}>
                <p>
                  Version {item.version_number} · {shortSha(item.sha256)} ·{" "}
                  {item.byte_count} bytes · XSD {item.xsd_valid ? "valid" : "invalid"}
                </p>
                <VersionInspect versionId={item.version_id} />
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="x-field">
        <label htmlFor={`network-new-xml-${networkId}`}>New version XML</label>
        <textarea
          id={`network-new-xml-${networkId}`}
          data-testid={`network-new-xml-${networkId}`}
          value={newXml}
          onChange={(event) => setNewXml(event.target.value)}
        />
        <label htmlFor={`network-new-confirm-${networkId}`}>
          <input
            id={`network-new-confirm-${networkId}`}
            type="checkbox"
            data-testid={`network-new-confirm-${networkId}`}
            checked={confirm}
            onChange={(event) => setConfirm(event.target.checked)}
          />{" "}
          Confirm new version
        </label>
        <button
          type="button"
          className="x-button"
          data-testid={`network-new-submit-${networkId}`}
          disabled={saving}
          onClick={() => void handleNewVersion()}
        >
          {saving ? "Adding…" : "Add version"}
        </button>
      </div>
      {notice ? <p role="status">{notice}</p> : null}
    </article>
  );
}

function BundlePanel() {
  const [workflow, setWorkflow] = useState("registration");
  const [pointer, setPointer] = useState<ModelBundle | null>(null);
  const [pinsText, setPinsText] = useState("");
  const [reviewer, setReviewer] = useState("owner");
  const [date, setDate] = useState("2026-09-22");
  const [activateConfirm, setActivateConfirm] = useState(false);
  const [rollbackTarget, setRollbackTarget] = useState("");
  const [rollbackConfirm, setRollbackConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const order = workflow === "followup" ? FOLLOWUP_ORDER : REGISTRATION_ORDER;

  const reload = useCallback(
    async (showLoading: boolean) => {
      if (showLoading) {
        setLoading(true);
      }
      try {
        setPointer(await getModelBundle(workflow));
        if (showLoading) {
          setError(null);
        }
      } catch {
        if (showLoading) {
          setError("Could not load the bundle.");
        }
      } finally {
        if (showLoading) {
          setLoading(false);
        }
      }
    },
    [workflow],
  );

  useEffect(() => {
    setPinsText("");
    setRollbackTarget("");
    setActivateConfirm(false);
    setRollbackConfirm(false);
    setNotice(null);
    setError(null);
    void reload(true);
  }, [reload]);

  function parsePins(): BundlePinInput[] | null {
    const lines = pinsText
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length > 0);
    if (lines.length !== order.length) {
      setError(`Enter ${order.length} lines (question_key=versionId) in workflow order.`);
      return null;
    }
    const pins: BundlePinInput[] = [];
    for (let i = 0; i < order.length; i++) {
      const line = lines[i];
      const sep = line.indexOf("=");
      if (sep < 0) {
        setError(`Line ${i + 1} must be question_key=versionId.`);
        return null;
      }
      const key = line.slice(0, sep).trim();
      const versionId = line.slice(sep + 1).trim();
      if (key !== order[i]) {
        setError(`Line ${i + 1} must start with ${order[i]}.`);
        return null;
      }
      if (!versionId) {
        setError(`Line ${i + 1} is missing a version id.`);
        return null;
      }
      pins.push({
        question_key: key,
        network_version_id: versionId,
        review: { decision: "approved", reviewer, date },
      });
    }
    return pins;
  }

  async function handleActivate(): Promise<void> {
    setError(null);
    setNotice(null);
    if (!activateConfirm) {
      setError("Confirm the activation before submitting.");
      return;
    }
    const pins = parsePins();
    if (pins === null) {
      return;
    }
    const expected = pointer?.revision ?? 0;
    try {
      const next = await activateModelBundle({
        workflow,
        pins,
        expected_revision: expected,
      });
      setPointer(next);
      setNotice(`Activated revision ${next.revision}.`);
    } catch (failure: unknown) {
      const status = (failure as { status?: number }).status;
      if (status === 412) {
        await reload(false);
        setError("Bundle changed. Reload and reconcile your edits.");
      } else if (failure instanceof Error && failure.message) {
        setError(failure.message);
      } else {
        setError("Could not activate the bundle.");
      }
    }
  }

  async function handleRollback(): Promise<void> {
    setError(null);
    setNotice(null);
    if (!rollbackConfirm) {
      setError("Confirm the rollback before submitting.");
      return;
    }
    const target = Number.parseInt(rollbackTarget.trim(), 10);
    if (!Number.isInteger(target) || target < 1) {
      setError("Target revision must be a positive integer.");
      return;
    }
    const expected = pointer?.revision ?? 0;
    try {
      const next = await rollbackModelBundle({
        workflow,
        target_revision: target,
        expected_revision: expected,
      });
      setPointer(next);
      setNotice(`Rolled back to revision ${next.revision}.`);
    } catch (failure: unknown) {
      const status = (failure as { status?: number }).status;
      if (status === 412) {
        await reload(false);
        setError("Bundle changed. Reload and reconcile your edits.");
      } else if (failure instanceof Error && failure.message) {
        setError(failure.message);
      } else {
        setError("Could not roll back the bundle.");
      }
    }
  }

  if (loading) {
    return (
      <section data-testid="bundle-section" aria-label="Workflow bundles">
        <h2>Workflow bundles</h2>
        <p>Loading…</p>
      </section>
    );
  }

  return (
    <section data-testid="bundle-section" aria-label="Workflow bundles">
      <h2>Workflow bundles</h2>
      <div className="x-field">
        <label htmlFor="bundle-workflow">Workflow</label>
        <select
          id="bundle-workflow"
          data-testid="bundle-workflow"
          value={workflow}
          onChange={(event) => setWorkflow(event.target.value)}
        >
          <option value="registration">registration</option>
          <option value="followup">followup</option>
        </select>
      </div>
      <div data-testid={`bundle-pointer-${workflow}`}>
        {pointer === null ? (
          <p>No bundle pointer.</p>
        ) : (
          <div data-testid="bundle-pointer">
            <p>
              Revision {pointer.revision} ·{" "}
              {pointer.bundle_hash ?? "no bundle hash"} · {pointer.workflow}
            </p>
            <p>Pins: {JSON.stringify(pointer.pins ?? [])}</p>
          </div>
        )}
      </div>
      <div className="x-field">
        <label htmlFor="bundle-activate-pins">
          Activation pins ({order.length} lines, question_key=versionId, workflow
          order)
        </label>
        <textarea
          id="bundle-activate-pins"
          data-testid="bundle-activate-pins"
          value={pinsText}
          placeholder={order.map((key) => `${key}=`).join("\n")}
          onChange={(event) => setPinsText(event.target.value)}
        />
        <label htmlFor="bundle-activate-reviewer">Reviewer</label>
        <input
          id="bundle-activate-reviewer"
          data-testid="bundle-activate-reviewer"
          autoComplete="off"
          value={reviewer}
          onChange={(event) => setReviewer(event.target.value)}
        />
        <label htmlFor="bundle-activate-date">Review date</label>
        <input
          id="bundle-activate-date"
          data-testid="bundle-activate-date"
          autoComplete="off"
          value={date}
          onChange={(event) => setDate(event.target.value)}
        />
        <label htmlFor="bundle-activate-confirm">
          <input
            id="bundle-activate-confirm"
            type="checkbox"
            data-testid="bundle-activate-confirm"
            checked={activateConfirm}
            onChange={(event) => setActivateConfirm(event.target.checked)}
          />{" "}
          Confirm activation
        </label>
        <button
          type="button"
          className="x-button"
          data-testid={`bundle-activate-${workflow}`}
          onClick={() => void handleActivate()}
        >
          Activate {workflow}
        </button>
        <button
          type="button"
          className="x-button"
          data-testid="bundle-activate"
          onClick={() => void handleActivate()}
        >
          Activate
        </button>
      </div>
      <div className="x-field">
        <label htmlFor="bundle-rollback-target">Rollback target revision</label>
        <input
          id="bundle-rollback-target"
          data-testid="bundle-rollback-target"
          autoComplete="off"
          inputMode="numeric"
          value={rollbackTarget}
          onChange={(event) => setRollbackTarget(event.target.value)}
        />
        <label htmlFor="bundle-rollback-confirm">
          <input
            id="bundle-rollback-confirm"
            type="checkbox"
            data-testid="bundle-rollback-confirm"
            checked={rollbackConfirm}
            onChange={(event) => setRollbackConfirm(event.target.checked)}
          />{" "}
          Confirm rollback
        </label>
        <button
          type="button"
          className="x-button"
          data-testid={`bundle-rollback-${workflow}`}
          onClick={() => void handleRollback()}
        >
          Roll back {workflow}
        </button>
        <button
          type="button"
          className="x-button"
          data-testid="bundle-rollback"
          onClick={() => void handleRollback()}
        >
          Roll back
        </button>
      </div>
      {notice ? (
        <p role="status" data-testid="bundle-notice">
          {notice}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="x-error" data-testid="bundle-error">
          {error}
        </p>
      ) : null}
    </section>
  );
}

function NetworksSection() {
  const [xml, setXml] = useState("");
  const [items, setItems] = useState<{ id: string; key: string }[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const reload = useCallback(async () => {
    try {
      const loaded = await listNetworks();
      setItems(loaded.map((entry) => ({ id: entry.network_id || entry.id, key: entry.key })));
      setError(null);
    } catch {
      setError("Could not load networks.");
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function handleImport(): Promise<void> {
    setError(null);
    setNotice(null);
    if (!xml.trim()) {
      setError("Network XML is required.");
      return;
    }
    setSaving(true);
    try {
      await importNetwork(xml);
      setXml("");
      await reload();
      setNotice("Network imported.");
    } catch {
      setError("Could not import the network.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <section data-testid="networks-section" aria-label="Networks">
        <h1>Networks</h1>
        <p>Admin only. Imports create new immutable versions.</p>
        <div className="x-field">
          <label htmlFor="networks-xml">Network XML</label>
          <textarea
            id="networks-xml"
            data-testid="networks-xml-input"
            value={xml}
            onChange={(event) => setXml(event.target.value)}
          />
          <button
            type="button"
            className="x-button"
            data-testid="networks-import"
            disabled={saving}
            onClick={() => void handleImport()}
          >
            {saving ? "Importing…" : "Import"}
          </button>
        </div>
        {notice ? (
          <p role="status" data-testid="networks-notice">
            {notice}
          </p>
        ) : null}
        {error ? (
          <p role="alert" className="x-error" data-testid="networks-error">
            {error}
          </p>
        ) : null}
        <div data-testid="networks-list">
          {items === null ? (
            <p>Loading networks…</p>
          ) : items.length === 0 ? (
            <p>No networks yet.</p>
          ) : (
            items.map((entry) => (
              <NetworkCard
                key={entry.id}
                networkId={entry.id}
                networkKey={entry.key}
                onChanged={() => void reload()}
              />
            ))
          )}
        </div>
      </section>
      <BundlePanel />
    </>
  );
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
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const reload = useCallback(() => {
    setError(null);
    listPhysicians()
      .then(setItems)
      .catch((failure: unknown) =>
        setError(failure instanceof Error ? failure.message : "Could not load physicians."),
      );
  }, []);

  useEffect(reload, [reload]);

  const selected =
    selectedId !== null && items !== null
      ? (items.find((item) => item.id === selectedId) ?? null)
      : null;

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
              <th scope="col">Review</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr
                key={item.id}
                data-testid={`physician-row-${item.id}`}
                onClick={() => setSelectedId(item.id)}
              >
                <td>{item.username}</td>
                <td>{item.active ? "Active" : "Inactive"}</td>
                <td>
                  <button
                    type="button"
                    className="x-button"
                    onClick={(event) => {
                      event.stopPropagation();
                      setSelectedId(item.id);
                    }}
                  >
                    Deactivate
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {selected !== null ? (
        <DeactivateReview
          key={selected.id}
          physicianId={selected.id}
          username={selected.username}
          onDeactivated={reload}
        />
      ) : null}
    </>
  );
}

/**
 * S51 deactivation review (T9): real draft-set review with explicit
 * retain-vs-discard choice and explicit discard confirmation. The confirm
 * action stays disabled until a choice is made and the checkbox is checked.
 * A changed draft_set_revision surfaces 412 with a Re-review action.
 */
function DeactivateReview({
  physicianId,
  username,
  onDeactivated,
}: {
  physicianId: string;
  username: string;
  onDeactivated: () => void;
}) {
  const [review, setReview] = useState<DeactivationReview | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [action, setAction] = useState<"retain" | "discard" | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [pending, setPending] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [done, setDone] = useState<"retain" | "discard" | null>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    setStale(false);
    try {
      setReview(await getDeactivationReview(physicianId));
    } catch (failure: unknown) {
      setLoadError(
        failure instanceof Error ? failure.message : "Could not load the draft review.",
      );
    }
  }, [physicianId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleConfirm(): Promise<void> {
    if (review === null || action === null || !confirmed || pending) {
      return;
    }
    setPending(true);
    setSubmitError(null);
    setStale(false);
    try {
      await deactivatePhysician(
        physicianId,
        {
          draft_action: action,
          draft_set_revision: review.draft_set_revision,
          confirm_discard: confirmed,
        },
        review.account_revision,
      );
      setDone(action);
      onDeactivated();
    } catch (failure: unknown) {
      const status = (failure as { status?: number }).status;
      if (status === 412) {
        setStale(true);
        setSubmitError(
          failure instanceof Error ? failure.message : "Draft review changed. Review it again.",
        );
      } else {
        setSubmitError(
          failure instanceof Error ? failure.message : "Could not deactivate the physician.",
        );
      }
    } finally {
      setPending(false);
    }
  }

  const drafts = review?.drafts ?? [];
  const valid = action !== null && confirmed && !pending;

  return (
    <section data-testid="physician-deactivate-review" aria-label="Deactivation review">
      <h2>Deactivation review — {username}</h2>
      {loadError ? (
        <p role="alert" className="x-error">
          {loadError}
        </p>
      ) : review === null ? (
        <p>Loading review…</p>
      ) : (
        <>
          <p data-testid="physician-draft-set-count">
            {drafts.length} draft{drafts.length === 1 ? "" : "s"}
          </p>
          <p data-testid="physician-draft-set-revision">
            {review.draft_set_revision.slice(0, 16)}
          </p>
          <ul>
            {drafts.map((draft) => (
              <li key={draft.id}>
                {draft.kind} · {draft.state} · rev {draft.revision}
              </li>
            ))}
          </ul>
          {done === null ? (
            <>
              <div className="x-field">
                <label>
                  <input
                    type="radio"
                    name={`deactivate-action-${physicianId}`}
                    data-testid="physician-deactivate-retain"
                    checked={action === "retain"}
                    onChange={() => setAction("retain")}
                  />{" "}
                  Retain drafts
                </label>
                <label>
                  <input
                    type="radio"
                    name={`deactivate-action-${physicianId}`}
                    data-testid="physician-deactivate-discard"
                    checked={action === "discard"}
                    onChange={() => setAction("discard")}
                  />{" "}
                  Discard drafts
                </label>
                <label>
                  <input
                    type="checkbox"
                    data-testid="physician-deactivate-confirm-checkbox"
                    checked={confirmed}
                    onChange={(event) => setConfirmed(event.target.checked)}
                  />{" "}
                  I confirm this deactivation
                </label>
                <button
                  type="button"
                  className="x-button"
                  data-testid="physician-deactivate-confirm-button"
                  disabled={!valid}
                  onClick={() => void handleConfirm()}
                >
                  {pending ? "Deactivating…" : "Deactivate"}
                </button>
              </div>
              {submitError ? (
                <p role="alert" className="x-error">
                  {submitError}
                </p>
              ) : null}
              {stale ? (
                <button
                  type="button"
                  className="x-button"
                  data-testid="physician-deactivate-rereview"
                  onClick={() => void load()}
                >
                  Re-review
                </button>
              ) : null}
            </>
          ) : done === "discard" ? (
            <p data-testid="physician-deactivate-tombstone">
              Deactivated — {drafts.length} draft{drafts.length === 1 ? "" : "s"} tombstoned.
            </p>
          ) : (
            <p role="status">Deactivated — drafts retained.</p>
          )}
        </>
      )}
    </section>
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
