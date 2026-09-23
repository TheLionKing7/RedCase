import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Briefcase,
  Building2,
  Check,
  Loader2,
  Mail,
  PartyPopper,
  Plus,
  ShieldCheck,
  Trash2,
} from "lucide-react";

export const Route = createFileRoute("/onboarding")({
  component: OnboardingPage,
});

type Step = 0 | 1 | 2 | 3 | 4 | 5;

const STEPS = [
  "Account",
  "Firm identity",
  "KYC",
  "First matter",
  "Teammates",
  "Done",
];

const PRACTICE_AREAS = [
  "Litigation",
  "Corporate / M&A",
  "Family",
  "Employment",
  "Real estate",
  "Intellectual property",
  "Other",
];

const ID_DOCUMENT_TYPES = ["passport", "national_id", "driver_license"];

const STORAGE_KEY = "redcase.onboarding";

interface FormState {
  name: string;
  email: string;
  firm: string;
  logoPath: string;
  practice: string;
  jurisdiction: string;
  rcPath: string;
  idDocumentPath: string;
  idDocumentType: string;
  firmWebsite: string;
  matter: string;
  teammates: string[];
}

const EMPTY: FormState = {
  name: "",
  email: "",
  firm: "",
  logoPath: "",
  practice: PRACTICE_AREAS[0],
  jurisdiction: "",
  rcPath: "",
  idDocumentPath: "",
  idDocumentType: ID_DOCUMENT_TYPES[0],
  firmWebsite: "",
  matter: "",
  teammates: [],
};

function load(): FormState {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return EMPTY;
    return { ...EMPTY, ...(JSON.parse(raw) as Partial<FormState>) };
  } catch {
    return EMPTY;
  }
}

function OnboardingPage() {
  const [step, setStep] = useState<Step>(0);
  const [form, setForm] = useState<FormState>(load);
  const [busy, setBusy] = useState(false);
  const [emailDraft, setEmailDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  function persist(data: FormState) {
    setForm(data);
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch {
      /* storage may be unavailable — non-fatal */
    }
  }

  function next() {
    setError(null);
    if (step === 0 && (!form.name.trim() || !form.email.trim())) {
      setError("Please add your name and work email to continue.");
      return;
    }
    setStep((step + 1) as Step);
  }

  function addEmail() {
    const email = emailDraft.trim();
    if (!email) return;
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      setError("That email does not look valid.");
      return;
    }
    persist({ ...form, teammates: [...form.teammates, email] });
    setEmailDraft("");
    setError(null);
  }

  function skip() {
    setStep((step + 1) as Step);
  }

  async function finish() {
    setBusy(true);
    try {
      // No public self-service signup endpoint exists: seats are provisioned via firm
      // invites. The wizard captures onboarding preferences locally (firm identity, KYC
      // document paths, optional first matter + teammates) and hands off to the sign-in
      // gate where the account is actually activated. KYC uploads are intentionally NOT
      // performed in this slice — document bytes belong in private storage and are
      // handled by firm admin flows; here we capture storage paths + status only.
      await new Promise((r) => setTimeout(r, 400));
      setStep(5);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-12">
      <div className="w-full max-w-xl">
        <div className="mb-8 flex flex-col items-center text-center">
          <img
            src={form.logoPath || "/brand/redcase-mark-crimson.svg"}
            alt="RedCase"
            className="size-12 rounded-full object-contain"
          />
          <h1 className="mt-4 font-display text-2xl font-semibold text-foreground">
            {step === 5 ? "You're all set" : "Set up your firm"}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {step === 5
              ? "Finish by signing in to activate your seat."
              : "A guided setup. You can skip anything you are not ready for."}
          </p>
        </div>

        {/* Stepper */}
        {step < 5 && (
          <ol className="mb-8 flex items-center justify-center gap-2">
            {STEPS.slice(0, 5).map((label, i) => (
              <li key={label} className="flex items-center gap-2">
                {i > 0 && (
                  <div
                    className={`h-px w-6 ${i <= step ? "bg-primary" : "bg-border"}`}
                  />
                )}
                <span
                  className={`flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.16em] ${
                    i < step
                      ? "text-primary"
                      : i === step
                        ? "text-foreground"
                        : "text-muted-foreground"
                  }`}
                >
                  <span
                    className={`flex size-6 items-center justify-center rounded-full border text-[10px] ${
                      i < step
                        ? "border-primary bg-primary text-primary-foreground"
                        : i === step
                          ? "border-primary"
                          : "border-border"
                    }`}
                  >
                    {i < step ? <Check className="size-3" /> : i + 1}
                  </span>
                  {label}
                </span>
              </li>
            ))}
          </ol>
        )}

        <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
          {step === 0 && (
            <StepAccount
              form={form}
              onChange={(p) => persist({ ...form, ...p })}
            />
          )}
          {step === 1 && (
            <StepFirm
              form={form}
              onChange={(p) => persist({ ...form, ...p })}
            />
          )}
          {step === 2 && (
            <StepKyc form={form} onChange={(p) => persist({ ...form, ...p })} />
          )}
          {step === 3 && (
            <StepMatter
              form={form}
              onChange={(p) => persist({ ...form, ...p })}
            />
          )}
          {step === 4 && (
            <StepTeammates
              form={form}
              draft={emailDraft}
              onDraft={setEmailDraft}
              onAdd={addEmail}
              onRemove={(email) =>
                persist({
                  ...form,
                  teammates: form.teammates.filter((t) => t !== email),
                })
              }
            />
          )}
          {step === 5 && <StepDone email={form.email} name={form.name} />}

          {error && (
            <p className="mt-4 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}


          {step < 5 && (
            <div className="mt-6 flex items-center justify-between">
              <button
                type="button"
                onClick={() => setStep((step - 1) as Step)}
                disabled={step === 0}
                className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground disabled:pointer-events-none disabled:opacity-40"
              >
                <ArrowLeft className="size-4" /> Back
              </button>
              <div className="flex items-center gap-3">
                {step >= 2 && step < 5 && (
                  <button
                    type="button"
                    onClick={skip}
                    className="rounded-lg px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
                  >
                    Skip
                  </button>
                )}
                {step < 4 ? (
                  <button
                    type="button"
                    onClick={next}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
                  >
                    Continue <ArrowRight className="size-4" />
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={finish}
                    disabled={busy}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold disabled:opacity-60"
                  >
                    {busy ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <Check className="size-4" />
                    )}
                    {busy ? "Setting up…" : "Finish setup"}
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Label({ children }: { children: string }) {
  return (
    <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
      {children}
    </span>
  );
}


function StepAccount({
  form,
  onChange,
}: {
  form: FormState;
  onChange: (p: Partial<FormState>) => void;
}) {
  return (
    <div className="space-y-4">
      <label className="block">
        <Label>Your name</Label>
        <input
          value={form.name}
          onChange={(e) => onChange({ name: e.target.value })}
          className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
          placeholder="Alex Rivera"
        />
      </label>
      <label className="block">
        <Label>Work email</Label>
        <input
          type="email"
          value={form.email}
          onChange={(e) => onChange({ email: e.target.value })}
          className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
          placeholder="alex@firm.com"
        />
      </label>
    </div>
  );
}

function StepFirm({
  form,
  onChange,
}: {
  form: FormState;
  onChange: (p: Partial<FormState>) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-start gap-3 rounded-lg border border-border/60 bg-background/50 px-3 py-2.5 text-sm text-muted-foreground">
        <Building2 className="mt-0.5 size-4 shrink-0 text-gold" />
        <p>
          Your firm identity — a display name and logo — appears across the
          workspace and on documents you send clients.
        </p>
      </div>
      {form.logoPath && (
        <div className="flex items-center justify-center">
          <img
            src={form.logoPath}
            alt="Firm logo preview"
            className="size-20 rounded-xl border border-border object-contain p-2"
          />
        </div>
      )}
      <label className="block">
        <Label>Firm name</Label>
        <input
          value={form.firm}
          onChange={(e) => onChange({ firm: e.target.value })}
          className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
          placeholder="Rivera &amp; Partners LLP"
        />
      </label>
      <label className="block">
        <Label>Logo (storage path)</Label>
        <input
          value={form.logoPath}
          onChange={(e) => onChange({ logoPath: e.target.value })}
          className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2 font-mono text-xs"
          placeholder="logos/aetoes/logo.svg"
        />
        <p className="mt-1.5 text-xs text-muted-foreground">
          The logo is stored in private storage; this wizard only records where
          it lives. Uploads are handled by firm admin flows.
        </p>
      </label>
    </div>
  );
}

function StepKyc({
  form,
  onChange,
}: {
  form: FormState;
  onChange: (p: Partial<FormState>) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-start gap-3 rounded-lg border border-border/60 bg-background/50 px-3 py-2.5 text-sm text-muted-foreground">
        <ShieldCheck className="mt-0.5 size-4 shrink-0 text-gold" />
        <p>
          To comply with practice rules we verify your firm and one managing
          member. Documents are kept confidential and reviewed manually.
        </p>
      </div>
      <label className="block">
        <Label>Firm registration certificate (RC) — storage path</Label>
        <input
          value={form.rcPath}
          onChange={(e) => onChange({ rcPath: e.target.value })}
          className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm font-mono"
          placeholder="kyc/your-firm/rc.pdf"
        />
        <span className="mt-1 block text-xs text-muted-foreground">
          Document bytes are stored privately — only the reference path is kept.
        </span>
      </label>
      <label className="block">
        <Label>Managing member ID — storage path</Label>
        <input
          value={form.idDocumentPath}
          onChange={(e) => onChange({ idDocumentPath: e.target.value })}
          className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm font-mono"
          placeholder="kyc/your-firm/admin-id.pdf"
        />
      </label>
      <label className="block">
        <Label>ID document type</Label>
        <select
          value={form.idDocumentType}
          onChange={(e) => onChange({ idDocumentType: e.target.value })}
          className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
        >
          {ID_DOCUMENT_TYPES.map((t) => (
            <option key={t} value={t}>
              {t.replace(/_/g, " ")}
            </option>
          ))}
        </select>
      </label>
      <label className="block">
        <Label>Firm website (optional)</Label>
        <input
          type="url"
          value={form.firmWebsite}
          onChange={(e) => onChange({ firmWebsite: e.target.value })}
          className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
          placeholder="https://firm.com"
        />
      </label>
    </div>
  );
}


function StepMatter({
  form,
  onChange,
}: {
  form: FormState;
  onChange: (p: Partial<FormState>) => void;
}) {
  return (
    <div className="space-y-4">
      <label className="block">
        <Label>Practice area</Label>
        <select
          value={form.practice}
          onChange={(e) => onChange({ practice: e.target.value })}
          className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
        >
          {PRACTICE_AREAS.map((area) => (
            <option key={area} value={area}>
              {area}
            </option>
          ))}
        </select>
      </label>
      <label className="block">
        <Label>Primary jurisdiction</Label>
        <input
          value={form.jurisdiction}
          onChange={(e) => onChange({ jurisdiction: e.target.value })}
          className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
          placeholder="e.g. federal — England &amp; Wales"
        />
      </label>
      <label className="block">
        <Label>First matter (optional)</Label>
        <input
          value={form.matter}
          onChange={(e) => onChange({ matter: e.target.value })}
          className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
          placeholder="e.g. Acme v. Beta — discovery"
        />
      </label>
      <p className="flex items-center gap-2 text-xs text-muted-foreground">
        <Briefcase className="size-4 text-gold" />
        You can skip this and create matters later from the workbench.
      </p>
    </div>
  );
}

function StepTeammates({
  form,
  draft,
  onDraft,
  onAdd,
  onRemove,
}: {
  form: FormState;
  draft: string;
  onDraft: (v: string) => void;
  onAdd: () => void;
  onRemove: (email: string) => void;
}) {
  return (
    <div className="space-y-4">
      <label className="block">
        <Label>Colleague work email</Label>
        <div className="mt-1.5 flex gap-2">
          <input
            type="email"
            value={draft}
            onChange={(e) => onDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                onAdd();
              }
            }}
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            placeholder="colleague@firm.com"
          />
          <button
            type="button"
            onClick={onAdd}
            className="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-background"
          >
            <Plus className="size-4" /> Add
          </button>
        </div>
      </label>
      <ul className="space-y-2">
        {form.teammates.map((email) => (
          <li
            key={email}
            className="flex items-center justify-between rounded-lg border border-border/60 bg-background/50 px-3 py-2 text-sm"
          >
            <span className="flex items-center gap-2">
              <Mail className="size-4 text-muted-foreground" /> {email}
            </span>
            <button
              type="button"
              onClick={() => onRemove(email)}
              aria-label={`Remove ${email}`}
              className="text-muted-foreground transition-colors hover:text-destructive"
            >
              <Trash2 className="size-4" />
            </button>
          </li>
        ))}
      </ul>
      {form.teammates.length === 0 && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Mail className="size-4 text-gold" />
          You can invite teammates later from Firm Command.
        </p>
      )}
    </div>
  );
}

function StepDone({ name, email }: { name: string; email: string }) {
  return (
    <div className="text-center">
      <PartyPopper className="mx-auto size-12 text-gold" />
      <h2 className="mt-4 font-display text-xl font-semibold text-foreground">
        Thanks{name ? `, ${name.split(" ")[0]}` : ""}
      </h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Your preferences are saved. A firm administrator activates seats and
        verifies your KYC — sign in
        {email ? ` with ${email}` : ""} to get started.
      </p>
      <Link
        to="/signin"
        className="mt-6 inline-flex items-center gap-1.5 rounded-lg bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
      >
        Go to sign in <ArrowRight className="size-4" />
      </Link>
    </div>
  );
}

