import { createContext, useContext, useState, useCallback } from 'react';

/**
 * SelectModeContext
 * 
 * Provides state management for session selection mode.
 * Handles:
 * - Toggle select mode on/off
 * - Track selected session IDs
 * - Select/deselect individual sessions
 * - Select/deselect all sessions
 * - Range selection with Shift+click
 */

const SelectModeContext = createContext(null);

export function SelectModeProvider({ children }) {
  const [isSelectMode, setIsSelectMode] = useState(false);
  const [selectedSessions, setSelectedSessions] = useState(new Set());
  const [lastSelectedIndex, setLastSelectedIndex] = useState(null);

  // Toggle select mode on/off
  const toggleSelectMode = useCallback(() => {
    setIsSelectMode(prev => {
      // If turning off, clear selection
      if (prev) {
        setSelectedSessions(new Set());
        setLastSelectedIndex(null);
      }
      return !prev;
    });
  }, []);

  // Exit select mode (used after actions complete)
  const exitSelectMode = useCallback(() => {
    setIsSelectMode(false);
    setSelectedSessions(new Set());
    setLastSelectedIndex(null);
  }, []);

  // Toggle selection for a single session
  const toggleSessionSelection = useCallback((sessionId) => {
    setSelectedSessions(prev => {
      const next = new Set(prev);
      if (next.has(sessionId)) {
        next.delete(sessionId);
      } else {
        next.add(sessionId);
      }
      return next;
    });
  }, []);

  // Handle shift+click range selection
  const handleShiftClick = useCallback((sessionId, sessionIds, currentIndex) => {
    if (lastSelectedIndex === null) {
      // First selection, just select this one
      toggleSessionSelection(sessionId);
      setLastSelectedIndex(currentIndex);
      return;
    }

    // Select range from lastSelectedIndex to currentIndex
    const start = Math.min(lastSelectedIndex, currentIndex);
    const end = Math.max(lastSelectedIndex, currentIndex);

    setSelectedSessions(prev => {
      const next = new Set(prev);
      for (let i = start; i <= end; i++) {
        if (sessionIds[i]) {
          next.add(sessionIds[i]);
        }
      }
      return next;
    });

    setLastSelectedIndex(currentIndex);
  }, [lastSelectedIndex, toggleSessionSelection]);

  // Handle regular click (updates last selected index)
  const handleRegularClick = useCallback((sessionId, currentIndex) => {
    toggleSessionSelection(sessionId);
    setLastSelectedIndex(currentIndex);
  }, [toggleSessionSelection]);

  // Select all sessions
  const selectAll = useCallback((sessionIds) => {
    setSelectedSessions(new Set(sessionIds));
  }, []);

  // Clear all selections
  const clearSelection = useCallback(() => {
    setSelectedSessions(new Set());
    setLastSelectedIndex(null);
  }, []);

  // Check if a session is selected
  const isSelected = useCallback((sessionId) => {
    return selectedSessions.has(sessionId);
  }, [selectedSessions]);

  const value = {
    isSelectMode,
    selectedSessions,
    toggleSelectMode,
    exitSelectMode,
    toggleSessionSelection,
    handleShiftClick,
    handleRegularClick,
    selectAll,
    clearSelection,
    isSelected,
    selectedCount: selectedSessions.size,
    selectedIds: Array.from(selectedSessions),
  };

  return (
    <SelectModeContext.Provider value={value}>
      {children}
    </SelectModeContext.Provider>
  );
}

export function useSelectMode() {
  const context = useContext(SelectModeContext);
  if (!context) {
    throw new Error('useSelectMode must be used within a SelectModeProvider');
  }
  return context;
}
