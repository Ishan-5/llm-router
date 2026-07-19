import { useState, useEffect, lazy, Suspense } from 'react'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { supabase } from './supabase'
import Header from './components/Header'
import RoutingDiagram from './components/RoutingDiagram'
import HowItWorks from './components/HowItWorks'
import Footer from './components/Footer'
import SettingsPanel from './components/SettingsPanel'
import CommandPalette from './components/CommandPalette'
import Reveal from './components/Reveal'
import { useTheme } from './useTheme'

const PricingPage = lazy(() => import('./components/PricingTable'))
const AboutPage = lazy(() => import('./components/AboutPage'))
const AuthPage = lazy(() => import('./components/AuthPage'))
const DashboardPage = lazy(() => import('./components/DashboardPage'))
const MetricsDashboard = lazy(() => import('./components/MetricsDashboard'))
const ApiPlayground = lazy(() => import('./components/ApiPlayground'))
const GuidePage = lazy(() => import('./components/GuidePage'))

const TITLES = {
  '/': 'Routewise — Cost-aware LLM routing',
  '/pricing': 'Routewise — Models & Pricing',
  '/playground': 'Routewise — API Playground',
  '/guide': 'Routewise — Developer Guide',
  '/about': 'Routewise — About',
  '/auth': 'Routewise — Sign in',
  '/dashboard': 'Routewise — Dashboard',
}

function PageSkeleton({ type }) {
  if (type === 'pricing') {
    return (
      <div className="max-w-6xl mx-auto px-6 py-20 border-t border-line">
        <div className="h-4 w-24 bg-line rounded animate-pulse mb-4" />
        <div className="h-8 w-72 bg-line rounded animate-pulse mb-2" />
        <div className="h-4 w-96 bg-line rounded animate-pulse mb-8" />
        <div className="flex gap-3 mb-8">
          <div className="h-8 w-48 bg-line rounded animate-pulse" />
          <div className="h-8 w-16 bg-line rounded-full animate-pulse" />
          <div className="h-8 w-20 bg-line rounded-full animate-pulse" />
          <div className="h-8 w-24 bg-line rounded-full animate-pulse" />
        </div>
        <div className="h-10 w-full bg-line rounded animate-pulse mb-4" />
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-12 w-full bg-line/50 rounded animate-pulse mb-2" />
        ))}
      </div>
    )
  }
  if (type === 'auth') {
    return (
      <div className="min-h-[70vh] flex items-center justify-center px-6">
        <div className="w-full max-w-sm flex flex-col gap-4">
          <div className="h-5 w-32 bg-line rounded animate-pulse" />
          <div className="h-8 w-40 bg-line rounded animate-pulse" />
          <div className="h-4 w-56 bg-line rounded animate-pulse" />
          <div className="h-12 w-full bg-line rounded animate-pulse" />
          <div className="h-12 w-full bg-line rounded animate-pulse" />
          <div className="h-10 w-full bg-signal/30 rounded-lg animate-pulse" />
        </div>
      </div>
    )
  }
  if (type === 'dashboard') {
    return (
      <div className="max-w-3xl mx-auto px-6 py-20">
        <div className="h-4 w-24 bg-line rounded animate-pulse mb-4" />
        <div className="h-8 w-48 bg-line rounded animate-pulse mb-2" />
        <div className="h-4 w-80 bg-line rounded animate-pulse mb-12" />
        <div className="flex gap-3 mb-8">
          <div className="h-12 flex-1 bg-line rounded animate-pulse" />
          <div className="h-12 w-32 bg-signal/30 rounded-lg animate-pulse" />
        </div>
        <div className="h-px w-full bg-line mb-4" />
        {[1, 2].map((i) => (
          <div key={i} className="h-16 w-full bg-line/50 rounded animate-pulse mb-2" />
        ))}
      </div>
    )
  }
  return (
    <div className="max-w-3xl mx-auto px-6 py-20">
      <div className="h-4 w-24 bg-line rounded animate-pulse mb-4" />
      <div className="h-10 w-80 bg-line rounded animate-pulse mb-8" />
      <div className="flex flex-col gap-4">
        <div className="h-4 w-full bg-line rounded animate-pulse" />
        <div className="h-4 w-5/6 bg-line rounded animate-pulse" />
        <div className="h-4 w-4/6 bg-line rounded animate-pulse" />
      </div>
    </div>
  )
}

const PAGE_SKELETONS = { '/pricing': 'pricing', '/about': 'about', '/auth': 'auth', '/dashboard': 'dashboard' }

function HomePage({ configVersion, backendOnline }) {
  return (
    <>
      <RoutingDiagram configVersion={configVersion} backendOnline={backendOnline} />
      <Reveal>
        <HowItWorks />
      </Reveal>
      <Reveal delay={100}>
        <Suspense fallback={
          <div className="max-w-6xl mx-auto px-6 py-20 border-t border-line bg-panel">
            <div className="h-7 w-48 bg-line rounded animate-pulse mb-2" />
            <div className="h-4 w-72 bg-line rounded animate-pulse mb-12" />
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="border-l-2 border-line pl-4">
                  <div className="h-3 w-20 bg-line rounded animate-pulse mb-3" />
                  <div className="h-9 w-16 bg-line rounded animate-pulse" />
                </div>
              ))}
            </div>
          </div>
        }>
          <MetricsDashboard isDark={undefined} backendOnline={backendOnline} />
        </Suspense>
      </Reveal>
    </>
  )
}

function PricingRoute({ onNavigate }) {
  return <PricingPage onBack={() => onNavigate('/')} />
}

export default function App() {
  const { isDark, toggle } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()
  const [user, setUser] = useState(null)
  const [toast, setToast] = useState(null)
  const [showSettings, setShowSettings] = useState(false)
  const [cmdOpen, setCmdOpen] = useState(false)
  const [configVersion, setConfigVersion] = useState(0)
  const [backendOnline, setBackendOnline] = useState(true)
  const [byomActive, setByomActive] = useState(() => {
    try { return Object.keys(JSON.parse(localStorage.getItem('byom_config') || '{}')).length > 0 }
    catch { return false }
  })

  useEffect(() => {
    document.title = TITLES[location.pathname] || 'Routewise'
  }, [location.pathname])

  function showToast(msg) {
    setToast(msg)
    setTimeout(() => setToast(null), 3000)
  }

  function handleNavigate(path) {
    navigate(path)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  useEffect(() => {
    function handleKey(e) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setCmdOpen((v) => !v)
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [])

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => setUser(session?.user ?? null))
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      setUser(session?.user ?? null)
      if (event === 'SIGNED_IN') { showToast('Signed in'); handleNavigate('/') }
      if (event === 'SIGNED_OUT') { showToast('Signed out'); handleNavigate('/') }
    })
    return () => subscription.unsubscribe()
  }, [])

  useEffect(() => {
    function checkHealth() {
      fetch('/health')
        .then((r) => setBackendOnline(r.ok))
        .catch(() => setBackendOnline(false))
    }
    checkHealth()
    const id = setInterval(checkHealth, 15_000)
    return () => clearInterval(id)
  }, [])

  function handleConfigSaved() {
    setConfigVersion((v) => v + 1)
    setShowSettings(false)
    try { setByomActive(Object.keys(JSON.parse(localStorage.getItem('byom_config') || '{}')).length > 0) }
    catch { setByomActive(false) }
  }

  return (
    <div className="min-h-screen bg-base font-body">
      {!backendOnline && (
        <div className="w-full bg-danger/10 border-b border-danger/30 px-6 py-2.5 flex items-center gap-3">
          <span className="w-2 h-2 rounded-full bg-danger shrink-0" />
          <p className="font-mono text-xs text-danger">
            Backend offline — routing and stats unavailable. Make sure the server is running.
          </p>
        </div>
      )}
      {toast && (
        <span className="fixed top-4 right-4 z-50 bg-surface border border-line text-primary text-xs font-mono px-4 py-2 rounded-full shadow-lg">{toast}</span>
      )}
      <Header
        isDark={isDark}
        toggleTheme={toggle}
        onOpenSettings={() => setShowSettings(true)}
        onOpenCmd={() => setCmdOpen(true)}
        byomActive={byomActive}
        user={user}
      />
      <div key={location.pathname} className="animate-[page-fade-in_0.25s_ease-out]">
        <Suspense fallback={<PageSkeleton type={PAGE_SKELETONS[location.pathname]} />}>
          <Routes location={location}>
            <Route path="/" element={<HomePage configVersion={configVersion} backendOnline={backendOnline} />} />
            <Route path="/pricing" element={<PricingRoute onNavigate={handleNavigate} />} />
            <Route path="/about" element={<AboutPage />} />
            <Route path="/auth" element={<AuthPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/playground" element={
              <div className="max-w-3xl mx-auto px-6 py-20">
                <p className="font-mono text-xs text-signal tracking-wide uppercase mb-4">API Playground</p>
                <h1 className="font-display text-3xl font-semibold mb-2">Playground</h1>
                <p className="text-muted text-sm mb-8">Test your router with live queries. Try different tiers, streaming, and see code snippets.</p>
                <ApiPlayground />
              </div>
            } />
            <Route path="/guide" element={<GuidePage />} />
          </Routes>
        </Suspense>
      </div>
      <Footer />
      <CommandPalette
        open={cmdOpen}
        onClose={() => setCmdOpen(false)}
        onAction={(action) => {
          if (action === 'theme') toggle()
          if (action === 'settings') setShowSettings(true)
        }}
      />
      {showSettings && (
        <SettingsPanel
          onClose={() => setShowSettings(false)}
          onSaved={handleConfigSaved}
        />
      )}
    </div>
  )
}
