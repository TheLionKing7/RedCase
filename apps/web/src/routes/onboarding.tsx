import { createFileRoute, Link, redirect } from "@tanstack/react-router";
import { useState, type ReactNode } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  Check,
  CheckCircle2,
  Loader2,
  Mail,
  PartyPopper,
  Plus,
  ShieldCheck,
  Trash2,
  Upload,
} from "lucide-react";
import { apiPost } from "@/lib/api/client";
import { getFirmAssetPreview, uploadFirmAsset, type FirmAssetType } from "@/lib/api/firmAssets";
import { saveDepartments, savePracticeAreas } from "@/lib/api/persona";
import { getAccessToken, getSession, refreshSession, signInWithEmail, verifyOtp } from "@/lib/auth/supabase";

export const Route = createFileRoute("/onboarding")({
  beforeLoad: () => {
    if (
      typeof window !== "undefined" &&
      import.meta.env.VITE_API_DEV_ADAPTER !== "1" &&
      getSession()
    ) {
      throw redirect({ to: "/home" });
    }
  },
  component: OnboardingPage,
});

type Step = 0 | 1 | 2 | 3 | 4 | 5;
type UploadStatus = { state: "uploading" | "success" | "failure"; progress: number; message?: string };

const STEPS = ["Account", "Firm identity", "KYC", "Services & departments", "Team", "Done"];
const PRACTICE_AREAS = [
  "Litigation", "Corporate & Commercial", "Property & Land", "Employment", "Family",
  "Banking & Finance", "Tax", "Intellectual Property", "Criminal", "Election & Constitutional",
];
const DEPARTMENTS = ["Legal Practice", "Accounts & Finance", "HR & Administration", "Operations"];
const ID_TYPES = ["national-id", "drivers-license", "passport"];
const STORAGE_KEY = "redcase.onboarding";

interface FormState {
  name: string;
  email: string;
  otp: string;
  verified: boolean;
  firm: string;
  logoPath: string;
  logoPreview: string;
  rcPath: string;
  idPath: string;
  idType: string;
  website: string;
  services: string[];
  departments: string[];
  teammates: string[];
}

const EMPTY: FormState = {
  name: "", email: "", otp: "", verified: false, firm: "", logoPath: "", logoPreview: "",
  rcPath: "", idPath: "", idType: "national-id", website: "", services: [],
  departments: ["Legal Practice"], teammates: [],
};

function loadDraft(): FormState {
  try {
    const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "null") as Partial<FormState> | null;
    return { ...EMPTY, ...saved, verified: false, otp: "", logoPreview: "" };
  } catch {
    return EMPTY;
  }
}

function OnboardingPage() {
  const [step, setStep] = useState<Step>(0);
  const [form, setForm] = useState<FormState>(loadDraft);
  const [busy, setBusy] = useState(false);
  const [otpSent, setOtpSent] = useState(false);
  const [emailDraft, setEmailDraft] = useState("");
  const [error, setError] = useState("");
  const [uploads, setUploads] = useState<Record<string, UploadStatus>>({});

  function update(patch: Partial<FormState>) {
    setForm((current) => {
      const next = { ...current, ...patch };
      try {
        const { otp: _otp, verified: _verified, logoPreview: _preview, ...safeDraft } = next;
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(safeDraft));
      } catch { /* Browser storage is optional; document bytes are never stored here. */ }
      return next;
    });
  }

  async function sendOrVerifyAccount() {
    if (!form.name.trim() || !form.email.trim() || !form.firm.trim()) {
      setError("Enter your name, work email and firm name to continue.");
      return false;
    }
    if (form.verified && getAccessToken()) return true;
    if (!otpSent) {
      const application = await apiPost<{ verify_token?: string }, { email: string; firm_name: string; jurisdiction: string }>("/v1/public/signup", {
        email: form.email.trim(), firm_name: form.firm.trim(), jurisdiction: "NG",
      });
      if (application.verify_token) {
        // Dev/CI uses the API's single-use signup verification token instead of
        // Supabase email OTP. Production requires the verified Supabase JWT.
        await apiPost("/v1/public/verify", { email: form.email.trim(), token: application.verify_token });
        setError("Application verified. Sign in with the confirmed Supabase account to continue private setup.");
        return false;
      }
      await signInWithEmail(form.email.trim());
      setOtpSent(true);
      setError("A one-time code is on its way. Enter it here to verify your work email.");
      return false;
    }
    if (!form.otp.trim()) {
      setError("Enter the one-time code from your email.");
      return false;
    }
    await verifyOtp(form.email.trim(), form.otp.trim());
    await apiPost("/v1/public/activate", { email: form.email.trim(), full_name: form.name.trim() });
    await refreshSession();
    update({ verified: true, otp: "" });
    return true;
  }

  async function continueStep() {
    setError("");
    if (step === 0) {
      setBusy(true);
      try {
        if (await sendOrVerifyAccount()) setStep(1);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Email verification failed.");
      } finally { setBusy(false); }
      return;
    }
    if (step === 2 && (!form.rcPath || !form.idPath)) {
      setError("Upload both the firm RC document and your personal ID to continue.");
      return;
    }
    if (step === 3) {
      setBusy(true);
      try {
        await savePracticeAreas(form.services.length ? form.services : ["Legal Practice"]);
        await saveDepartments(form.departments);
        setStep(4);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not save firm preferences.");
      } finally { setBusy(false); }
      return;
    }
    if (step === 4) {
      setBusy(true);
      try {
        await apiPost("/v1/firm/kyc", {
          firm_website: form.website || null,
          rc_path: form.rcPath,
          id_document_path: form.idPath,
          id_document_type: form.idType,
        });
        if (form.logoPath) {
          await apiPost("/v1/firm/identity", { firm_name: form.firm, jurisdiction: "NG", logo_path: form.logoPath });
        }
        for (const email of form.teammates) {
          await apiPost("/v1/invites", { email, role: "ASSOCIATE" });
        }
        setStep(5);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not submit the firm setup.");
      } finally { setBusy(false); }
      return;
    }
    setStep((step + 1) as Step);
  }

  async function upload(type: FirmAssetType, file: File, field: "logoPath" | "rcPath" | "idPath") {
    if (file.size > 10 * 1024 * 1024) {
      setUploads((current) => ({ ...current, [field]: { state: "failure", progress: 0, message: "Maximum file size is 10 MB." } }));
      return;
    }
    setUploads((current) => ({ ...current, [field]: { state: "uploading", progress: 0 } }));
    try {
      const result = await uploadFirmAsset(type, file, (progress) => {
        setUploads((current) => ({ ...current, [field]: { state: "uploading", progress } }));
      });
      update({ [field]: result.path } as Pick<FormState, typeof field>);
      if (type === "logo") update({ logoPreview: await getFirmAssetPreview(type, result.path) });
      setUploads((current) => ({ ...current, [field]: { state: "success", progress: 100 } }));
    } catch (err) {
      setUploads((current) => ({
        ...current,
        [field]: { state: "failure", progress: 0, message: err instanceof Error ? err.message : "Upload failed." },
      }));
    }
  }

  function addTeammate() {
    const email = emailDraft.trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      setError("Enter a valid teammate email address.");
      return;
    }
    if (form.teammates.includes(email)) {
      setError("That teammate has already been added.");
      return;
    }
    update({ teammates: [...form.teammates, email] });
    setEmailDraft("");
    setError("");
  }

    return (
      <main className="flex min-h-screen items-center justify-center bg-background px-4 py-12">
      <div className="w-full max-w-xl">
        <header className="mb-8 flex flex-col items-center text-center">
          <img src="/brand/redcase-logo.svg" alt="RedCase" className="h-12 w-auto object-contain" />
          <h1 className="mt-4 font-display text-2xl font-semibold text-foreground">
            {step === 5 ? "Your firm is ready" : "Set up your firm"}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">Five steps to a secure firm workspace.</p>
        </header>

        {step < 5 && (
          <ol className="mb-8 flex flex-wrap items-center justify-center gap-x-2 gap-y-3" aria-label="Onboarding steps">
            {STEPS.slice(0, 5).map((label, index) => (
              <li key={label} className="flex items-center gap-2">
                {index > 0 && <span className={`h-px w-4 ${index <= step ? "bg-primary" : "bg-border"}`} />}
                <span className={`flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-widest ${index === step ? "text-foreground" : index < step ? "text-primary" : "text-muted-foreground"}`}>
                  <span className={`flex size-6 items-center justify-center rounded-full border ${index < step ? "border-primary bg-primary text-white" : index === step ? "border-primary text-primary" : "border-border"}`}>
                    {index < step ? <Check className="size-3" /> : index + 1}
                  </span>{label}
                </span>
              </li>
            ))}
          </ol>
        )}

        <section className="rounded-xl border border-border bg-surface p-6 shadow-elevated sm:p-8">
          {step === 0 && <StepAccount form={form} onChange={update} otpSent={otpSent} />}
          {step === 1 && (
            <StepFirm form={form} onChange={update} upload={upload} uploads={uploads} />
          )}
          {step === 2 && <StepKyc form={form} onChange={update} upload={upload} uploads={uploads} />}
          {step === 3 && <StepServices form={form} onChange={update} />}
          {step === 4 && <StepTeam form={form} emailDraft={emailDraft} onDraft={setEmailDraft} onAdd={addTeammate} onRemove={(email) => update({ teammates: form.teammates.filter((entry) => entry !== email) })} />}
          {step === 5 && <StepDone name={form.name} email={form.email} />}

          {error && <p role="alert" className="mt-4 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
          {step < 5 && (
            <div className="mt-6 flex items-center justify-between">
              <button type="button" onClick={() => setStep((Math.max(0, step - 1)) as Step)} disabled={step === 0 || busy} className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm text-muted-foreground transition-all duration-200 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold disabled:pointer-events-none disabled:opacity-40">
                <ArrowLeft className="size-4" /> Back
              </button>
              <button type="button" onClick={continueStep} disabled={busy || (step === 1 && Boolean(uploads["logoPath"]?.state === "uploading")) || (step === 2 && (uploads["rcPath"]?.state === "uploading" || uploads["idPath"]?.state === "uploading"))} className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground transition-all duration-200 hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold disabled:opacity-60">
                {busy && <Loader2 className="size-4 animate-spin" />}
                {step === 4 ? "Complete setup" : otpSent && step === 0 ? "Verify and continue" : "Continue"}
                {!busy && <ArrowRight className="size-4" />}
              </button>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}


function FieldLabel({ children }: { children: ReactNode }) {
  return <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">{children}</span>;
}

function UploadField({ title, type, field, upload, uploads, accept = ".pdf,.jpg,.jpeg,.png" }: {
  title: string; type: FirmAssetType; field: "logoPath" | "rcPath" | "idPath";
  upload: (type: FirmAssetType, file: File, field: "logoPath" | "rcPath" | "idPath") => void;
  uploads: Record<string, UploadStatus>; accept?: string;
}) {
  const current = uploads[field];
  return (
    <div>
      <label className="flex cursor-pointer items-center justify-between gap-4 rounded-xl border border-dashed border-border bg-background/50 p-4 transition-all duration-200 hover:border-primary/60 focus-within:ring-2 focus-within:ring-gold">
        <span><span className="block text-sm font-medium text-foreground">{title}</span><span className="mt-1 block text-xs text-muted-foreground">PDF, JPG or PNG · Up to 10 MB</span></span>
        <span className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs font-medium"><Upload className="size-4" /> Choose file</span>
        <input className="sr-only" type="file" accept={accept} onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          if (file) upload(type, file, field);
          event.currentTarget.value = "";
        }} />
      </label>
      {current?.state === "uploading" && <div className="mt-2" role="status"><div className="h-1.5 overflow-hidden rounded bg-border"><div className="h-full bg-primary transition-all duration-200" style={{ width: `${current.progress}%` }} /></div><p className="mt-1 text-xs text-muted-foreground">Uploading… {current.progress}%</p></div>}
      {current?.state === "success" && <p role="status" className="mt-2 flex items-center gap-1.5 text-xs text-success"><CheckCircle2 className="size-4" /> Uploaded securely</p>}
      {current?.state === "failure" && <p role="alert" className="mt-2 text-xs text-destructive">{current.message}</p>}
    </div>
  );
}

function StepAccount({ form, onChange, otpSent }: { form: FormState; onChange: (patch: Partial<FormState>) => void; otpSent: boolean }) {
  return <div className="space-y-4">
    <div className="flex items-start gap-3 rounded-lg border border-border/60 bg-background/50 p-3 text-sm text-muted-foreground"><Mail className="mt-0.5 size-4 shrink-0 text-gold" /><p>Verify your work email first. This confirms the firm admin account before private files can be uploaded.</p></div>
    <label className="block"><FieldLabel>Your name</FieldLabel><input autoComplete="name" value={form.name} onChange={(event) => onChange({ name: event.target.value })} className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm" placeholder="Your full name" /></label>
    <label className="block"><FieldLabel>Work email</FieldLabel><input type="email" autoComplete="email" value={form.email} onChange={(event) => onChange({ email: event.target.value })} className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm" placeholder="you@yourfirm.com" /></label>
    <label className="block"><FieldLabel>Firm name</FieldLabel><input value={form.firm} onChange={(event) => onChange({ firm: event.target.value })} className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm" placeholder="Aetoes Legal" /></label>
    {otpSent && <label className="block"><FieldLabel>Email verification code</FieldLabel><input inputMode="numeric" autoComplete="one-time-code" value={form.otp} onChange={(event) => onChange({ otp: event.target.value })} className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm tracking-[0.25em]" placeholder="Enter code from email" /></label>}
  </div>;
}

function StepFirm({ form, onChange, upload, uploads }: { form: FormState; onChange: (patch: Partial<FormState>) => void; upload: (type: FirmAssetType, file: File, field: "logoPath" | "rcPath" | "idPath") => void; uploads: Record<string, UploadStatus> }) {
  return <div className="space-y-5">
    <div className="flex items-start gap-3 rounded-lg border border-border/60 bg-background/50 p-3 text-sm text-muted-foreground"><Building2 className="mt-0.5 size-4 shrink-0 text-gold" /><p>Your firm workspace starts with a secure identity. Upload a logo to preview it here.</p></div>
    {form.logoPreview && <img src={form.logoPreview} alt="Uploaded firm logo preview" className="mx-auto size-24 rounded-xl border border-border bg-background object-contain p-3" />}
    <label className="block"><FieldLabel>Firm name</FieldLabel><input value={form.firm} onChange={(event) => onChange({ firm: event.target.value })} className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm" /></label>
    <UploadField title="Firm logo" type="logo" field="logoPath" upload={upload} uploads={uploads} accept=".jpg,.jpeg,.png" />
    <label className="block"><FieldLabel>Jurisdiction</FieldLabel><select value="NG" disabled className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm"><option value="NG">Nigeria</option></select></label>
    <label className="block"><FieldLabel>Firm website (optional)</FieldLabel><input type="url" value={form.website} onChange={(event) => onChange({ website: event.target.value })} className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm" placeholder="https://yourfirm.com" /></label>
  </div>;
}

function StepKyc({ form, onChange, upload, uploads }: { form: FormState; onChange: (patch: Partial<FormState>) => void; upload: (type: FirmAssetType, file: File, field: "logoPath" | "rcPath" | "idPath") => void; uploads: Record<string, UploadStatus> }) {
  return <div className="space-y-5">
    <div className="flex items-start gap-3 rounded-lg border border-gold/30 bg-gold/5 p-3 text-sm text-muted-foreground"><ShieldCheck className="mt-0.5 size-4 shrink-0 text-gold" /><p>These documents are PARTNER_RESTRICTED, stored in a private bucket and accessible only through short-lived, admin-gated links.</p></div>
    <label className="block"><FieldLabel>Administrator ID type</FieldLabel><select value={form.idType} onChange={(event) => onChange({ idType: event.target.value })} className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm">{ID_TYPES.map((type) => <option key={type} value={type}>{type === "national-id" ? "National ID (NIN)" : type === "drivers-license" ? "Driver’s licence" : "International passport"}</option>)}</select></label>
    <UploadField title="CAC registration certificate (RC)" type="rc-document" field="rcPath" upload={upload} uploads={uploads} />
    <UploadField title="Administrator personal ID" type="personal-id" field="idPath" upload={upload} uploads={uploads} />
  </div>;
}

function StepServices({ form, onChange }: { form: FormState; onChange: (patch: Partial<FormState>) => void }) {
  function toggle(key: "services" | "departments", value: string) {
    if (key === "departments" && value === "Legal Practice") return;
    const values = form[key];
    onChange({ [key]: values.includes(value) ? values.filter((entry) => entry !== value) : [...values, value] });
  }
  return <div className="space-y-6">
    <div><h2 className="font-display text-lg font-semibold">Choose your practice &amp; departments</h2><p className="mt-1 text-sm text-muted-foreground">Shape the modules your firm uses. You can always change these later.</p></div>
    <fieldset><legend className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Practice areas</legend><div className="mt-3 grid gap-2 sm:grid-cols-2">{PRACTICE_AREAS.map((area) => <ToggleCard key={area} label={area} selected={form.services.includes(area)} onClick={() => toggle("services", area)} />)}</div></fieldset>
    <fieldset><legend className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Departments</legend><div className="mt-3 grid gap-2 sm:grid-cols-2">{DEPARTMENTS.map((department) => <ToggleCard key={department} label={department} selected={form.departments.includes(department)} onClick={() => toggle("departments", department)} />)}</div></fieldset>
  </div>;
}

function ToggleCard({ label, selected, onClick }: { label: string; selected: boolean; onClick: () => void }) {
  return <button type="button" aria-pressed={selected} onClick={onClick} className={`rounded-lg border px-3 py-3 text-left text-sm transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold ${selected ? "border-gold bg-gold/10 text-foreground" : "border-border text-muted-foreground hover:border-gold/50 hover:text-foreground"}`}><span className="flex items-center justify-between gap-2">{label}{selected && <Check className="size-4 text-gold" />}</span></button>;
}

function StepTeam({ form, emailDraft, onDraft, onAdd, onRemove }: { form: FormState; emailDraft: string; onDraft: (value: string) => void; onAdd: () => void; onRemove: (email: string) => void }) {
  return <div className="space-y-5">
    <div><h2 className="font-display text-lg font-semibold">Invite your team</h2><p className="mt-1 text-sm text-muted-foreground">You can invite colleagues now or add them later from Firm Ops.</p></div>
    <div className="flex gap-2"><label className="min-w-0 flex-1"><span className="sr-only">Colleague work email</span><input type="email" value={emailDraft} onChange={(event) => onDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); onAdd(); } }} className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm" placeholder="colleague@firm.com" /></label><button type="button" onClick={onAdd} className="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-2 text-sm transition-all duration-200 hover:border-gold/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"><Plus className="size-4" />Add</button></div>
    <ul className="space-y-2">{form.teammates.map((email) => <li key={email} className="flex items-center justify-between rounded-lg border border-border/60 px-3 py-2 text-sm"><span className="flex items-center gap-2"><Mail className="size-4 text-muted-foreground" />{email}</span><button type="button" aria-label={`Remove ${email}`} onClick={() => onRemove(email)} className="text-muted-foreground transition-all duration-200 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"><Trash2 className="size-4" /></button></li>)}</ul>
    <p className="text-xs text-muted-foreground">Each invitation consumes a seat; teammates join as Associate unless their role is changed later by an Admin.</p>
  </div>;
}

function StepDone({ name, email }: { name: string; email: string }) {
  return <div className="text-center"><PartyPopper className="mx-auto size-12 text-gold" /><h2 className="mt-4 font-display text-xl font-semibold">Welcome, {name.split(" ")[0]}</h2><p className="mt-2 text-sm text-muted-foreground">Your firm setup is complete. The assistant starts with its default persona; personalize it later in Settings → Assistant Persona.{email ? ` We sent a confirmation to ${email}.` : ""}</p><Link to="/home" className="mt-6 inline-flex items-center gap-2 rounded-lg bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground transition-all duration-200 hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold">Open your workspace <ArrowRight className="size-4" /></Link></div>;
}