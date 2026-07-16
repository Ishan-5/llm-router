import { useState, useEffect } from 'react'
import { supabase } from './supabase'
import Header from './components/Header'
import RoutingDiagram from './components/RoutingDiagram'
import HowItWorks from './components/HowItWorks'
import MetricsDashboard from './components/MetricsDashboard'
import PricingTable from './components/PricingTable'
import AboutPage from './components/AboutPage'
import AuthPage from './components/AuthPage'
import DashboardPage from './components/DashboardPage'
import Footer from './components/Footer'
import SettingsPanel from './components/SettingsPanel'
import { useTheme } from './useTheme'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'

export default function App() {
  const { isDark, toggle } = useTheme()
  const [page, setPage] = useState('home')
  const [user, setUser] = useState(null)
  const [toast, setToast] = useState(null)

  function showToast(msg) {
    setToast(msg)
    setTimeout(() => setToast(null), 3000)
  }

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => setUser(session?.user ?? null))
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      setUser(session?.user ?? null)
      if (event === 'SIGNED_IN') { showToast('Signed in'); setPage('home') }
      if (event === 'SIGNED_OUT') { showToast('Signed out'); setPage('home') }
    })
    return () => subscription.unsubscribe()
  }, [])

  function navigate(p) {
    setPage(p)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
  const [showSettings, setShowSettings] = useState(false)
  const [configVersion, setConfigVersion] = useState(0)
  const [backendOnline, setBackendOnline] = useState(true)
  const [byomActive, setByomActive] = useState(() => {
    try { return Object.keys(JSON.parse(localStorage.getItem('byom_config') || '{}')).length > 0 }
    catch { return false }
  })

  useEffect(() => {
    function checkHealth() {
      fetch(`${API_BASE}/health`)
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
      <Header isDark={isDark} toggleTheme={toggle} onOpenSettings={() => setShowSettings(true)} byomActive={byomActive} onNavigate={navigate} page={page} user={user} />
      {page === 'pricing' ? (
        <PricingTable onBack={() => navigate('home')} />
      ) : page === 'about' ? (
        <AboutPage />
      ) : page === 'auth' ? (
        <AuthPage />
      ) : page === 'dashboard' ? (
        <DashboardPage />
      ) : (
        <>
          <RoutingDiagram configVersion={configVersion} backendOnline={backendOnline} />
          <HowItWorks />
          <MetricsDashboard isDark={isDark} backendOnline={backendOnline} />
        </>
      )}
      <Footer />
      {showSettings && (
        <SettingsPanel
          onClose={() => setShowSettings(false)}
          onSaved={handleConfigSaved}
        />
      )}
    </div>
  )
}
