import type { StreamEvent, StreamStatus } from '../types';

/**
 * Maps stream events to user-friendly status messages
 */
export function mapStreamEventToStatus(event: StreamEvent, currentStatus?: StreamStatus): Partial<StreamStatus> {
  const updates: Partial<StreamStatus> = {
    lastEvent: event,
    lastEventTime: new Date().toISOString(),
  };

  switch (event.type) {
    case 'connected':
      return {
        ...updates,
        currentStatus: 'Running',
        connectionState: 'connected',
      };

    case 'system':
      if ('subtype' in event && event.subtype === 'init') {
        return {
          ...updates,
          currentStatus: 'Initializing...',
          connectionState: 'connected',
        };
      }
      break;

    case 'user':
      // Don't update status for user messages - just update the last event info
      return {
        lastEvent: event,
        lastEventTime: new Date().toISOString(),
      };

    case 'assistant':
      return mapAssistantMessage(event, updates);

    case 'result':
      return mapResultMessage(event, updates);

    case 'closed':
      return {
        ...updates,
        currentStatus: 'Closed',
        connectionState: 'disconnected',
      };

    case 'error':
      return {
        ...updates,
        currentStatus: 'Error occurred',
        connectionState: 'error',
      };

    case 'permission_request':
      return {
        ...updates,
        currentStatus: `Awaiting approval...`,
      };
  }

  return updates;
}

/**
 * Maps assistant messages to status updates
 */
function mapAssistantMessage(event: Extract<StreamEvent, { type: 'assistant' }>, updates: Partial<StreamStatus>): Partial<StreamStatus> {
  const message = event.message;
  const result: Partial<StreamStatus> = { ...updates };

  if (message.content && Array.isArray(message.content)) {
    // Check for tool use
    const toolUseItems = message.content.filter(item => 
      typeof item === 'object' && 'type' in item && item.type === 'tool_use'
    );

    if (toolUseItems.length > 0) {
      // Get the first tool being used
      const firstTool = toolUseItems[0];
      if (typeof firstTool === 'object' && 'name' in firstTool) {
        const toolName = firstTool.name as string;
        result.currentStatus = getToolStatusMessage(toolName);
      }
    } else {
      // No tools, just thinking
      result.currentStatus = 'Thinking...';
    }

  } else {
    // Fallback for non-array content
    result.currentStatus = 'Processing...';
  }

  return result;
}

/**
 * Maps result messages to status updates
 */
function mapResultMessage(event: Extract<StreamEvent, { type: 'result' }>, updates: Partial<StreamStatus>): Partial<StreamStatus> {
  const result: Partial<StreamStatus> = { ...updates };

  switch (event.subtype) {
    case 'success':
      result.currentStatus = 'Completed';
      result.connectionState = 'disconnected';
      break;
    case 'error_max_turns':
      result.currentStatus = 'Max turns reached';
      result.connectionState = 'disconnected';
      break;
    default:
      result.currentStatus = 'Finished';
      result.connectionState = 'disconnected';
  }

  // Include usage metrics if available
  if (event.usage) {
    result.toolMetrics = {
      linesAdded: 0,
      linesRemoved: 0,
      editCount: 0,
      writeCount: 0,
    };
  }

  return result;
}

/**
 * Get user-friendly status message for tool usage
 */
function getToolStatusMessage(toolName: string): string {
  const toolStatusMap: Record<string, string> = {
    // File operations
    'Read': 'Reading file...',
    'Write': 'Writing file...',
    'Edit': 'Editing file...',
    'MultiEdit': 'Editing multiple sections...',
    'NotebookRead': 'Reading notebook...',
    'NotebookEdit': 'Editing notebook...',
    
    // Search operations
    'Grep': 'Searching files...',
    'Glob': 'Finding files...',
    'LS': 'Listing directory...',
    
    // System operations
    'Bash': 'Running command...',
    'Task': 'Running task...',
    
    // Web operations
    'WebFetch': 'Fetching web content...',
    'WebSearch': 'Searching web...',
    
    // Todo operations
    'TodoRead': 'Reading To-Do...',
    'TodoWrite': 'Updating To-Do...',
    
    // Planning
    'exit_plan_mode': 'Finalizing plan...',
  };

  return toolStatusMap[toolName] || `Running ${toolName}...`;
}

/**
 * Extract tool metrics from stream events
 */
export function extractToolMetrics(events: StreamEvent[]): StreamStatus['toolMetrics'] {
  const metrics = {
    linesAdded: 0,
    linesRemoved: 0,
    editCount: 0,
    writeCount: 0,
  };

  events.forEach(event => {
    if (event.type === 'assistant' && event.message.content && Array.isArray(event.message.content)) {
      event.message.content.forEach(item => {
        if (typeof item === 'object' && 'type' in item && item.type === 'tool_use' && 'name' in item) {
          const toolName = item.name as string;
          
          // Count edits and writes
          if (toolName === 'Edit' || toolName === 'MultiEdit') {
            metrics.editCount++;
          } else if (toolName === 'Write' || toolName === 'NotebookEdit') {
            metrics.writeCount++;
          }
        }
      });
    }
  });

  return metrics;
}

/**
 * Get a concise summary of the current conversation state
 */
export function getConversationSummary(events: StreamEvent[]): string {
  if (events.length === 0) return 'No activity';

  const lastEvent = events[events.length - 1];
  
  // Check if conversation is complete
  if (lastEvent.type === 'result') {
    if (lastEvent.subtype === 'success') {
      return 'Task completed successfully';
    } else if (lastEvent.subtype === 'error_max_turns') {
      return 'Reached conversation limit';
    }
  }

  // Look for the last meaningful activity
  for (let i = events.length - 1; i >= 0; i--) {
    const event = events[i];
    
    if (event.type === 'assistant' && event.message.content && Array.isArray(event.message.content)) {
      const toolUse = event.message.content.find(item => 
        typeof item === 'object' && 'type' in item && item.type === 'tool_use'
      );
      
      if (toolUse && typeof toolUse === 'object' && 'name' in toolUse) {
        return `Last action: ${toolUse.name}`;
      }
      
      const textContent = event.message.content.find(item => 
        typeof item === 'object' && 'type' in item && item.type === 'text'
      );
      
      if (textContent && typeof textContent === 'object' && 'text' in textContent) {
        const text = textContent.text as string;
        return text.length > 50 ? text.substring(0, 47) + '...' : text;
      }
    }
  }

  return 'Active conversation';
}