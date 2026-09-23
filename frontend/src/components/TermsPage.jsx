import { Link } from 'react-router-dom'

function Section({ title, children }) {
  return (
    <section className="mb-8">
      <h2 className="font-display text-lg font-semibold text-primary mb-2">{title}</h2>
      <div className="text-sm text-muted leading-relaxed space-y-3">{children}</div>
    </section>
  )
}

function P({ children }) {
  return <p>{children}</p>
}

const LAST_UPDATED = 'September 24, 2026'

export default function TermsPage() {
  return (
    <div className="max-w-3xl mx-auto px-6 py-20">
      <p className="font-mono text-xs text-signal tracking-wide uppercase mb-4">Legal</p>
      <h1 className="font-display text-3xl md:text-4xl font-semibold text-primary mb-2">
        Terms &amp; Conditions
      </h1>
      <p className="text-muted text-sm mb-12">Last updated: {LAST_UPDATED}</p>

      <Section title="1. Agreement">
        <P>
          By accessing or using RouteWise (&quot;the service&quot;) you agree to these Terms and our{' '}
          <Link to="/privacy" className="text-signal hover:underline">
            Privacy Policy
          </Link>
          . If you do not agree, do not use the service. The service is operated on a best-effort basis for evaluation,
          learning and lightweight automations.
        </P>
      </Section>

      <Section title="2. The service">
        <P>
          RouteWise routes natural-language queries to the most cost-effective LLM tier (cheap / mid / frontier) based
          on an automated difficulty score. It provides a web chat, an API, and an SDK. The service may change,
          limit, or discontinue features at any time.
        </P>
      </Section>

      <Section title="3. Accounts and authentication">
        <P>
          Creating an account requires an email address and password, or Google sign-in. You are responsible for
          keeping your credentials confidential. Email verification may be required before an account is active. You
          may close your account at any time. One person may operate one account unless we agree otherwise.
        </P>
      </Section>

      <Section title="4. Acceptable use">
        <P>
          You agree not to: use the service to generate unlawful, abusive, harassing or harmful content; attempt to
          circumvent rate limits or billing controls; probe, scan or attack the infrastructure; resell the service as a
          competing router without permission; or misrepresent model safety filters. We may terminate access for
          violations without prior notice.
        </P>
      </Section>

      <Section title="5. API keys and quotas">
        <P>
          The API is accessed with API keys scoped to your account. Rate limits apply (e.g. requests per minute) and
          may change. Keys you configure for third-party model providers are your responsibility; the service relays
          them only to the named provider to serve your own requests.
        </P>
      </Section>

      <Section title="6. Fees and free tier">
        <P>
          The service currently provides free usage with limits. If paid plans are introduced later, pricing, payment
          and refund terms will be published before they take effect and will apply only to use after their effective
          date.
        </P>
      </Section>

      <Section title="7. Intellectual property">
        <P>
          The RouteWise software, design, models and documentation are proprietary to their respective owners and are
          licensed, not sold. You retain rights to the content you submit, subject to the licenses you grant to model
          providers when we route your queries.
        </P>
      </Section>

      <Section title="8. Availability, disclaimers">
        <P>
          THE SERVICE IS PROVIDED &quot;AS IS&quot; WITHOUT WARRANTIES OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING
          MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NON-INFRINGEMENT. Model outputs may be inaccurate,
          unsafe or unusable; you are responsible for reviewing and using them. The free tier includes periods of
          cold-start latency and no uptime commitment.
        </P>
      </Section>

      <Section title="9. Limitation of liability">
        <P>
          To the maximum extent permitted by law, RouteWise and its operators are not liable for indirect, incidental,
          special, consequential or exemplary damages, or for any loss of profits, revenue, data or goodwill, arising
          from your use of the service. Our total aggregate liability is limited to the amount you paid us in the 12
          months preceding the claim (or $0 for free-tier use).
        </P>
      </Section>

      <Section title="10. Third-party content and safety">
        <P>
          Queries are routed to and answered by third-party LLM providers. Content generated is their responsibility
          and is passed through with minimal filtering. You use generated content at your own risk.
        </P>
      </Section>

      <Section title="11. Changes to these terms">
        <P>
          We may revise these Terms. Updated terms take effect on the corrected &quot;Last updated&quot; date; your
          continued use after that date accepts the change. Where reasonably possible we will highlight material
          changes.
        </P>
      </Section>

      <Section title="12. Governing law and disputes">
        <P>
          These Terms are governed by the laws applicable where the operator is domiciled, without regard to conflict
          of law principles. Any dispute will be handled informally through the contact channel below before any legal
          action.
        </P>
      </Section>

      <Section title="13. Contact">
        <P>
          For questions about these Terms, contact us via the GitHub repository:{' '}
          <a
            href="https://github.com/Ishan-5/llm-router"
            target="_blank"
            rel="noreferrer"
            className="text-signal hover:underline font-mono text-xs"
          >
            github.com/Ishan-5/llm-router
          </a>
          .
        </P>
      </Section>

      <div className="border-t border-line pt-6 mt-12">
        <p className="font-mono text-xs text-muted">
          Also see our{' '}
          <Link to="/privacy" className="text-signal hover:underline">
            Privacy Policy
          </Link>
          .
        </p>
      </div>
    </div>
  )
}