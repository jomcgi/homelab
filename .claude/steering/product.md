# Product Steering Document

## Vision
A personal Kubernetes homelab that serves as both a platform for running useful services and a learning environment for mastering Kubernetes operators and SRE best practices.

## Primary User
- **Individual developer** (solo user)
- Some public-facing websites for general access
- Selected services exposed to friends on request

## Core Objectives
1. **Learning Platform**: Deep understanding of Kubernetes operators and SRE best practices
2. **Service Hosting**: Reliable platform for personal tools and automation
3. **Experimentation**: Easy deployment of new tools and technologies as discovered
4. **Observability**: Know immediately when things break, measure everything

## Current Services
- **Hiking Route Finder** (hikes.jomcgi.dev) - Public website for finding Scottish hikes with good weather
- **Workflow Automation** (N8N) - Process automation and integrations

## Planned Services
1. **N8N Workflows** - Advanced automation and integration platform
2. **Obsidian Server** - Linux server running Obsidian with official sync
   - Plugin for API exposure to automate note interactions
3. **AIS Maritime Streaming** - Real-time vessel tracking for local bay
   - Clickhouse for time-series data storage
   - NATS JetStream for message streaming
   - Visualization service for maritime data
4. **Future Integrations**:
   - Obsidian Sync (official paid service)
   - Various LLM providers for AI capabilities

## Success Metrics
- **Availability**: Personal use tolerates downtime, but alerts are critical
- **Observability**: Complete visibility into system health and performance
- **Response Times**: Web requests must be fast, batch processing can be slow
- **SLOs**: Defined service level objectives to prioritize improvement efforts
- **Learning Velocity**: Regular deployment of new operators and services

## Key Constraints
- **Single User**: No multi-tenancy or user management complexity
- **Resource Aware**: Must work within cluster constraints (currently 3x 12CPU/16GB nodes)
- **Security First**: Zero internet exposure except through Cloudflare tunnels
- **Simplicity**: Prefer simple, understandable solutions over complex ones

## Product Principles
1. **Easy Deployment**: New tools should be deployable with minimal friction
2. **Observable by Default**: Every service must expose metrics and health status
3. **Secure by Design**: All services follow zero-trust security model
4. **Learning Focused**: Choose technologies that advance SRE/operator knowledge
5. **Pragmatic Choices**: Personal use allows for practical trade-offs