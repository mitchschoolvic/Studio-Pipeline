import React from 'react';
import { CheckCircle, AlertCircle } from 'lucide-react';

export function StatusOverlay({ message, type = 'success', isVisible, onHide }) {
    return (
        <div
            className={`absolute top-16 left-1/2 transform -translate-x-1/2 z-50 px-6 py-3 rounded-full shadow-lg flex items-center gap-2 transition-all ${isVisible
                ? 'opacity-100 translate-y-0 duration-300 ease-out'
                : 'opacity-0 -translate-y-4 duration-1000 ease-in pointer-events-none'
                } ${type === 'success' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'
                }`}
        >
            {type === 'success' ? <CheckCircle className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />}
            <span className="font-medium">{message}</span>
        </div>
    );
}
