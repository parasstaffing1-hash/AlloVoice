import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms of Service — Allo",
  description: "Allo Terms of Service: plans, billing, acceptable use, AI service notes, liability and governing law.",
};

const sections = [
  { id: "who-we-are", label: "1. Who we are & your account" },
  { id: "plans", label: "2. Plans, trial & billing" },
  { id: "acceptable-use", label: "3. Acceptable use" },
  { id: "ai-services", label: "4. AI & voice service notes" },
  { id: "customer-data", label: "5. Your customers & your data" },
  { id: "liability", label: "6. Warranties & liability cap" },
  { id: "termination", label: "7. Suspension & termination" },
  { id: "law", label: "8. Governing law" },
];

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-3xl px-6 py-16">
        <Link href="/" className="text-sm text-muted-foreground hover:text-primary hover:underline">
          ← Back to home
        </Link>
        <p className="mt-8 text-xs font-semibold uppercase tracking-widest text-primary">Legal</p>
        <h1 className="mt-2 text-4xl font-bold tracking-tight">Terms of Service</h1>
        <p className="mt-3 text-sm text-muted-foreground">
          Last updated: 1 September 2026 · These terms form the agreement between you (“you”, “the Customer”)
          and Allo (“we”, “us”) for use of the Allo field-service platform, including our web app, voice agent,
          messaging and payment features.
        </p>

        <nav className="mt-8 rounded-2xl border border-border/50 bg-card/50 p-5">
          <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground">On this page</p>
          <ul className="grid gap-2 text-sm sm:grid-cols-2">
            {sections.map((s) => (
              <li key={s.id}>
                <a href={`#${s.id}`} className="text-muted-foreground hover:text-primary hover:underline">
                  {s.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="mt-10 space-y-10 text-[15px] leading-relaxed">
          <section id="who-we-are" className="scroll-mt-24">
            <h2 className="mb-3 text-xl font-semibold">1. Who we are &amp; your account</h2>
            <div className="space-y-3 text-muted-foreground">
              <p>
                Allo provides AI-assisted software for UK field-service businesses: quoting, scheduling, dispatch,
                certificates, invoicing, reviews and an AI voice agent that answers calls and messages on your behalf.
              </p>
              <ul className="list-disc space-y-2 pl-5">
                <li>You must be at least 18 years old and authorised to act for the business you sign up with.</li>
                <li>Keep your login credentials confidential. You are responsible for all activity under your account, including actions taken by team members you invite.</li>
                <li>Give us accurate business details (legal name, contact, billing address) and keep them up to date in Settings.</li>
                <li>One account per business unless you have a multi-branch plan. Do not share logins across businesses or resell access without written permission.</li>
              </ul>
            </div>
          </section>

          <section id="plans" className="scroll-mt-24">
            <h2 className="mb-3 text-xl font-semibold">2. Plans, 14-day trial &amp; billing</h2>
            <div className="space-y-3 text-muted-foreground">
              <p>
                Allo is billed per user, per month, excluding VAT. Current plans are{" "}
                <strong className="text-foreground">Starter at £29</strong>,{" "}
                <strong className="text-foreground">Growth at £49</strong> and{" "}
                <strong className="text-foreground">Trade at £79</strong> per user per month, as shown on our
                pricing page. If prices change, we will give at least 30 days&apos; notice and the new price
                applies from your next renewal.
              </p>
              <ul className="list-disc space-y-2 pl-5">
                <li>
                  <strong className="text-foreground">14-day free trial.</strong> New workspaces start with a
                  14-day trial, no card required. At the end of the trial, choose a paid plan to keep using Allo.
                </li>
                <li>
                  <strong className="text-foreground">Subscriptions.</strong> Paid plans renew monthly until
                  cancelled. Adding users mid-cycle adds pro-rated seats; removing users takes effect at the next renewal.
                </li>
                <li>
                  <strong className="text-foreground">Usage charges.</strong> Card payments via Stripe cost
                  1.5% + 20p per transaction. AI voice minutes, SMS and WhatsApp messages are metered at the
                  rates shown in-app and billed in arrears or deducted from any usage allowance on your plan.
                </li>
                <li>
                  <strong className="text-foreground">Cancellation.</strong> Cancel anytime from Settings →
                  Billing. You keep access until the end of the paid period; we do not refund part-months except
                  where required by law.
                </li>
                <li>
                  <strong className="text-foreground">Failed payments.</strong> If a payment fails we will retry
                  and notify you. After 14 days overdue we may pause paid features until the balance is cleared.
                </li>
              </ul>
            </div>
          </section>

          <section id="acceptable-use" className="scroll-mt-24">
            <h2 className="mb-3 text-xl font-semibold">3. Acceptable use</h2>
            <div className="space-y-3 text-muted-foreground">
              <p>
                Allo gives you powerful voice, SMS, email and WhatsApp tools. With that power comes responsibility
                for how you contact your customers. You agree not to:
              </p>
              <ul className="list-disc space-y-2 pl-5">
                <li>Send spam, bulk unsolicited messages, or marketing messages without valid consent and a clear opt-out.</li>
                <li>Abuse the voice agent to harass, deceive, impersonate, or cold-call numbers that have not consented to contact.</li>
                <li>Use SMS, email or WhatsApp features to send unlawful, threatening, discriminatory or misleading content.</li>
                <li>Make excessive, automated or “robocall-style” outbound calls that breach Ofcom rules or the Privacy and Electronic Communications Regulations (PECR).</li>
                <li>Upload malware, attempt to breach our systems, scrape the service, or interfere with other customers&apos; use.</li>
                <li>Use Allo for emergency-dispatch, life-safety, or other high-risk purposes where an AI delay or error could cause harm.</li>
              </ul>
              <p>
                You are the sender of every message and call Allo places on your behalf. You must hold the necessary
                consents, keep an up-to-date suppression list, honour opt-outs promptly, and comply with PECR, the UK
                GDPR and Ofcom guidance. We may throttle, block or suspend messaging or calling that looks abusive,
                and pass-through carrier or provider fees remain payable.
              </p>
            </div>
          </section>

          <section id="ai-services" className="scroll-mt-24">
            <h2 className="mb-3 text-xl font-semibold">4. AI &amp; voice service notes</h2>
            <div className="space-y-3 text-muted-foreground">
              <ul className="list-disc space-y-2 pl-5">
                <li>
                  <strong className="text-foreground">AI assistance, not professional advice.</strong> Quotes,
                  transcriptions, summaries and suggested replies are generated by AI and may contain errors.
                  Always review quotes, certificates, safety findings and customer-facing messages before you send or act on them.
                </li>
                <li>
                  <strong className="text-foreground">Call recording &amp; transcription.</strong> Where you enable
                  it, calls handled by the voice agent may be recorded and transcribed so you have a record of
                  bookings, quotes and consent. Allo plays or sends a recording notice where required, but{" "}
                  <em>you</em> are responsible for telling your callers that calls may be recorded and for having a
                  lawful basis to record.
                </li>
                <li>
                  <strong className="text-foreground">Your review duty.</strong> Do not present AI-generated
                  certificates (Gas Safety CP12, F-Gas, EICR), prices or diagnoses as verified until a competent
                  person has checked them.
                </li>
                <li>
                  <strong className="text-foreground">Training.</strong> We do not train shared AI models on your
                  private customer data. Any model improvement uses de-identified, aggregated data only, and only
                  where permitted by our Privacy Notice.
                </li>
                <li>
                  <strong className="text-foreground">Availability.</strong> AI, telephony and messaging providers
                  can have outages or latency. We do not guarantee uninterrupted or error-free voice services.
                </li>
              </ul>
            </div>
          </section>

          <section id="customer-data" className="scroll-mt-24">
            <h2 className="mb-3 text-xl font-semibold">5. Your customers &amp; your data</h2>
            <div className="space-y-3 text-muted-foreground">
              <p>
                You remain the data controller of your own customer data; Allo acts as your processor under our
                Data Processing Agreement and Privacy Notice. You confirm you have the right to share customer
                details with us and to instruct us to call, message, invoice or otherwise process them.
              </p>
              <p>
                You can export your jobs, customers, invoices and recordings at any time, and request erasure from
                the in-app GDPR page. After termination we retain data only as described in the Privacy Notice
                (for example, for invoicing records the law requires us to keep).
              </p>
            </div>
          </section>

          <section id="liability" className="scroll-mt-24">
            <h2 className="mb-3 text-xl font-semibold">6. Warranties &amp; liability cap</h2>
            <div className="space-y-3 text-muted-foreground">
              <p>
                Allo is provided “as is”. To the maximum extent permitted by law, we disclaim implied warranties
                of merchantability, fitness for a particular purpose and non-infringement. We do not warrant that
                quotes will be accurate, work will be won, or AI transcriptions will be error-free.
              </p>
              <p>
                Nothing in these terms limits liability that cannot legally be limited, including for death or
                personal injury caused by negligence, fraud, or breach of data-protection obligations where statute
                forbids exclusion. Subject to that, our total aggregate liability for all claims in any 12-month
                period is capped at the amounts you paid for Allo in those 12 months (or £500 if you were on a free
                trial). We are not liable for indirect losses such as lost profit, lost jobs, or missed call-outs.
              </p>
            </div>
          </section>

          <section id="termination" className="scroll-mt-24">
            <h2 className="mb-3 text-xl font-semibold">7. Suspension &amp; termination</h2>
            <div className="space-y-3 text-muted-foreground">
              <ul className="list-disc space-y-2 pl-5">
                <li>You may cancel anytime; termination takes effect at the end of the current billing period.</li>
                <li>
                  We may suspend or terminate with notice if you breach these terms (including non-payment or
                  messaging abuse), or immediately where continued provision would breach law, harm our network,
                  or expose us or others to risk.
                </li>
                <li>
                  On termination, paid features stop at period-end. You have 30 days to export your data; after
                  that we delete or anonymise it in line with the Privacy Notice, except records we must keep by law.
                </li>
              </ul>
            </div>
          </section>

          <section id="law" className="scroll-mt-24">
            <h2 className="mb-3 text-xl font-semibold">8. Governing law</h2>
            <div className="space-y-3 text-muted-foreground">
              <p>
                These terms are governed by the laws of <strong className="text-foreground">England and Wales</strong>,
                and the courts of England and Wales have exclusive jurisdiction — except that if you are based
                outside the UK, mandatory consumer or local laws of your country may also apply, and nothing here
                removes those protections.
              </p>
              <p>
                If any part of these terms is found unenforceable, the rest continues in force. Changes to these
                terms take effect when published in-app or on this page; material changes get at least 14 days&apos;
                notice, and continued use after that means you accept them. Questions about these terms? Contact us
                through <strong className="text-foreground">Settings → Support</strong> in the app.
              </p>
            </div>
          </section>
        </div>

        <div className="mt-12 flex flex-wrap gap-4 border-t border-border/50 pt-8 text-sm">
          <Link href="/privacy" className="text-muted-foreground hover:text-primary hover:underline">
            Privacy Notice →
          </Link>
          <Link href="/" className="text-muted-foreground hover:text-primary hover:underline">
            Back to home →
          </Link>
        </div>
      </div>
    </div>
  );
}
