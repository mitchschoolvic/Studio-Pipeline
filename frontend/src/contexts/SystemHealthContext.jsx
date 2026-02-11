import { createContext, useContext, useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, X } from 'lucide-react';

const SystemHealthContext = createContext(null);

export function SystemHealthProvider({ children }) {
    const [isDismissed, setIsDismissed] = useState(false);

    // Poll system health every 30 seconds
    const { data: health, isLoading, error } = useQuery({
        queryKey: ['system-health'],
        queryFn: async () => {
            const res = await fetch('/api/settings/validate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            if (!res.ok) throw new Error('Failed to validate settings');
            return res.json();
        },
        refetchInterval: 30000, // 30 seconds
        staleTime: 10000,
        retry: false
    });

    // Reset dismissal if health becomes invalid again (or changes)
    useEffect(() => {
        if (health && !health.overall_valid) {
            // If it was valid before and now invalid, un-dismiss
            // But we don't track previous state easily here without ref.
            // For now, just keep dismissed state local.
        } else if (health && health.overall_valid) {
            setIsDismissed(false);
        }
    }, [health]);

    const value = {
        health,
        isLoading,
        error,
        isDismissed,
        dismiss: () => setIsDismissed(true)
    };

    return (
        <SystemHealthContext.Provider value={value}>
            {children}
        </SystemHealthContext.Provider>
    );
}

export function useSystemHealth() {
    const ctx = useContext(SystemHealthContext);
    if (!ctx) throw new Error('useSystemHealth must be used within SystemHealthProvider');
    return ctx;
}


