import React, { useState } from 'react';
import { AlertTriangle, Database, RefreshCw, Power, Trash2, CheckCircle } from 'lucide-react';

const MaintenanceModal = ({ isOpen, issues, onResolved }) => {
    if (!isOpen) return null;

    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [successMessage, setSuccessMessage] = useState(null);

    const handleMigrate = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await fetch('/api/maintenance/migrate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await response.json();

            if (data.success) {
                setSuccessMessage(data.message);
                setTimeout(() => {
                    // Reload page to restart app logic (or trigger onResolved if we want to hot-reload)
                    window.location.reload();
                }, 2000);
            } else {
                setError(data.message);
            }
        } catch (err) {
            setError(err.message || "Migration failed");
        } finally {
            setLoading(false);
        }
    };

    const handleReset = async () => {
        if (!confirm("Are you sure you want to DELETE ALL DATA? This cannot be undone.")) return;

        setLoading(true);
        setError(null);
        try {
            const response = await fetch('/api/maintenance/reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await response.json();

            if (data.success) {
                setSuccessMessage(data.message);
                setTimeout(() => {
                    window.location.reload();
                }, 2000);
            } else {
                setError(data.message);
            }
        } catch (err) {
            setError(err.message || "Reset failed");
        } finally {
            setLoading(false);
        }
    };

    const handleQuit = async () => {
        try {
            await fetch('/api/maintenance/quit', { method: 'POST' });
            window.close(); // Try to close window
        } catch (err) {
            console.error("Quit failed", err);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-gray-900 border border-red-500/30 rounded-xl shadow-2xl max-w-lg w-full overflow-hidden">

                {/* Header */}
                <div className="p-6 border-b border-gray-800 flex items-center gap-4 bg-red-500/10">
                    <div className="p-3 bg-red-500/20 rounded-full">
                        <AlertTriangle className="w-8 h-8 text-red-500" />
                    </div>
                    <div>
                        <h2 className="text-xl font-bold text-white">Database Version Mismatch</h2>
                        <p className="text-red-400 text-sm">Action Required</p>
                    </div>
                </div>

                {/* Content */}
                <div className="p-6 space-y-6">
                    <p className="text-gray-300">
                        The application has detected that your database schema is outdated.
                        This usually happens after an update. To continue, you must update the database.
                    </p>

                    {issues && issues.length > 0 && (
                        <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
                            <h3 className="text-sm font-medium text-gray-400 mb-2">Detected Issues:</h3>
                            <ul className="space-y-1">
                                {issues.map((issue, idx) => (
                                    <li key={idx} className="text-sm text-red-300 flex items-start gap-2">
                                        <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" />
                                        {issue}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {error && (
                        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 text-red-400 text-sm">
                            {error}
                        </div>
                    )}

                    {successMessage && (
                        <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-4 text-green-400 text-sm flex items-center gap-2">
                            <CheckCircle className="w-4 h-4" />
                            {successMessage}
                        </div>
                    )}
                </div>

                {/* Actions */}
                <div className="p-6 border-t border-gray-800 bg-gray-900/50 flex flex-col gap-3">

                    <button
                        onClick={handleMigrate}
                        disabled={loading || successMessage}
                        className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {loading ? <RefreshCw className="w-5 h-5 animate-spin" /> : <Database className="w-5 h-5" />}
                        Migrate Database (Recommended)
                    </button>

                    <div className="grid grid-cols-2 gap-3">
                        <button
                            onClick={handleReset}
                            disabled={loading || successMessage}
                            className="py-3 px-4 bg-red-900/30 hover:bg-red-900/50 text-red-400 border border-red-900/50 rounded-lg font-medium transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <Trash2 className="w-4 h-4" />
                            Reset Database
                        </button>

                        <button
                            onClick={handleQuit}
                            disabled={loading || successMessage}
                            className="py-3 px-4 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg font-medium transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <Power className="w-4 h-4" />
                            Quit
                        </button>
                    </div>
                </div>

            </div>
        </div>
    );
};

export default MaintenanceModal;
