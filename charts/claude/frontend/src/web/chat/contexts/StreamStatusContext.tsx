import React, { createContext, useContext, useState, useCallback, useRef, ReactNode } from 'react';
import { useMultipleStreams } from '../hooks/useMultipleStreams';
import { mapStreamEventToStatus } from '../utils/streamEventMapper';
import type { StreamEvent, StreamStatus } from '../types';

interface StreamStatusContextType {
  streamStatuses: Map<string, StreamStatus>;
  subscribeToStreams: (streamingIds: string[]) => void;
  unsubscribeFromStream: (streamingId: string) => void;
  getStreamStatus: (streamingId: string) => StreamStatus | undefined;
  activeStreamCount: number;
}

const StreamStatusContext = createContext<StreamStatusContextType | undefined>(undefined);

export function StreamStatusProvider({ children }: { children: ReactNode }) {
  const [streamStatuses, setStreamStatuses] = useState<Map<string, StreamStatus>>(new Map());
  const [subscribedStreamIds, setSubscribedStreamIds] = useState<string[]>([]);
  const streamStatusesRef = useRef<Map<string, StreamStatus>>(new Map());

  // Handle stream messages
  const handleStreamMessage = useCallback((streamingId: string, event: StreamEvent) => {
    const currentStatus = streamStatusesRef.current.get(streamingId) || {
      connectionState: 'connected' as const,
      currentStatus: 'Running',
    };

    // Use the streamEventMapper utility to map event to status
    const statusUpdates = mapStreamEventToStatus(event, currentStatus);
    
    // Merge with current status
    const updatedStatus: StreamStatus = {
      ...currentStatus,
      ...statusUpdates,
    };

    streamStatusesRef.current.set(streamingId, updatedStatus);
    setStreamStatuses(new Map(streamStatusesRef.current));
  }, []);

  // Handle stream errors
  const handleStreamError = useCallback((streamingId: string, error: Error) => {
    const currentStatus = streamStatusesRef.current.get(streamingId) || {
      connectionState: 'error' as const,
      currentStatus: 'Error',
    };

    const updatedStatus: StreamStatus = {
      ...currentStatus,
      connectionState: 'error',
      currentStatus: `Error: ${error.message}`,
      lastEventTime: new Date().toISOString(),
    };

    streamStatusesRef.current.set(streamingId, updatedStatus);
    setStreamStatuses(new Map(streamStatusesRef.current));
  }, []);

  // Handle stream connect
  const handleStreamConnect = useCallback((streamingId: string) => {
    const updatedStatus: StreamStatus = {
      connectionState: 'connected',
      currentStatus: 'Running',
      lastEventTime: new Date().toISOString(),
    };

    streamStatusesRef.current.set(streamingId, updatedStatus);
    setStreamStatuses(new Map(streamStatusesRef.current));
  }, []);

  // Handle stream disconnect
  const handleStreamDisconnect = useCallback((streamingId: string) => {
    const currentStatus = streamStatusesRef.current.get(streamingId);
    if (currentStatus && currentStatus.connectionState !== 'disconnected') {
      const updatedStatus: StreamStatus = {
        ...currentStatus,
        connectionState: 'disconnected',
        lastEventTime: new Date().toISOString(),
      };

      streamStatusesRef.current.set(streamingId, updatedStatus);
      setStreamStatuses(new Map(streamStatusesRef.current));
    }
  }, []);

  // Use the multiple streams hook
  const { activeConnectionCount } = useMultipleStreams(subscribedStreamIds, {
    onStreamMessage: handleStreamMessage,
    onStreamError: handleStreamError,
    onStreamConnect: handleStreamConnect,
    onStreamDisconnect: handleStreamDisconnect,
    maxConcurrentConnections: 5,
    maxRetries: 3,
    initialRetryDelay: 1000,
  });

  // Subscribe to streams
  const subscribeToStreams = useCallback((streamingIds: string[]) => {
    // Filter out any null or undefined values
    const validStreamIds = streamingIds.filter(id => id && id.length > 0);
    
    // Update subscribed streams
    setSubscribedStreamIds(current => {
      const newSet = new Set([...current, ...validStreamIds]);
      return Array.from(newSet);
    });

    // Initialize status for new streams
    validStreamIds.forEach(streamingId => {
      if (!streamStatusesRef.current.has(streamingId)) {
        const initialStatus: StreamStatus = {
          connectionState: 'connecting',
          currentStatus: 'Connecting...',
          lastEventTime: new Date().toISOString(),
        };
        streamStatusesRef.current.set(streamingId, initialStatus);
      }
    });
    
    setStreamStatuses(new Map(streamStatusesRef.current));
  }, []);

  // Unsubscribe from a stream
  const unsubscribeFromStream = useCallback((streamingId: string) => {
    setSubscribedStreamIds(current => current.filter(id => id !== streamingId));
    
    // Remove status
    streamStatusesRef.current.delete(streamingId);
    setStreamStatuses(new Map(streamStatusesRef.current));
  }, []);

  // Get stream status
  const getStreamStatus = useCallback((streamingId: string): StreamStatus | undefined => {
    return streamStatuses.get(streamingId);
  }, [streamStatuses]);

  return (
    <StreamStatusContext.Provider
      value={{
        streamStatuses,
        subscribeToStreams,
        unsubscribeFromStream,
        getStreamStatus,
        activeStreamCount: activeConnectionCount,
      }}
    >
      {children}
    </StreamStatusContext.Provider>
  );
}

export function useStreamStatus() {
  const context = useContext(StreamStatusContext);
  if (context === undefined) {
    throw new Error('useStreamStatus must be used within a StreamStatusProvider');
  }
  return context;
}