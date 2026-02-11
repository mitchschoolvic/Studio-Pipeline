import React from 'react';
import { Check, X, Loader2, FolderOpen, Download, Cog, FolderCheck, CheckCircle2 } from 'lucide-react';

/**
 * FileStepIndicator - Visualizes the processing pipeline for a single file
 * 
 * Pipeline Flow: Found → Copied → Processing (with substeps) → Organizing → Completed
 * 
 * Processing Substeps:
 * - Extract: Extract audio tracks
 * - Boost: Normalize audio levels
 * - Denoise: Apply noise reduction
 * - Convert: Convert to high-quality format
 * - Remux: Remux video with enhanced audio
 * - Quad Split: Create quad-split view (main files only)
 */
const FileStepIndicator = ({ file }) => {
  // Processing substeps configuration
  const processingSubsteps = [
    { id: 'extract', label: 'Extract' },
    { id: 'boost', label: 'Boost' },
    { id: 'denoise', label: 'Denoise' },
    { id: 'convert', label: 'Convert' },
    { id: 'remux', label: 'Remux' },
    { id: 'gesturetrim', label: 'Gesture Trim' },
    { id: 'faststart', label: 'Faststart' },
    { id: 'quadsplit', label: 'Quad Split' }
  ];

  // Determine step status based on file state
  const getStepStatus = (stepName) => {
    const state = file.state;

    // Map file states to step statuses
    const stateOrder = ['DISCOVERED', 'COPYING', 'COPIED', 'PROCESSING', 'PROCESSED', 'ORGANIZING', 'COMPLETED', 'FAILED'];
    const currentStateIndex = stateOrder.indexOf(state);

    switch (stepName) {
      case 'discovered':
        return currentStateIndex >= 0 ? 'completed' : 'pending';

      case 'copied':
        if (state === 'FAILED' && currentStateIndex <= 2) return 'failed';
        if (state === 'COPYING') return 'active';
        return currentStateIndex >= 2 ? 'completed' : 'pending';

      case 'processing':
        if (!file.is_program_output) return 'skipped'; // ISO files skip processing
        if (state === 'FAILED' && currentStateIndex === 3) return 'failed';
        if (state === 'PROCESSING') return 'active';
        return currentStateIndex >= 4 ? 'completed' : 'pending';

      case 'organizing':
        if (state === 'FAILED' && currentStateIndex === 5) return 'failed';
        if (state === 'ORGANIZING') return 'active';
        return currentStateIndex >= 6 ? 'completed' : 'pending';

      case 'completed':
        return state === 'COMPLETED' ? 'completed' : 'pending';

      default:
        return 'pending';
    }
  };

  // Determine substep status during PROCESSING state
  const getSubstepStatus = (substepId) => {
    // Quad split is currently not implemented in the backend, so it's always skipped
    if (substepId === 'quadsplit') return 'skipped';

    // Gesture trim can be skipped if no gesture was detected
    if (substepId === 'gesturetrim') {
      // Check if gesture trim was skipped (no gesture found)
      if (file.gesture_trim_skipped) return 'skipped';
      // If file is completed/processed, check if gesture_trimmed flag is set
      if (file.state === 'COMPLETED' || file.state === 'PROCESSED' || file.state === 'ORGANIZING') {
        return file.gesture_trimmed ? 'completed' : 'skipped';
      }
    }

    if (file.state !== 'PROCESSING') {
      // If completed, all substeps are done (except quadsplit for ISO files)
      if (file.state === 'COMPLETED' || file.state === 'PROCESSED' || file.state === 'ORGANIZING') {
        return file.is_program_output ? 'completed' : 'skipped';
      }
      return 'pending';
    }

    // File is actively processing
    const currentStage = file.processing_stage;
    const substepOrder = ['extract', 'boost', 'denoise', 'convert', 'remux', 'gesturetrim', 'faststart', 'quadsplit'];
    const currentIndex = substepOrder.indexOf(currentStage);
    const substepIndex = substepOrder.indexOf(substepId);

    if (substepIndex < currentIndex) return 'completed';
    if (substepIndex === currentIndex) return 'active';
    return 'pending';
  };

  // Get icon for step status
  const getStepIcon = (status, DefaultIcon) => {
    switch (status) {
      case 'completed':
        return <Check className="w-2.5 h-2.5 text-green-600" />;
      case 'active':
        return <Loader2 className="w-2.5 h-2.5 text-blue-600 animate-spin" />;
      case 'failed':
        return <X className="w-2.5 h-2.5 text-red-600" />;
      case 'skipped':
        return <DefaultIcon className="w-2.5 h-2.5 text-gray-400 opacity-50" />;
      default:
        return <DefaultIcon className="w-2.5 h-2.5 text-gray-400" />;
    }
  };

  // Get color classes for step
  const getStepColor = (status) => {
    switch (status) {
      case 'completed':
        return 'bg-green-100 text-green-600';
      case 'active':
        return 'bg-blue-100 text-blue-600';
      case 'failed':
        return 'bg-red-100 text-red-600';
      case 'skipped':
        return 'bg-gray-100 text-gray-400';
      default:
        return 'bg-gray-100 text-gray-400';
    }
  };

  // Get text color for labels
  const getTextColor = (status) => {
    switch (status) {
      case 'completed':
        return 'text-green-600';
      case 'active':
        return 'text-blue-600 font-medium';
      case 'failed':
        return 'text-red-600';
      case 'skipped':
        return 'text-gray-400 line-through';
      default:
        return 'text-gray-400';
    }
  };

  // Get substep icon character
  const getSubstepIcon = (status) => {
    switch (status) {
      case 'completed':
        return '✓';
      case 'active':
        return '⟳';
      case 'failed':
        return '✗';
      case 'skipped':
        return '−';
      default:
        return '○';
    }
  };

  // Get substep color classes
  const getSubstepColor = (status) => {
    switch (status) {
      case 'completed':
        return 'bg-green-500 text-white';
      case 'active':
        return 'bg-blue-500 text-white';
      case 'failed':
        return 'bg-red-500 text-white';
      case 'skipped':
        return 'bg-gray-300 text-gray-500';
      default:
        return 'bg-gray-200 text-gray-500';
    }
  };

  // Determine processing box border/background
  const processingStatus = getStepStatus('processing');
  const processingBoxClasses =
    processingStatus === 'completed' ? 'border-green-200 bg-green-50' :
      processingStatus === 'active' ? 'border-blue-200 bg-blue-50' :
        processingStatus === 'skipped' ? 'border-gray-200 bg-gray-50' :
          'border-gray-200 bg-white';

  return (
    <div className="bg-white rounded-lg p-4 shadow-sm">
      <div className="flex items-center space-x-2">
        {/* Found Step */}
        <div className="flex flex-col items-center space-y-0.5">
          <div className={`w-5 h-5 rounded-full flex items-center justify-center ${getStepColor(getStepStatus('discovered'))}`}>
            {getStepIcon(getStepStatus('discovered'), FolderOpen)}
          </div>
          <span className={`text-[9px] text-center leading-tight ${getTextColor(getStepStatus('discovered'))}`}>
            Found
          </span>
        </div>

        {/* Arrow */}
        <div className="text-gray-300 text-xs pb-3">→</div>

        {/* Copied Step */}
        <div className="flex flex-col items-center space-y-0.5">
          <div className={`w-5 h-5 rounded-full flex items-center justify-center ${getStepColor(getStepStatus('copied'))}`}>
            {getStepIcon(getStepStatus('copied'), Download)}
          </div>
          <span className={`text-[9px] text-center leading-tight ${getTextColor(getStepStatus('copied'))}`}>
            Copied
          </span>
        </div>

        {/* Arrow */}
        <div className="text-gray-300 text-xs pb-3">→</div>

        {/* Processing Steps - Expanded with substeps */}
        <div className={`flex-1 border-2 rounded-lg px-3 py-2 ${processingBoxClasses}`}>
          {file.is_program_output ? (
            <div className="flex items-center justify-between">
              {processingSubsteps.map((step) => {
                const status = getSubstepStatus(step.id);
                return (
                  <div key={step.id} className="flex flex-col items-center space-y-0.5">
                    <div className={`w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold ${getSubstepColor(status)}`}>
                      {getSubstepIcon(status)}
                    </div>
                    <span className={`text-[9px] text-center leading-tight ${getTextColor(status)}`}>
                      {step.label}
                    </span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-center text-xs text-gray-400 py-1">
              <span className="line-through">Processing skipped (ISO)</span>
            </div>
          )}
        </div>

        {/* Arrow */}
        <div className="text-gray-300 text-xs pb-3">→</div>

        {/* Organizing Step */}
        <div className="flex flex-col items-center space-y-0.5">
          <div className={`w-5 h-5 rounded-full flex items-center justify-center ${getStepColor(getStepStatus('organizing'))}`}>
            {getStepIcon(getStepStatus('organizing'), FolderCheck)}
          </div>
          <span className={`text-[9px] text-center leading-tight ${getTextColor(getStepStatus('organizing'))}`}>
            Organizing
          </span>
        </div>

        {/* Arrow */}
        <div className="text-gray-300 text-xs pb-3">→</div>

        {/* Completed Step */}
        <div className="flex flex-col items-center space-y-0.5">
          <div className={`w-5 h-5 rounded-full flex items-center justify-center ${getStepColor(getStepStatus('completed'))}`}>
            {getStepIcon(getStepStatus('completed'), CheckCircle2)}
          </div>
          <span className={`text-[9px] text-center leading-tight ${getTextColor(getStepStatus('completed'))}`}>
            Completed
          </span>
        </div>
      </div>

      {/* Additional Details for Active/Failed States */}
      {file.state === 'PROCESSING' && file.processing_detail && (
        <div className="mt-3 pt-3 border-t border-gray-200 text-xs text-gray-600">
          <span className="font-medium">Currently:</span> {file.processing_detail}
        </div>
      )}

      {file.state === 'FAILED' && file.error_message && (
        <div className="mt-3 pt-3 border-t border-gray-200">
          <div className="text-xs text-red-700 bg-red-50 p-2 rounded flex items-start space-x-2">
            <X className="w-3 h-3 mt-0.5 flex-shrink-0" />
            <div className="flex-1">
              <span className="font-medium">Error:</span> {file.error_message}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default FileStepIndicator;
