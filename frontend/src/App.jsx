import { QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { queryClient } from './data/client';
import { WebSocketProvider } from './contexts/WebSocketContext';
import { SelectModeProvider } from './contexts/SelectModeContext';
import { SessionsProvider } from './contexts/SessionsContext';
import { SystemHealthProvider } from './contexts/SystemHealthContext';
import { MainLayout } from './layouts/MainLayout';
import { PipelineView } from './views/PipelineView';
import { KioskView } from './views/KioskView';
import './App.css';

/**
 * Main App with React Router
 * 
 * Routes:
 * - /        -> Main Pipeline View (dashboard)
 * - /kiosk   -> Kiosk Video Playback View
 */
function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <WebSocketProvider>
        <BrowserRouter>
          <Routes>
            {/* Main dashboard with all providers and layout */}
            <Route path="/" element={
              <SelectModeProvider>
                <SessionsProvider>
                  <SystemHealthProvider>
                    <MainLayout>
                      <PipelineView />
                    </MainLayout>
                  </SystemHealthProvider>
                </SessionsProvider>
              </SelectModeProvider>
            } />

            {/* Kiosk view - minimal providers, fullscreen optimized */}
            <Route path="/kiosk" element={<KioskView />} />

            {/* Fallback redirect */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </WebSocketProvider>
    </QueryClientProvider>
  );
}

export default App;
