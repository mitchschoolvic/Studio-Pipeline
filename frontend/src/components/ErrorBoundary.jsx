import React from 'react';

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // You could integrate with logging service here
    console.error('ErrorBoundary caught error:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-6 bg-red-50 border border-red-300 rounded-md">
          <h2 className="text-red-700 font-semibold mb-2">Analytics crashed</h2>
          <p className="text-sm text-red-600 mb-4">{this.state.error?.message || 'Unknown error'}.</p>
          <button
            className="px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white text-sm rounded"
            onClick={() => this.setState({ hasError: false, error: null })}
          >
            Retry Render
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
