import { useState, useEffect } from 'react';
import { Wifi, CheckCircle, AlertCircle, Loader2, RefreshCw } from 'lucide-react';

/**
 * Network Settings Tab - Configure which network interfaces the server listens on
 */
export function NetworkSettingsTab({ localSettings, handleAutoSave, showStatus }) {
  const [interfaces, setInterfaces] = useState([]);
  const [networkStatus, setNetworkStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedHost, setSelectedHost] = useState(localSettings.server_host || '0.0.0.0');
  const [saving, setSaving] = useState(false);

  // Fetch network interfaces and status on mount
  useEffect(() => {
    fetchNetworkData();
  }, []);

  // Sync selectedHost when localSettings changes
  useEffect(() => {
    if (localSettings.server_host) {
      setSelectedHost(localSettings.server_host);
    }
  }, [localSettings.server_host]);

  const fetchNetworkData = async () => {
    setLoading(true);
    try {
      const [ifacesRes, statusRes] = await Promise.all([
        fetch('/api/network/interfaces').then(r => r.json()),
        fetch('/api/network/status').then(r => r.json())
      ]);
      setInterfaces(ifacesRes.interfaces || []);
      setNetworkStatus(statusRes);
      // Use the current setting from the server if we don't have a local value
      if (statusRes.current_host && !localSettings.server_host) {
        setSelectedHost(statusRes.current_host);
      }
    } catch (err) {
      console.error('Failed to fetch network info:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveInterface = async () => {
    setSaving(true);
    try {
      const res = await fetch('/api/settings/server_host', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: 'server_host', value: selectedHost })
      });
      if (res.ok) {
        showStatus('Network interface saved. Restart the server to apply changes.', 'success');
        // Refresh status
        fetchNetworkData();
      } else {
        showStatus('Failed to save network setting', 'error');
      }
    } catch (err) {
      showStatus('Failed to save network setting', 'error');
    } finally {
      setSaving(false);
    }
  };

  const getInterfaceLabel = (address) => {
    if (address === '0.0.0.0') return 'All Interfaces';
    if (address === '127.0.0.1') return 'Localhost Only';
    return address;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <Wifi className="w-5 h-5 text-blue-600" />
        <h3 className="text-lg font-semibold text-gray-800">Network Settings</h3>
      </div>

      {/* Current Status Banner */}
      {networkStatus && (
        <div className={`mb-4 rounded-lg p-4 border ${
          networkStatus.current_host === '0.0.0.0'
            ? 'bg-green-50 border-green-200'
            : networkStatus.current_host === '127.0.0.1'
              ? 'bg-amber-50 border-amber-200'
              : 'bg-blue-50 border-blue-200'
        }`}>
          <div className="flex items-center gap-3">
            {networkStatus.current_host === '0.0.0.0' ? (
              <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0" />
            ) : (
              <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0" />
            )}
            <div>
              <div className={`font-medium ${
                networkStatus.current_host === '0.0.0.0' ? 'text-green-800' : 'text-amber-800'
              }`}>
                {networkStatus.current_host === '0.0.0.0'
                  ? 'Accessible on all network interfaces'
                  : networkStatus.current_host === '127.0.0.1'
                    ? 'Only accessible from this machine'
                    : `Bound to ${networkStatus.current_host}`}
              </div>
              <div className="text-sm text-gray-600 mt-1">
                Hostname: <span className="font-mono text-xs">{networkStatus.hostname}</span>
                {' · '}
                Port: <span className="font-mono text-xs">{networkStatus.port}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Access URLs */}
      {networkStatus && networkStatus.all_ips && networkStatus.all_ips.length > 0 && (
        <div className="mb-4 bg-gray-50 p-4 rounded-lg">
          <div className="text-sm font-semibold text-gray-700 mb-3">Access URLs</div>
          <div className="space-y-2">
            {networkStatus.all_ips
              .filter(ip => ip !== '127.0.0.1')
              .map(ip => (
                <div key={ip} className="flex items-center justify-between bg-white border border-gray-200 rounded p-2">
                  <span className="text-sm font-mono text-gray-800">
                    http://{ip}:{networkStatus.port}
                  </span>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(`http://${ip}:${networkStatus.port}`);
                      showStatus('URL copied to clipboard', 'success');
                    }}
                    className="text-xs text-blue-600 hover:text-blue-800 font-medium px-2 py-1 rounded hover:bg-blue-50 transition-colors"
                  >
                    Copy
                  </button>
                </div>
              ))}
            <div className="flex items-center justify-between bg-white border border-gray-200 rounded p-2">
              <span className="text-sm font-mono text-gray-800">
                http://127.0.0.1:{networkStatus.port}
              </span>
              <span className="text-xs text-gray-400 px-2 py-1">localhost</span>
            </div>
          </div>
        </div>
      )}

      {/* Interface Selection */}
      <div className="space-y-4 bg-gray-50 p-4 rounded-lg">
        <div className="text-sm font-semibold text-gray-700 mb-2">Listen Interface</div>
        <p className="text-xs text-gray-500 mb-3">
          Select which network interface the server should listen on. Changes require a server restart to take effect.
        </p>

        <div className="space-y-2">
          {interfaces.map((iface) => (
            <label
              key={iface.address}
              className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                selectedHost === iface.address
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 bg-white hover:border-gray-300'
              }`}
            >
              <input
                type="radio"
                name="server_host"
                value={iface.address}
                checked={selectedHost === iface.address}
                onChange={() => setSelectedHost(iface.address)}
                className="mt-0.5 w-4 h-4 text-blue-600 border-gray-300 focus:ring-blue-500"
              />
              <div className="flex-1">
                <div className="text-sm font-medium text-gray-800">{iface.name}</div>
                <div className="text-xs text-gray-500 mt-0.5">{iface.description}</div>
                <div className="text-xs font-mono text-gray-400 mt-0.5">{iface.address}</div>
              </div>
              {iface.address === '0.0.0.0' && (
                <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">
                  Recommended
                </span>
              )}
            </label>
          ))}
        </div>

        {/* Save Button */}
        <div className="flex items-center gap-3 pt-2">
          <button
            onClick={handleSaveInterface}
            disabled={saving || selectedHost === networkStatus?.current_host}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white rounded text-sm font-medium flex items-center gap-2 transition-colors"
          >
            {saving ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Saving...
              </>
            ) : (
              'Save & Restart Required'
            )}
          </button>
          <button
            onClick={fetchNetworkData}
            className="px-3 py-2 text-gray-600 hover:text-gray-800 hover:bg-gray-200 rounded text-sm flex items-center gap-1 transition-colors"
            title="Refresh network interfaces"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        {selectedHost !== networkStatus?.current_host && (
          <div className="mt-2 p-3 bg-amber-50 border border-amber-200 rounded text-sm text-amber-700">
            <div className="font-medium mb-1">⚠️ Restart Required</div>
            <div className="text-xs">
              After saving, you must restart the server for the new network interface to take effect.
              The current session will continue using the existing binding until restart.
            </div>
          </div>
        )}
      </div>

      {/* Help Info */}
      <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded text-sm text-blue-700">
        <div className="font-medium mb-1">💡 Network Access Tips</div>
        <div className="text-xs space-y-1">
          <p>• <strong>All Interfaces (0.0.0.0)</strong> — Accessible from any device on your network</p>
          <p>• <strong>Localhost (127.0.0.1)</strong> — Only accessible from this computer</p>
          <p>• <strong>Specific IP</strong> — Only accessible via that specific network interface</p>
          <p>• Other devices can access this app using your computer's IP address and port {networkStatus?.port || 8888}</p>
        </div>
      </div>
    </div>
  );
}
