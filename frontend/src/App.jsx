import { useState, useEffect } from 'react'
import Header from './components/Header'
import RoutingDiagram from './components/RoutingDiagram'
import HowItWorks from './components/HowItWorks'
import MetricsDashboard from './components/MetricsDashboard'
import PricingTable from './components/PricingTable'
import Footer from './components/Footer'
import SettingsPanel from './components/SettingsPanel'
import { useTheme } from './useTheme'
import AboutPage from './components/AboutPage'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'

export default function App() {
  const { isDark, toggle } = useTheme()
  const [page, setPage] = useState('home')

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
      <Header isDark={isDark} toggleTheme={toggle} onOpenSettings={() => setShowSettings(true)} byomActive={byomActive} onNavigate={navigate} page={page} />
      {page === 'pricing' ? (
        <PricingTable onBack={() => navigate('home')} />
      ) : page === 'about' ? (
        <AboutPage />
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
