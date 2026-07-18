import { Component } from 'react'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-base font-body flex items-center justify-center px-6">
          <div className="max-w-md text-center">
            <div className="w-3 h-3 rounded-full bg-danger mx-auto mb-6" />
            <h1 className="font-display text-2xl font-semibold mb-3">Something went wrong</h1>
            <p className="text-sm text-muted mb-6">
              The app hit an unexpected error. Try refreshing the page.
            </p>
            <button
              onClick={() => window.location.reload()}
              className="bg-signal text-white font-semibold text-sm px-6 py-3 rounded-lg hover:brightness-110 transition"
            >
              Reload page
            </button>
            {this.state.error && (
              <pre className="mt-6 text-[10px] font-mono text-danger text-left bg-panel border border-line rounded-lg p-4 overflow-x-auto">
                {this.state.error.message}
              </pre>
            )}
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
