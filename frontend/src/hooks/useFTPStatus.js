import { useState, useEffect } from 'react';
import { useWebSocket } from './useWebSocket';

export function useFTPStatus(validationStatus) {
    const { lastMessage } = useWebSocket();
    const [ftpConnected, setFtpConnected] = useState(true);
    const [ftpConnectionState, setFtpConnectionState] = useState('disconnected');
    const [ftpHost, setFtpHost] = useState('');
    const [ftpPort, setFtpPort] = useState(21);
    const [ftpErrorMessage, setFtpErrorMessage] = useState('');

    // Fetch FTP settings for display
    useEffect(() => {
        const fetchFTPSettings = async () => {
            try {
                const response = await fetch('/api/settings');
                const settings = await response.json();
                const hostSetting = settings.find(s => s.key === 'ftp_host');
                const portSetting = settings.find(s => s.key === 'ftp_port');
                if (hostSetting) setFtpHost(hostSetting.value);
                if (portSetting) setFtpPort(parseInt(portSetting.value) || 21);
            } catch (error) {
                console.error('Failed to fetch FTP settings:', error);
            }
        };
        fetchFTPSettings();
    }, []);

    // Update FTP connection status based on validation
    useEffect(() => {
        if (validationStatus?.ftp_connection) {
            const isFtpValid = validationStatus.ftp_connection.valid;
            setFtpConnected(isFtpValid);

            if (isFtpValid) {
                setFtpConnectionState('connected');
                setFtpErrorMessage('');
            } else {
                setFtpConnectionState('disconnected');
                setFtpErrorMessage(validationStatus.ftp_connection.message || 'Connection failed');
            }
        }
    }, [validationStatus]);

    // Listen for WebSocket updates
    useEffect(() => {
        if (!lastMessage) return;

        // Handle live FTP connection status updates
        if (lastMessage.type === 'ftp_connection_status') {
            const { connected, host, port, error_message } = lastMessage.data || lastMessage;

            setFtpConnected(connected);
            setFtpConnectionState(connected ? 'connected' : 'disconnected');
            setFtpErrorMessage(error_message || '');

            // Update host/port if provided
            if (host) setFtpHost(host);
            if (port) setFtpPort(port);
        }

        // Detect FTP connection recovery when files are successfully deleted
        if (lastMessage.type === 'file_deleted') {
            if (!ftpConnected) {
                setFtpConnected(true);
                setFtpConnectionState('connected');
                setFtpErrorMessage('');
            }
        }

        // Check if error indicates FTP connection issue
        if (lastMessage.type === 'file_deletion_failed') {
            const { error } = lastMessage;
            if (error && (
                error.includes('Connection error') ||
                error.includes('not accessible') ||
                error.includes('Failed to connect') ||
                error.includes('FTP error')
            )) {
                setFtpConnected(false);
                setFtpConnectionState('disconnected');
                setFtpErrorMessage(error);
            }
        }
    }, [lastMessage, ftpConnected]);

    return {
        ftpConnected,
        ftpConnectionState,
        ftpHost,
        ftpPort,
        ftpErrorMessage
    };
}
