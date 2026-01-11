import { useEffect, useRef, useCallback, useState } from 'react';
import type { StreamEvent } from '../types';
import { getAuthToken } from '../../hooks/useAuth';

interface StreamConnection {
  streamingId: string;
  connectionState: 'connecting' | 'connected' | 'disconnected' | 'error';
  lastEvent?: StreamEvent;
  lastEventTime?: Date;
  reader: ReadableStreamDefaultReader<Uint8Array> | null;
  abortController: AbortController | null;
  retryCount: number;
  retryTimeout?: NodeJS.Timeout;
}

interface UseMultipleStreamsOptions {
  onStreamMessage: (streamingId: string, event: StreamEvent) => void;
  onStreamError?: (streamingId: string, error: Error) => void;
  onStreamConnect?: (streamingId: string) => void;
  onStreamDisconnect?: (streamingId: string) => void;
  maxConcurrentConnections?: number;
  maxRetries?: number;
  initialRetryDelay?: number;
}

const DEFAULT_MAX_CONNECTIONS = 5;
const DEFAULT_MAX_RETRIES = 3;
const DEFAULT_INITIAL_RETRY_DELAY = 1000;

export function useMultipleStreams(
  streamingIds: string[],
  options: UseMultipleStreamsOptions
) {
  const [connections, setConnections] = useState<Map<string, StreamConnection>>(new Map());
  const connectionsRef = useRef<Map<string, StreamConnection>>(new Map());
  const optionsRef = useRef(options);
  const pendingQueue = useRef<string[]>([]);
  
  // Keep options ref up to date
  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  // Get active connection count
  const getActiveConnectionCount = useCallback(() => {
    let count = 0;
    connectionsRef.current.forEach(conn => {
      if (conn.connectionState === 'connecting' || conn.connectionState === 'connected') {
        count++;
      }
    });
    return count;
  }, []);

  // Disconnect a specific stream
  const disconnectStream = useCallback((streamingId: string) => {
    const connection = connectionsRef.current.get(streamingId);
    if (!connection) return;

    // Clear retry timeout if exists
    if (connection.retryTimeout) {
      clearTimeout(connection.retryTimeout);
    }

    // Cancel reader and abort connection
    if (connection.reader) {
      connection.reader.cancel().catch(() => {});
    }
    if (connection.abortController) {
      connection.abortController.abort();
    }

    // Update connection state
    connection.connectionState = 'disconnected';
    connection.reader = null;
    connection.abortController = null;
    
    connectionsRef.current.set(streamingId, connection);
    setConnections(new Map(connectionsRef.current));

    // Notify disconnect
    optionsRef.current.onStreamDisconnect?.(streamingId);
    
    // Process pending queue
    processPendingConnections();
  }, []);

  // Process pending connections when slots are available
  const processPendingConnections = useCallback(() => {
    const maxConnections = optionsRef.current.maxConcurrentConnections || DEFAULT_MAX_CONNECTIONS;
    const activeCount = getActiveConnectionCount();
    
    while (pendingQueue.current.length > 0 && activeCount < maxConnections) {
      const nextStreamingId = pendingQueue.current.shift();
      if (nextStreamingId) {
        connectToStream(nextStreamingId);
      }
    }
  }, []);

  // Connect to a single stream
  const connectToStream = useCallback(async (streamingId: string) => {
    // Check if already connecting/connected
    const existingConnection = connectionsRef.current.get(streamingId);
    if (existingConnection && 
        (existingConnection.connectionState === 'connecting' || 
         existingConnection.connectionState === 'connected')) {
      return;
    }

    // Check connection limit
    const maxConnections = optionsRef.current.maxConcurrentConnections || DEFAULT_MAX_CONNECTIONS;
    if (getActiveConnectionCount() >= maxConnections) {
      // Add to pending queue if not already there
      if (!pendingQueue.current.includes(streamingId)) {
        pendingQueue.current.push(streamingId);
      }
      return;
    }

    // Create or update connection object
    const connection: StreamConnection = existingConnection || {
      streamingId,
      connectionState: 'connecting',
      reader: null,
      abortController: null,
      retryCount: 0,
    };

    connection.connectionState = 'connecting';
    connection.abortController = new AbortController();
    
    connectionsRef.current.set(streamingId, connection);
    setConnections(new Map(connectionsRef.current));

    try {
      // Get auth token for Bearer authorization
      const authToken = getAuthToken();
      const headers: Record<string, string> = {};
      
      // Add Bearer token if available
      if (authToken) {
        headers.Authorization = `Bearer ${authToken}`;
      }
      
      const response = await fetch(`/api/stream/${streamingId}`, {
        signal: connection.abortController.signal,
        headers,
      });

      if (!response.ok) {
        throw new Error(`Stream connection failed: ${response.status}`);
      }

      if (!response.body) {
        throw new Error('No response body');
      }

      const reader = response.body.getReader();
      connection.reader = reader;
      connection.connectionState = 'connected';
      connection.retryCount = 0; // Reset retry count on successful connection
      
      connectionsRef.current.set(streamingId, connection);
      setConnections(new Map(connectionsRef.current));
      
      optionsRef.current.onStreamConnect?.(streamingId);

      // Read stream
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const decoded = decoder.decode(value, { stream: true });
        buffer += decoded;
        
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.trim()) {
            try {
              // Handle SSE format: remove "data: " prefix
              let jsonLine = line;
              if (line.startsWith('data: ')) {
                jsonLine = line.substring(6);
              }
              
              // Skip SSE comments (lines starting with :)
              if (line.startsWith(':')) {
                continue;
              }
              
              const event = JSON.parse(jsonLine) as StreamEvent;
              connection.lastEvent = event;
              connection.lastEventTime = new Date();
              
              connectionsRef.current.set(streamingId, connection);
              setConnections(new Map(connectionsRef.current));
              
              optionsRef.current.onStreamMessage(streamingId, event);
            } catch (err) {
              console.error('Failed to parse stream message:', line, err);
            }
          }
        }
      }
    } catch (error: any) {
      if (error.name !== 'AbortError') {
        console.error(`Stream error for ${streamingId}:`, error);
        
        connection.connectionState = 'error';
        connectionsRef.current.set(streamingId, connection);
        setConnections(new Map(connectionsRef.current));
        
        optionsRef.current.onStreamError?.(streamingId, error);
        
        // Retry logic
        const maxRetries = optionsRef.current.maxRetries || DEFAULT_MAX_RETRIES;
        if (connection.retryCount < maxRetries) {
          connection.retryCount++;
          const retryDelay = (optionsRef.current.initialRetryDelay || DEFAULT_INITIAL_RETRY_DELAY) * 
                            Math.pow(2, connection.retryCount - 1); // Exponential backoff
          
          connection.retryTimeout = setTimeout(() => {
            connectToStream(streamingId);
          }, retryDelay);
        }
      }
    } finally {
      // Clean up if still in connecting/connected state
      const currentConnection = connectionsRef.current.get(streamingId);
      if (currentConnection && 
          (currentConnection.connectionState === 'connecting' || 
           currentConnection.connectionState === 'connected')) {
        disconnectStream(streamingId);
      }
    }
  }, [disconnectStream, getActiveConnectionCount]);

  // Manage connections based on streamingIds
  useEffect(() => {
    // Determine which streams to connect/disconnect
    const currentStreamIds = new Set(Array.from(connectionsRef.current.keys()));
    const targetStreamIds = new Set(streamingIds);
    
    // Disconnect streams no longer in the list
    currentStreamIds.forEach(streamingId => {
      if (!targetStreamIds.has(streamingId)) {
        disconnectStream(streamingId);
      }
    });
    
    // Connect to new streams
    streamingIds.forEach(streamingId => {
      if (!currentStreamIds.has(streamingId)) {
        connectToStream(streamingId);
      }
    });
  }, [streamingIds, connectToStream, disconnectStream]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      // Disconnect all streams
      connectionsRef.current.forEach((_, streamingId) => {
        disconnectStream(streamingId);
      });
      pendingQueue.current = [];
    };
  }, [disconnectStream]);

  return {
    connections,
    getConnectionState: (streamingId: string) => connections.get(streamingId),
    reconnect: connectToStream,
    disconnect: disconnectStream,
    activeConnectionCount: getActiveConnectionCount(),
  };
}