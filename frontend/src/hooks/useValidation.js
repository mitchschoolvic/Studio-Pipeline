/**
 * Custom hook for validation status management.
 *
 * Separated from ValidationBanner component to follow separation of concerns:
 * - This hook handles data fetching and state management
 * - ValidationBanner component handles only presentation
 */

import { useEffect, useState } from 'react';

const VALIDATION_CHECK_INTERVAL = 60000; // Check every minute

export function useValidation() {
  const [validationStatus, setValidationStatus] = useState(null);
  const [dismissed, setDismissed] = useState(false);

  const checkValidation = async () => {
    try {
      const response = await fetch('/api/settings/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await response.json();
      setValidationStatus(data);

      // Auto-dismiss if all valid
      if (data.overall_valid) {
        setDismissed(true);
      } else {
        setDismissed(false);
      }
    } catch (err) {
      console.error('Validation check failed:', err);
    }
  };

  useEffect(() => {
    // Check validation status on mount and periodically
    checkValidation();
    const interval = setInterval(checkValidation, VALIDATION_CHECK_INTERVAL);
    return () => clearInterval(interval);
  }, []);

  return {
    validationStatus,
    dismissed,
    setDismissed,
    checkValidation
  };
}
