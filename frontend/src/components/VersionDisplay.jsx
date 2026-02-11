import React from 'react';
import '../styles/VersionDisplay.css';

export function VersionDisplay() {
  // Get environment variables from Vite
  const version = import.meta.env.VITE_APP_VERSION;
  const devMode = import.meta.env.VITE_APP_DEV_MODE === 'true';
  const aiEnabled = import.meta.env.VITE_APP_AI_ENABLED === 'true';

  // Determine display text
  const versionText = devMode ? 'Dev Mode' : `v${version || '1.0.0'}`;
  const aiText = aiEnabled ? ' AI Enabled' : '';

  return (
    <div className="version-display">
      <span className="version-text">{versionText}</span>
      {aiText && <span className="ai-badge">{aiText}</span>}
    </div>
  );
}
