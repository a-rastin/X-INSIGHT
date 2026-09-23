# Registration Spec

> 16 nodes · cohesion 0.12

## Key Concepts

- **@playwright/test** (18 connections) — `web/package.json`
- **registration.spec.ts** (8 connections) — `e2e/registration.spec.ts`
- **identity.spec.ts** (6 connections) — `e2e/identity.spec.ts`
- **createPhysicianViaAdminApi()** (1 connections) — `e2e/identity.spec.ts`
- **dismissResearchNotice()** (1 connections) — `e2e/identity.spec.ts`
- **loginViaUI()** (1 connections) — `e2e/identity.spec.ts`
- **uniquePassword()** (1 connections) — `e2e/identity.spec.ts`
- **uniquePhysicianUsername()** (1 connections) — `e2e/identity.spec.ts`
- **createPatientViaPhysicianApi()** (1 connections) — `e2e/registration.spec.ts`
- **createPhysicianViaAdminApi()** (1 connections) — `e2e/registration.spec.ts`
- **dismissResearchNotice()** (1 connections) — `e2e/registration.spec.ts`
- **loginViaUI()** (1 connections) — `e2e/registration.spec.ts`
- **uniqueName()** (1 connections) — `e2e/registration.spec.ts`
- **uniquePatientId()** (1 connections) — `e2e/registration.spec.ts`
- **uniquePhysicianUsername()** (1 connections) — `e2e/registration.spec.ts`
- **playwright.config.ts** (1 connections) — `playwright.config.ts`

## Relationships

- [Vite Config](Vite_Config.md) (1 shared connections)
- [Accessibility Spec](Accessibility_Spec.md) (1 shared connections)
- [Autosave Spec](Autosave_Spec.md) (1 shared connections)
- [C-SSRS Spec](C-SSRS_Spec.md) (1 shared connections)
- [DDI Spec](DDI_Spec.md) (1 shared connections)
- [Diagnosis Spec](Diagnosis_Spec.md) (1 shared connections)
- [Discard Spec](Discard_Spec.md) (1 shared connections)
- [Draft Safety Spec](Draft_Safety_Spec.md) (1 shared connections)
- [Followup Spec](Followup_Spec.md) (1 shared connections)
- [History Spec](History_Spec.md) (1 shared connections)
- [Networks Spec](Networks_Spec.md) (1 shared connections)
- [Notes Spec](Notes_Spec.md) (1 shared connections)

## Source Files

- `e2e/identity.spec.ts`
- `e2e/registration.spec.ts`
- `playwright.config.ts`
- `web/package.json`

## Audit Trail

- EXTRACTED: 30 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*