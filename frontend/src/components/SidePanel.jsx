import React from 'react';
import { Play, Pause, Activity } from 'lucide-react';
import { FTPStatusPanel } from './FTPStatusPanel';
import { LocalPathStatusPanel } from './LocalPathStatusPanel';

export function SidePanel({
    isPipelinePaused,
    onTogglePipelinePause,
    isAnalyticsPaused,
    onToggleAnalyticsPause,
    aiEnabled = false,
    queuedCount,
    runningJobId,
    runWhenIdle,

    onToggleRunWhenIdle,
    analyticsStartHour,
    analyticsEndHour,
    onUpdateAnalyticsSchedule,
    analyticsScheduleEnabled,
    onToggleAnalyticsSchedule,
    validationStatus,
    ftpConnectionState,
    ftpHost,
    ftpPort,
    ftpErrorMessage,
    onOpenSettings
}) {
    // Calculate blocking errors
    const ftpError = ftpConnectionState !== 'connected';

    // Check path errors (Temp, Output, and External Audio if configured)
    const tempPathValid = validationStatus?.temp_path?.valid ?? true;
    const outputPathValid = validationStatus?.output_path?.valid ?? true;

    const externalAudioStatus = validationStatus?.external_audio_path;
    const externalAudioConfigured = externalAudioStatus && externalAudioStatus.message !== "Not configured (optional)";
    const externalAudioValid = !externalAudioConfigured || externalAudioStatus?.valid;

    const pathError = !tempPathValid || !outputPathValid || !externalAudioValid;

    const getBlockingError = () => {
        if (ftpError) return "Waiting on FTP";
        if (pathError) return "Waiting on local paths";
        return null;
    };

    const blockingError = getBlockingError();
    const isBlocked = !!blockingError;
    return (
        <div className="w-64 bg-white border-r border-gray-200 flex flex-col h-full shrink-0">
            {/* Pipeline Controls Section */}
            <div className="p-4 border-b border-gray-100">
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                    Pipeline Control
                </h3>
                <button
                    onClick={() => {
                        if (isPipelinePaused && isBlocked) return;
                        onTogglePipelinePause();
                    }}
                    disabled={isPipelinePaused && isBlocked}
                    className={`w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg font-medium transition-all ${isPipelinePaused
                        ? isBlocked
                            ? 'bg-gray-100 text-gray-400 border border-gray-200 cursor-not-allowed'
                            : 'bg-orange-50 text-orange-700 border border-orange-200 hover:bg-orange-100'
                        : 'bg-blue-50 text-blue-700 border border-blue-200 hover:bg-blue-100'
                        }`}
                >
                    {isPipelinePaused ? (
                        <>
                            <Play className="w-5 h-5" />
                            Resume Pipeline
                        </>
                    ) : (
                        <>
                            <Pause className="w-5 h-5" />
                            Pause Pipeline
                        </>
                    )}
                </button>
                <div className="mt-2 text-center">
                    <span className={`text-xs font-medium ${isPipelinePaused
                        ? isBlocked ? 'text-red-500' : 'text-orange-600'
                        : 'text-blue-600'
                        }`}>
                        {isPipelinePaused
                            ? (blockingError || 'Pipeline is Paused')
                            : 'Pipeline is Active'}
                    </span>
                </div>
            </div>

            {/* Analytics Controls Section - Only show when AI is enabled */}
            {aiEnabled && (
            <div className="p-4 border-b border-gray-100">
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                    Analytics Engine
                </h3>

                <button
                    onClick={() => {
                        if (isAnalyticsPaused && isBlocked) return;
                        onToggleAnalyticsPause();
                    }}
                    disabled={isAnalyticsPaused && isBlocked}
                    className={`w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg font-medium transition-all mb-4 ${isAnalyticsPaused && isBlocked
                        ? 'bg-gray-100 text-gray-400 border border-gray-200 cursor-not-allowed'
                        : analyticsPausedStyle(isAnalyticsPaused)
                        }`}
                >
                    {isAnalyticsPaused ? (
                        <>
                            <Play className="w-5 h-5" />
                            Resume Analytics
                        </>
                    ) : (
                        <>
                            <Pause className="w-5 h-5" />
                            Pause Analytics
                        </>
                    )}
                </button>

                {isAnalyticsPaused && isBlocked && (
                    <div className="mb-4 text-center">
                        <span className="text-xs font-medium text-red-500">
                            {blockingError}
                        </span>
                    </div>
                )}

                <div className="space-y-3 bg-gray-50 rounded-lg p-3 border border-gray-100">
                    <div className="flex items-center justify-between text-sm">
                        <span className="text-gray-600">Status</span>
                        <span className={`font-medium ${isAnalyticsPaused ? 'text-orange-600' : 'text-green-600'}`}>
                            {isAnalyticsPaused ? 'Paused' : 'Running'}
                        </span>
                    </div>

                    <div className="flex items-center justify-between text-sm">
                        <span className="text-gray-600">Queued Jobs</span>
                        <span className="font-medium text-gray-900">{queuedCount}</span>
                    </div>

                    {runningJobId && (
                        <div className="flex items-center gap-2 text-xs text-blue-600 bg-blue-50 p-2 rounded">
                            <Activity className="w-3 h-3 animate-pulse" />
                            <span>Processing job...</span>
                        </div>
                    )}
                </div>

                <div className="mt-4 space-y-3">
                    <label className="flex items-start gap-3 cursor-pointer group">
                        <div className="relative flex items-center mt-0.5">
                            <input
                                type="checkbox"
                                checked={runWhenIdle}
                                onChange={onToggleRunWhenIdle}
                                className="peer h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                            />
                        </div>
                        <div className="text-sm">
                            <span className="font-medium text-gray-700 group-hover:text-gray-900">Only run Analytics when Pipeline is idle</span>
                            <p className="text-xs text-gray-500 mt-0.5">Pauses analytics if pipeline is active</p>
                        </div>
                    </label>

                    <div className="pt-2 border-t border-gray-100">
                        <label className="flex items-start gap-3 cursor-pointer group mb-3">
                            <div className="relative flex items-center mt-0.5">
                                <input
                                    type="checkbox"
                                    checked={analyticsScheduleEnabled}
                                    onChange={onToggleAnalyticsSchedule}
                                    className="peer h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                                />
                            </div>
                            <div className="text-sm">
                                <span className="font-medium text-gray-700 group-hover:text-gray-900">Only run Analytics during these hours</span>
                            </div>
                        </label>

                        <div className={`transition-opacity duration-200 ${!analyticsScheduleEnabled ? 'opacity-50 pointer-events-none' : ''}`}>
                            <label className="block text-xs font-semibold text-gray-900 mb-2 uppercase tracking-wide">
                                Scheduled Hours (24h)
                            </label>
                            <div className="flex items-center gap-2">
                                <div className="flex-1">
                                    <label className="text-xs text-gray-900 mb-1 block">Start</label>
                                    <select
                                        value={analyticsStartHour}
                                        onChange={(e) => onUpdateAnalyticsSchedule(parseInt(e.target.value), analyticsEndHour)}
                                        disabled={!analyticsScheduleEnabled}
                                        className="w-full text-sm border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
                                    >
                                        {Array.from({ length: 24 }, (_, i) => (
                                            <option key={i} value={i} className="text-gray-900">{i}:00</option>
                                        ))}
                                    </select>
                                </div>
                                <span className="text-gray-900 mt-5">to</span>
                                <div className="flex-1">
                                    <label className="text-xs text-gray-900 mb-1 block">End</label>
                                    <select
                                        value={analyticsEndHour}
                                        onChange={(e) => onUpdateAnalyticsSchedule(analyticsStartHour, parseInt(e.target.value))}
                                        disabled={!analyticsScheduleEnabled}
                                        className="w-full text-sm border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
                                    >
                                        {Array.from({ length: 24 }, (_, i) => (
                                            <option key={i} value={i} className="text-gray-900">{i}:00</option>
                                        ))}
                                    </select>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            )}

            {/* System Status Section */}
            <div className="p-4 mt-auto bg-gray-50 border-t border-gray-200">
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                    System Status
                </h3>

                <FTPStatusPanel
                    connectionState={ftpConnectionState}
                    host={ftpHost}
                    port={ftpPort}
                    errorMessage={ftpErrorMessage}
                    onOpenSettings={onOpenSettings}
                />

                <LocalPathStatusPanel
                    validationStatus={validationStatus}
                    onOpenSettings={onOpenSettings}
                />
            </div>
        </div>
    );
}

function analyticsPausedStyle(isPaused) {
    return isPaused
        ? 'bg-orange-50 text-orange-700 border border-orange-200 hover:bg-orange-100'
        : 'bg-green-50 text-green-700 border border-green-200 hover:bg-green-100';
}
