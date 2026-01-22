import React, { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useLocation, useNavigate } from "react-router-dom";
import { MessageList } from "../MessageList/MessageList";
import { Composer, ComposerRef } from "@/web/chat/components/Composer";
import { ConversationHeader } from "../ConversationHeader/ConversationHeader";
import { api, ApiServiceError } from "../../services/api";
import { useStreaming, useConversationMessages } from "../../hooks";
import type {
  ChatMessage,
  ConversationDetailsResponse,
  ConversationMessage,
  ConversationSummary,
} from "../../types";

// Helper to format errors with full details
function formatError(err: unknown): string {
  if (err instanceof ApiServiceError) {
    return err.toDisplayString();
  }
  if (err instanceof Error) {
    return err.message;
  }
  return String(err);
}

interface NavigationState {
  streamingId?: string;
}

export function ConversationView() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  // Initialize streamingId from navigation state if available (for resume/continuation)
  const [streamingId, setStreamingId] = useState<string | null>(() => {
    const state = location.state as NavigationState | null;
    return state?.streamingId || null;
  });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [conversationTitle, setConversationTitle] =
    useState<string>("Conversation");
  const [isPermissionDecisionLoading, setIsPermissionDecisionLoading] =
    useState(false);
  const [conversationSummary, setConversationSummary] =
    useState<ConversationSummary | null>(null);
  // Always use /repos/homelab as the working directory
  const currentWorkingDirectory = "/repos/homelab";
  const composerRef = useRef<ComposerRef>(null);

  // Use shared conversation messages hook
  const {
    messages,
    toolResults,
    currentPermissionRequest,
    childrenMessages,
    expandedTasks,
    clearMessages,
    addMessage,
    setAllMessages,
    handleStreamMessage,
    toggleTaskExpanded,
    clearPermissionRequest,
    setPermissionRequest,
  } = useConversationMessages({
    onResult: (newSessionId) => {
      // Navigate to the new session page if session changed
      if (newSessionId && newSessionId !== sessionId) {
        navigate(`/c/${newSessionId}`);
      }
    },
    onError: (err) => {
      setError(err);
      setStreamingId(null);
    },
    onClosed: () => {
      setStreamingId(null);
    },
  });

  // Handle streamingId from navigation state
  // This effect SETS the streamingId when navigating with state (critical for streaming to work)
  useEffect(() => {
    const state = location.state as NavigationState | null;
    if (state?.streamingId) {
      // Set the streamingId to connect to the stream
      setStreamingId(state.streamingId);
      // Clear navigation state after extracting streamingId to prevent issues on refresh
      window.history.replaceState({}, document.title);
    }
  }, [location.state]);

  // Clear streaming when sessionId changes (navigating to different conversation)
  const prevSessionIdRef = React.useRef(sessionId);
  useEffect(() => {
    // Only clear streamingId if sessionId actually changed (different conversation)
    // Don't clear when location.state changes - that's how we receive new streamingId
    if (prevSessionIdRef.current !== sessionId) {
      setStreamingId(null);
      prevSessionIdRef.current = sessionId;
    }
    // Note: No cleanup - useStreaming handles its own cleanup
  }, [sessionId]);

  // Load conversation history
  useEffect(() => {
    const loadConversation = async () => {
      if (!sessionId) return;

      setIsLoading(true);
      setError(null);

      try {
        const details = await api.getConversationDetails(sessionId);
        const chatMessages = convertToChatlMessages(details);

        // Always load fresh messages from backend
        setAllMessages(chatMessages);

        // Set working directory from the most recent message with a working directory
        const messagesWithCwd = chatMessages.filter(
          (msg) => msg.workingDirectory,
        );
        if (messagesWithCwd.length > 0) {
          const latestCwd =
            messagesWithCwd[messagesWithCwd.length - 1].workingDirectory;
          if (latestCwd) {
            setCurrentWorkingDirectory(latestCwd);
          }
        }

        // Check if this conversation has an active stream
        const conversationsResponse = await api.getConversations({
          limit: 100,
        });
        const currentConversation = conversationsResponse.conversations.find(
          (conv) => conv.sessionId === sessionId,
        );

        if (currentConversation) {
          setConversationSummary(currentConversation);

          // Set conversation title from custom name or summary
          const title =
            currentConversation.sessionInfo.custom_name ||
            currentConversation.summary ||
            "Untitled";
          setConversationTitle(title);

          if (
            currentConversation.status === "ongoing" &&
            currentConversation.streamingId
          ) {
            // Active stream, check for existing pending permissions
            setStreamingId(currentConversation.streamingId);

            try {
              const { permissions } = await api.getPermissions({
                streamingId: currentConversation.streamingId,
                status: "pending",
              });

              if (permissions.length > 0) {
                // Take the most recent pending permission (by timestamp)
                const mostRecentPermission = permissions.reduce(
                  (latest, current) =>
                    new Date(current.timestamp) > new Date(latest.timestamp)
                      ? current
                      : latest,
                );

                setPermissionRequest(mostRecentPermission);
              }
            } catch (permissionError) {
              // Don't break conversation loading if permission fetching fails
              console.warn(
                "[ConversationView] Failed to fetch existing permissions:",
                permissionError,
              );
            }
          }
        }
      } catch (err: unknown) {
        setError(formatError(err) || "Failed to load conversation");
      } finally {
        setIsLoading(false);

        // Focus the input after loading is complete
        setTimeout(() => {
          composerRef.current?.focusInput();
        }, 100);
      }
    };

    loadConversation();
  }, [sessionId, setAllMessages]);

  const { isConnected, isReconnecting, disconnect } = useStreaming(
    streamingId,
    {
      onMessage: handleStreamMessage,
      onError: (err) => {
        // Show error but DON'T clear streamingId - let auto-reconnect handle it
        console.error("Streaming error:", err);
        // Only show persistent errors, not transient network issues
        if (!err.message.includes("Failed to fetch")) {
          setError(err.message);
        }
      },
    },
  );

  const handleSendMessage = async (
    message: string,
    workingDirectory?: string,
    model?: string,
    permissionMode?: string,
  ) => {
    if (!sessionId) return;

    setError(null);

    // Add optimistic user message to UI immediately
    addMessage({
      id: `optimistic-${Date.now()}`,
      type: "user",
      content: message,
      timestamp: new Date().toISOString(),
      workingDirectory: "/repos/homelab",
    });

    try {
      // Always use /repos/homelab and opus model
      const response = await api.startConversation({
        resumedSessionId: sessionId,
        initialPrompt: message,
        workingDirectory: "/repos/homelab",
        model: "opus",
        // Convert "default" to undefined to let server use DEFAULT_PERMISSION_MODE env var
        permissionMode:
          permissionMode === "default" ? undefined : permissionMode,
      });

      // Set the new streamingId to connect to the response stream
      // This is critical for receiving Claude's response after resume
      setStreamingId(response.streamingId);

      // Navigate to the session with streamingId in state
      // This is needed because navigation to a new session unmounts this component,
      // and the new component instance needs the streamingId to connect to the stream
      navigate(`/c/${response.sessionId}`, {
        state: { streamingId: response.streamingId } as NavigationState,
      });
    } catch (err: unknown) {
      setError(formatError(err) || "Failed to send message");
    }
  };

  const handleStop = async () => {
    if (!streamingId) return;

    try {
      // Call the API to stop the conversation
      await api.stopConversation(streamingId);

      // Disconnect the streaming connection
      disconnect();

      // Clear the streaming ID
      setStreamingId(null);

      // Streaming has stopped
    } catch (err: unknown) {
      console.error("Failed to stop conversation:", err);
      setError(formatError(err) || "Failed to stop conversation");
    }
  };

  const handlePermissionDecision = async (
    requestId: string,
    action: "approve" | "deny",
    denyReason?: string,
  ) => {
    if (isPermissionDecisionLoading) return;

    setIsPermissionDecisionLoading(true);
    try {
      await api.sendPermissionDecision(requestId, { action, denyReason });
      // Clear the permission request after successful decision
      clearPermissionRequest();
    } catch (err: unknown) {
      console.error("Failed to send permission decision:", err);
      setError(formatError(err) || "Failed to send permission decision");
    } finally {
      setIsPermissionDecisionLoading(false);
    }
  };

  return (
    <div
      className="h-full flex flex-col bg-background relative"
      role="main"
      aria-label="Conversation view"
    >
      <ConversationHeader
        title={
          conversationSummary?.sessionInfo.custom_name || conversationTitle
        }
        sessionId={sessionId}
        isArchived={conversationSummary?.sessionInfo.archived || false}
        isPinned={conversationSummary?.sessionInfo.pinned || false}
        subtitle={
          conversationSummary
            ? {
                date: new Date(
                  conversationSummary.createdAt,
                ).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                }),
                repo:
                  conversationSummary.projectPath.split("/").pop() || "project",
                commitSHA: conversationSummary.sessionInfo.initial_commit_head,
                changes: conversationSummary.toolMetrics
                  ? {
                      additions: conversationSummary.toolMetrics.linesAdded,
                      deletions: conversationSummary.toolMetrics.linesRemoved,
                    }
                  : undefined,
              }
            : undefined
        }
        onTitleUpdate={async (newTitle) => {
          // Update local state immediately for instant feedback
          setConversationTitle(newTitle);

          // Update the conversation summary with the new custom name
          if (conversationSummary) {
            setConversationSummary({
              ...conversationSummary,
              sessionInfo: {
                ...conversationSummary.sessionInfo,
                custom_name: newTitle,
              },
            });
          }

          // Optionally refresh from backend to ensure consistency
          try {
            const conversationsResponse = await api.getConversations({
              limit: 100,
            });
            const updatedConversation =
              conversationsResponse.conversations.find(
                (conv) => conv.sessionId === sessionId,
              );
            if (updatedConversation) {
              setConversationSummary(updatedConversation);
              const title =
                updatedConversation.sessionInfo.custom_name ||
                updatedConversation.summary ||
                "Untitled";
              setConversationTitle(title);
            }
          } catch (error) {
            console.error(
              "Failed to refresh conversation after rename:",
              error,
            );
          }
        }}
        onPinToggle={async (isPinned) => {
          if (conversationSummary) {
            setConversationSummary({
              ...conversationSummary,
              sessionInfo: {
                ...conversationSummary.sessionInfo,
                pinned: isPinned,
              },
            });
          }
        }}
      />

      {error && (
        <div
          className="bg-red-500/10 border-b border-red-500 text-red-600 dark:text-red-400 px-4 py-3 animate-in slide-in-from-top duration-300"
          role="alert"
          aria-label="Error message"
        >
          <div className="max-w-3xl mx-auto flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <div className="font-medium text-sm mb-1">Error</div>
              <div className="text-sm whitespace-pre-wrap break-words font-mono">
                {error}
              </div>
            </div>
            <button
              onClick={() => setError(null)}
              className="shrink-0 p-1 hover:bg-red-500/20 rounded transition-colors"
              aria-label="Dismiss error"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {isReconnecting && !isConnected && (
        <div
          className="bg-yellow-500/10 border-b border-yellow-500 text-yellow-600 dark:text-yellow-400 px-4 py-2 animate-in slide-in-from-top duration-300"
          role="status"
          aria-label="Reconnecting message"
        >
          <div className="max-w-3xl mx-auto flex items-center gap-2">
            <svg
              className="animate-spin h-4 w-4"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              ></circle>
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              ></path>
            </svg>
            <span className="text-sm font-medium">Reconnecting...</span>
          </div>
        </div>
      )}

      <MessageList
        messages={messages}
        toolResults={toolResults}
        childrenMessages={childrenMessages}
        expandedTasks={expandedTasks}
        onToggleTaskExpanded={toggleTaskExpanded}
        isLoading={isLoading}
        isStreaming={!!streamingId}
      />

      <div
        className="fixed bottom-0 left-0 right-0 bg-white/80 dark:bg-zinc-900/80 backdrop-blur-sm z-10 w-full flex justify-center px-2 pb-6"
        style={{ paddingBottom: "max(1.5rem, env(safe-area-inset-bottom))" }}
        aria-label="Message composer section"
      >
        <div className="w-full max-w-3xl">
          <Composer
            ref={composerRef}
            onSubmit={handleSendMessage}
            onStop={handleStop}
            onPermissionDecision={handlePermissionDecision}
            isLoading={isConnected || isPermissionDecisionLoading}
            placeholder="Continue the conversation..."
            permissionRequest={currentPermissionRequest}
            showPermissionUI={true}
            showStopButton={true}
            enableFileAutocomplete={true}
            dropdownPosition="above"
            workingDirectory="/repos/homelab"
            showDirectorySelector={false}
            showModelSelector={false}
            model="opus"
            onFetchFileSystem={async () => {
              try {
                const response = await api.listDirectory({
                  path: "/repos/homelab",
                  recursive: true,
                  respectGitignore: true,
                });
                return response.entries;
              } catch (error) {
                console.error("Failed to fetch file system entries:", error);
                return [];
              }
            }}
            onFetchCommands={async () => {
              try {
                const response = await api.getCommands("/repos/homelab");
                return response.commands;
              } catch (error) {
                console.error("Failed to fetch commands:", error);
                return [];
              }
            }}
          />
        </div>
      </div>
    </div>
  );
}

// Helper function to convert API response to chat messages
function convertToChatlMessages(
  details: ConversationDetailsResponse,
): ChatMessage[] {
  // Create a map for quick parent message lookup
  const messageMap = new Map<string, ConversationMessage>();
  details.messages.forEach((msg) => messageMap.set(msg.uuid, msg));

  return details.messages
    .filter((msg) => !msg.isSidechain) // Filter out sidechain messages
    .map((msg) => {
      // Extract content from the message structure
      let content = msg.message;

      // Handle Anthropic message format
      if (typeof msg.message === "object" && "content" in msg.message) {
        content = msg.message.content;
      }

      return {
        id: msg.uuid,
        messageId: msg.uuid, // For historical messages, use UUID as messageId
        type: msg.type as "user" | "assistant" | "system",
        content: content,
        timestamp: msg.timestamp,
        workingDirectory: msg.cwd, // Add working directory from backend message
      };
    });
}
