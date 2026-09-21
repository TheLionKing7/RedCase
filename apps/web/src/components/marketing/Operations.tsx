import { Eyebrow } from "./MarketingLayout";

const OPS_ITEMS = [
  "Time capture where work happens",
  "invoices in your letterhead",
  "conflict checks before the engagement letter",
  "court deadlines computed from validated rules and pushed to your calendar",
];

export function Operations() {
  return (
    <section className="mx-auto max-w-7xl px-5 py-20 lg:px-8 lg:py-28">
      <div className="max-w-3xl">
        <Eyebrow>Operations</Eyebrow>
        <h2 className="mt-4 font-display text-3xl font-semibold leading-tight sm:text-4xl">
          The OS, not a chatbot.
        </h2>
        <p className="mt-6 text-lg leading-relaxed text-foreground/90">
          {OPS_ITEMS[0]}
          <span className="text-muted-foreground">,</span> {OPS_ITEMS[1]}
          <span className="text-muted-foreground">,</span> {OPS_ITEMS[2]}
          <span className="text-muted-foreground">,</span> {OPS_ITEMS[3]}
          <span className="text-muted-foreground">.</span>
        </p>
      </div>
    </section>
  );
}
