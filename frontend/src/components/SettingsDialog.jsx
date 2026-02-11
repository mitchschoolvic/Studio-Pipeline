import { useState, useEffect, useMemo, useRef } from 'react';
import { Save, X, Folder, Server, CheckCircle, XCircle, Loader2, AlertCircle, Cloud, Zap, Trash2, Monitor, Brain, Database, RefreshCw, Wifi } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useSettings, useAiInfo, usePrompts, useWhisperSettings } from '../api/settings';
import { StatusOverlay } from './StatusOverlay';
import { NetworkSettingsTab } from './NetworkSettingsTab';



export function SettingsDialog({ isOpen, onClose }) {
  // React Query hooks - automatically fetch and cache data
  const queryClient = useQueryClient();
  const { data: settingsData, isLoading: settingsLoading, error: settingsError } = useSettings();
  const { data: aiInfo, isLoading: aiInfoLoading } = useAiInfo();
  const { data: aiPrompts, isLoading: promptsLoading } = usePrompts();
  const { data: whisperSettingsData, isLoading: whisperSettingsLoading } = useWhisperSettings();

  // Convert settings array to object for easier access
  const settings = useMemo(() => {
    if (!settingsData) return {};
    const settingsObj = {};
    settingsData.forEach(setting => {
      settingsObj[setting.key] = setting.value;
    });
    return settingsObj;
  }, [settingsData]);

  // Local state for edits (not saved yet)
  const [localSettings, setLocalSettings] = useState({});
  const [localAiPrompts, setLocalAiPrompts] = useState({ system_prompt: '', user_prompt: '' });
  const [localWhisperSettings, setLocalWhisperSettings] = useState({ prompt_words: '' });

  // Update local state when data loads
  useEffect(() => {
    if (settings) {
      setLocalSettings(settings);
      // Parse excluded folders from comma-separated string
      const excludedStr = settings.ftp_exclude_folders || '';
      setExcludedFolders(excludedStr ? excludedStr.split(',').map(f => f.trim()).filter(f => f) : []);
    }
  }, [settings]);

  useEffect(() => {
    if (aiPrompts) setLocalAiPrompts(aiPrompts);
  }, [aiPrompts]);

  useEffect(() => {
    if (whisperSettingsData?.settings) {
      setLocalWhisperSettings(whisperSettingsData.settings);
    }
  }, [whisperSettingsData]);

  // Other state
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);
  const [connectionStatus, setConnectionStatus] = useState(null);
  const [validationStatus, setValidationStatus] = useState(null);
  const [validationErrors, setValidationErrors] = useState({});
  const [activeTab, setActiveTab] = useState('ftp');
  const [excludedFolderInput, setExcludedFolderInput] = useState('');
  const [excludedFolders, setExcludedFolders] = useState([]);

  // Status Overlay State
  const [statusOverlay, setStatusOverlay] = useState({ visible: false, message: '', type: 'success' });
  const statusTimeoutRef = useRef(null);

  const showStatus = (message, type = 'success') => {
    if (statusTimeoutRef.current) clearTimeout(statusTimeoutRef.current);
    setStatusOverlay({ visible: true, message, type });
    statusTimeoutRef.current = setTimeout(() => {
      setStatusOverlay(prev => ({ ...prev, visible: false }));
    }, 2000); // Hide after 2 seconds
  };

  // GUI preferences (stored in localStorage)
  const [guiPreferences, setGuiPreferences] = useState(() => {
    const saved = localStorage.getItem('guiPreferences');
    return saved ? JSON.parse(saved) : { showQueueNumbers: false };
  });

  // Combined loading state
  const loading = settingsLoading || aiInfoLoading || promptsLoading || whisperSettingsLoading;

  const handleChange = (key, value) => {
    setLocalSettings(prev => ({ ...prev, [key]: value }));
    // Clear validation error for this field
    setValidationErrors(prev => ({ ...prev, [key]: null }));
    // Clear connection status when FTP settings change
    if (key.startsWith('ftp_') || key === 'source_path') {
      setConnectionStatus(null);
    }
  };

  // Auto-save handler for toggles
  const handleAutoSave = async (key, value) => {
    // Update local state first for immediate feedback
    handleChange(key, value);

    try {
      const response = await fetch(`/api/settings/${key}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key, value: String(value) })
      });

      if (!response.ok) {
        throw new Error(`Failed to update ${key}`);
      }

      // Invalidate cache
      queryClient.invalidateQueries({ queryKey: ['settings-main'] });

      // Show success overlay
      showStatus('Setting saved');
    } catch (err) {
      console.error(`Error auto-saving ${key}:`, err);
      showStatus('Failed to save setting', 'error');
    }
  };

  const handleGuiPreferenceChange = (key, value) => {
    const newPreferences = { ...guiPreferences, [key]: value };
    setGuiPreferences(newPreferences);
    localStorage.setItem('guiPreferences', JSON.stringify(newPreferences));
    // Dispatch custom event to notify App.jsx of preference change
    window.dispatchEvent(new CustomEvent('guiPreferencesChanged', { detail: newPreferences }));
    showStatus('Preference saved');
  };

  const handlePromptChange = (key, value) => {
    setLocalAiPrompts(prev => ({ ...prev, [key]: value }));
  };

  const handleWhisperSettingChange = (key, value) => {
    setLocalWhisperSettings(prev => ({ ...prev, [key]: value }));
  };

  const handleExcludedFolderInput = (value) => {
    setExcludedFolderInput(value);

    // Check if comma was entered
    if (value.includes(',')) {
      // Split by comma and add non-empty folders
      const newFolders = value.split(',').map(f => f.trim()).filter(f => f);
      const updatedFolders = [...new Set([...excludedFolders, ...newFolders])]; // Remove duplicates
      setExcludedFolders(updatedFolders);
      setExcludedFolderInput(''); // Clear input

      // Update localSettings with comma-separated string
      handleChange('ftp_exclude_folders', updatedFolders.join(','));
    }
  };

  const removeExcludedFolder = (folderToRemove) => {
    const updatedFolders = excludedFolders.filter(f => f !== folderToRemove);
    setExcludedFolders(updatedFolders);

    // Update localSettings with comma-separated string
    handleChange('ftp_exclude_folders', updatedFolders.join(','));
  };

  const addExcludedFolder = () => {
    const trimmed = excludedFolderInput.trim();
    if (trimmed && !excludedFolders.includes(trimmed)) {
      const updatedFolders = [...excludedFolders, trimmed];
      setExcludedFolders(updatedFolders);
      setExcludedFolderInput('');

      // Update localSettings with comma-separated string
      handleChange('ftp_exclude_folders', updatedFolders.join(','));
    }
  };

  const saveAiPromptsApi = async (prompts) => {
    const response = await fetch('/api/analytics/prompts', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(prompts)
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || 'Failed to update prompts');
    }

    return response.json();
  };

  const saveWhisperSettingsApi = async (settings) => {
    const response = await fetch('/api/analytics/whisper-settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ settings })
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || 'Failed to update Whisper settings');
    }

    return response.json();
  };

  const saveAiPrompts = async () => {
    try {
      setSaving(true);
      setError(null);
      setSuccessMessage(null);

      await saveAiPromptsApi(localAiPrompts);

      // Invalidate cache to force refresh
      queryClient.invalidateQueries({ queryKey: ['settings-prompts'] });

      setSuccessMessage('AI prompts saved successfully!');
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      console.error('Error saving AI prompts:', err);
      setError(err.message || 'Failed to save AI prompts');
    } finally {
      setSaving(false);
    }
  };

  const saveWhisperSettings = async () => {
    try {
      setSaving(true);
      setError(null);
      setSuccessMessage(null);

      await saveWhisperSettingsApi(localWhisperSettings);

      // Invalidate cache to force refresh
      queryClient.invalidateQueries({ queryKey: ['settings-whisper'] });

      setSuccessMessage('Whisper settings saved successfully!');
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      console.error('Error saving Whisper settings:', err);
      setError(err.message || 'Failed to save Whisper settings');
    } finally {
      setSaving(false);
    }
  };

  const validateSettings = () => {
    const errors = {};

    // Validate FTP host
    if (!localSettings.ftp_host || !localSettings.ftp_host.trim()) {
      errors.ftp_host = 'FTP host is required';
    }

    // Validate port
    const port = parseInt(localSettings.ftp_port);
    if (isNaN(port) || port < 1 || port > 65535) {
      errors.ftp_port = 'Port must be between 1 and 65535';
    }

    // Validate username if not anonymous
    const isAnonymous = localSettings.ftp_anonymous === 'true';
    if (!isAnonymous && (!localSettings.ftp_username || !localSettings.ftp_username.trim())) {
      errors.ftp_username = 'Username required for non-anonymous login';
    }

    // Validate source path
    if (!localSettings.source_path || !localSettings.source_path.trim()) {
      errors.source_path = 'Source path is required';
    }

    // Validate output path
    if (!localSettings.output_path || !localSettings.output_path.trim()) {
      errors.output_path = 'Output path is required';
    }

    // Validate bitrate threshold
    const bitrateThreshold = parseFloat(localSettings.bitrate_threshold_kbps);
    if (isNaN(bitrateThreshold) || bitrateThreshold < 0 || bitrateThreshold > 50000) {
      errors.bitrate_threshold_kbps = 'Bitrate threshold must be between 0 and 50000 kbps';
    }

    // Validate auto-deletion age if enabled
    if (localSettings.auto_delete_enabled === 'true') {
      const ageMonths = parseInt(localSettings.auto_delete_age_months);
      if (isNaN(ageMonths) || ageMonths < 1 || ageMonths > 120) {
        errors.auto_delete_age_months = 'Age must be between 1 and 120 months';
      }
    }

    // Validate external audio export path if enabled
    if (localSettings.external_audio_export_enabled === 'true') {
      if (!localSettings.external_audio_export_path || !localSettings.external_audio_export_path.trim()) {
        errors.external_audio_export_path = 'External audio path is required when export is enabled';
      }
    }

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const testConnection = async () => {
    if (!validateSettings()) {
      setError('Please fix validation errors before testing connection');
      return;
    }

    try {
      setTesting(true);
      setConnectionStatus(null);
      setError(null);

      const response = await fetch('/api/settings/test-connection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ftp_host: localSettings.ftp_host,
          ftp_port: localSettings.ftp_port,
          ftp_anonymous: localSettings.ftp_anonymous || 'true',
          ftp_username: localSettings.ftp_username || '',
          ftp_password_encrypted: localSettings.ftp_password_encrypted || '',
          source_path: localSettings.source_path
        })
      });

      const result = await response.json();
      setConnectionStatus(result);
    } catch (err) {
      console.error('Error testing connection:', err);
      setConnectionStatus({
        success: false,
        message: 'Failed to test connection',
        details: err.message
      });
    } finally {
      setTesting(false);
    }
  };

  const validateAllSettings = async () => {
    try {
      setValidating(true);
      setValidationStatus(null);
      setError(null);

      const response = await fetch('/api/settings/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });

      const result = await response.json();
      setValidationStatus(result);

      // Show error if validation failed
      if (!result.overall_valid) {
        const errors = [];
        if (!result.ftp_connection.valid) errors.push(`FTP: ${result.ftp_connection.message}`);
        if (!result.temp_path.valid) errors.push(`Temp Path: ${result.temp_path.message}`);
        if (!result.output_path.valid) errors.push(`Output Path: ${result.output_path.message}`);
        if (result.external_audio_path && !result.external_audio_path.valid) {
          errors.push(`External Audio: ${result.external_audio_path.message}`);
        }
        setError(`Configuration invalid:\n${errors.join('\n')}`);
      }
    } catch (err) {
      console.error('Error validating settings:', err);
      setError(`Failed to validate settings: ${err.message}`);
    } finally {
      setValidating(false);
    }
  };

  const handleSave = async () => {
    if (!validateSettings()) {
      setError('Please fix validation errors before saving');
      return;
    }

    try {
      setSaving(true);
      setError(null);
      setSuccessMessage(null);

      // 1. Save Main Settings
      for (const [key, value] of Object.entries(localSettings)) {
        const response = await fetch(`/api/settings/${key}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key, value: String(value) })
        });

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || `Failed to update ${key}`);
        }
      }

      // 2. Save AI Settings (if enabled)
      if (aiInfo && aiInfo.enabled) {
        // Save Prompts
        await saveAiPromptsApi(localAiPrompts);

        // Save Whisper Settings
        await saveWhisperSettingsApi(localWhisperSettings);

        // Invalidate AI queries
        queryClient.invalidateQueries({ queryKey: ['settings-prompts'] });
        queryClient.invalidateQueries({ queryKey: ['settings-whisper'] });
      }

      // Invalidate main settings cache
      queryClient.invalidateQueries({ queryKey: ['settings-main'] });

      // Settings will be automatically refetched by React Query
      showStatus('All settings saved successfully!');
    } catch (err) {
      console.error('Error saving settings:', err);
      setError(err.message || 'Failed to save settings');
      showStatus('Failed to save settings', 'error');
    } finally {
      setSaving(false);
    }
  };

  const fileInputRef = useRef(null);
  const [dbStats, setDbStats] = useState(null);
  const [clearingDatabase, setClearingDatabase] = useState(false);
  const [resettingSettings, setResettingSettings] = useState(false);

  useEffect(() => {
    if (isOpen && activeTab === 'paths') {
      fetch('/api/settings/database/stats')
        .then(res => res.json())
        .then(data => setDbStats(data))
        .catch(err => console.error('Failed to fetch DB stats:', err));
    }
  }, [isOpen, activeTab]);

  const handleExportDatabase = () => {
    window.open('/api/settings/database/export', '_blank');
  };

  const handleRestoreDatabase = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    try {
      setSaving(true);
      setError(null);
      setSuccessMessage(null);

      // First, inspect the database to show stats
      const inspectFormData = new FormData();
      inspectFormData.append('file', file);

      const inspectResponse = await fetch('/api/settings/database/inspect', {
        method: 'POST',
        body: inspectFormData,
      });

      if (!inspectResponse.ok) {
        throw new Error('Failed to inspect database file');
      }

      const inspectResult = await inspectResponse.json();

      if (!inspectResult.valid) {
        throw new Error(inspectResult.message || 'Invalid database file');
      }

      const confirmMessage = `WARNING: You are about to restore a database with:\n\n` +
        `• ${inspectResult.sessions} Sessions\n` +
        `• ${inspectResult.thumbnails} Thumbnails\n\n` +
        `This will OVERWRITE your current database (${dbStats ? `${dbStats.sessions} sessions, ${dbStats.thumbnails} thumbnails` : 'unknown'}).\n\n` +
        `This action cannot be undone. Are you sure you want to proceed?`;

      if (!window.confirm(confirmMessage)) {
        event.target.value = null;
        setSaving(false);
        return;
      }

      // Proceed with restore
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch('/api/settings/database/restore', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to restore database');
      }

      const result = await response.json();
      setSuccessMessage(`Database restored successfully! Backup created: ${result.backup_created}`);

      // Reload page after short delay to reflect restored data
      setTimeout(() => {
        window.location.reload();
      }, 2000);

    } catch (err) {
      console.error('Error restoring database:', err);
      setError(err.message || 'Failed to restore database');
      event.target.value = null; // Reset input on error
    } finally {
      setSaving(false);
      if (event.target.value) event.target.value = null; // Ensure reset
    }
  };

  const handleClearDatabase = async () => {
    const confirmMessage = `⚠️ DESTRUCTIVE ACTION WARNING ⚠️\n\n` +
      `You are about to DELETE ALL DATA from the database:\n\n` +
      `• ${dbStats ? dbStats.sessions : '?'} Sessions\n` +
      `• ${dbStats ? dbStats.thumbnails : '?'} Thumbnails\n` +
      `• All files, jobs, and events\n\n` +
      `An automatic backup will be created, but this action will:\n` +
      `✗ Remove all session history\n` +
      `✗ Clear all processing queues\n` +
      `✗ Delete all analytics data\n` +
      `✓ Keep your settings intact\n\n` +
      `Type 'DELETE' below to confirm you understand this action cannot be undone.`;

    const userInput = window.prompt(confirmMessage);

    if (userInput !== 'DELETE') {
      if (userInput !== null) {
        setError('Database clear cancelled - confirmation text did not match');
      }
      return;
    }

    try {
      setClearingDatabase(true);
      setError(null);
      setSuccessMessage(null);

      const response = await fetch('/api/settings/database/clear', {
        method: 'POST',
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to clear database');
      }

      const result = await response.json();

      setSuccessMessage(
        `Database cleared successfully!\n` +
        `Deleted: ${result.deleted.sessions} sessions, ${result.deleted.files} files\n` +
        `Backup: ${result.backup_created}`
      );

      // Refresh database stats
      fetch('/api/settings/database/stats')
        .then(res => res.json())
        .then(data => setDbStats(data))
        .catch(err => console.error('Failed to fetch DB stats:', err));

      // Reload page after short delay
      setTimeout(() => {
        window.location.reload();
      }, 2000);

    } catch (err) {
      console.error('Error clearing database:', err);
      setError(err.message || 'Failed to clear database');
    } finally {
      setClearingDatabase(false);
    }
  };

  const handleResetSettings = async () => {
    const confirmMessage = `⚠️ RESET SETTINGS WARNING ⚠️\n\n` +
      `You are about to reset ALL settings to their default values:\n\n` +
      `✗ FTP configuration will be reset\n` +
      `✗ Path settings will be reset\n` +
      `✗ Processing settings will be reset\n` +
      `✗ All custom configurations will be lost\n\n` +
      `✓ Your database (sessions, files) will NOT be affected\n\n` +
      `Are you sure you want to continue?`;

    if (!window.confirm(confirmMessage)) {
      return;
    }

    try {
      setResettingSettings(true);
      setError(null);
      setSuccessMessage(null);

      const response = await fetch('/api/settings/reset', {
        method: 'POST',
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to reset settings');
      }

      const result = await response.json();

      setSuccessMessage(`Settings reset successfully! ${result.reset_count} settings restored to defaults.`);

      // Reload page after short delay to reflect new settings
      setTimeout(() => {
        window.location.reload();
      }, 2000);

    } catch (err) {
      console.error('Error resetting settings:', err);
      setError(err.message || 'Failed to reset settings');
    } finally {
      setResettingSettings(false);
    }
  };

  const [populatingCache, setPopulatingCache] = useState(false);

  const handlePopulateCache = async () => {
    try {
      setPopulatingCache(true);
      const response = await fetch('/api/analytics/settings/cache/update', {
        method: 'POST',
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to update cache');
      }

      // Show success toast
      const stats = data.stats;
      const message = `Cache updated: ${stats.processed} added, ${stats.skipped} skipped, ${stats.failed} failed`;

      // We can use a simple alert or console log if no toast system is readily available in this scope,
      // but ideally we'd use the existing notification system if present.
      // Assuming there might be a toast/notification mechanism, but for now we'll rely on the button state reset
      // and maybe a temporary success indicator or just log it.
      console.log(message);

      // If there's a way to show a toast from here, we should use it.
      // For now, let's just alert for visibility as requested in the plan.
      alert(message);

    } catch (err) {
      console.error('Failed to populate cache:', err);
      alert(`Error: ${err.message}`);
    } finally {
      setPopulatingCache(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col relative"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Status Overlay */}
        <StatusOverlay
          message={statusOverlay.message}
          type={statusOverlay.type}
          isVisible={statusOverlay.visible}
          onHide={() => setStatusOverlay(prev => ({ ...prev, visible: false }))}
        />
        {/* macOS-style Title Bar */}
        <div className="h-12 bg-gradient-to-b from-gray-100 to-gray-200 border-b border-gray-300 flex items-center px-4 justify-between rounded-t-lg">
          <div className="flex items-center gap-2">
            <div className="flex gap-2">
              <button
                onClick={onClose}
                className="w-3 h-3 rounded-full bg-red-500 hover:bg-red-600 transition-colors"
                title="Close"
              />
              <div className="w-3 h-3 rounded-full bg-yellow-500 opacity-50" />
              <div className="w-3 h-3 rounded-full bg-green-500 opacity-50" />
            </div>
          </div>
          <div className="text-sm font-medium text-gray-700">Pipeline Settings</div>
          <div className="w-5" />
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden flex flex-col">
          {/* Tabs */}
          <div className="border-b border-gray-200 px-6">
            <nav className="flex gap-6" aria-label="Tabs">
              <button
                onClick={() => setActiveTab('ftp')}
                className={`py-3 px-1 border-b-2 font-medium text-sm flex items-center gap-2 transition-colors ${activeTab === 'ftp'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
              >
                <Server className="w-4 h-4" />
                FTP Server
              </button>
              <button
                onClick={() => setActiveTab('paths')}
                className={`py-3 px-1 border-b-2 font-medium text-sm flex items-center gap-2 transition-colors ${activeTab === 'paths'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
              >
                <Folder className="w-4 h-4" />
                Paths & Export
              </button>
              <button
                onClick={() => setActiveTab('workers')}
                className={`py-3 px-1 border-b-2 font-medium text-sm flex items-center gap-2 transition-colors ${activeTab === 'workers'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
              >
                <Zap className="w-4 h-4" />
                Processing
              </button>
              <button
                onClick={() => setActiveTab('cloud')}
                className={`py-3 px-1 border-b-2 font-medium text-sm flex items-center gap-2 transition-colors ${activeTab === 'cloud'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
              >
                <Cloud className="w-4 h-4" />
                Cloud Sync
              </button>
              <button
                onClick={() => setActiveTab('cleanup')}
                className={`py-3 px-1 border-b-2 font-medium text-sm flex items-center gap-2 transition-colors ${activeTab === 'cleanup'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
              >
                <Trash2 className="w-4 h-4" />
                Cleanup
              </button>
              <button
                onClick={() => setActiveTab('gui')}
                className={`py-3 px-1 border-b-2 font-medium text-sm flex items-center gap-2 transition-colors ${activeTab === 'gui'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
              >
                <Monitor className="w-4 h-4" />
                GUI
              </button>
              <button
                onClick={() => setActiveTab('network')}
                className={`py-3 px-1 border-b-2 font-medium text-sm flex items-center gap-2 transition-colors ${activeTab === 'network'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
              >
                <Wifi className="w-4 h-4" />
                Network
              </button>
              {aiInfo && aiInfo.enabled && (
                <button
                  onClick={() => setActiveTab('ai')}
                  className={`py-3 px-1 border-b-2 font-medium text-sm flex items-center gap-2 transition-colors ${activeTab === 'ai'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                    }`}
                >
                  <Brain className="w-4 h-4" />
                  AI
                </button>
              )}
            </nav>
          </div>

          {/* Tab Content */}
          <div className="flex-1 overflow-auto p-6">
            {loading ? (
              <div className="flex items-center justify-center h-64">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
              </div>
            ) : (
              <div className="space-y-6">
                {/* Error/Success Messages */}
                {error && (
                  <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded flex items-start gap-2">
                    <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                    <span>{error}</span>
                  </div>
                )}
                {successMessage && (
                  <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded flex items-start gap-2">
                    <CheckCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                    <span>{successMessage}</span>
                  </div>
                )}

                {/* Connection Status */}
                {connectionStatus && activeTab === 'ftp' && (
                  <div className={`border px-4 py-3 rounded flex items-start gap-2 ${connectionStatus.success
                    ? 'bg-green-50 border-green-200 text-green-700'
                    : 'bg-yellow-50 border-yellow-200 text-yellow-700'
                    }`}>
                    {connectionStatus.success ? (
                      <CheckCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                    ) : (
                      <XCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                    )}
                    <div>
                      <div className="font-medium">{connectionStatus.message}</div>
                      {connectionStatus.details && (
                        <div className="text-sm mt-1">{connectionStatus.details}</div>
                      )}
                    </div>
                  </div>
                )}

                {/* FTP Settings Tab */}
                {activeTab === 'ftp' && (
                  <div>
                    <div className="flex items-center gap-2 mb-4">
                      <Server className="w-5 h-5 text-blue-600" />
                      <h3 className="text-lg font-semibold text-gray-800">FTP Server Settings</h3>
                    </div>
                    <div className="space-y-4 bg-gray-50 p-4 rounded-lg">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          FTP Host <span className="text-red-500">*</span>
                        </label>
                        <input
                          type="text"
                          value={localSettings.ftp_host || ''}
                          onChange={(e) => handleChange('ftp_host', e.target.value)}
                          className={`w-full px-3 py-2 border rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900 ${validationErrors.ftp_host ? 'border-red-300' : 'border-gray-300'
                            }`}
                          placeholder="atem.studio.local"
                        />
                        {validationErrors.ftp_host && (
                          <p className="text-xs text-red-600 mt-1">{validationErrors.ftp_host}</p>
                        )}
                        <p className="text-xs text-gray-500 mt-1">
                          Hostname or IP address of the ATEM FTP server
                        </p>
                      </div>

                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">
                            Port <span className="text-red-500">*</span>
                          </label>
                          <input
                            type="number"
                            value={localSettings.ftp_port || '21'}
                            onChange={(e) => handleChange('ftp_port', e.target.value)}
                            className={`w-full px-3 py-2 border rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900 ${validationErrors.ftp_port ? 'border-red-300' : 'border-gray-300'
                              }`}
                          />
                          {validationErrors.ftp_port && (
                            <p className="text-xs text-red-600 mt-1">{validationErrors.ftp_port}</p>
                          )}
                        </div>

                        <div className="flex items-center pt-6">
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={localSettings.ftp_anonymous === 'true'}
                              onChange={(e) => {
                                handleAutoSave('ftp_anonymous', e.target.checked ? 'true' : 'false');
                                if (e.target.checked) {
                                  handleAutoSave('ftp_username', 'anonymous');
                                }
                              }}
                              className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                            />
                            <span className="text-sm font-medium text-gray-700">Anonymous Login</span>
                          </label>
                        </div>
                      </div>

                      {settings.ftp_anonymous !== 'true' && (
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">
                              Username <span className="text-red-500">*</span>
                            </label>
                            <input
                              type="text"
                              value={localSettings.ftp_username || ''}
                              onChange={(e) => handleChange('ftp_username', e.target.value)}
                              className={`w-full px-3 py-2 border rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900 ${validationErrors.ftp_username ? 'border-red-300' : 'border-gray-300'
                                }`}
                              placeholder="studio_user"
                            />
                            {validationErrors.ftp_username && (
                              <p className="text-xs text-red-600 mt-1">{validationErrors.ftp_username}</p>
                            )}
                          </div>

                          <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">
                              Password
                            </label>
                            <input
                              type="password"
                              value={localSettings.ftp_password_encrypted || ''}
                              onChange={(e) => handleChange('ftp_password_encrypted', e.target.value)}
                              className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900"
                              placeholder="••••••••"
                            />
                          </div>
                        </div>
                      )}

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Source Path (on FTP server) <span className="text-red-500">*</span>
                        </label>
                        <input
                          type="text"
                          value={localSettings.source_path || ''}
                          onChange={(e) => handleChange('source_path', e.target.value)}
                          className={`w-full px-3 py-2 border rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900 ${validationErrors.source_path ? 'border-red-300' : 'border-gray-300'
                            }`}
                          placeholder="/ATEM/recordings"
                        />
                        {validationErrors.source_path && (
                          <p className="text-xs text-red-600 mt-1">{validationErrors.source_path}</p>
                        )}
                        <p className="text-xs text-gray-500 mt-1">
                          Directory path where recordings are stored on the FTP server
                        </p>
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Exclude Folders
                        </label>
                        <input
                          type="text"
                          value={excludedFolderInput}
                          onChange={(e) => handleExcludedFolderInput(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault();
                              addExcludedFolder();
                            }
                          }}
                          className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900"
                          placeholder="Enter folder names separated by commas (e.g., TEST, BACKUP)"
                        />
                        <p className="text-xs text-gray-500 mt-1">
                          Folders to exclude from scanning. Type a name and press comma or Enter to add.
                        </p>

                        {/* Display excluded folders as badges */}
                        {excludedFolders.length > 0 && (
                          <div className="flex flex-wrap gap-2 mt-3">
                            {excludedFolders.map((folder, index) => (
                              <span
                                key={index}
                                className="inline-flex items-center gap-1.5 px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm font-medium"
                              >
                                {folder}
                                <button
                                  onClick={() => removeExcludedFolder(folder)}
                                  className="hover:bg-blue-200 rounded-full p-0.5 transition-colors"
                                  title={`Remove ${folder}`}
                                >
                                  <X className="w-3.5 h-3.5" />
                                </button>
                              </span>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Campus Name */}
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Campus Name
                        </label>
                        <input
                          type="text"
                          value={localSettings.campus || 'Keysborough'}
                          onChange={(e) => handleChange('campus', e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900"
                          placeholder="Keysborough"
                        />
                        <p className="text-xs text-gray-500 mt-1">
                          Campus name to assign to new sessions discovered from this FTP server
                        </p>
                      </div>

                      {/* Test Connection Button */}
                      <div className="pt-2">
                        <button
                          onClick={testConnection}
                          disabled={testing}
                          className="px-4 py-2 bg-blue-100 hover:bg-blue-200 text-blue-700 rounded font-medium flex items-center gap-2 transition-colors disabled:opacity-50"
                        >
                          {testing ? (
                            <>
                              <Loader2 className="w-4 h-4 animate-spin" />
                              Testing Connection...
                            </>
                          ) : (
                            <>
                              <Server className="w-4 h-4" />
                              Test FTP Connection
                            </>
                          )}
                        </button>
                      </div>

                      {/* Pause Processing Toggle */}
                      <div className="mt-4">
                        <label className="flex items-center gap-3 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={localSettings.pause_processing === 'true'}
                            onChange={(e) => handleAutoSave('pause_processing', e.target.checked ? 'true' : 'false')}
                            className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                          />
                          <div>
                            <div className="text-sm font-medium text-gray-700">Pause Processing Queue</div>
                            <div className="text-xs text-gray-500">When enabled, new PROCESS jobs will not start. Discovery and copy continue to run; processing will resume when disabled.</div>
                          </div>
                        </label>
                      </div>

                    </div>
                  </div>
                )}

                {/* Paths & Export Tab */}
                {activeTab === 'paths' && (
                  <div>
                    <div className="flex items-center gap-2 mb-4">
                      <Folder className="w-5 h-5 text-blue-600" />
                      <h3 className="text-lg font-semibold text-gray-800">Local Paths</h3>
                    </div>
                    <div className="space-y-4 bg-gray-50 p-4 rounded-lg">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Temporary Processing Path
                        </label>
                        <input
                          type="text"
                          value={localSettings.temp_path || ''}
                          onChange={(e) => handleChange('temp_path', e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900"
                          placeholder="~/Documents/StudioPipeline/temp"
                        />
                        <p className="text-xs text-gray-500 mt-1">
                          Where files are copied and processed before final organization
                        </p>
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Final Output Path <span className="text-red-500">*</span>
                        </label>
                        <input
                          type="text"
                          value={localSettings.output_path || ''}
                          onChange={(e) => handleChange('output_path', e.target.value)}
                          className={`w-full px-3 py-2 border rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900 ${validationErrors.output_path ? 'border-red-300' : 'border-gray-300'
                            }`}
                          placeholder="~/Videos/StudioPipeline"
                        />
                        {validationErrors.output_path && (
                          <p className="text-xs text-red-600 mt-1">{validationErrors.output_path}</p>
                        )}
                        <p className="text-xs text-gray-500 mt-1">
                          Final destination for processed videos (organized by session/date)
                        </p>
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Analytics/Excel Export Path
                        </label>
                        <input
                          type="text"
                          value={localSettings.analytics_output_path || ''}
                          onChange={(e) => handleChange('analytics_output_path', e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900"
                          placeholder="~/Documents/Analytics"
                        />
                        <p className="text-xs text-gray-500 mt-1">
                          Directory for Excel exports (analytics.xlsx). Leave blank to use: [Final Output Path]/analytics
                        </p>
                      </div>

                    </div>

                    {/* Database Management Section */}
                    <div className="mt-6">
                      <div className="flex items-center gap-2 mb-4">
                        <Database className="w-5 h-5 text-blue-600" />
                        <h3 className="text-lg font-semibold text-gray-800">Database Management</h3>
                      </div>
                      <div className="bg-gray-50 p-4 rounded-lg space-y-4">
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="font-medium text-gray-700">Export Database</div>
                            <div className="text-xs text-gray-500">
                              Download a backup of the current database configuration and history.
                              {dbStats && (
                                <span className="block mt-1 text-blue-600">
                                  Contains {dbStats.sessions} sessions and {dbStats.thumbnails} thumbnails.
                                </span>
                              )}
                            </div>
                          </div>
                          <button
                            onClick={handleExportDatabase}
                            className="px-3 py-1.5 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 rounded text-sm font-medium flex items-center gap-2 transition-colors shadow-sm"
                          >
                            <Database className="w-4 h-4" />
                            Export Backup
                          </button>
                        </div>

                        <div className="border-t border-gray-200 pt-4 flex items-center justify-between">
                          <div>
                            <div className="font-medium text-gray-700">Restore Database</div>
                            <div className="text-xs text-gray-500">Restore from a previous backup file. <span className="text-red-600 font-medium">Warning: Overwrites current data.</span></div>
                          </div>
                          <div>
                            <input
                              type="file"
                              ref={fileInputRef}
                              onChange={handleRestoreDatabase}
                              accept=".db"
                              className="hidden"
                            />
                            <button
                              onClick={() => fileInputRef.current?.click()}
                              disabled={saving}
                              className="px-3 py-1.5 bg-white border border-red-200 hover:bg-red-50 text-red-700 rounded text-sm font-medium flex items-center gap-2 transition-colors shadow-sm"
                            >
                              <Database className="w-4 h-4" />
                              Restore Backup
                            </button>
                          </div>
                        </div>

                        <div className="border-t border-gray-200 pt-4 flex items-center justify-between">
                          <div>
                            <div className="font-medium text-gray-700">Clear Database</div>
                            <div className="text-xs text-gray-500">Delete all sessions, files, and processing data. <span className="text-red-600 font-medium">Destructive! Creates backup first.</span></div>
                          </div>
                          <button
                            onClick={handleClearDatabase}
                            disabled={clearingDatabase || saving}
                            className="px-3 py-1.5 bg-white border border-orange-300 hover:bg-orange-50 text-orange-700 rounded text-sm font-medium flex items-center gap-2 transition-colors shadow-sm"
                          >
                            {clearingDatabase ? (
                              <>
                                <Loader2 className="w-4 h-4 animate-spin" />
                                Clearing...
                              </>
                            ) : (
                              <>
                                <Trash2 className="w-4 h-4" />
                                Clear All Data
                              </>
                            )}
                          </button>
                        </div>
                      </div>
                    </div>

                    {/* Settings Management Section */}
                    <div className="mt-6">
                      <div className="flex items-center gap-2 mb-4">
                        <Monitor className="w-5 h-5 text-blue-600" />
                        <h3 className="text-lg font-semibold text-gray-800">Settings Management</h3>
                      </div>
                      <div className="bg-gray-50 p-4 rounded-lg space-y-4">
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="font-medium text-gray-700">Reset All Settings</div>
                            <div className="text-xs text-gray-500">
                              Restore all configuration settings to their default values. Database content is preserved.
                            </div>
                          </div>
                          <button
                            onClick={handleResetSettings}
                            disabled={resettingSettings || saving}
                            className="px-3 py-1.5 bg-white border border-blue-200 hover:bg-blue-50 text-blue-700 rounded text-sm font-medium flex items-center gap-2 transition-colors shadow-sm"
                          >
                            {resettingSettings ? (
                              <>
                                <Loader2 className="w-4 h-4 animate-spin" />
                                Resetting...
                              </>
                            ) : (
                              <>
                                <Server className="w-4 h-4" />
                                Reset to Defaults
                              </>
                            )}
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Processing Tab */}
                {activeTab === 'workers' && (
                  <div>
                    <div className="flex items-center gap-2 mb-4">
                      <Zap className="w-5 h-5 text-blue-600" />
                      <h3 className="text-lg font-semibold text-gray-800">Worker Configuration</h3>
                    </div>
                    <div className="space-y-4 bg-gray-50 p-4 rounded-lg">
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">
                            Max Concurrent Copies
                          </label>
                          <input
                            type="number"
                            min="1"
                            max="10"
                            value={localSettings.max_concurrent_copy || '1'}
                            onChange={(e) => handleAutoSave('max_concurrent_copy', e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900"
                          />
                          <p className="text-xs text-gray-500 mt-1">
                            Number of files to download simultaneously (1-10)
                          </p>
                        </div>

                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">
                            Max Concurrent Processing
                          </label>
                          <input
                            type="number"
                            min="1"
                            max="10"
                            value={localSettings.max_concurrent_process || '1'}
                            onChange={(e) => handleAutoSave('max_concurrent_process', e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900"
                          />
                          <p className="text-xs text-gray-500 mt-1">
                            Number of files to process simultaneously (1-10, CPU intensive)
                          </p>
                        </div>
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Bitrate Threshold (kbps)
                        </label>
                        <input
                          type="number"
                          min="0"
                          max="50000"
                          step="100"
                          value={localSettings.bitrate_threshold_kbps || '500'}
                          onChange={(e) => handleChange('bitrate_threshold_kbps', e.target.value)}
                          className={`w-full px-3 py-2 border rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900 ${validationErrors.bitrate_threshold_kbps ? 'border-red-300' : 'border-gray-300'
                            }`}
                        />
                        {validationErrors.bitrate_threshold_kbps && (
                          <p className="text-xs text-red-600 mt-1">{validationErrors.bitrate_threshold_kbps}</p>
                        )}
                        <p className="text-xs text-gray-500 mt-1">
                          Files with bitrate below this threshold will be marked as empty (default: 500 kbps)
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Cloud Sync Tab */}
                {activeTab === 'cloud' && (
                  <div>
                    <div className="flex items-center gap-2 mb-4">
                      <Cloud className="w-5 h-5 text-blue-600" />
                      <h3 className="text-lg font-semibold text-gray-800">Cloud Sync (OneDrive)</h3>
                    </div>
                    <div className="space-y-4 bg-gray-50 p-4 rounded-lg">
                      <label className="flex items-center gap-3 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={(localSettings.onedrive_detection_enabled || 'true') === 'true'}
                          onChange={(e) => handleAutoSave('onedrive_detection_enabled', e.target.checked ? 'true' : 'false')}
                          className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                        />
                        <div>
                          <div className="text-sm font-medium text-gray-700">Detect OneDrive Uploads (macOS)</div>
                          <div className="text-xs text-gray-500">Uses macOS File Provider to mark files as Uploaded when OneDrive finishes syncing. Runs only after processing completes.</div>
                        </div>
                      </label>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          OneDrive Root Path (optional)
                        </label>
                        <input
                          type="text"
                          value={localSettings.onedrive_root || ''}
                          onChange={(e) => handleChange('onedrive_root', e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900"
                          placeholder="~/Library/CloudStorage/OneDrive-<YourOrg>"
                        />
                        <p className="text-xs text-gray-500 mt-1">
                          Leave blank to auto-detect the standard macOS OneDrive location. Used to scope detection to files organized under OneDrive.
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Cleanup Tab */}
                {activeTab === 'cleanup' && (
                  <div>
                    <div className="flex items-center gap-2 mb-4">
                      <Trash2 className="w-5 h-5 text-orange-600" />
                      <h3 className="text-lg font-semibold text-gray-800">Auto-Deletion</h3>
                    </div>
                    <div className="space-y-4 bg-gray-50 p-4 rounded-lg">
                      <label className="flex items-center gap-3 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={(localSettings.auto_delete_enabled || 'false') === 'true'}
                          onChange={(e) => handleAutoSave('auto_delete_enabled', e.target.checked ? 'true' : 'false')}
                          className="w-4 h-4 text-orange-600 border-gray-300 rounded focus:ring-orange-500"
                        />
                        <div>
                          <div className="text-sm font-medium text-gray-700">Enable Auto-Deletion</div>
                          <div className="text-xs text-gray-500">Automatically mark completed files older than the specified age for deletion from the ATEM FTP server.</div>
                        </div>
                      </label>

                      {(settings.auto_delete_enabled || 'false') === 'true' && (
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">
                            Delete Files Older Than (months)
                          </label>
                          <input
                            type="number"
                            min="1"
                            max="120"
                            value={localSettings.auto_delete_age_months || '12'}
                            onChange={(e) => handleChange('auto_delete_age_months', e.target.value)}
                            className={`w-full px-3 py-2 border rounded focus:ring-2 focus:ring-orange-500 focus:border-orange-500 text-gray-900 ${validationErrors.auto_delete_age_months ? 'border-red-300' : 'border-gray-300'
                              }`}
                          />
                          {validationErrors.auto_delete_age_months && (
                            <p className="text-xs text-red-600 mt-1">{validationErrors.auto_delete_age_months}</p>
                          )}
                          <p className="text-xs text-gray-500 mt-1">
                            Files will be marked for deletion after this age. They will be deleted from the FTP server 7 days after being marked, but kept in the database for reference.
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* GUI Settings Tab */}
                {activeTab === 'gui' && (
                  <div>
                    <div className="flex items-center gap-2 mb-4">
                      <Monitor className="w-5 h-5 text-blue-600" />
                      <h3 className="text-lg font-semibold text-gray-800">GUI Preferences</h3>
                    </div>
                    <div className="space-y-4 bg-gray-50 p-4 rounded-lg">
                      <label className="flex items-center gap-3 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={guiPreferences.showQueueNumbers}
                          onChange={(e) => handleGuiPreferenceChange('showQueueNumbers', e.target.checked)}
                          className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                        />
                        <div>
                          <div className="text-sm font-medium text-gray-700">Show Queue Numbers</div>
                          <div className="text-xs text-gray-500">
                            Display queue position numbers on session cards when sorting by "First Queued" or "Last Queued"
                          </div>
                        </div>
                      </label>

                      <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded text-sm text-blue-700">
                        <div className="font-medium mb-1">💡 Tip</div>
                        <div className="text-xs">
                          Queue numbers show the order in which sessions were discovered. Lower numbers indicate earlier discovery.
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Network Settings Tab */}
                {activeTab === 'network' && (
                  <NetworkSettingsTab
                    localSettings={localSettings}
                    handleAutoSave={handleAutoSave}
                    showStatus={showStatus}
                  />
                )}

                {/* AI Settings Tab */}
                {activeTab === 'ai' && (
                  <div>
                    <div className="flex items-center gap-2 mb-4">
                      <Brain className="w-5 h-5 text-purple-600" />
                      <h3 className="text-lg font-semibold text-gray-800">AI Analytics</h3>
                    </div>

                    {aiInfoLoading ? (
                      <div className="flex items-center justify-center h-64">
                        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500"></div>
                      </div>
                    ) : aiInfo && aiInfo.enabled ? (
                      <div className="space-y-4">
                        {/* Status Banner */}
                        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                          <div className="flex items-center gap-3">
                            <CheckCircle className="w-6 h-6 text-green-600 flex-shrink-0" />
                            <div>
                              <div className="font-medium text-green-800">AI Features Enabled</div>
                              <div className="text-sm text-green-700 mt-1">
                                Transcription and content analysis are available for processed files
                              </div>
                            </div>
                          </div>
                        </div>

                        {/* Model Information */}
                        <div className="space-y-4 bg-gray-50 p-4 rounded-lg">
                          <div>
                            <div className="text-sm font-semibold text-gray-700 mb-3">Whisper (Transcription)</div>
                            <div className="bg-white border border-gray-200 rounded p-3 space-y-2">
                              <div className="flex items-center justify-between">
                                <span className="text-sm text-gray-600">Model:</span>
                                <span className="text-sm font-medium text-gray-800 font-mono">
                                  {aiInfo.whisper_model || 'mlx-community/whisper-small'}
                                </span>
                              </div>
                              <div className="flex items-center justify-between">
                                <span className="text-sm text-gray-600">Status:</span>
                                {aiInfo.whisper_available ? (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium text-green-700 bg-green-100">
                                    <CheckCircle className="w-3 h-3" />
                                    Available
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium text-red-700 bg-red-100">
                                    <XCircle className="w-3 h-3" />
                                    Not Found
                                  </span>
                                )}
                              </div>
                              {aiInfo.whisper_path && (
                                <div className="flex items-start justify-between pt-2 border-t border-gray-100">
                                  <span className="text-xs text-gray-500">Path:</span>
                                  <span className="text-xs text-gray-600 font-mono text-right ml-2 break-all">
                                    {aiInfo.whisper_path}
                                  </span>
                                </div>
                              )}
                            </div>
                          </div>

                          <div>
                            <div className="text-sm font-semibold text-gray-700 mb-3">LLM (Content Analysis)</div>
                            <div className="bg-white border border-gray-200 rounded p-3 space-y-2">
                              <div className="flex items-center justify-between">
                                <span className="text-sm text-gray-600">Model:</span>
                                <span className="text-sm font-medium text-gray-800 font-mono">
                                  {aiInfo.llm_model || 'Qwen3-VL-4B-Instruct-MLX-8bit'}
                                </span>
                              </div>
                              <div className="flex items-center justify-between">
                                <span className="text-sm text-gray-600">Status:</span>
                                {aiInfo.llm_available ? (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium text-green-700 bg-green-100">
                                    <CheckCircle className="w-3 h-3" />
                                    Available
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium text-red-700 bg-red-100">
                                    <XCircle className="w-3 h-3" />
                                    Not Found
                                  </span>
                                )}
                              </div>
                              {aiInfo.llm_path && (
                                <div className="flex items-start justify-between pt-2 border-t border-gray-100">
                                  <span className="text-xs text-gray-500">Path:</span>
                                  <span className="text-xs text-gray-600 font-mono text-right ml-2 break-all">
                                    {aiInfo.llm_path}
                                  </span>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* Whisper Translation Setting */}
                        <div className="space-y-3 bg-gray-50 p-4 rounded-lg">
                          <div>
                            <div className="text-sm font-semibold text-gray-700 mb-3">Transcription Settings</div>

                            {/* Translate to English */}
                            <label className="flex items-center gap-3 cursor-pointer mb-3">
                              <input
                                type="checkbox"
                                checked={localSettings.whisper_translate_to_english === 'true'}
                                onChange={(e) => handleAutoSave('whisper_translate_to_english', e.target.checked ? 'true' : 'false')}
                                className="w-4 h-4 text-purple-600 border-gray-300 rounded focus:ring-purple-500"
                              />
                              <div>
                                <div className="text-sm font-medium text-gray-700">Translate to English</div>
                                <div className="text-xs text-gray-500">
                                  Automatically translate transcripts to English while preserving the detected language in the analytics metadata
                                </div>
                              </div>
                            </label>

                            {/* Prompt Words for Whisper */}
                            <div className="mt-3">
                              <label className="block text-sm font-medium text-gray-700 mb-1">
                                Custom Vocabulary / Proper Nouns
                              </label>
                              <input
                                type="text"
                                value={localWhisperSettings.prompt_words || ''}
                                onChange={(e) => handleWhisperSettingChange('prompt_words', e.target.value)}
                                className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-gray-900"
                                placeholder="e.g., Haileybury, VCE, ATAR, Pakenham, Berwick"
                              />
                              <p className="text-xs text-gray-500 mt-1">
                                Enter comma-separated words to help Whisper correctly transcribe proper nouns and domain-specific terms.
                              </p>
                              <button
                                onClick={saveWhisperSettings}
                                disabled={saving || whisperSettingsLoading}
                                className="mt-2 px-3 py-1 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-400 text-white rounded text-sm font-medium flex items-center gap-2 transition-colors"
                              >
                                {saving ? (
                                  <>
                                    <Loader2 className="w-3 h-3 animate-spin" />
                                    Saving...
                                  </>
                                ) : (
                                  <>
                                    <Save className="w-3 h-3" />
                                    Save Whisper Settings
                                  </>
                                )}
                              </button>
                            </div>
                          </div>
                        </div>

                        {/* AI Analytics Cache */}
                        <div className="space-y-3 bg-gray-50 p-4 rounded-lg">
                          <div>
                            <div className="text-sm font-semibold text-gray-700 mb-3">AI Analytics Cache</div>
                            <label className="flex items-center gap-3 cursor-pointer mb-3">
                              <input
                                type="checkbox"
                                checked={localSettings.external_audio_export_enabled === 'true'}
                                onChange={(e) => handleAutoSave('external_audio_export_enabled', e.target.checked ? 'true' : 'false')}
                                className="w-4 h-4 text-purple-600 border-gray-300 rounded focus:ring-purple-500"
                              />
                              <div>
                                <div className="text-sm font-medium text-gray-700">Enable Local Analytics Cache</div>
                                <div className="text-xs text-gray-500">
                                  Store audio files and thumbnails locally for AI processing. Recommended when final output path uses cloud storage with "Free Up Space" enabled.
                                </div>
                              </div>
                            </label>

                            {(settings.external_audio_export_enabled || 'false') === 'true' && (
                              <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                  Local Cache Path
                                </label>
                                <input
                                  type="text"
                                  value={localSettings.external_audio_export_path || ''}
                                  onChange={(e) => handleChange('external_audio_export_path', e.target.value)}
                                  className={`w-full px-3 py-2 border rounded focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-gray-900 ${validationErrors.external_audio_export_path ? 'border-red-300' : 'border-gray-300'
                                    }`}
                                  placeholder="/Users/Shared/StudioPipeline/analytics_cache"
                                />
                                {validationErrors.external_audio_export_path && (
                                  <p className="text-xs text-red-600 mt-1">{validationErrors.external_audio_export_path}</p>
                                )}
                                <p className="text-xs text-gray-500 mt-1">
                                  Audio and thumbnails cached at: {'{path}'}/{'{file_id}'}/{'{session_name}'}.[mp3|jpg]
                                </p>
                                <p className="text-xs text-purple-600 mt-2">
                                  💡 Whisper will use cached audio files for faster, more reliable transcription
                                </p>
                              </div>
                            )}

                            {(settings.external_audio_export_enabled || 'false') === 'true' && localSettings.external_audio_export_path && (
                              <div className="mt-3 pt-3 border-t border-gray-200">
                                <div className="flex items-center justify-between">
                                  <div>
                                    <div className="text-sm font-medium text-gray-700">Populate Local Cache</div>
                                    <div className="text-xs text-gray-500">
                                      Scan existing processed files and copy audio/thumbnails to the cache directory.
                                    </div>
                                  </div>
                                  <button
                                    onClick={handlePopulateCache}
                                    disabled={populatingCache || saving}
                                    className="px-3 py-1.5 bg-purple-50 hover:bg-purple-100 text-purple-700 border border-purple-200 rounded text-sm font-medium flex items-center gap-2 transition-colors"
                                  >
                                    {populatingCache ? (
                                      <>
                                        <Loader2 className="w-3 h-3 animate-spin" />
                                        Updating...
                                      </>
                                    ) : (
                                      <>
                                        <RefreshCw className="w-3 h-3" />
                                        Update Cache
                                      </>
                                    )}
                                  </button>
                                </div>
                              </div>
                            )}
                          </div>
                        </div>

                        {/* AI Prompt Configuration */}
                        <div className="space-y-4 bg-gray-50 p-4 rounded-lg">
                          <div className="flex items-center justify-between mb-2">
                            <h4 className="text-sm font-semibold text-gray-700">LLM Prompt Configuration</h4>
                            <button
                              onClick={saveAiPrompts}
                              disabled={saving || promptsLoading}
                              className="px-3 py-1 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-400 text-white rounded text-sm font-medium flex items-center gap-2 transition-colors"
                            >
                              {saving ? (
                                <>
                                  <Loader2 className="w-3 h-3 animate-spin" />
                                  Saving...
                                </>
                              ) : (
                                <>
                                  <Save className="w-3 h-3" />
                                  Save Prompts
                                </>
                              )}
                            </button>
                          </div>

                          {promptsLoading ? (
                            <div className="flex items-center justify-center py-8">
                              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500"></div>
                            </div>
                          ) : (
                            <>
                              <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                  System Prompt
                                </label>
                                <textarea
                                  value={localAiPrompts.system_prompt}
                                  onChange={(e) => handlePromptChange('system_prompt', e.target.value)}
                                  className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-gray-900 font-mono text-xs"
                                  rows={3}
                                  placeholder="System message that defines the AI's role and behavior..."
                                />
                                <p className="text-xs text-gray-500 mt-1">
                                  Defines the AI assistant's role and overall behavior (e.g., "You are a JSON-only assistant")
                                </p>
                              </div>

                              <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                  User Prompt Template
                                </label>
                                <textarea
                                  value={localAiPrompts.user_prompt}
                                  onChange={(e) => handlePromptChange('user_prompt', e.target.value)}
                                  className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-gray-900 font-mono text-xs"
                                  rows={16}
                                  placeholder="User message template with instructions and placeholders..."
                                />
                                <p className="text-xs text-gray-500 mt-1">
                                  The specific instructions and output format. Supports placeholders: {'{transcript}'}, {'{filename}'}, {'{duration}'}, {'{recording_date}'}
                                </p>
                              </div>

                              <div className="p-3 bg-purple-100 border border-purple-300 rounded text-xs text-purple-800">
                                <div className="font-medium mb-1">💡 Tip: Separate Prompts</div>
                                <p>
                                  System prompt: Sets the AI's persona and constraints<br />
                                  User prompt: Contains the specific task and data to analyze
                                </p>
                              </div>
                            </>
                          )}
                        </div>

                        {/* Info Box */}
                        <div className="p-3 bg-purple-50 border border-purple-200 rounded text-sm text-purple-700">
                          <div className="font-medium mb-1">ℹ️ About AI Analytics</div>
                          <div className="text-xs space-y-1">
                            <p>• Transcription automatically extracts speech from video files</p>
                            <p>• Analysis generates summaries and insights from transcriptions</p>
                            <p>• Processing happens in the background after video processing completes</p>
                            <p>• View results in the Analytics tab in the left sidebar</p>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-4">
                        {/* Disabled Banner */}
                        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                          <div className="flex items-center gap-3">
                            <AlertCircle className="w-6 h-6 text-gray-400 flex-shrink-0" />
                            <div>
                              <div className="font-medium text-gray-800">AI Features Not Available</div>
                              <div className="text-sm text-gray-600 mt-1">
                                This build does not include AI analytics features. Use the AI-enabled build to access transcription and content analysis.
                              </div>
                            </div>
                          </div>
                        </div>

                        {/* Info Box */}
                        <div className="p-3 bg-blue-50 border border-blue-200 rounded text-sm text-blue-700">
                          <div className="font-medium mb-1">💡 Enable AI Features</div>
                          <div className="text-xs space-y-1">
                            <p>To use AI analytics:</p>
                            <p>1. Build the app with AI support using <span className="font-mono">./build_ai.sh</span></p>
                            <p>2. Or start the development server with <span className="font-mono">./start_servers_ai.sh</span></p>
                            <p>3. AI models will be automatically loaded and made available</p>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-gray-200 px-6 py-4 bg-gray-50 rounded-b-lg flex justify-between items-center">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 hover:text-gray-900 font-medium flex items-center gap-2"
          >
            <X className="w-4 h-4" />
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || loading}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white rounded font-medium flex items-center gap-2 transition-colors"
          >
            {saving ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </div>
    </div >
  );
}
