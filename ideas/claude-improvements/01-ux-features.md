# UX Improvements & Missing Features

## Overview
Enhance Claude Code's user experience with better visualization capabilities and development workflow integration.

## Features

### 1. Mock Preview Rendering
- **Diagram Support**: Render Mermaid and PlantUML diagrams inline in chat responses
- **Markdown Preview**: Live markdown rendering with GitHub-flavored markdown support
- **Syntax Highlighting**: Language-specific syntax highlighting with theme support
- **Image Preview**: Display generated images and screenshots inline

### 2. Development Server Integration
- **Port Routing**: Proxy development server ports (3000-3999) to accessible URLs
- **Service URL**: Route `npm run dev` output to `claude.jomcgi.dev/preview/*`
- **Terminal Integration**: Embed ttyd for terminal access within Claude UI
- **Port Forwarding UI**: Visual interface to manage and expose local dev servers

### 3. Enhanced Code Editor Features
- **Multi-file Diff View**: Show changes across multiple files simultaneously
- **File Tree Navigation**: Interactive file browser with search capabilities
- **Code Folding**: Collapse/expand code sections for better navigation
- **Split Pane Editor**: View and edit multiple files side-by-side

## Implementation Details

### Nginx Configuration for Dev Server Routing
```nginx
location ~ ^/preview/(\d+)/(.*)$ {
    proxy_pass http://claude:$1/$2;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### Mermaid Diagram Rendering
- Client-side rendering using mermaid.js
- Server-side rendering option for better performance
- Export to SVG/PNG functionality
- Dark mode support for diagrams

### Terminal Session Management
- Persistent terminal sessions across page refreshes
- Multiple terminal support with tabs
- Command history preservation
- Customizable shell environment

## Benefits
- **Improved Visualization**: Better understanding of system architecture and data flow
- **Faster Development**: Immediate preview of changes without context switching
- **Enhanced Productivity**: Integrated development environment within Claude
- **Better Collaboration**: Share previews and diagrams easily

## Technical Requirements
- Mermaid.js library for diagram rendering
- WebSocket support for terminal sessions
- Reverse proxy configuration for dev servers
- Browser-based markdown renderer

## Success Metrics
- Reduced time to preview changes
- Increased usage of diagram features
- Improved developer satisfaction scores
- Decreased context switching between tools