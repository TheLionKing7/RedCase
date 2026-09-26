import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import {
  Bot,
  Check,
  KeyRound,
  Loader2,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import {
  PERSONA_TONES,
  usePersona,
  useSavePersona,
  type PersonaInput,
  type TonePreset,
} from "@/lib/api/persona";
import { useProfile, useSaveProfile, type Profile } from "@/lib/api/profile";
import { updatePassword } from "@/lib/auth/supabase";

export const Route = createFileRoute("/_authed/settings")({
  component: SettingsPage,
});

const inputClass =
  "mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm outline-none transition-all duration-200 focus-visible:ring-2 focus-visible:ring-gold";
const fieldLabel =
  "font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground";

function SettingsPage() {
  const profile = useProfile();
  const saveProfile = useSaveProfile();
  const persona = usePersona();
  const savePersona = useSavePersona();
  const [profileForm, setProfileForm] = useState({
    full_name: "",
    phone: "",
    email: "",
    timezone: "Africa/Lagos",
  });
  const [personaForm, setPersonaForm] = useState<PersonaInput>({
    agent_name: "Assistant",
    tone_preset: "PROFESSIONAL",
    redteam_temperature: 0.2,
  });
  const [profileNotice, setProfileNotice] = useState("");
  const [personaNotice, setPersonaNotice] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [passwordNotice, setPasswordNotice] = useState<{
    kind: "success" | "error";
    text: string;
  } | null>(null);

  useEffect(() => {
    if (profile.data)
      setProfileForm({
        full_name: profile.data.full_name,
        phone: profile.data.phone ?? "",
        email: profile.data.email,
        timezone: profile.data.timezone,
      });
  }, [profile.data]);
  useEffect(() => {
    if (persona.data) setPersonaForm(persona.data);
  }, [persona.data]);

  const saveProfileForm = (event: React.FormEvent) => {
    event.preventDefault();
    saveProfile.mutate(
      { ...profileForm, phone: profileForm.phone.trim() || null },
      {
        onSuccess: () => setProfileNotice("Profile saved."),
        onError: () =>
          setProfileNotice(
            "Profile could not be saved. Check your connection and try again.",
          ),
      },
    );
  };
  const savePersonaForm = (event: React.FormEvent) => {
    event.preventDefault();
    savePersona.mutate(personaForm, {
      onSuccess: () => setPersonaNotice("Workbench preferences saved."),
      onError: () =>
        setPersonaNotice(
          "Preferences could not be saved. Check your connection and try again.",
        ),
    });
  };
  const set = (key: keyof PersonaInput, value: string | number) =>
    setPersonaForm((current) => ({ ...current, [key]: value }));

  const savePassword = async (event: React.FormEvent) => {
    event.preventDefault();
    setPasswordNotice(null);
    if (newPassword !== confirmPassword) {
      setPasswordNotice({ kind: "error", text: "Passwords do not match." });
      return;
    }
    setPasswordBusy(true);
    try {
      await updatePassword(newPassword);
      setNewPassword("");
      setConfirmPassword("");
      setPasswordNotice({
        kind: "success",
        text: "Password saved. You can now sign in with your password or continue using magic links.",
      });
    } catch (err) {
      setPasswordNotice({
        kind: "error",
        text:
          err instanceof Error ? err.message : "Password could not be saved.",
      });
    } finally {
      setPasswordBusy(false);
    }
  };

  return (
    <AppShell eyebrow="WORKBENCH CONTROL ROOM" title="Settings">
      <div className="mx-auto max-w-6xl space-y-8">
        <header className="max-w-3xl border-l-2 border-gold/70 pl-5 py-1">
          <p className="font-mono text-[10px] uppercase tracking-[0.24em] text-gold">
            Your working instrument
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl">
            Set the voice. Keep the guardrails.
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            Personal settings shape how RedCase works with you—not which sources
            it can use or what it may claim.
          </p>
        </header>

        <section className="panel overflow-hidden">
          <div className="flex items-center gap-3 border-b border-border px-5 py-4 sm:px-7">
            <span className="grid size-9 place-items-center rounded-lg bg-gold/10 text-gold">
              <KeyRound className="size-4" />
            </span>
            <div>
              <h3 className="font-semibold">Security</h3>
              <p className="text-xs text-muted-foreground">
                Add password sign-in without giving up magic links
              </p>
            </div>
          </div>
          <form onSubmit={savePassword} className="space-y-5 p-5 sm:p-7">
            <div>
              <p className="text-sm font-medium text-foreground">
                Set password{" "}
                <span className="text-muted-foreground">(optional)</span>
              </p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                Your email magic link remains available. Choose a password only
                if you would also like to sign in with email and password.
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="New password">
                <input
                  className={inputClass}
                  type="password"
                  autoComplete="new-password"
                  minLength={6}
                  required
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  placeholder="At least 6 characters"
                />
              </Field>
              <Field label="Confirm new password">
                <input
                  className={inputClass}
                  type="password"
                  autoComplete="new-password"
                  minLength={6}
                  required
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  placeholder="Re-enter your password"
                />
              </Field>
            </div>
            {passwordNotice && (
              <p
                role={passwordNotice.kind === "error" ? "alert" : "status"}
                className={`text-sm ${passwordNotice.kind === "error" ? "text-destructive" : "text-success"}`}
              >
                {passwordNotice.text}
              </p>
            )}
            <button
              type="submit"
              disabled={passwordBusy || !newPassword || !confirmPassword}
              className="inline-flex items-center gap-2 rounded-lg border border-border bg-background px-5 py-2.5 text-sm font-semibold text-foreground transition-all duration-200 hover:border-gold/50 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold disabled:cursor-not-allowed disabled:opacity-60"
            >
              {passwordBusy ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <ShieldCheck className="size-4" />
              )}
              {passwordBusy ? "Saving password…" : "Set password"}
            </button>
          </form>
        </section>

        <section className="panel overflow-hidden">
          <div className="flex items-center gap-3 border-b border-border px-5 py-4 sm:px-7">
            <span className="grid size-9 place-items-center rounded-lg bg-gold/10 text-gold">
              <UserRound className="size-4" />
            </span>
            <div>
              <h3 className="font-semibold">Profile</h3>
              <p className="text-xs text-muted-foreground">
                Your firm directory identity and contact details
              </p>
            </div>
          </div>
          {profileNotice && (
            <p role="status" className="px-6 pt-4 text-sm text-success">
              {profileNotice}
            </p>
          )}
          {profile.isPending ? (
            <Loading />
          ) : profile.isError ? (
            <LoadError text="Profile is unavailable. Your firm administrator may need to provision your member record." />
          ) : (
            <form
              onSubmit={saveProfileForm}
              className="grid gap-5 p-5 sm:grid-cols-2 sm:p-7"
            >
              <Field label="Full name">
                <input
                  className={inputClass}
                  required
                  maxLength={200}
                  value={profileForm.full_name}
                  onChange={(e) =>
                    setProfileForm({
                      ...profileForm,
                      full_name: e.target.value,
                    })
                  }
                />
              </Field>
              <Field label="Phone">
                <input
                  className={inputClass}
                  type="tel"
                  maxLength={40}
                  value={profileForm.phone}
                  onChange={(e) =>
                    setProfileForm({ ...profileForm, phone: e.target.value })
                  }
                />
              </Field>
              <Field label="Email">
                <input
                  className={inputClass}
                  required
                  type="email"
                  maxLength={320}
                  value={profileForm.email}
                  onChange={(e) =>
                    setProfileForm({ ...profileForm, email: e.target.value })
                  }
                />
                <span className="mt-1 block text-[11px] text-muted-foreground">
                  Directory contact only; changing your sign-in address requires
                  email verification.
                </span>
              </Field>
              <Field label="Timezone">
                <input
                  className={inputClass}
                  required
                  maxLength={100}
                  value={profileForm.timezone}
                  onChange={(e) =>
                    setProfileForm({
                      ...profileForm,
                      timezone: e.target.value,
                    })
                  }
                  placeholder="Africa/Lagos"
                />
              </Field>
              <div className="sm:col-span-2">
                <SaveButton
                  pending={saveProfile.isPending}
                  label="Save profile"
                />
              </div>
            </form>
          )}
        </section>

        <section className="panel overflow-hidden">
          <div className="flex items-center gap-3 border-b border-border px-5 py-4 sm:px-7">
            <span className="grid size-9 place-items-center rounded-lg bg-primary/10 text-primary">
              <Bot className="size-4" />
            </span>
            <div>
              <h3 className="font-semibold">Workbench behavior</h3>
              <p className="text-xs text-muted-foreground">
                Personal controls for your specialist tools
              </p>
            </div>
          </div>
          {personaNotice && (
            <p role="status" className="px-6 pt-4 text-sm text-success">
              {personaNotice}
            </p>
          )}
          {persona.isPending ? (
            <Loading />
          ) : persona.isError ? (
            <LoadError text="Workbench preferences could not be loaded. Check the API connection and retry." />
          ) : (
            <form onSubmit={savePersonaForm} className="space-y-7 p-5 sm:p-7">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Assistant name">
                  <input
                    className={inputClass}
                    maxLength={120}
                    value={personaForm.agent_name ?? "Assistant"}
                    onChange={(e) => set("agent_name", e.target.value)}
                  />
                </Field>
                <Field label="Assistant tone">
                  <select
                    className={inputClass}
                    value={personaForm.tone_preset ?? "PROFESSIONAL"}
                    onChange={(e) =>
                      set("tone_preset", e.target.value as TonePreset)
                    }
                  >
                    {PERSONA_TONES.map((tone) => (
                      <option key={tone} value={tone}>
                        {tone.toLowerCase()}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Rules of engagement">
                  <textarea
                    className={`${inputClass} min-h-28 resize-y`}
                    maxLength={4000}
                    value={personaForm.rules_of_engagement ?? ""}
                    onChange={(e) => set("rules_of_engagement", e.target.value)}
                    placeholder="How should your assistant handle uncertainty, citations, and follow-up?"
                  />
                </Field>
                <Field label="Personality">
                  <textarea
                    className={`${inputClass} min-h-28 resize-y`}
                    maxLength={2000}
                    value={personaForm.personality ?? ""}
                    onChange={(e) => set("personality", e.target.value)}
                    placeholder="For example: measured, candid, and supportive."
                  />
                </Field>
                <Field label="Working style">
                  <textarea
                    className={`${inputClass} min-h-24 resize-y`}
                    maxLength={2000}
                    value={personaForm.working_style ?? ""}
                    onChange={(e) => set("working_style", e.target.value)}
                    placeholder="Preferred structure, level of detail, and pacing."
                  />
                </Field>
                <Field label="Reviewer specialty">
                  <textarea
                    className={`${inputClass} min-h-24 resize-y`}
                    maxLength={2000}
                    value={personaForm.reviewer_specialty ?? ""}
                    onChange={(e) => set("reviewer_specialty", e.target.value)}
                    placeholder="Areas of focus for reviewer workflows."
                  />
                </Field>
                <Field label="Researcher specialty">
                  <textarea
                    className={`${inputClass} min-h-24 resize-y`}
                    maxLength={2000}
                    value={personaForm.researcher_specialty ?? ""}
                    onChange={(e) =>
                      set("researcher_specialty", e.target.value)
                    }
                    placeholder="Research lens and subject-matter priorities."
                  />
                </Field>
                <label className="block">
                  <span className={fieldLabel}>
                    Red-Teamer temperature ·{" "}
                    {Number(personaForm.redteam_temperature ?? 0.2).toFixed(2)}
                  </span>
                  <input
                    aria-label="Red-Teamer temperature"
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={personaForm.redteam_temperature ?? 0.2}
                    onChange={(e) =>
                      set("redteam_temperature", Number(e.target.value))
                    }
                    className="mt-4 w-full accent-gold"
                  />
                  <span className="mt-1 flex justify-between font-mono text-[10px] text-muted-foreground">
                    <span>Precise</span>
                    <span>Exploratory</span>
                  </span>
                </label>
              </div>
              <div className="flex items-start gap-2 rounded-lg border border-gold/20 bg-gold/5 p-3 text-xs leading-5 text-muted-foreground">
                <ShieldCheck className="mt-0.5 size-4 shrink-0 text-gold" />
                Specialty and style guide the workflow only. They cannot expand
                Vault access, weaken citation checks, or override safety policy.
              </div>
              <SaveButton
                pending={savePersona.isPending}
                label="Save workbench settings"
              />
            </form>
          )}
        </section>
      </div>
    </AppShell>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className={fieldLabel}>{label}</span>
      {children}
    </label>
  );
}
function SaveButton({ pending, label }: { pending: boolean; label: string }) {
  return (
    <button
      type="submit"
      disabled={pending}
      className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground transition-all duration-200 hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold disabled:opacity-60"
    >
      {pending ? (
        <Loader2 className="size-4 animate-spin" />
      ) : (
        <Check className="size-4" />
      )}
      {pending ? "Saving…" : label}
    </button>
  );
}
function Loading() {
  return (
    <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
      <Loader2 className="size-4 animate-spin" />
      Loading settings…
    </div>
  );
}
function LoadError({ text }: { text: string }) {
  return (
    <p
      role="alert"
      className="m-5 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-muted-foreground"
    >
      {text}
    </p>
  );
}
