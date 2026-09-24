// Agent persona typed client — Addendum §10.3 (S10-2).
//
// Mirrors the FastAPI wire model in app/routers/persona.py (owner ruling 2 — no
// invented fields). The persona is per-user agent metadata (agent_name,
// rules_of_engagement, tone_preset, practice_areas) that shapes HOW the assistant
// writes — it can never change WHAT it may cite (grounding contract survives
// byte-for-byte). Practice-area defaults are firm-scoped; the write path is
// firm-admin gated server-side (GET is open to all tenants).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPut } from "@/lib/api/client";

/** The allowed tone presets (mirror of app/assistant/service.py PERSONA_TONES). */
export const PERSONA_TONES = [
  "PROFESSIONAL",
  "CONCISE",
  "NARRATIVE",
  "FORMAL",
] as const;

export type TonePreset = (typeof PERSONA_TONES)[number];

/** Wire mirror of PersonaUpsert + the GET /v1/persona response. */
export interface Persona {
  agent_name: string;
  rules_of_engagement: string | null;
  tone_preset: TonePreset;
  practice_areas: string[];
}

export interface PersonaInput {
  agent_name?: string;
  rules_of_engagement?: string | null;
  tone_preset?: TonePreset;
  practice_areas?: string[];
}

/** Wire mirror of GET /v1/persona/practice-areas. */
export interface PracticeAreas {
  tags: string[];
}

export interface Departments {
  departments: string[];
}

export function getPersona(): Promise<Persona> {
  return apiGet<Persona>("/v1/persona");
}

export function savePersona(input: PersonaInput): Promise<Persona> {
  return apiPut<Persona, PersonaInput>("/v1/persona", input);
}

export function getPracticeAreas(): Promise<PracticeAreas> {
  return apiGet<PracticeAreas>("/v1/persona/practice-areas");
}

export function savePracticeAreas(tags: string[]): Promise<PracticeAreas> {
  return apiPut<PracticeAreas, { tags: string[] }>(
    "/v1/persona/practice-areas",
    { tags },
  );
}

export function usePersona() {
  return useQuery({ queryKey: ["persona"], queryFn: getPersona });
}

export function usePracticeAreas() {
  return useQuery({
    queryKey: ["persona", "practice-areas"],
    queryFn: getPracticeAreas,
  });
}

export function getDepartments(): Promise<Departments> {
  return apiGet<Departments>("/v1/persona/departments");
}

export function saveDepartments(departments: string[]): Promise<Departments> {
  return apiPut<Departments, { departments: string[] }>(
    "/v1/persona/departments",
    { departments },
  );
}

export function useSavePersona() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: savePersona,
    onSuccess: (saved) => {
      qc.setQueryData(["persona"], saved);
    },
  });
}
