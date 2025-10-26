# N8N Go Client

Typed Go client for the [n8n](https://n8n.io) workflow automation API, auto-generated from the official OpenAPI specification.

## Features

- ✅ **Type-safe** - Full type safety from OpenAPI spec
- ✅ **Observable** - Built-in OpenTelemetry tracing and structured logging
- ✅ **Auto-generated** - Always in sync with n8n API
- ✅ **Complete** - All n8n API endpoints supported

## Installation

```bash
go get github.com/jomcgi/homelab/pkg/n8n
```

## Usage

### Basic Usage

```go
package main

import (
    "context"
    "log"

    "github.com/jomcgi/homelab/pkg/n8n"
)

func main() {
    // Create client with API key
    client, err := n8n.NewObservableClient("https://n8n.example.com", "your-api-key")
    if err != nil {
        log.Fatal(err)
    }

    // List all workflows
    workflows, err := client.ListWorkflows(context.Background(), nil)
    if err != nil {
        log.Fatal(err)
    }

    for _, workflow := range *workflows.Data {
        log.Printf("Workflow: %s (ID: %s)", workflow.Name, *workflow.Id)
    }
}
```

### Creating a Workflow

```go
workflow := n8n.Workflow{
    Name: "My Workflow",
    Nodes: []n8n.Node{
        // Define your workflow nodes
    },
    Connections: map[string]interface{}{
        // Define your workflow connections
    },
    Settings: n8n.WorkflowSettings{},
}

created, err := client.CreateWorkflow(ctx, workflow)
if err != nil {
    log.Fatal(err)
}
```

### Working with Tags

```go
// Create a tag
tag := n8n.Tag{
    Name: "production",
}

created, err := client.CreateTag(ctx, tag)
if err != nil {
    log.Fatal(err)
}

// Add tag to workflow
tagIDs := n8n.TagIds{
    {Id: *created.Id},
}

err = client.UpdateWorkflowTags(ctx, workflowID, tagIDs)
if err != nil {
    log.Fatal(err)
}
```

### Using the Raw Generated Client

For full control, you can use the raw generated client directly:

```go
// Create raw client without observability wrapper
rawClient, err := n8n.NewClientWithResponses(
    "https://n8n.example.com",
    n8n.WithRequestEditorFn(func(ctx context.Context, req *http.Request) error {
        req.Header.Set("X-N8N-API-KEY", "your-api-key")
        return nil
    }),
)

// Use any generated method
resp, err := rawClient.GetWorkflowsWithResponse(ctx, nil)
if err != nil {
    log.Fatal(err)
}

if resp.JSON200 != nil {
    // Handle response
}
```

## Observability

The `ObservableClient` automatically:
- **Traces** all API calls with OpenTelemetry
- **Logs** operations with structured logging (slog)
- **Attributes** spans with workflow/tag IDs and counts

### Custom Logger

```go
import "log/slog"

logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
client := client.WithLogger(logger)
```

## Regenerating the Client

If the n8n API changes, regenerate the client:

```bash
# Update openapi.yaml with latest spec from n8n
# Then regenerate:
make generate

# Or manually:
go generate ./pkg/n8n
```

## Architecture

```
pkg/n8n/
├── openapi.yaml         # n8n OpenAPI specification
├── oapi-codegen.yaml    # Code generation config
├── generated.go         # Auto-generated client (DO NOT EDIT)
├── client.go            # Observable wrapper with tracing/logging
├── doc.go               # Package documentation + go:generate
└── tools.go             # Build tool dependencies
```

## Type Safety Example

```go
// Compile-time type checking ensures correctness
workflow := n8n.Workflow{
    Name: "Test",              // Required field (string)
    Nodes: []n8n.Node{},       // Correctly typed
    Connections: map[string]interface{}{},
    Settings: n8n.WorkflowSettings{}, // Required field
}

// Invalid code won't compile:
// workflow.Name = nil  // ❌ Error: cannot use nil as string
// workflow.ID = "123"  // ❌ Error: Id is *string, not string
```

## API Coverage

All n8n API endpoints are supported:

- ✅ Workflows (CRUD, activate/deactivate, transfer)
- ✅ Tags (CRUD, workflow tagging)
- ✅ Executions (list, get, retry, delete)
- ✅ Credentials (CRUD, schema)
- ✅ Users (list, create, delete, roles)
- ✅ Projects (CRUD, user management)
- ✅ Variables (CRUD)
- ✅ Source Control (pull)
- ✅ Audit (security audit)

## License

Part of the [jomcgi/homelab](https://github.com/jomcgi/homelab) project.
