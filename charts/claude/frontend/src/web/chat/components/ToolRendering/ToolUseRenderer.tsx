import React from 'react';
import type { ContentBlockParam } from '@anthropic-ai/sdk/resources/messages/messages';
import type { ChatMessage, ToolResult } from '../../types';
import { ToolLabel } from './ToolLabel';
import { ToolContent } from './ToolContent';

interface ToolUse {
  type: 'tool_use';
  id: string;
  name: string;
  input: any;
}

interface ToolUseRendererProps {
  toolUse: ToolUse;
  toolResult?: ToolResult;
  toolResults?: Record<string, ToolResult>;
  workingDirectory?: string;
  childrenMessages?: Record<string, ChatMessage[]>;
  expandedTasks?: Set<string>;
  onToggleTaskExpanded?: (toolUseId: string) => void;
}

export function ToolUseRenderer({ 
  toolUse, 
  toolResult, 
  toolResults = {},
  workingDirectory,
  childrenMessages = {},
  expandedTasks = new Set(),
  onToggleTaskExpanded
}: ToolUseRendererProps) {
  return (
    <>
      <ToolLabel 
        toolName={toolUse.name}
        toolInput={toolUse.input}
        workingDirectory={workingDirectory}
      />
      <ToolContent
        toolName={toolUse.name}
        toolInput={toolUse.input}
        toolResult={toolResult}
        workingDirectory={workingDirectory}
        toolUseId={toolUse.id}
        childrenMessages={childrenMessages}
        toolResults={toolResults}
      />
    </>
  );
}