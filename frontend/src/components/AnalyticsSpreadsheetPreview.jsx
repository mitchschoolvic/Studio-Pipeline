import { useMemo, useState } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
} from '@tanstack/react-table';
import { useAnalyticsSummary, useAnalyticsDetail } from '../api/analytics';
import { formatISOTimestamp } from '../utils/dateUtils';
import { Download, ChevronUp, ChevronDown, ChevronsUpDown, X, Loader2 } from 'lucide-react';

/**
 * Modal to show full analytics detail for a row
 */
function AnalyticsDetailModal({ analyticsId, onClose }) {
  const { data: detail, isLoading, error } = useAnalyticsDetail(analyticsId);

  if (isLoading) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <div className="bg-white rounded-lg p-6 max-w-4xl w-full max-h-[90vh] overflow-auto">
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
            <span className="ml-3 text-gray-600">Loading details...</span>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <div className="bg-white rounded-lg p-6 max-w-4xl w-full max-h-[90vh] overflow-auto">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-red-600">Error Loading Details</h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 transition-colors"
            >
              <X className="h-6 w-6" />
            </button>
          </div>
          <p className="text-gray-700">{error.message}</p>
        </div>
      </div>
    );
  }

  if (!detail) return null;

  // All 17 Excel columns in order
  const excelFields = [
    { label: 'Title', value: detail.title || '' },
    { label: 'Description', value: detail.description || '' },
    { label: 'Duration', value: detail.duration || '' },
    { label: 'DurationSeconds', value: detail.duration_seconds || 0 },
    { label: 'Type', value: detail.content_type || '' },
    { label: 'Faculty', value: detail.faculty || '' },
    { label: 'Speaker', value: detail.speaker || '' },
    { label: 'Audience', value: detail.audience || '' },
    { label: 'Timestamp', value: detail.timestamp || '' },
    { label: 'TimestampSort', value: detail.timestamp_sort || '' },
    { label: 'ThumbnailUrl', value: detail.thumbnail_url || '' },
    { label: 'ThumbnailPath', value: detail.thumbnail_path || '' },
    { label: 'Filename', value: detail.filename || detail.file_name || '' },
    { label: 'StudioLocation', value: detail.studio_location || '' },
    { label: 'Language', value: detail.detected_language || 'English' },
    { label: 'SpeakerCount', value: detail.speaker_count || 0 },
    { label: 'Transcript', value: detail.transcript || '', isLarge: true },
    { label: 'VideoUrl', value: detail.video_url || '' },
  ];

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-900">
            Full Analytics Record
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
          >
            <X className="h-6 w-6" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-6">
          <div className="space-y-4">
            {excelFields.map((field, idx) => (
              <div key={idx} className="border-b border-gray-100 pb-3">
                <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                  {field.label}
                </div>
                {field.isLarge ? (
                  <div className="bg-gray-50 p-3 rounded text-sm text-gray-700 whitespace-pre-wrap max-h-64 overflow-auto font-mono">
                    {field.value || <span className="text-gray-400 italic">Empty</span>}
                  </div>
                ) : (
                  <div className="text-sm text-gray-900">
                    {field.value || <span className="text-gray-400 italic">Empty</span>}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end p-6 border-t border-gray-200">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Main Spreadsheet Preview Component
 */
export function AnalyticsSpreadsheetPreview() {
  const [page, setPage] = useState(0);
  const [pageSize] = useState(50);
  const [sorting, setSorting] = useState([{ id: 'created_at', desc: true }]);
  const [selectedId, setSelectedId] = useState(null);
  const [isExporting, setIsExporting] = useState(false);

  // Build sort string from sorting state
  const sortString = useMemo(() => {
    if (sorting.length === 0) return 'created_at:desc';
    const { id, desc } = sorting[0];
    return `${id}:${desc ? 'desc' : 'asc'}`;
  }, [sorting]);

  // Fetch data using existing hook
  const { data, isLoading, error } = useAnalyticsSummary({
    page,
    pageSize,
    sort: sortString,
    state: 'COMPLETED', // Only show completed analytics
  });

  // Define columns matching Excel export order
  const columns = useMemo(
    () => [
      {
        accessorKey: 'title',
        header: 'Title',
        cell: ({ getValue }) => (
          <div className="max-w-xs truncate" title={getValue()}>
            {getValue() || <span className="text-gray-400 italic">N/A</span>}
          </div>
        ),
      },
      {
        accessorKey: 'content_type',
        header: 'Type',
        cell: ({ getValue }) => (
          <div className="max-w-xs truncate" title={getValue()}>
            {getValue() || <span className="text-gray-400 italic">N/A</span>}
          </div>
        ),
      },
      {
        accessorKey: 'faculty',
        header: 'Faculty',
        cell: ({ getValue }) => (
          <div className="max-w-xs truncate" title={getValue()}>
            {getValue() || <span className="text-gray-400 italic">N/A</span>}
          </div>
        ),
      },
      {
        accessorKey: 'speaker',
        header: 'Speaker',
        cell: ({ getValue }) => (
          <div className="max-w-xs truncate" title={getValue()}>
            {getValue() || <span className="text-gray-400 italic">N/A</span>}
          </div>
        ),
      },
      {
        accessorKey: 'audience',
        header: 'Audience',
        cell: ({ getValue }) => (
          <div className="max-w-xs truncate" title={getValue()}>
            {getValue() || <span className="text-gray-400 italic">N/A</span>}
          </div>
        ),
      },
      {
        accessorKey: 'created_at',
        header: 'Timestamp',
        cell: ({ getValue }) => (
          <div className="whitespace-nowrap">
            {formatISOTimestamp(getValue())}
          </div>
        ),
      },
      {
        accessorKey: 'filename',
        header: 'Filename',
        cell: ({ row }) => {
          const filename = row.original.filename || row.original.file_name;
          return (
            <div className="max-w-xs truncate font-mono text-xs" title={filename}>
              {filename || <span className="text-gray-400 italic">N/A</span>}
            </div>
          );
        },
      },
      {
        accessorKey: 'owner',
        header: 'Owner',
        cell: ({ getValue }) => (
          <div className="max-w-xs truncate" title={getValue()}>
            {getValue() || <span className="text-gray-400 italic">N/A</span>}
          </div>
        ),
      },
      {
        accessorKey: 'state',
        header: 'State',
        cell: ({ getValue }) => {
          const state = getValue();
          const colorMap = {
            COMPLETED: 'bg-green-100 text-green-800',
            PENDING: 'bg-yellow-100 text-yellow-800',
            TRANSCRIBING: 'bg-blue-100 text-blue-800',
            ANALYZING: 'bg-purple-100 text-purple-800',
            FAILED: 'bg-red-100 text-red-800',
          };
          const colorClass = colorMap[state] || 'bg-gray-100 text-gray-800';
          return (
            <span className={`px-2 py-1 rounded text-xs font-medium ${colorClass}`}>
              {state}
            </span>
          );
        },
      },
    ],
    []
  );

  const table = useReactTable({
    data: data || [],
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    manualSorting: true, // Server-side sorting
    manualPagination: true, // Server-side pagination
  });

  // Handle Excel export
  const handleExport = async () => {
    setIsExporting(true);
    try {
      // Create a link that triggers the download
      const downloadLink = document.createElement('a');
      downloadLink.href = '/api/analytics/export/download';
      downloadLink.download = 'analytics.xlsx';
      document.body.appendChild(downloadLink);
      downloadLink.click();
      document.body.removeChild(downloadLink);

      // Give user feedback
      setTimeout(() => {
        setIsExporting(false);
      }, 1000);
    } catch (err) {
      console.error('Export error:', err);
      alert('Failed to export analytics data. Please try again.');
      setIsExporting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
        <span className="ml-3 text-gray-600">Loading analytics data...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <p className="text-red-600 font-semibold mb-2">Error loading analytics data</p>
          <p className="text-gray-600">{error.message}</p>
        </div>
      </div>
    );
  }

  const hasData = data && data.length > 0;

  return (
    <div className="flex flex-col h-full">
      {/* Header with Export Button */}
      <div className="flex items-center justify-between p-4 border-b border-gray-200 bg-white">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Analytics Spreadsheet Preview</h1>
          <p className="text-sm text-gray-600 mt-1">
            Preview analytics data in Excel format before exporting
          </p>
        </div>
        <button
          onClick={handleExport}
          disabled={isExporting || !hasData}
          className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
        >
          {isExporting ? (
            <>
              <Loader2 className="h-5 w-5 animate-spin" />
              Exporting...
            </>
          ) : (
            <>
              <Download className="h-5 w-5" />
              Export to Excel
            </>
          )}
        </button>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto p-4 bg-gray-50">
        {hasData ? (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead className="bg-gray-100 sticky top-0">
                  {table.getHeaderGroups().map((headerGroup) => (
                    <tr key={headerGroup.id}>
                      {headerGroup.headers.map((header) => (
                        <th
                          key={header.id}
                          className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b-2 border-gray-300 cursor-pointer hover:bg-gray-200 transition-colors"
                          onClick={header.column.getToggleSortingHandler()}
                        >
                          <div className="flex items-center gap-2">
                            {flexRender(
                              header.column.columnDef.header,
                              header.getContext()
                            )}
                            {header.column.getIsSorted() ? (
                              header.column.getIsSorted() === 'desc' ? (
                                <ChevronDown className="h-4 w-4" />
                              ) : (
                                <ChevronUp className="h-4 w-4" />
                              )
                            ) : (
                              <ChevronsUpDown className="h-4 w-4 text-gray-400" />
                            )}
                          </div>
                        </th>
                      ))}
                    </tr>
                  ))}
                </thead>
                <tbody>
                  {table.getRowModel().rows.map((row, idx) => (
                    <tr
                      key={row.id}
                      className="hover:bg-blue-50 cursor-pointer transition-colors border-b border-gray-200"
                      onClick={() => setSelectedId(row.original.id)}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id} className="px-4 py-3 text-sm text-gray-900">
                          {flexRender(
                            cell.column.columnDef.cell,
                            cell.getContext()
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-64 bg-white rounded-lg border border-gray-200">
            <div className="text-center">
              <p className="text-gray-600 font-medium">No analytics data available</p>
              <p className="text-gray-500 text-sm mt-2">
                Complete analytics will appear here once processing is finished
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Pagination */}
      {hasData && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 bg-white">
          <div className="text-sm text-gray-600">
            Page {page + 1} • Showing {data.length} records
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
            >
              Previous
            </button>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={!data || data.length < pageSize}
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Detail Modal */}
      {selectedId && (
        <AnalyticsDetailModal
          analyticsId={selectedId}
          onClose={() => setSelectedId(null)}
        />
      )}
    </div>
  );
}
