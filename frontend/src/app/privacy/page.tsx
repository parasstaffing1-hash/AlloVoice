import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Notice — Allo",
  description: "How Allo collects, uses, shares and retains personal data under UK GDPR, including sub-processors, retention and your rights.",
};

const subProcessors: { name: string; purpose: string; region: string }[] = [
  { name: "Aiven (PostgreSQL)", purpose: "Managed database hosting for accounts, customers, jobs and invoices", region: "EU (EEA)" },
  { name: "Cloudflare R2 & Workers", purpose: "File/object storage, CDN, edge compute and caching", region: "EU / UK with global edge cache" },
  { name: "Resend", purpose: "Transactional email (quotes, invoices, notifications)", region: "United States" },
  { name: "Twilio", purpose: "Voice calls, SMS and WhatsApp delivery for the voice agent and messaging", region: "United States / Global routing" },
  { name: "OpenRouter", purpose: "AI inference gateway for quote building, summaries and drafting", region: "United States" },
  { name: "Groq", purpose: "Fast AI inference for transcription assistance and generation", region: "United States" },
  { name: "Sarvam", purpose: "Speech and voice AI, including multilingual transcription and synthesis", region: "India" },
  { name: "Stripe", purpose: "Card payments, Direct Debit and billing", region: "United States / EU" },
  { name: "Xero", purpose: "Accounting synchronisation where you connect Xero", region: "United Kingdom / Australia / United States" },
];

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-3xl px-6 py-16">
        <Link href="/" className="text-sm text-muted-foreground hover:text-primary hover:underline">
          ← Back to home
        </Link>
        <p className="mt-8 text-xs font-semibold uppercase tracking-widest text-primary">Legal</p>
        <h1 className="mt-2 text-4xl font-bold tracking-tight">Privacy Notice</h1>
        <p className="mt-3 text-sm text-muted-foreground">
          Last updated: 1 September 2026 · Allo (“we”, “us”) is the data controller for your Allo account.
          This notice is framed around <strong className="text-foreground">UK GDPR</strong>. If you use Allo
          outside the UK, your local data-protection law may also apply — the practices below still describe
          how we handle your data.
        </p>

        <div className="mt-10 space-y-10 text-[15px] leading-relaxed">
          <section>
            <h2 className="mb-3 text-xl font-semibold">1. Data controller</h2>
            <p className="text-muted-foreground">
              Allo is the data controller for account and service-administration data. For the customer details
              you upload (names, addresses, job histories), <em>you</em> are the controller and Allo acts as your
              processor under our Data Processing Agreement. Contact us any time through{" "}
              <strong className="text-foreground">Settings → Support</strong> in the app for privacy queries,
              and we will route your request to the privacy team.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold">2. Data we collect</h2>
            <div className="space-y-3 text-muted-foreground">
              <ul className="list-disc space-y-2 pl-5">
                <li>
                  <strong className="text-foreground">Account data:</strong> name, business name, email, phone,
                  billing address, VAT number, login and settings.
                </li>
                <li>
                  <strong className="text-foreground">Your customers &amp; jobs:</strong> customer contact details,
                  addresses, job descriptions, quotes, schedules, certificates (e.g. CP12, F-Gas, EICR), invoices
                  and payment status that you create or upload.
                </li>
                <li>
                  <strong className="text-foreground">Recordings &amp; communications:</strong> call recordings and
                  transcripts, voicemails, SMS / email / WhatsApp content and delivery logs, where you enable those features.
                </li>
                <li>
                  <strong className="text-foreground">Analytics &amp; device data:</strong> pages viewed, feature use,
                  crash reports, IP address, browser and device identifiers, and cookie-derived preferences.
                </li>
                <li>
                  <strong className="text-foreground">Support data:</strong> messages you send to support and any
                  attachments you include.
                </li>
              </ul>
              <p>We do not intentionally collect sensitive special-category data. Please do not dictate or upload health, biometric or other sensitive details into job notes or recordings.</p>
            </div>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold">3. Why we use it (purposes &amp; lawful bases)</h2>
            <div className="overflow-x-auto rounded-xl border border-border/50">
              <table className="w-full min-w-[560px] text-left text-sm">
                <thead>
                  <tr className="border-b border-border/50 bg-card/60 text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-3">Purpose</th>
                    <th className="px-4 py-3">Lawful basis (UK GDPR)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40 text-muted-foreground">
                  <tr><td className="px-4 py-3">Provide the service: jobs, quotes, dispatch, certificates, invoicing</td><td className="px-4 py-3">Contract</td></tr>
                  <tr><td className="px-4 py-3">Voice agent calls, messaging, reminders and review requests you instruct</td><td className="px-4 py-3">Contract · Legitimate interests (running your business communications)</td></tr>
                  <tr><td className="px-4 py-3">Billing, fraud prevention and account security</td><td className="px-4 py-3">Contract · Legal obligation · Legitimate interests</td></tr>
                  <tr><td className="px-4 py-3">Product analytics and improvement (aggregated / de-identified)</td><td className="px-4 py-3">Legitimate interests</td></tr>
                  <tr><td className="px-4 py-3">Marketing emails about Allo (opt-in only)</td><td className="px-4 py-3">Consent</td></tr>
                  <tr><td className="px-4 py-3">Compliance with tax, accounting and law-enforcement duties</td><td className="px-4 py-3">Legal obligation</td></tr>
                </tbody>
              </table>
            </div>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold">4. Sub-processors</h2>
            <p className="mb-4 text-muted-foreground">
              We share personal data only with the providers below (and only what each needs to perform its task).
              All are bound by data-processing terms. International transfers use UK-approved safeguards such as
              adequacy regulations, the UK IDTA or EU Standard Contractual Clauses.
            </p>
            <div className="overflow-x-auto rounded-xl border border-border/50">
              <table className="w-full min-w-[640px] text-left text-sm">
                <thead>
                  <tr className="border-b border-border/50 bg-card/60 text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-3">Provider</th>
                    <th className="px-4 py-3">Purpose</th>
                    <th className="px-4 py-3">Region</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40 text-muted-foreground">
                  {subProcessors.map((s) => (
                    <tr key={s.name}>
                      <td className="px-4 py-3 font-medium text-foreground">{s.name}</td>
                      <td className="px-4 py-3">{s.purpose}</td>
                      <td className="px-4 py-3">{s.region}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-sm text-muted-foreground">
              We will update this table if we add or replace a sub-processor and notify workspace owners of material changes.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold">5. Retention summary</h2>
            <div className="space-y-3 text-muted-foreground">
              <ul className="list-disc space-y-2 pl-5">
                <li><strong className="text-foreground">Active accounts:</strong> kept while your workspace is open and for 30 days after termination so you can export.</li>
                <li><strong className="text-foreground">Invoices &amp; tax records:</strong> kept for 6 years as HMRC requires.</li>
                <li><strong className="text-foreground">Call recordings &amp; transcripts:</strong> kept for 12 months by default (configurable per workspace), then deleted or anonymised.</li>
                <li><strong className="text-foreground">Support tickets &amp; logs:</strong> kept for 24 months for quality and dispute handling.</li>
                <li><strong className="text-foreground">Analytics:</strong> kept in aggregated, de-identified form.</li>
              </ul>
              <p>When retention ends we delete or anonymise the data. Backups roll off within 90 days.</p>
            </div>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold">6. Your rights</h2>
            <div className="space-y-3 text-muted-foreground">
              <p>
                You have the right to access, correct, export, restrict or erase your personal data, to object to
                processing based on legitimate interests, to withdraw marketing consent, and to complain to the{" "}
                <a className="underline hover:text-primary" href="https://ico.org.uk" target="_blank" rel="noreferrer">UK ICO</a>.
                If you are outside the UK you may also complain to your local supervisory authority.
              </p>
              <p>
                The fastest way to act on your rights is the in-app <strong className="text-foreground">GDPR page</strong>:
                go to <strong className="text-foreground">Settings → Privacy / GDPR</strong> in Allo to download a
                full export of your workspace or request erasure. Erasure requests are completed within 30 days,
                subject to records we must keep by law (e.g. invoices). For anything else, reach us through{" "}
                <strong className="text-foreground">Settings → Support</strong> in the app.
              </p>
            </div>
          </section>

          <section id="cookies">
            <h2 className="mb-3 scroll-mt-24 text-xl font-semibold">7. Cookies summary</h2>
            <div className="space-y-3 text-muted-foreground">
              <ul className="list-disc space-y-2 pl-5">
                <li><strong className="text-foreground">Strictly necessary:</strong> login session, security, load balancing and your cookie choice itself. Always on.</li>
                <li><strong className="text-foreground">Analytics (optional):</strong> privacy-friendly usage measurement to improve Allo. Off unless you choose “Accept all”.</li>
                <li><strong className="text-foreground">Marketing (optional):</strong> used only if we run campaign measurement. Off by default.</li>
              </ul>
              <p>
                Your choice is stored on-device as <code className="rounded bg-card px-1.5 py-0.5 text-xs text-foreground">allo_cookie_consent</code> and
                you can change it any time by clearing that stored choice or using the cookie prompt again. See the
                banner on any page for “Accept essential-only” vs “Accept all”.
              </p>
            </div>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold">8. Contact</h2>
            <p className="text-muted-foreground">
              For privacy questions, rights requests or complaints, contact us through{" "}
              <strong className="text-foreground">Settings → Support</strong> in the app and select “Privacy”.
              We respond within 30 days. If you remain unhappy you may complain to the UK ICO or your local regulator.
            </p>
          </section>
        </div>

        <div className="mt-12 flex flex-wrap gap-4 border-t border-border/50 pt-8 text-sm">
          <Link href="/terms" className="text-muted-foreground hover:text-primary hover:underline">
            Terms of Service →
          </Link>
          <Link href="/" className="text-muted-foreground hover:text-primary hover:underline">
            Back to home →
          </Link>
        </div>
      </div>
    </div>
  );
}
