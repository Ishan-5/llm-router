import Header from './components/Header'
import RoutingDiagram from './components/RoutingDiagram'
import HowItWorks from './components/HowItWorks'
import MetricsDashboard from './components/MetricsDashboard'
import Footer from './components/Footer'
import { useTheme } from './useTheme'

export default function App() {
  const { isDark, toggle } = useTheme()

  return (
    <div className="min-h-screen bg-base font-body">
      <Header isDark={isDark} toggleTheme={toggle} />
      <RoutingDiagram />
      <HowItWorks />
      <MetricsDashboard isDark={isDark} />
      <Footer />
    </div>
  )
}
