import { useState } from 'react';
import { ChevronDown, ChevronRight, Settings, Search } from 'lucide-react';
import { FTPDiagnosticModal } from './FTPDiagnosticModal';

/**
 * FTP Connection Status Panel
 *
 * Displays FTP connection status in a collapsible panel:
 * - Collapsed: Shows status dot (green/orange/red) and connection state
 * - Expanded: Shows detailed info including error messages, IP, port, and settings button
 */
export function FTPStatusPanel({
  connectionState = 'disconnected', // 'connected' | 'connecting' | 'disconnected'
  host = '',
  port = 21,
  errorMessage = '',
  onOpenSettings
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showDiagnostic, setShowDiagnostic] = useState(false);

  // Determine status display properties
  const getStatusProps = () => {
    switch (connectionState) {
      case 'connected':
        return {
          color: 'bg-green-500',
          label: 'FTP Connected',
          textColor: 'text-green-700',
          bgColor: 'bg-green-50',
          borderColor: 'border-green-200'
        };
      case 'connecting':
        return {
          color: 'bg-orange-500 animate-pulse',
          label: 'FTP Connecting',
          textColor: 'text-orange-700',
          bgColor: 'bg-orange-50',
          borderColor: 'border-orange-200'
        };
      case 'disconnected':
      default:
        return {
          color: 'bg-red-500',
          label: 'FTP Disconnected',
          textColor: 'text-red-700',
          bgColor: 'bg-red-50',
          borderColor: 'border-red-200'
        };
    }
  };

  const statusProps = getStatusProps();

  return (
    <div className={`border ${statusProps.borderColor} rounded-lg ${statusProps.bgColor} overflow-hidden mb-3`}>
      {/* Collapsed Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2 px-3 py-2 hover:opacity-80 transition-opacity"
      >
        {isExpanded ? (
          <ChevronDown className="w-3 h-3 text-gray-600" />
        ) : (
          <ChevronRight className="w-3 h-3 text-gray-600" />
        )}
        <div className={`w-2 h-2 rounded-full ${statusProps.color}`} />
        <span className={`text-xs font-medium ${statusProps.textColor}`}>
          {statusProps.label}
        </span>
      </button>

      {/* Expanded Details */}
      {isExpanded && (
        <div className="px-3 pb-3 space-y-2 border-t border-gray-200 pt-2">
          {/* Connection Details */}
          {host && (
            <div className="text-xs">
              <div className="text-gray-600 font-medium">Server:</div>
              <div className={`${statusProps.textColor} font-mono`}>
                {host}:{port}
              </div>
            </div>
          )}

          {/* Error Message */}
          {errorMessage && connectionState === 'disconnected' && (
            <div className="text-xs">
              <div className="text-gray-600 font-medium">Error:</div>
              <div className="text-red-600 break-words">
                {errorMessage}
              </div>
            </div>
          )}

          {/* Settings Button */}
          <button
            onClick={(e) => {
              e.stopPropagation();
              onOpenSettings();
            }}
            className="w-full flex items-center justify-center gap-2 px-3 py-1.5 bg-white hover:bg-gray-100 border border-gray-300 rounded text-xs font-medium transition-colors text-gray-700"
          >
            <Settings className="w-3 h-3" />
            FTP Settings
          </button>

          {/* Diagnose Button - Only show when connected */}
          {connectionState === 'connected' && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowDiagnostic(true);
              }}
              className="w-full flex items-center justify-center gap-2 px-3 py-1.5 bg-blue-50 hover:bg-blue-100 border border-blue-200 rounded text-xs font-medium transition-colors text-blue-700"
            >
              <Search className="w-3 h-3" />
              Diagnose Discovery
            </button>
          )}
        </div>
      )}

      {/* Diagnostic Modal */}
      <FTPDiagnosticModal 
        isOpen={showDiagnostic} 
        onClose={() => setShowDiagnostic(false)} 
      />
    </div>
  );
}
