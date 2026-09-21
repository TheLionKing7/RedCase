import { Eyebrow } from "./MarketingLayout";

const PROBLEM_CARDS = [
  {
    title: "Briefs buried in folders and memory",
    body: "Your firm&rsquo;s hardest-won reasoning sits in inboxes and this year&rsquo;s senior&rsquo;s head. When they leave, the reasoning leaves with them.",
  },
  {
    title: "Research that takes hours and still risks a wrong authority",
    body: "Hours of hunting for a precedent &mdash; and the risk of citing a case the court has since distinguished or reversed.",
  },
  {
    title: "WhatsApp threads no auditor would call a file",
    body: "Decisions live in group chats and voice notes &mdash; unversioned, unowned, and invisible to anyone not in the thread.",
  },
];

export function Problem() {
  return (
    <section className="mx-auto max-w-7xl px-5 py-20 lg:px-8 lg:py-28">
      <div className="max-w-2xl">
        <Eyebrow>The problem</Eyebrow>
        <h2 className="mt-4 font-display text-3xl font-semibold leading-tight sm:text-4xl">
          Your knowledge walks out the door every evening.
        </h2>
      </div>
      <div className="mt-10 grid grid-cols-1 gap-5 md:grid-cols-3">
        {PROBLEM_CARDS.map((card) => (
          <article
            key={card.title}
            className="rounded-xl border border-border bg-surface p-6 transition-all duration-200 hover:border-gold/30 hover:shadow-elevated"
          >
            <h3 className="font-display text-lg font-semibold leading-snug">
              {card.title}
            </h3>
            <p
              className="mt-3 text-sm leading-relaxed text-muted-foreground"
              dangerouslySetInnerHTML={{ __html: card.body }}
            />
          </article>
        ))}
      </div>
    </section>
  );
}
