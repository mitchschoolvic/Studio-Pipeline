import React, { useState } from 'react';
import { X, AlertTriangle } from 'lucide-react';

/**
 * Dialog that appears when user attempts to pause while jobs are active
 * Offers two choices:
 * 1. Wait for active jobs to finish before pausing
 * 2. Immediately cancel active jobs and reset to resumable checkpoints
 */
export default function PauseConfirmDialog({ activeJobs, onConfirm, onCancel }) {
  const [choice, setChoice] = useState('wait'); // 'wait' or 'reset'

  const handleConfirm = () => {
    onConfirm(choice);
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <div className="flex items-center gap-3">
            <AlertTriangle className="text-amber-500" size={24} />
            <h2 className="text-xl font-semibold text-gray-900">
              Active Processes Running
            </h2>
          </div>
          <button
            onClick={onCancel}
            className="text-gray-400 hover:text-gray-600 transition-colors"
          >
            <X size={24} />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-4 overflow-y-auto flex-1">
          <p className="text-gray-700 mb-4">
            There {activeJobs.length === 1 ? 'is' : 'are'} <strong>{activeJobs.length}</strong> active{' '}
            {activeJobs.length === 1 ? 'process' : 'processes'} currently running. How would you like to proceed?
          </p>

          {/* Choice Options */}
          <div className="space-y-3 mb-6">
            {/* Wait Option */}
            <label
              className={`flex items-start gap-3 p-4 border-2 rounded-lg cursor-pointer transition-colors ${
                choice === 'wait'
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <input
                type="radio"
                name="pause-choice"
                value="wait"
                checked={choice === 'wait'}
                onChange={(e) => setChoice(e.target.value)}
                className="mt-1"
              />
              <div className="flex-1">
                <div className="font-medium text-gray-900">Wait for completion</div>
                <div className="text-sm text-gray-600 mt-1">
                  Allow active processes to finish normally, then pause. New processes will not start.
                </div>
              </div>
            </label>

            {/* Reset Option */}
            <label
              className={`flex items-start gap-3 p-4 border-2 rounded-lg cursor-pointer transition-colors ${
                choice === 'reset'
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <input
                type="radio"
                name="pause-choice"
                value="reset"
                checked={choice === 'reset'}
                onChange={(e) => setChoice(e.target.value)}
                className="mt-1"
              />
              <div className="flex-1">
                <div className="font-medium text-gray-900">Cancel and reset immediately</div>
                <div className="text-sm text-gray-600 mt-1">
                  Stop active processes and reset them to their last resumable checkpoint. Work in progress will be discarded.
                </div>
              </div>
            </label>
          </div>

          {/* Active Jobs List */}
          <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
            <h3 className="text-sm font-medium text-gray-700 mb-3">Active Processes:</h3>
            <div className="space-y-2">
              {activeJobs && activeJobs.length > 0 ? activeJobs.map((job) => (
                <div key={job.id || Math.random()} className="bg-white rounded p-3 border border-gray-200">
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-sm font-medium text-gray-900 truncate flex-1">
                      {job.file?.filename || job.filename || `Job ${job.id || 'Unknown'}`}
                    </div>
                    {job.retries > 0 && (
                      <span className="ml-2 px-2 py-0.5 bg-amber-100 text-amber-700 text-xs rounded-full">
                        Retry {job.retries}
                      </span>
                    )}
                  </div>

                  {/* Progress Bar */}
                  {job.progress_pct !== null && job.progress_pct !== undefined && (
                    <div className="mb-2">
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div
                          className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                          style={{ width: `${Math.min(100, Math.max(0, job.progress_pct))}%` }}
                        />
                      </div>
                    </div>
                  )}

                  <div className="flex items-center justify-between text-xs">
                    <span className="text-gray-600">
                      {job.progress_stage || job.kind || 'Processing'}
                    </span>
                    {job.progress_pct !== null && job.progress_pct !== undefined && (
                      <span className="text-gray-500 font-medium">
                        {Math.round(job.progress_pct)}%
                      </span>
                    )}
                  </div>

                  {job.checkpoint_state && (
                    <div className="mt-2 text-xs text-gray-500">
                      Will resume from: <span className="font-medium">{job.checkpoint_state}</span>
                    </div>
                  )}
                </div>
              )) : (
                <div className="text-sm text-gray-500 text-center py-4">
                  No active jobs found
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-200">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            {choice === 'wait' ? 'Wait and Pause' : 'Reset and Pause'}
          </button>
        </div>
      </div>
    </div>
  );
}
