import React, { useState } from 'react';
import { X, Info, Folder, File, ChevronRight, Layout, FileText } from 'lucide-react';

export function DocsDialog({ isOpen, onClose }) {
  const [activeTab, setActiveTab] = useState('general');
  const [fileStructureTab, setFileStructureTab] = useState('iso');
  const [showMultiPart, setShowMultiPart] = useState(false);

  if (!isOpen) return null;

  const renderFileTree = (items, level = 0) => {
    return (
      <div className="space-y-0.5">
        {items.map((item, index) => (
          <div key={index} style={{ paddingLeft: `${level * 12}px` }}>
            <div className={`flex items-center gap-1.5 text-xs py-0.5 ${item.ignored ? 'text-gray-500 italic' : 'text-gray-700'}`}>
              {item.type === 'folder' ? (
                <Folder className={`w-3.5 h-3.5 shrink-0 ${item.ignored ? 'text-gray-400 fill-gray-50' : 'text-blue-500 fill-blue-50'}`} />
              ) : (
                <File className={`w-3.5 h-3.5 shrink-0 ${item.ignored ? 'text-gray-400' : 'text-gray-400'}`} />
              )}
              <span className={`truncate ${item.type === 'folder' ? 'font-medium' : ''}`}>{item.name}</span>
              {item.note && <span className="text-[10px] text-gray-400 italic ml-1 shrink-0 whitespace-nowrap">- {item.note}</span>}
              {item.ignored && <span className="text-[10px] text-gray-500 italic ml-1 shrink-0 whitespace-nowrap">(ignored)</span>}
            </div>
            {item.children && renderFileTree(item.children, level + 1)}
          </div>
        ))}
      </div>
    );
  };

  const isoStructure = [
    {
      type: 'folder',
      name: 'FTP_Root',
      children: [
        {
          type: 'folder',
          name: showMultiPart ? 'Studio Keysborough 2024-10-09 11-06-51' : 'Studio Keysborough 2024-10-09 11-06-51',
          note: 'Session Folder',
          children: [
            {
              type: 'folder',
              name: 'Audio Source Files',
              ignored: true,
              children: [
                { type: 'file', name: 'Studio Keysborough... CAM 1 01.wav', ignored: true },
                { type: 'file', name: 'Studio Keysborough... CAM 2 01.wav', ignored: true },
                { type: 'file', name: '...' }
              ]
            },
            {
              type: 'folder',
              name: 'Video ISO Files',
              children: [
                { type: 'file', name: 'Studio Keysborough... CAM 1 01.mp4' },
                { type: 'file', name: 'Studio Keysborough... CAM 2 01.mp4' },
                ...(showMultiPart ? [
                  { type: 'file', name: 'Studio Keysborough... CAM 1 02.mp4' },
                  { type: 'file', name: 'Studio Keysborough... CAM 2 02.mp4' }
                ] : []),
                { type: 'file', name: '...' }
              ]
            },
            { type: 'file', name: 'Studio Keysborough... 01.mp4' },
            ...(showMultiPart ? [{ type: 'file', name: 'Studio Keysborough... 02.mp4' }] : []),
            { type: 'file', name: 'Studio Keysborough... .drp', ignored: true }
          ]
        }
      ]
    }
  ];

  const singleFileStructure = [
    {
      type: 'folder',
      name: 'FTP_Root',
      children: [
        { type: 'file', name: 'Studio Keysborough... 01.mp4', note: 'Program File' },
        { type: 'file', name: 'Studio Keysborough... CAM 1 01.mp4', note: 'ISO File' }
      ]
    }
  ];

  const destinationStructure = [
    {
      type: 'folder',
      name: 'Final_Destination',
      children: [
        {
          type: 'folder',
          name: '2024',
          children: [
            {
              type: 'folder',
              name: '10 - October',
              children: [
                {
                  type: 'folder',
                  name: '09 Wed October',
                  children: [
                    {
                      type: 'folder',
                      name: 'Source Files',
                      children: [
                        {
                          type: 'folder',
                          name: 'Studio Keysborough 2024-10-09 11-06-51 01',
                          children: [
                            { type: 'file', name: 'Studio Keysborough... CAM 1 01.mp4' },
                            { type: 'file', name: 'Studio Keysborough... CAM 2 01.mp4' },
                            { type: 'file', name: 'Studio Keysborough... 01.mp3' }
                          ]
                        },
                        ...(showMultiPart ? [{
                          type: 'folder',
                          name: 'Studio Keysborough 2024-10-09 11-06-51 02',
                          children: [
                            { type: 'file', name: 'Studio Keysborough... CAM 1 02.mp4' },
                            { type: 'file', name: 'Studio Keysborough... CAM 2 02.mp4' },
                            { type: 'file', name: 'Studio Keysborough... 02.mp3' }
                          ]
                        }] : [])
                      ]
                    },
                    { type: 'file', name: 'Studio Keysborough... 01.mp4' },
                    ...(showMultiPart ? [{ type: 'file', name: 'Studio Keysborough... 02.mp4' }] : [])
                  ]
                }
              ]
            }
          ]
        }
      ]
    }
  ];

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-2xl w-full max-w-4xl h-[80vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="h-14 bg-white border-b border-gray-200 flex items-center px-4 justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center">
              <Info className="w-5 h-5 text-blue-600" />
            </div>
            <h2 className="text-lg font-semibold text-gray-800">Documentation</h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-full transition-colors text-gray-500"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Sidebar */}
          <div className="w-64 bg-gray-50 border-r border-gray-200 flex flex-col p-4 gap-2 shrink-0">
            <button
              onClick={() => setActiveTab('general')}
              className={`flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors ${activeTab === 'general'
                ? 'bg-blue-50 text-blue-700'
                : 'text-gray-600 hover:bg-gray-100'
                }`}
            >
              <Layout className="w-4 h-4" />
              General Info
            </button>
            <button
              onClick={() => setActiveTab('files')}
              className={`flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors ${activeTab === 'files'
                ? 'bg-blue-50 text-blue-700'
                : 'text-gray-600 hover:bg-gray-100'
                }`}
            >
              <FileText className="w-4 h-4" />
              File Structure
            </button>
          </div>

          {/* Content Area */}
          <div className="flex-1 overflow-auto p-8">
            {activeTab === 'general' && (
              <div className="max-w-2xl space-y-6">
                <div>
                  <h3 className="text-xl font-bold text-gray-900 mb-4">Session Discovery Rules</h3>
                  <p className="text-gray-600 mb-6">
                    When grouping recordings into a session, the system uses a stable set of rules to pick the recording date and time. This prevents duplicate sessions when ISO files are discovered before the main Program output.
                  </p>

                  <div className="bg-blue-50 border border-blue-100 rounded-xl p-6">
                    <h4 className="font-semibold text-blue-900 mb-4">Priority Order</h4>
                    <ol className="space-y-4">
                      <li className="flex gap-3">
                        <div className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-200 text-blue-700 flex items-center justify-center text-sm font-bold">1</div>
                        <div>
                          <p className="font-medium text-gray-900">Program Filename Match</p>
                          <p className="text-sm text-gray-600">Prefer a Program output filename that matches known patterns.</p>
                        </div>
                      </li>
                      <li className="flex gap-3">
                        <div className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-200 text-blue-700 flex items-center justify-center text-sm font-bold">2</div>
                        <div>
                          <p className="font-medium text-gray-900">Any Filename Match</p>
                          <p className="text-sm text-gray-600">Otherwise, use any filename that matches a known pattern.</p>
                        </div>
                      </li>
                      <li className="flex gap-3">
                        <div className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-200 text-blue-700 flex items-center justify-center text-sm font-bold">3</div>
                        <div>
                          <p className="font-medium text-gray-900">Folder Name Parse</p>
                          <p className="text-sm text-gray-600">Parse it from the session folder name (e.g., "... 2025-08-06 11-23-49-A8").</p>
                        </div>
                      </li>
                      <li className="flex gap-3">
                        <div className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-200 text-blue-700 flex items-center justify-center text-sm font-bold">4</div>
                        <div>
                          <p className="font-medium text-gray-900">Earliest Timestamp</p>
                          <p className="text-sm text-gray-600">As a last resort, use the earliest modified timestamp among files.</p>
                        </div>
                      </li>
                    </ol>
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'files' && (
              <div className="max-w-3xl">
                <div className="mb-6">
                  <h3 className="text-xl font-bold text-gray-900">File Organization</h3>
                  <p className="text-gray-600 mt-2">
                    See how files are organized from the FTP server to their final destination.
                  </p>
                </div>

                {/* Sub-tabs */}
                <div className="flex gap-2 mb-8 bg-gray-100 p-1 rounded-lg w-fit">
                  <button
                    onClick={() => setFileStructureTab('iso')}
                    className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${fileStructureTab === 'iso'
                      ? 'bg-white text-gray-900 shadow-sm'
                      : 'text-gray-600 hover:text-gray-900'
                      }`}
                  >
                    ISO Folders
                  </button>
                  <button
                    onClick={() => setFileStructureTab('single')}
                    className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${fileStructureTab === 'single'
                      ? 'bg-white text-gray-900 shadow-sm'
                      : 'text-gray-600 hover:text-gray-900'
                      }`}
                  >
                    Single Files
                  </button>
                </div>

                {fileStructureTab === 'iso' && (
                  <div className="mb-6 flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="showMultiPart"
                      checked={showMultiPart}
                      onChange={(e) => setShowMultiPart(e.target.checked)}
                      className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                    />
                    <label htmlFor="showMultiPart" className="text-sm text-gray-700 select-none cursor-pointer">
                      Show multi-part session example (01, 02...)
                    </label>
                  </div>
                )}

                <div className="grid grid-cols-[1fr,auto,1fr] gap-4 items-start">
                  {/* Source */}
                  <div className="bg-gray-50 rounded-xl border border-gray-200 p-4">
                    <div className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">FTP Source</div>
                    {renderFileTree(fileStructureTab === 'iso' ? isoStructure : singleFileStructure)}
                  </div>

                  {/* Arrow */}
                  <div className="self-center text-gray-400 pt-8">
                    <ChevronRight className="w-6 h-6" />
                  </div>

                  {/* Destination */}
                  <div className="bg-blue-50 rounded-xl border border-blue-100 p-4">
                    <div className="text-xs font-bold text-blue-600 uppercase tracking-wider mb-3">Final Destination</div>
                    {renderFileTree(destinationStructure)}
                  </div>
                </div>

                <div className="mt-8 bg-yellow-50 border border-yellow-100 rounded-lg p-4">
                  <h4 className="font-medium text-yellow-800 mb-2">Organization Logic</h4>
                  <p className="text-sm text-yellow-700">
                    The system organizes sessions by date (Year / Month / Day). Program files are placed directly in the Day folder. ISO recordings and Audio files are grouped into a 'Source Files' subfolder, organized by session name.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
