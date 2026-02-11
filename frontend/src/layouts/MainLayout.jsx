import React, { useState } from 'react';
import { Settings, HelpCircle, RefreshCw, Activity } from 'lucide-react';
import { SettingsDialog } from '../components/SettingsDialog';
import { DocsDialog } from '../components/DocsDialog';
import { VersionDisplay } from '../components/VersionDisplay';
import { WorkerStatus } from '../components/WorkerStatus';



export function MainLayout({ children }) {
    const [showSettings, setShowSettings] = useState(false);
    const [showDocs, setShowDocs] = useState(false);
    const [workerStatusVisible, setWorkerStatusVisible] = useState(false);



    const toggleWorkerStatus = () => setWorkerStatusVisible(!workerStatusVisible);

    return (
        <div className="flex flex-col h-screen bg-gray-50">
            {/* Header */}
            <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between shadow-sm z-10">
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center shadow-sm">
                        <RefreshCw className="w-5 h-5 text-white" />
                    </div>
                    <h1 className="text-xl font-bold text-gray-800 tracking-tight">
                        Studio Pipeline
                    </h1>
                    <VersionDisplay />
                </div>

                <div className="flex items-center gap-3">


                    <div className="h-6 w-px bg-gray-200 mx-1"></div>

                    <button
                        onClick={toggleWorkerStatus}
                        className={`p-2 rounded-lg transition-colors ${workerStatusVisible ? 'text-blue-600 bg-blue-50' : 'text-gray-500 hover:text-blue-600 hover:bg-blue-50'}`}
                        title="Worker Status"
                    >
                        <Activity className="w-5 h-5" />
                    </button>

                    <button
                        onClick={() => setShowDocs(true)}
                        className="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                        title="Documentation"
                    >
                        <HelpCircle className="w-5 h-5" />
                    </button>

                    <button
                        onClick={() => setShowSettings(true)}
                        className="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                        title="Settings"
                    >
                        <Settings className="w-5 h-5" />
                    </button>
                </div>
            </header>



            {/* Main Layout Body */}
            <div className="flex flex-1 overflow-hidden">
                {/* Main Content */}
                <main className="flex-1 overflow-hidden relative">
                    {React.Children.map(children, child => {
                        if (React.isValidElement(child)) {
                            return React.cloneElement(child, {
                                onOpenSettings: () => setShowSettings(true)
                            });
                        }
                        return child;
                    })}
                </main>
            </div>

            {/* Worker Status Widget */}
            <WorkerStatus
                isVisible={workerStatusVisible}
                onToggleVisibility={toggleWorkerStatus}
            />

            {/* Dialogs */}
            <SettingsDialog
                isOpen={showSettings}
                onClose={() => setShowSettings(false)}
            />

            <DocsDialog
                isOpen={showDocs}
                onClose={() => setShowDocs(false)}
            />
        </div>
    );
}
