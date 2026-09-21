import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Eyebrow } from "./MarketingLayout";

const FAQS = [
  {
    q: "Is my data used to train your models?",
    a: "No. Every AI call is zero-retention — client conversations never touch a model provider's logs, and nothing you write is used to train anyone's model.",
  },
  {
    q: "What does 'page-pinned citations' actually mean?",
    a: "Every legal proposition carries a citation to a specific page and paragraph of a stored source you can open and verify. If RedCase can't verify the authority in the vaults, it refuses to answer rather than guess.",
  },
  {
    q: "Who controls access to our firm's documents?",
    a: "Documents are encrypted with AES-256, per-document keys your firm controls. Permission is scoped per user by clearance and explicit grants — a restricted partner brief is invisible to everyone without a named grant.",
  },
  {
    q: "Which Nigerian courts are covered?",
    a: "Vault B indexes jurisprudence from the Supreme Court, Court of Appeal, Federal and State High Courts, and the NICN, cited to page and paragraph by ratio decidendi.",
  },
  {
    q: "How does the Legal Assistant learn how I work?",
    a: "One assistant per lawyer, bound to a Workbench. It learns your preferences from the work you do in your workbench — and converses only there, under your permissions, never in shared channels.",
  },
];

export function Faq() {
  return (
    <section id="faq" className="mx-auto max-w-3xl px-5 py-20 lg:px-8 lg:py-28">
      <Eyebrow>FAQ</Eyebrow>
      <h2 className="mt-4 font-display text-3xl font-semibold leading-tight">
        Questions, answered plainly.
      </h2>
      <Accordion type="single" collapsible className="mt-8">
        {FAQS.map((item, i) => (
          <AccordionItem
            key={item.q}
            value={`item-${i}`}
            className="border-b border-border/60"
          >
            <AccordionTrigger className="py-5 text-left font-medium text-foreground transition-colors duration-200 hover:text-gold">
              {item.q}
            </AccordionTrigger>
            <AccordionContent className="pb-5 text-sm leading-relaxed text-muted-foreground">
              {item.a}
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </section>
  );
}
