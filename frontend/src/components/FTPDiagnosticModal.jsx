import React, { useState, useEffect } from 'react';
import { 
  X, 
  FolderX, 
  Folder, 
  FileVideo, 
  RefreshCw, 
  CheckCircle, 
  Clock, 
  AlertCircle,
  Ban,
  FileX,
  Eye,
  EyeOff,
  ChevronDown,
  ChevronRight,
  Radio
} from 'lucide-react';
import { useFTPDiagnose, useDiscoveryStatus, FileStatus, FileStatusLabels, FileStatusColors } from '../api/discovery';

/**
 * FTP Discovery Diagnostic Modal
 * 
 * Shows detailed information about files found on FTP and why they
 * are or aren't being added to sessions.
 */
export function FTPDiagnosticModal({ isOpen, onClose }) {
  const [showDirectories, setShowDirectories] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');
  
  const { 
    data: diagnostic, 
    isLoading, 
    isFetching,
    isError, 
    error, 
    refetch 
  } = useFTPDiagnose({ enabled: isOpen });
  
  // Fetch auto-scan status (refreshes every 5 seconds when modal is open)
  const { data: discoveryStatus } = useDiscoveryStatus({ 
    enabled: isOpen,
    refetchInterval: 5_000 
  });
  
  // Track refresh state for better UX feedback
  const [lastRefreshTime, setLastRefreshTime] = useState(null);

  // Refetch when modal opens
  useEffect(() => {
    if (isOpen) {
      refetch();
    }
  }, [isOpen, refetch]);

  if (!isOpen) return null;

  // Filter files by status
  const filteredFiles = diagnostic?.files?.filter(file => {
    if (statusFilter === 'all') return true;
    return file.status === statusFilter;
  }) || [];

  // Get status icon
  const getStatusIcon = (status) => {
    switch (status) {
      case FileStatus.ADDED:
        return <CheckCircle className="w-4 h-4 text-green-600" />;
      case FileStatus.EXISTS:
        return <Clock className="w-4 h-4 text-blue-600" />;
      case FileStatus.EXCLUDED:
        return <Ban className="w-4 h-4 text-orange-600" />;
      case FileStatus.TOO_SMALL:
        return <AlertCircle className="w-4 h-4 text-red-600" />;
      case FileStatus.WRONG_EXTENSION:
        return <FileX className="w-4 h-4 text-yellow-600" />;
      case FileStatus.HIDDEN:
      case FileStatus.SYSTEM:
        return <EyeOff className="w-4 h-4 text-gray-500" />;
      default:
        return <AlertCircle className="w-4 h-4 text-gray-500" />;
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl max-w-4xl w-full max-h-[85vh] overflow-hidden flex flex-col">
        
        {/* Header */}
        <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between bg-gray-50 dark:bg-gray-800">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
              <Eye className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                FTP Discovery Diagnostic
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {diagnostic?.source_path || '/'} 
                {diagnostic?.scanned_at && (
                  <span className="ml-2">
                    • Diagnostic: {new Date(diagnostic.scanned_at).toLocaleTimeString()}
                  </span>
                )}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                setLastRefreshTime(new Date());
                refetch();
              }}
              disabled={isFetching}
              className={`p-2 text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors ${isFetching ? 'opacity-50 cursor-wait' : ''}`}
              title="Refresh FTP scan"
            >
              <RefreshCw className={`w-5 h-5 ${isFetching ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={onClose}
              className="p-2 text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>
        
        {/* Auto-Scan Status Bar */}
        {discoveryStatus?.auto_scan && (
          <div className="px-4 py-2 bg-gray-100 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
              <Radio className={`w-4 h-4 ${discoveryStatus.auto_scan.enabled ? 'text-green-500' : 'text-gray-400'}`} />
              <span className="text-gray-600 dark:text-gray-400">
                Auto-scan: {discoveryStatus.auto_scan.enabled ? (
                  <span className="text-green-600 dark:text-green-400">
                    Every {discoveryStatus.auto_scan.interval_seconds}s
                  </span>
                ) : (
                  <span className="text-gray-500">Disabled</span>
                )}
              </span>
            </div>
            <div className="flex items-center gap-4 text-gray-500 dark:text-gray-400">
              {discoveryStatus.auto_scan.last_scan && (
                <span>
                  Last auto-scan: {new Date(discoveryStatus.auto_scan.last_scan).toLocaleTimeString()}
                </span>
              )}
              <span className={`flex items-center gap-1 ${discoveryStatus.auto_scan.ftp_connected ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
                <span className={`w-2 h-2 rounded-full ${discoveryStatus.auto_scan.ftp_connected ? 'bg-green-500' : 'bg-red-500'}`} />
                {discoveryStatus.auto_scan.ftp_connected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          
          {/* Error State */}
          {isError && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
              <div className="flex items-center gap-2 text-red-700 dark:text-red-400">
                <AlertCircle className="w-5 h-5" />
                <span className="font-medium">Failed to run diagnostic</span>
              </div>
              <p className="mt-1 text-sm text-red-600 dark:text-red-300">
                {error?.message || diagnostic?.error || 'Unknown error'}
              </p>
            </div>
          )}

          {/* Loading State */}
          {(isLoading || (isFetching && !diagnostic)) && (
            <div className="flex items-center justify-center py-12">
              <RefreshCw className="w-8 h-8 text-blue-500 animate-spin" />
              <span className="ml-3 text-gray-600 dark:text-gray-400">Scanning FTP server...</span>
            </div>
          )}
          
          {/* Refreshing indicator (when we have existing data) */}
          {isFetching && diagnostic && (
            <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 rounded-lg p-3 flex items-center gap-2">
              <RefreshCw className="w-4 h-4 text-blue-500 animate-spin" />
              <span className="text-sm text-blue-700 dark:text-blue-300">Refreshing FTP scan...</span>
            </div>
          )}

          {/* Results */}
          {!isLoading && diagnostic?.success && (
            <>
              {/* Summary */}
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                <SummaryCard 
                  label="Total Files" 
                  value={diagnostic.summary.total_files} 
                  icon={<FileVideo className="w-4 h-4" />}
                />
                <SummaryCard 
                  label="Directories" 
                  value={diagnostic.summary.total_directories} 
                  icon={<Folder className="w-4 h-4 text-blue-500" />}
                />
                <SummaryCard 
                  label="Will Add" 
                  value={diagnostic.summary.by_status?.[FileStatus.ADDED] || 0} 
                  icon={<CheckCircle className="w-4 h-4 text-green-500" />}
                  highlight="green"
                />
                <SummaryCard 
                  label="Already Added" 
                  value={diagnostic.summary.by_status?.[FileStatus.EXISTS] || 0} 
                  icon={<Clock className="w-4 h-4 text-blue-500" />}
                  highlight="blue"
                />
                <SummaryCard 
                  label="Filtered Out" 
                  value={(diagnostic.summary.by_status?.[FileStatus.EXCLUDED] || 0) + 
                         (diagnostic.summary.by_status?.[FileStatus.HIDDEN] || 0) +
                         (diagnostic.summary.by_status?.[FileStatus.SYSTEM] || 0) +
                         (diagnostic.summary.by_status?.[FileStatus.TOO_SMALL] || 0) +
                         (diagnostic.summary.by_status?.[FileStatus.WRONG_EXTENSION] || 0)} 
                  icon={<Ban className="w-4 h-4 text-orange-500" />}
                  highlight="orange"
                />
              </div>
              
              {/* Scan Statistics - shows what was actually scanned */}
              {diagnostic.summary?.scanned_directories !== undefined && (
                <div className="text-xs text-gray-500 dark:text-gray-400 flex gap-4">
                  <span>Scanned: {diagnostic.summary.scanned_directories} directories</span>
                  {diagnostic.summary.excluded_directories > 0 && (
                    <span className="text-orange-500">• {diagnostic.summary.excluded_directories} directories excluded (contents not scanned)</span>
                  )}
                </div>
              )}

              {/* Excluded Folders Info */}
              {diagnostic.excluded_folders?.length > 0 && (
                <div className="bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800 rounded-lg p-3">
                  <div className="flex items-center gap-2 text-orange-700 dark:text-orange-400 text-sm font-medium">
                    <FolderX className="w-4 h-4" />
                    Excluded Folder Names: {diagnostic.excluded_folders.join(', ')}
                  </div>
                </div>
              )}

              {/* Directories Section */}
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                <button
                  onClick={() => setShowDirectories(!showDirectories)}
                  className="w-full flex items-center gap-2 p-3 bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                >
                  {showDirectories ? (
                    <ChevronDown className="w-4 h-4 text-gray-500" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-gray-500" />
                  )}
                  <Folder className="w-4 h-4 text-gray-500" />
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Directories ({diagnostic.directories?.length || 0})
                    {diagnostic.summary?.excluded_directories > 0 && (
                      <span className="ml-2 text-orange-600 dark:text-orange-400">
                        ({diagnostic.summary.excluded_directories} excluded)
                      </span>
                    )}
                  </span>
                </button>
                
                {showDirectories && diagnostic.directories?.length > 0 && (
                  <div className="max-h-48 overflow-y-auto border-t border-gray-200 dark:border-gray-700">
                    {diagnostic.directories.map((dir, i) => (
                      <div
                        key={i}
                        className={`flex items-center gap-2 px-3 py-2 text-sm ${
                          dir.is_excluded
                            ? 'bg-orange-50 dark:bg-orange-900/10 text-orange-700 dark:text-orange-400'
                            : dir.is_system
                            ? 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-500'
                            : 'text-gray-700 dark:text-gray-300'
                        }`}
                        style={{ paddingLeft: `${12 + (dir.depth || 0) * 16}px` }}
                      >
                        {dir.is_excluded ? (
                          <FolderX className="w-4 h-4 flex-shrink-0" />
                        ) : dir.is_system ? (
                          <FolderX className="w-4 h-4 flex-shrink-0 text-gray-400" />
                        ) : (
                          <Folder className="w-4 h-4 flex-shrink-0 text-blue-500" />
                        )}
                        <span className="truncate">{dir.name || dir.path}</span>
                        <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto flex-shrink-0">
                          {dir.path}
                        </span>
                        {dir.is_excluded && (
                          <span className="text-xs bg-orange-200 dark:bg-orange-800 text-orange-800 dark:text-orange-200 px-1.5 py-0.5 rounded flex-shrink-0">
                            excluded
                          </span>
                        )}
                        {dir.is_system && (
                          <span className="text-xs bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400 px-1.5 py-0.5 rounded flex-shrink-0">
                            system
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
                
                {showDirectories && (!diagnostic.directories || diagnostic.directories.length === 0) && (
                  <div className="p-4 text-center text-gray-500 dark:text-gray-400 text-sm border-t border-gray-200 dark:border-gray-700">
                    No directories found on FTP server
                  </div>
                )}
              </div>

              {/* Files Section */}
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                {/* Files Header with Filter */}
                <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
                  <div className="flex items-center gap-2">
                    <FileVideo className="w-4 h-4 text-gray-500" />
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      Files ({filteredFiles.length})
                    </span>
                  </div>
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    className="text-xs border border-gray-300 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300"
                  >
                    <option value="all">All Status</option>
                    <option value={FileStatus.ADDED}>Will Add</option>
                    <option value={FileStatus.EXISTS}>Already Added</option>
                    <option value={FileStatus.EXCLUDED}>Excluded</option>
                    <option value={FileStatus.TOO_SMALL}>Too Small</option>
                    <option value={FileStatus.WRONG_EXTENSION}>Wrong Extension</option>
                    <option value={FileStatus.HIDDEN}>Hidden</option>
                    <option value={FileStatus.SYSTEM}>System</option>
                  </select>
                </div>
                
                {/* Files Table */}
                <div className="max-h-80 overflow-y-auto">
                  {filteredFiles.length === 0 ? (
                    <div className="p-4 text-center text-gray-500 dark:text-gray-400 text-sm">
                      No files match the selected filter
                    </div>
                  ) : (
                    <table className="w-full text-sm">
                      <thead className="bg-gray-100 dark:bg-gray-800 sticky top-0">
                        <tr>
                          <th className="text-left px-3 py-2 text-gray-600 dark:text-gray-400 font-medium">File</th>
                          <th className="text-right px-3 py-2 text-gray-600 dark:text-gray-400 font-medium w-20">Size</th>
                          <th className="text-center px-3 py-2 text-gray-600 dark:text-gray-400 font-medium w-32">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                        {filteredFiles.map((file, i) => (
                          <tr key={i} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                            <td className="px-3 py-2">
                              <div className="flex items-center gap-2">
                                {getStatusIcon(file.status)}
                                <div className="min-w-0">
                                  <div className="font-medium text-gray-900 dark:text-white truncate" title={file.filename}>
                                    {file.filename}
                                  </div>
                                  <div className="text-xs text-gray-500 dark:text-gray-400 truncate" title={file.folder}>
                                    {file.folder}
                                  </div>
                                </div>
                              </div>
                            </td>
                            <td className="px-3 py-2 text-right text-gray-600 dark:text-gray-400 whitespace-nowrap">
                              {file.size_mb} MB
                            </td>
                            <td className="px-3 py-2 text-center">
                              <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${FileStatusColors[file.status] || 'bg-gray-100 text-gray-600'}`}>
                                {FileStatusLabels[file.status] || file.status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-800 dark:text-gray-200 rounded-lg text-sm font-medium transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Summary card component for the diagnostic header
 */
function SummaryCard({ label, value, icon, highlight }) {
  const highlightClasses = {
    green: 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800',
    blue: 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800',
    orange: 'bg-orange-50 dark:bg-orange-900/20 border-orange-200 dark:border-orange-800',
  };

  return (
    <div className={`border rounded-lg p-3 ${highlight ? highlightClasses[highlight] : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800'}`}>
      <div className="flex items-center gap-2 mb-1">
        {icon}
        <span className="text-xs text-gray-500 dark:text-gray-400">{label}</span>
      </div>
      <div className="text-2xl font-bold text-gray-900 dark:text-white">{value}</div>
    </div>
  );
}

export default FTPDiagnosticModal;
