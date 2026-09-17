export type Vault = "A" | "B";

export type SearchResult = {
  id: string;
  vault: Vault;
  title: string;
  citation: string;
  court: string;
  year: number;
  ratio: string;
  excerpt: string;
  source: string;
  page: number;
  paragraph: string;
  confidence: number;
};

export const VAULT_RESULTS: SearchResult[] = [
  {
    id: "b1",
    vault: "B",
    title: "Amaechi v. INEC & Ors",
    citation: "(2008) 5 NWLR (Pt. 1080) 227",
    court: "Supreme Court",
    year: 2008,
    ratio: "Substitution of candidate",
    excerpt:
      "A political party cannot substitute a validly nominated candidate without cogent and verifiable reasons; the courts will not permit a party to profit from its own wrongdoing where the substitution is shown to be arbitrary.",
    source: "NJOS_SC_2008_Amaechi_v_INEC.pdf",
    page: 312,
    paragraph: "¶ 44–47 (Oguntade JSC)",
    confidence: 0.97,
  },
  {
    id: "b2",
    vault: "B",
    title: "Madukolu v. Nkemdilim",
    citation: "(1962) 2 SCNLR 341",
    court: "Supreme Court",
    year: 1962,
    ratio: "Jurisdiction / competence of court",
    excerpt:
      "A court is competent when it is properly constituted, the subject matter is within its jurisdiction, and the case comes before it initiated by due process of law and upon fulfilment of any condition precedent.",
    source: "NJOS_SC_1962_Madukolu_v_Nkemdilim.pdf",
    page: 348,
    paragraph: "¶ 12 (Bairamian FJ)",
    confidence: 0.99,
  },
  {
    id: "b3",
    vault: "B",
    title: "Skye Bank Plc v. Iwu",
    citation: "(2017) 16 NWLR (Pt. 1590) 24",
    court: "Supreme Court",
    year: 2017,
    ratio: "National Industrial Court appeals",
    excerpt:
      "Appeals from the National Industrial Court to the Court of Appeal are not restricted to fundamental rights matters; section 243(2) of the Constitution must be read alongside section 240.",
    source: "NJOS_SC_2017_SkyeBank_v_Iwu.pdf",
    page: 88,
    paragraph: "¶ 31 (Ogunbiyi JSC)",
    confidence: 0.93,
  },
  {
    id: "b4",
    vault: "B",
    title: "Dangote Gen. Textiles Ltd v. Hascon Assoc. (Nig) Ltd",
    citation: "(2013) 16 NWLR (Pt. 1379) 60",
    court: "Supreme Court",
    year: 2013,
    ratio: "Interlocutory injunction principles",
    excerpt:
      "The applicant must show a legal right, a substantial issue to be tried, balance of convenience, irreparable damage and an undertaking as to damages before an interlocutory injunction issues.",
    source: "NJOS_SC_2013_Dangote_v_Hascon.pdf",
    page: 104,
    paragraph: "¶ 22 (Fabiyi JSC)",
    confidence: 0.9,
  },
  {
    id: "b5",
    vault: "B",
    title: "Nwankwo v. Yar'Adua",
    citation: "(2010) 12 NWLR (Pt. 1209) 518",
    court: "Court of Appeal",
    year: 2010,
    ratio: "Locus standi in constitutional matters",
    excerpt:
      "The rigid application of locus standi has been relaxed in constitutional matters where a plaintiff shows sufficient interest in the observance of the Constitution.",
    source: "NJOS_CA_2010_Nwankwo_v_YarAdua.pdf",
    page: 561,
    paragraph: "¶ 18",
    confidence: 0.86,
  },
  {
    id: "a1",
    vault: "A",
    title: "Aetoes Internal Brief — Zenith Energy v. NNPCL (Arbitration)",
    citation: "AET/BRF/2024/117",
    court: "Internal (Arbitral)",
    year: 2024,
    ratio: "Force majeure under JV agreement",
    excerpt:
      "Our position paper argues that pipeline vandalism is a classic force majeure event under clause 22.3 and that the counterparty's failure to serve a 14-day notice defeats its claim for liquidated damages.",
    source: "AET_Brief_ZenithEnergy_v_NNPCL_v3.pdf",
    page: 14,
    paragraph: "§ 4.2",
    confidence: 0.95,
  },
  {
    id: "a2",
    vault: "A",
    title: "Aetoes Memo — Preliminary Objection Playbook (Lagos Division)",
    citation: "AET/MEM/2023/041",
    court: "Internal (Precedent Bank)",
    year: 2023,
    ratio: "Condition precedent / pre-action protocol",
    excerpt:
      "Where the claimant fails to file a Pre-Action Protocol Form 01 under Order 3 Rule 2(1) of the Lagos State High Court (Civil Procedure) Rules 2019, the originating process is liable to be struck out.",
    source: "AET_Memo_PO_Playbook_Lagos.pdf",
    page: 6,
    paragraph: "§ 2.1",
    confidence: 0.94,
  },
  {
    id: "a3",
    vault: "A",
    title: "Aetoes Brief — Adeyemi Holdings v. First Trust Bank",
    citation: "AET/BRF/2025/008",
    court: "Internal (Federal High Court)",
    year: 2025,
    ratio: "Banker's duty of care / unauthorised debit",
    excerpt:
      "Reliance on CBN Consumer Protection Framework 2016 to establish that the bank bore the burden of proving mandate authenticity for the disputed ₦412m transfer.",
    source: "AET_Brief_Adeyemi_v_FirstTrust.pdf",
    page: 22,
    paragraph: "§ 6.4",
    confidence: 0.91,
  },
  {
    id: "a4",
    vault: "A",
    title: "Aetoes Opinion — Tax Appeal Tribunal Strategy Note",
    citation: "AET/OPN/2024/203",
    court: "Internal (TAT)",
    year: 2024,
    ratio: "Deductibility of intercompany management fees",
    excerpt:
      "We advised that FIRS' disallowance is vulnerable on appeal given the transfer pricing documentation filed within the statutory window under the Income Tax (TP) Regulations 2018.",
    source: "AET_Opinion_TAT_MgmtFees.pdf",
    page: 9,
    paragraph: "§ 3.3",
    confidence: 0.88,
  },
];

export const COURT_LEVELS = [
  "All Courts",
  "Supreme Court",
  "Court of Appeal",
  "Federal High Court",
  "State High Court",
  "National Industrial Court",
];

export const RATIO_TAGS = [
  "All Ratios",
  "Jurisdiction",
  "Interlocutory injunction",
  "Locus standi",
  "Force majeure",
  "Condition precedent",
  "Evidence & burden of proof",
];

/* ---------------- Red-Teamer ---------------- */

export type Flaw = {
  title: string;
  detail: string;
  severity: "Critical" | "High" | "Moderate";
  rule: string;
};

export type OpposingArgument = {
  argument: string;
  strength: number;
  rebuttal: string;
};

export type CounterPrecedent = {
  case: string;
  citation: string;
  holding: string;
  page: string;
};

export const BATTLE_CARD: {
  matter: string;
  filedBy: string;
  overallRisk: string;
  flaws: Flaw[];
  arguments: OpposingArgument[];
  precedents: CounterPrecedent[];
} = {
  matter: "Zenith Energy Ltd v. Meridian Offshore Services Ltd — Suit No. FHC/L/CS/1184/2026",
  filedBy: "Opposing counsel: Balogun, Okoro & Co.",
  overallRisk: "Moderate — two procedural kill-shots available before merits",
  flaws: [
    {
      title: "No pre-action protocol form filed",
      detail:
        "The originating summons is unaccompanied by Form 01 and the requisite written statements on oath. This is a condition precedent, not a mere irregularity.",
      severity: "Critical",
      rule: "Order 3 Rule 2(1)(e), Federal High Court (Civil Procedure) Rules 2019",
    },
    {
      title: "Affidavit contains legal argument and conclusions",
      detail:
        "Paragraphs 9, 14 and 21 of the supporting affidavit contain submissions and prayers, offending the rule against argumentative affidavits; liable to be struck out.",
      severity: "High",
      rule: "Section 115(2), Evidence Act 2011",
    },
    {
      title: "Arbitration clause not pleaded around",
      detail:
        "Clause 34 of the JV Agreement mandates LCA arbitration. The brief does not plead waiver or invalidity, exposing the suit to a stay application.",
      severity: "Critical",
      rule: "Sections 5 & 34, Arbitration and Mediation Act 2023",
    },
    {
      title: "Exhibits not certified",
      detail:
        "Exhibits ZE-3 to ZE-7 are photocopies of public documents tendered without CTC endorsement; inadmissible as secondary evidence.",
      severity: "Moderate",
      rule: "Sections 102 & 104, Evidence Act 2011",
    },
  ],
  arguments: [
    {
      argument:
        "Meridian repudiated the charterparty by withdrawing the vessel on 11 March 2026.",
      strength: 72,
      rebuttal:
        "Withdrawal followed 41 days of unpaid hire; the anti-technicality notice was validly served, converting withdrawal into a contractual right, not repudiation.",
    },
    {
      argument: "Force majeure notice was served out of time and is void.",
      strength: 38,
      rebuttal:
        "Clause 22.3 contains no time bar; the 14-day requirement applies only to claims for extension, not to suspension of obligations.",
    },
    {
      argument: "The Federal High Court has admiralty jurisdiction over the claim.",
      strength: 61,
      rebuttal:
        "Claim is in substance for breach of a joint venture funding obligation — not a maritime claim under s.2 AJA 1991. Madukolu competence test fails on subject-matter.",
    },
    {
      argument: "Liquidated damages of US$4.2m are enforceable as agreed.",
      strength: 29,
      rebuttal:
        "Sum is a penalty: it is not a genuine pre-estimate of loss and exceeds total contract value for the affected period by 2.4x.",
    },
  ],
  precedents: [
    {
      case: "Madukolu v. Nkemdilim",
      citation: "(1962) 2 SCNLR 341",
      holding:
        "Competence requires due process and fulfilment of every condition precedent — defeats the suit on the unfiled pre-action protocol.",
      page: "p. 348, ¶ 12",
    },
    {
      case: "M.V. Lupex v. N.O.C. & S. Ltd",
      citation: "(2003) 15 NWLR (Pt. 844) 469",
      holding:
        "Where parties agree to arbitrate, the court should stay proceedings absent strong cause — supports our stay application.",
      page: "p. 490, ¶ 26",
    },
    {
      case: "Josien Holdings Ltd v. Lornamead Ltd",
      citation: "(1995) 1 NWLR (Pt. 371) 254",
      holding:
        "A sum stipulated in terrorem of the offending party is a penalty and unenforceable — neutralises the US$4.2m LD claim.",
      page: "p. 264, ¶ 9",
    },
    {
      case: "Buhari v. INEC",
      citation: "(2008) 19 NWLR (Pt. 1120) 246",
      holding:
        "Affidavit evidence offending s.115 Evidence Act is liable to be discountenanced in its entirety.",
      page: "p. 391, ¶ 55",
    },
  ],
};

export const STREAM_LINES: string[] = [
  "› Ingesting brief: Meridian_Reply_Brief_FHC_L_CS_1184_2026.pdf (34 pages)…",
  "› OCR + layout parse complete — 12,841 tokens, 47 paragraph nodes indexed.",
  "› Cross-checking 6 procedural gates against Federal High Court (Civil Procedure) Rules 2019…",
  "› 2 CRITICAL procedural defects detected (condition precedent, arbitration clause).",
  "› Retrieving binding authority from Vault B: Nigerian Juris OS — 1,412 SC judgments scanned.",
  "› 4 counter-precedents pinned with verified page citations. Hallucination guard: PASSED.",
  "› Scoring opposing arguments against Aetoes internal win-rate model…",
  "› Battle Card compiled. Confidence: 0.94. Rendering report.",
];

/* ---------------- Statutory Tracker ---------------- */

export type Deadline = {
  id: string;
  date: string; // ISO
  matter: string;
  task: string;
  rule: string;
  status: "critical" | "due" | "upcoming" | "filed";
  court: string;
  computedFrom: string;
};

export const DEADLINES: Deadline[] = [
  {
    id: "d1",
    date: "2026-08-17",
    matter: "Zenith Energy v. Meridian Offshore",
    task: "File Memorandum of Conditional Appearance",
    rule: "Order 9 Rule 1 — FHC Rules 2019 (14 days from service)",
    status: "critical",
    court: "Federal High Court, Lagos",
    computedFrom: "Service of originating process: 03 Aug 2026",
  },
  {
    id: "d2",
    date: "2026-08-20",
    matter: "Adeyemi Holdings v. First Trust Bank",
    task: "Reply on Points of Law to Counter-Affidavit",
    rule: "Order 26 Rule 5 — Lagos HC Rules 2019 (7 days)",
    status: "critical",
    court: "High Court of Lagos State, Ikeja",
    computedFrom: "Counter-affidavit served: 13 Aug 2026",
  },
  {
    id: "d3",
    date: "2026-08-24",
    matter: "Aetoes Legal v. FIRS (TAT Appeal)",
    task: "Hearing — Tax Appeal Tribunal, Lagos Zone",
    rule: "TAT Procedure Rules 2021, Order 3",
    status: "due",
    court: "Tax Appeal Tribunal",
    computedFrom: "Hearing notice dated 30 Jul 2026",
  },
  {
    id: "d4",
    date: "2026-08-28",
    matter: "Okonkwo v. Delta State Govt.",
    task: "File Notice of Appeal",
    rule: "S.24(2)(a) Court of Appeal Act — 14 days (interlocutory)",
    status: "due",
    court: "Court of Appeal, Asaba Division",
    computedFrom: "Ruling delivered: 14 Aug 2026",
  },
  {
    id: "d5",
    date: "2026-09-02",
    matter: "Sterling Maritime v. NPA",
    task: "Transmit Record of Appeal to CA Registry",
    rule: "Order 8 Rule 1 — CA Rules 2021 (60 days)",
    status: "upcoming",
    court: "Court of Appeal, Lagos Division",
    computedFrom: "Notice of appeal filed: 04 Jul 2026",
  },
  {
    id: "d6",
    date: "2026-09-08",
    matter: "Zenith Energy v. Meridian Offshore",
    task: "Motion on Notice for Stay Pending Arbitration",
    rule: "S.5 Arbitration & Mediation Act 2023 (before further steps)",
    status: "upcoming",
    court: "Federal High Court, Lagos",
    computedFrom: "Appearance entered: 17 Aug 2026",
  },
  {
    id: "d7",
    date: "2026-09-15",
    matter: "Ibrahim v. Kano State Housing Corp.",
    task: "Final Written Address (Claimant)",
    rule: "Order 30 Rule 15 — Kano HC Rules (21 days from close of case)",
    status: "upcoming",
    court: "High Court of Kano State",
    computedFrom: "Close of claimant's case: 25 Aug 2026",
  },
  {
    id: "d8",
    date: "2026-08-11",
    matter: "Lagos Free Zone Co. v. NCS",
    task: "File Statement of Defence",
    rule: "Order 15 Rule 1 — FHC Rules 2019",
    status: "filed",
    court: "Federal High Court, Lagos",
    computedFrom: "Service: 28 Jul 2026 — FILED 10 Aug 2026",
  },
];

export const RULE_PRESETS = [
  { label: "Memorandum of Appearance — FHC (14 days)", days: 14 },
  { label: "Statement of Defence — Lagos HC (42 days)", days: 42 },
  { label: "Notice of Appeal, interlocutory — CA (14 days)", days: 14 },
  { label: "Notice of Appeal, final — CA (90 days)", days: 90 },
  { label: "Record of Appeal transmission — CA (60 days)", days: 60 },
  { label: "Reply on points of law — Lagos HC (7 days)", days: 7 },
];
