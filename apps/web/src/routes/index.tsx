import { createFileRoute } from "@tanstack/react-router";
import { MarketingLayout } from "@/components/marketing/MarketingLayout";
import { Hero } from "@/components/marketing/Hero";
import { Problem } from "@/components/marketing/Problem";
import { DualVault } from "@/components/marketing/DualVault";
import { Trust } from "@/components/marketing/Trust";
import { Workbench } from "@/components/marketing/Workbench";
import { RedTeam } from "@/components/marketing/RedTeam";
import { SecureMessenger } from "@/components/marketing/SecureMessenger";
import { Operations } from "@/components/marketing/Operations";
import { Security } from "@/components/marketing/Security";
import { Pricing } from "@/components/marketing/Pricing";
import { Receptionist } from "@/components/marketing/Receptionist";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "RedCase — The Legal Operating System for Nigerian Firms" },
      {
        name: "description",
        content:
          "Your firm's brain. Nigeria's law. One engine. RedCase unites your firm's knowledge and the country's jurisprudence in two secure vaults, answered with page-pinned citations to real authority.",
      },
      { property: "og:title", content: "RedCase — The Legal Operating System" },
      {
        property: "og:description",
        content:
          "Dual-vault legal intelligence for Nigerian firms. Never invented. Always page-pinned.",
      },
    ],
  }),
  component: MarketingHome,
});

function MarketingHome() {
  return (
    <MarketingLayout>
      <Hero />
      <Problem />
      <DualVault />
      <Trust />
      <Workbench />
      <RedTeam />
      <SecureMessenger />
      <Operations />
      <Security />
      <Pricing />
      <Receptionist />
      <section className="border-t border-border/60 bg-primary/5">
        <div className="mx-auto max-w-3xl px-5 py-20 text-center lg:px-8">
          <h2 className="font-display text-3xl font-semibold leading-tight sm:text-4xl">Put the law back in your firm&rsquo;s hands.</h2>
          <a href="/signin" className="mt-8 inline-flex items-center justify-center rounded-lg bg-primary px-8 py-3 text-sm font-semibold text-primary-foreground shadow-sm transition-all duration-200 hover:bg-primary/90 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold">Start your firm</a>
        </div>
      </section>
    </MarketingLayout>
  );
}
