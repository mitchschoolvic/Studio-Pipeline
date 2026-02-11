import { useState } from 'react';
import { ChevronDown, ChevronRight, FolderOpen } from 'lucide-react';

/**
 * Local Path Status Panel
 *
 * Displays validation status for local paths (Temp and Output)
 */
export function LocalPathStatusPanel({ validationStatus, onOpenSettings }) {
    const [isExpanded, setIsExpanded] = useState(false);

    const tempPathValid = validationStatus?.temp_path?.valid ?? true;
    const outputPathValid = validationStatus?.output_path?.valid ?? true;

    // Check external audio path (AI Analytics Cache)
    // It's considered valid if it's missing (optional) OR if it's present and valid
    // We only want to flag it as invalid if it's explicitly configured but invalid
    const externalAudioStatus = validationStatus?.external_audio_path;
    const externalAudioConfigured = externalAudioStatus && externalAudioStatus.message !== "Not configured (optional)";
    const externalAudioValid = !externalAudioConfigured || externalAudioStatus?.valid;

    const allValid = tempPathValid && outputPathValid && externalAudioValid;

    const getStatusProps = () => {
        if (allValid) {
            return {
                color: 'bg-green-500',
                label: 'Local Paths OK',
                textColor: 'text-green-700',
                bgColor: 'bg-green-50',
                borderColor: 'border-green-200'
            };
        } else {
            return {
                color: 'bg-red-500',
                label: 'Path Config Issues',
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
                    {/* Temp Path Status */}
                    <div className="text-xs">
                        <div className="flex items-center justify-between mb-1">
                            <span className="text-gray-600 font-medium">Temp Path:</span>
                            <span className={tempPathValid ? 'text-green-600' : 'text-red-600'}>
                                {tempPathValid ? 'Valid' : 'Invalid'}
                            </span>
                        </div>
                        {!tempPathValid && validationStatus?.temp_path?.message && (
                            <div className="text-red-600 break-words mb-2">
                                {validationStatus.temp_path.message}
                            </div>
                        )}
                    </div>

                    {/* Output Path Status */}
                    <div className="text-xs">
                        <div className="flex items-center justify-between mb-1">
                            <span className="text-gray-600 font-medium">Output Path:</span>
                            <span className={outputPathValid ? 'text-green-600' : 'text-red-600'}>
                                {outputPathValid ? 'Valid' : 'Invalid'}
                            </span>
                        </div>
                        {!outputPathValid && validationStatus?.output_path?.message && (
                            <div className="text-red-600 break-words mb-2">
                                {validationStatus.output_path.message}
                            </div>
                        )}
                    </div>

                    {/* AI Analytics Cache Status */}
                    {externalAudioConfigured && (
                        <div className="text-xs">
                            <div className="flex items-center justify-between mb-1">
                                <span className="text-gray-600 font-medium">AI Analytics Cache:</span>
                                <span className={externalAudioValid ? 'text-green-600' : 'text-red-600'}>
                                    {externalAudioValid ? 'Valid' : 'Invalid'}
                                </span>
                            </div>
                            {!externalAudioValid && externalAudioStatus?.message && (
                                <div className="text-red-600 break-words mb-2">
                                    {externalAudioStatus.message}
                                </div>
                            )}
                        </div>
                    )}

                    {/* Settings Button */}
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            onOpenSettings();
                        }}
                        className="w-full flex items-center justify-center gap-2 px-3 py-1.5 bg-white hover:bg-gray-100 border border-gray-300 rounded text-xs font-medium transition-colors text-gray-700 mt-2"
                    >
                        <FolderOpen className="w-3 h-3" />
                        Path Settings
                    </button>
                </div>
            )}
        </div>
    );
}
