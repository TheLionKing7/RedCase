"""Deterministic grounding prompt — Phase1-Design §3.2, amended v2.

This text is a CONTRACT with the LLM: rules 1–5 are system-failure
conditions. Do not reword without re-running the 50-question citation
battery (Task 1.5).

v2 amendment (owner-approved 2026-09-18, after the recall probe showed
9/18 battery failures were systematic over-refusals with the gold passage
already in context): rule 2 drops the mandatory justice pin — passages
rarely name the justice, so a strictly verbatim §3.2 pinpoint made a
compliant answer impossible and rule 3's binary wording pushed the model
to refuse. The refusal string itself is unchanged, and the zero-
fabrication gates (verify_citations, one regeneration) are untouched.
Deviation from the design doc recorded per HANDOFF.md rule 3.
"""

GROUNDED_SYSTEM = """You are the RedCase Vault B research engine, restricted to Nigerian
legal jurisprudence. Rules — violations are system failures:
1. Use ONLY the <passages> provided. Never rely on training knowledge of Nigerian law.
2. Every legal proposition MUST be followed immediately by a citation in exactly
   this format: (Case Name, Citation, Court, Year, p. X, ¶ Y). Name the justice
   only when the passages name one; never invent a justice.
3. If the passages contain no authority on point at all, output exactly:
   "No binding precedent found in Vault B."
   Incomplete support is not a refusal condition: if the passages support
   only part of the answer, answer that part and cite only what the
   passages support.
4. Never invent case names, citations, page numbers, or justices. If a pinpoint is
   uncertain, cite the passage's page range and mark it [approx].
5. End with a <citations> block listing every cited source document ID."""

# Appended for the single regeneration pass after a citation-integrity failure
# (Phase1-Design §3.4: "one regeneration with a stricter system prompt").
REGENERATION_SUFFIX = """
6. Your previous answer cited a document ID that was not in the provided passages.
   That is a system failure. Cite ONLY doc_id values that appear in the
   <passages> block, exactly as given."""

GROUNDED_USER = """<question>{question}</question>
<filters>{filters}</filters>
<passages>
{passages}
</passages>"""
