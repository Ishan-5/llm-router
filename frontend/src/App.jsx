import { useState } from 'react'
import Header from './components/Header'
import RoutingDiagram from './components/RoutingDiagram'
import HowItWorks from './components/HowItWorks'
import MetricsDashboard from './components/MetricsDashboard'
import Footer from './components/Footer'
import SettingsPanel from './components/SettingsPanel'
import { useTheme } from './useTheme'

export default function App() {
  const { isDark, toggle } = useTheme()
  const [showSettings, setShowSettings] = useState(false)
  const [configVersion, setConfigVersion] = useState(0)

  function handleConfigSaved() {
    setConfigVersion((v) => v + 1)  // triggers RoutingDiagram to re-fetch config
    setShowSettings(false)
  }

  return (
    <div className="min-h-screen bg-base font-body">
      <Header isDark={isDark} toggleTheme={toggle} onOpenSettings={() => setShowSettings(true)} />
      <RoutingDiagram configVersion={configVersion} />
      <HowItWorks />
      <MetricsDashboard isDark={isDark} />
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
