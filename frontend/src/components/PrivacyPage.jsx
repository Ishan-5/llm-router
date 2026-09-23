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

export default function PrivacyPage() {
  return (
    <div className="max-w-3xl mx-auto px-6 py-20">
      <p className="font-mono text-xs text-signal tracking-wide uppercase mb-4">Legal</p>
      <h1 className="font-display text-3xl md:text-4xl font-semibold text-primary mb-2">
        Privacy Policy
      </h1>
      <p className="text-muted text-sm mb-12">Last updated: {LAST_UPDATED}</p>

      <Section title="1. Who we are">
        <P>
          RouteWise (&quot;we&quot;, &quot;us&quot;) operates a cost-aware LLM request router available at{' '}
          <span className="font-mono text-primary">https://llm-router-nine-eta.vercel.app</span>. This policy explains
          what information we collect when you use the service and how we handle it.
        </P>
      </Section>

      <Section title="2. Information we collect">
        <P>
          <strong className="text-primary">Account information.</strong> If you create an account we receive the email
          address, display name and password you provide. Authentication is handled by our identity provider (Supabase
          Auth); we do not store plaintext passwords.
        </P>
        <P>
          <strong className="text-primary">Queries and responses.</strong> To route your requests we process the text you
          submit, along with any model API keys you choose to configure for your account. Your queries are sent to the
          third-party LLM provider selected for your tier.
        </P>
        <P>
          <strong className="text-primary">Routing logs.</strong> We store a log of each request — query text, routed
          tier, model used, token counts, cost, latency, and cache hits — to operate the service and power your usage
          dashboard.
        </P>
        <P>
          <strong className="text-primary">Cache.</strong> Frequently asked queries and their responses may be stored in
          our semantic cache to reduce cost and latency.
        </P>
        <P>
          <strong className="text-primary">Payment / billing.</strong> The service currently offers free usage tiers; we
          do not process payments directly.
        </P>
      </Section>

      <Section title="3. Cookies and local storage">
        <P>
          We use your browser&apos;s local storage to remember your sign-in session, theme preference and router
          settings. These are stored on your device and are not used for cross-site advertising.
        </P>
      </Section>

      <Section title="4. How we use your information">
        <P>We use the information we collect to: provide and operate the router, route queries to the appropriate model tier, compute usage and cost metrics, maintain the semantic cache, improve routing quality, and keep the service secure (rate limiting, abuse prevention).</P>
      </Section>

      <Section title="5. Third-party services">
        <P>
          <strong className="text-primary">Model providers.</strong> When a query is routed, the query text is shared
          with the provider that serves your tier (for example DeepSeek, OpenAI-compatible providers) under that
          provider&apos;s own terms and privacy policy.
        </P>
        <P>
          <strong className="text-primary">Supabase.</strong> Account authentication, the JWT session and email
          verification are handled by Supabase. See Supabase&apos;s privacy policy for how they process auth data.
        </P>
        <P>
          <strong className="text-primary">Google.</strong> If you sign in with Google, Google shares a verified email
          address and profile details with us; sign-in itself is governed by Google&apos;s privacy policy.
        </P>
        <P>
          <strong className="text-primary">Infrastructure.</strong> The service is hosted on Render (backend) and
          Vercel (frontend); those platforms process network requests in the course of hosting.
        </P>
      </Section>

      <Section title="6. How long we keep data">
        <P>
          Cache entries and usage logs are kept for a rolling period (cached entries are evicted automatically; logs
          support the stats dashboard). You can delete your account and we will remove your account data accordingly.
          Requests will be held no longer than necessary to operate the service.
        </P>
      </Section>

      <Section title="7. Your rights">
        <P>
          You may request a copy of the data we hold about you, ask us to correct it, or ask us to delete your account
          and related records by contacting us at the address below. You may also stop using the service at any time.
        </P>
      </Section>

      <Section title="8. Security">
        <P>
          We follow security best practices: API keys are stored as hashes, model keys you provide are kept in your
          account configuration, the frontend never receives server-side secret keys, and rate limits guard the API. No
          method of transmission is 100% secure, and we cannot guarantee absolute security.
        </P>
      </Section>

      <Section title="9. Children">
        <P>The service is not directed at children under 13. We do not knowingly collect data from children.</P>
      </Section>

      <Section title="10. Changes to this policy">
        <P>
          We may update this policy from time to time. Material changes will be reflected by an updated &quot;Last
          updated&quot; date above. Continued use of the service after changes constitutes acceptance.
        </P>
      </Section>

      <Section title="11. Contact">
        <P>
          Questions about this policy can be addressed via the GitHub repository:{' '}
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
          <Link to="/terms" className="text-signal hover:underline">
            Terms &amp; Conditions
          </Link>
          .
        </p>
      </div>
    </div>
  )
}