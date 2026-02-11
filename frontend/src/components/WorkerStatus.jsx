import React from 'react';
import { useWorkerStatus } from '../api/workers'; // Import the new hook
import '../styles/WorkerStatus.css';

export const WorkerStatus = ({ isVisible = true }) => {
  // 1. Use the hook instead of manual fetch/useEffect
  const { data: workerData, isLoading, isError } = useWorkerStatus();

  if (isLoading || !workerData) return null;
  if (isError) return <div className="worker-status-error">Unable to load worker status</div>;

  const { workers, queue_counts } = workerData;

  // Filter workers (same logic as before) 
  const displayWorkers = workers || [];
  const pipelineWorkers = displayWorkers.filter(w => w.worker_type === 'pipeline');
  const analyticsWorkers = displayWorkers.filter(w => w.worker_type === 'analytics');
  const totalQueued = Object.values(queue_counts || {}).reduce((sum, count) => sum + count, 0);

  // Helper for icons (moved from inline logic)
  const getWorkerIcon = (name) => {
    if (name.includes('Copy')) return '📥';
    if (name.includes('Process')) return '⚙️';
    if (name.includes('Organize')) return '📂';
    if (name.includes('Thumbnail')) return '🖼️';
    if (name.includes('Transcribe')) return '🎤';
    if (name.includes('Analyze')) return '📊';
    return '🔧';
  };

  // Render individual worker card
  const renderWorker = (worker) => {
    const isActive = worker.state === 'ACTIVE';
    const stateClass = `status-${worker.state.toLowerCase()}`;

    return (
      <div key={worker.name} className={`worker-card ${stateClass}`}>
        <div className="worker-header">
          <span className="worker-icon">{getWorkerIcon(worker.name)}</span>
          <span className="worker-name">{worker.name}</span>
          <span className={`worker-state ${stateClass}`}>
            {/* Simple state mapping */}
            {worker.state === 'ACTIVE' ? '▶️' :
              worker.state === 'PAUSED' ? '⏸️' :
                worker.state === 'ERROR' ? '❌' : '⏳'} {worker.state}
          </span>
        </div>

        {isActive ? (
          <div className="worker-details">
            <div className="worker-detail">
              <span className="detail-label">File:</span>
              <span className="detail-value" title={worker.current_filename}>
                {worker.current_filename || 'Unknown'}
              </span>
            </div>
            {/* Add progress bar if active [cite: 1882] */}
            {worker.progress_pct !== undefined && (
              <div className="worker-progress">
                <div className="progress-bar">
                  <div className="progress-fill" style={{ width: `${worker.progress_pct}%` }} />
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="worker-details">
            <span className={`detail-value ${worker.state === 'ERROR' ? 'text-red-500 font-medium' : 'text-gray-400'}`}>
              {worker.state === 'ERROR' ? (worker.error_message || 'Unknown Error') : (worker.wait_reason || 'Idle')}
            </span>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className={`worker-status-container ${isVisible ? '' : 'hidden'}`}>
      <div className="worker-status-header">
        <h3>Worker Status</h3>
      </div>

      <div className="worker-status-body">
        {/* Pipeline Section */}
        {pipelineWorkers.length > 0 && (
          <div className="worker-section">
            <h4 className="section-title">Pipeline</h4>
            <div className="worker-list">{pipelineWorkers.map(renderWorker)}</div>
          </div>
        )}

        {/* Analytics Section */}
        {analyticsWorkers.length > 0 && (
          <div className="worker-section">
            <h4 className="section-title">AI Analytics</h4>
            <div className="worker-list">{analyticsWorkers.map(renderWorker)}</div>
          </div>
        )}

        {/* Queue Summary */}
        {totalQueued > 0 && (
          <div className="queue-summary">
            <span>{totalQueued} job{totalQueued !== 1 ? 's' : ''} pending</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default WorkerStatus;
