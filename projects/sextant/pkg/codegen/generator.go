// Package codegen generates Go code from state machine definitions.
package codegen

import (
	"bytes"
	"embed"
	"fmt"
	"go/format"
	"os"
	"path/filepath"
	"strings"
	"text/template"
	"time"

	"github.com/jomcgi/homelab/projects/sextant/pkg/schema"
)

//go:embed templates/*.tmpl
var templates embed.FS

// Config configures code generation.
type Config struct {
	// OutputDir is the directory to write generated files
	OutputDir string

	// Package is the Go package name for generated code
	Package string

	// Module is the Go module path (e.g., "github.com/joe/operator")
	Module string

	// APIImportPath is the import path for the API types
	APIImportPath string
}

// Generator generates Go code from state machine definitions.
type Generator struct {
	config    Config
	templates *template.Template
}

// New creates a new Generator with the given configuration.
func New(config Config) (*Generator, error) {
	funcMap := template.FuncMap{
		"lower":           strings.ToLower,
		"upper":           strings.ToUpper,
		"title":           strings.Title,
		"camelToSnake":    camelToSnake,
		"toEventName":     toEventName,
		"goType":          goType,
		"defaultValue":    defaultValue,
		"hasRequeue":      hasRequeue,
		"durationLiteral": durationLiteral,
		"join":            strings.Join,
		"add":             func(a, b int) int { return a + b },
		"fieldGroupName":  fieldGroupName,
		"hasFieldInGroup": hasFieldInGroup,
		"contains":        contains,
	}

	tmpl, err := template.New("").Funcs(funcMap).ParseFS(templates, "templates/*.tmpl")
	if err != nil {
		return nil, fmt.Errorf("failed to parse templates: %w", err)
	}

	return &Generator{
		config:    config,
		templates: tmpl,
	}, nil
}

// Generate generates Go code for the given state machine.
func (g *Generator) Generate(sm *schema.StateMachine) error {
	// Ensure output directory exists
	if err := os.MkdirAll(g.config.OutputDir, 0o755); err != nil {
		return fmt.Errorf("failed to create output directory: %w", err)
	}

	// Build template data
	data := g.buildTemplateData(sm)

	// Generate each file
	files := []struct {
		name     string
		template string
	}{
		{fmt.Sprintf("%s_phases.go", camelToSnake(sm.Metadata.Name)), "phases.go.tmpl"},
		{fmt.Sprintf("%s_types.go", camelToSnake(sm.Metadata.Name)), "types.go.tmpl"},
		{fmt.Sprintf("%s_calculator.go", camelToSnake(sm.Metadata.Name)), "calculator.go.tmpl"},
		{fmt.Sprintf("%s_transitions.go", camelToSnake(sm.Metadata.Name)), "transitions.go.tmpl"},
		{fmt.Sprintf("%s_visit.go", camelToSnake(sm.Metadata.Name)), "visit.go.tmpl"},
		{fmt.Sprintf("%s_observability.go", camelToSnake(sm.Metadata.Name)), "observability.go.tmpl"},
		{fmt.Sprintf("%s_status.go", camelToSnake(sm.Metadata.Name)), "status.go.tmpl"},
	}

	for _, f := range files {
		if err := g.generateFile(f.name, f.template, data); err != nil {
			return fmt.Errorf("failed to generate %s: %w", f.name, err)
		}
	}

	// Conditionally generate metrics file when observability.metrics is enabled
	if sm.Observability.Metrics {
		metricsFile := fmt.Sprintf("%s_metrics.go", camelToSnake(sm.Metadata.Name))
		if err := g.generateFile(metricsFile, "metrics.go.tmpl", data); err != nil {
			return fmt.Errorf("failed to generate %s: %w", metricsFile, err)
		}
	}

	return nil
}

// generateFile generates a single file from a template.
func (g *Generator) generateFile(name, tmplName string, data *TemplateData) error {
	var buf bytes.Buffer

	if err := g.templates.ExecuteTemplate(&buf, tmplName, data); err != nil {
		return fmt.Errorf("template execution failed: %w", err)
	}

	// Format the Go code
	formatted, err := format.Source(buf.Bytes())
	if err != nil {
		// Write unformatted for debugging
		path := filepath.Join(g.config.OutputDir, name+".unformatted")
		os.WriteFile(path, buf.Bytes(), 0o644)
		return fmt.Errorf("go format failed (unformatted written to %s): %w", path, err)
	}

	// Write the file
	path := filepath.Join(g.config.OutputDir, name)
	if err := os.WriteFile(path, formatted, 0o644); err != nil {
		return fmt.Errorf("failed to write file: %w", err)
	}

	return nil
}

// TemplateData contains all data needed for code generation templates.
type TemplateData struct {
	// Package name for generated code
	Package string

	// Resource name (e.g., "CloudflareTunnel")
	Name string

	// API group (e.g., "cloudflare.io")
	Group string

	// API version (e.g., "v1alpha1")
	Version string

	// Import path for API types
	APIImportPath string

	// States in the state machine
	States []StateData

	// Field groups
	FieldGroups []FieldGroupData

	// Transitions organized by source state
	TransitionsByState map[string][]TransitionData

	// All transitions
	Transitions []TransitionData

	// Guards
	Guards map[string]schema.Guard

	// Observability config
	Observability schema.Observability

	// ErrorHandling config
	ErrorHandling *schema.ErrorHandling

	// SpecChangeHandling config
	SpecChangeHandling *schema.SpecChangeHandling

	// Initial state name
	InitialState string

	// Status field configuration
	PhaseField      string
	ConditionsField string
}

// StateData contains data for a single state.
type StateData struct {
	Name        string
	Initial     bool
	Terminal    bool
	Error       bool
	Deletion    bool
	Generated   bool
	Requeue     schema.Duration
	Fields      []FieldData
	FieldGroups []string
}

// FieldData contains data for a single field.
type FieldData struct {
	Name string
	Type string
}

// FieldGroupData contains data for a field group.
type FieldGroupData struct {
	Name   string
	Fields []FieldData
}

// TransitionData contains data for a single transition.
type TransitionData struct {
	From   []string
	To     string
	Action string
	Params []FieldData
	Guard  string
}

func (g *Generator) buildTemplateData(sm *schema.StateMachine) *TemplateData {
	data := &TemplateData{
		Package:            g.config.Package,
		Name:               sm.Metadata.Name,
		Group:              sm.Metadata.Group,
		Version:            sm.Metadata.Version,
		APIImportPath:      g.config.APIImportPath,
		Guards:             sm.Guards,
		Observability:      sm.Observability,
		ErrorHandling:      sm.ErrorHandling,
		SpecChangeHandling: sm.SpecChangeHandling,
		PhaseField:         sm.Status.PhaseField,
		ConditionsField:    sm.Status.ConditionsField,
		TransitionsByState: make(map[string][]TransitionData),
	}

	if data.ErrorHandling == nil {
		data.ErrorHandling = &schema.ErrorHandling{
			MaxRetries: 10,
			Backoff: schema.BackoffConfig{
				Base:       schema.Duration{Duration: 1 * time.Second},
				Multiplier: 2.0,
				Max:        schema.Duration{Duration: 5 * time.Minute},
				Jitter:     0.1,
			},
		}
	}

	// Apply defaults for SpecChangeHandling when enabled but field not specified
	if data.SpecChangeHandling != nil && data.SpecChangeHandling.Enabled {
		if data.SpecChangeHandling.ObservedGenerationField == "" {
			data.SpecChangeHandling.ObservedGenerationField = "observedGeneration"
		}
	}

	if data.PhaseField == "" {
		data.PhaseField = "phase"
	}
	if data.ConditionsField == "" {
		data.ConditionsField = "conditions"
	}

	// Convert field groups
	for name, group := range sm.FieldGroups {
		fg := FieldGroupData{Name: name}
		for fieldName, fieldType := range group {
			fg.Fields = append(fg.Fields, FieldData{Name: fieldName, Type: fieldType})
		}
		data.FieldGroups = append(data.FieldGroups, fg)
	}

	// Convert states
	for _, s := range sm.States {
		if s.Initial {
			data.InitialState = s.Name
		}

		// Build a set of fields that are in the field groups THIS STATE embeds
		embeddedFields := make(map[string]bool)
		for _, groupName := range s.FieldGroups {
			if group, ok := sm.FieldGroups[groupName]; ok {
				for fieldName := range group {
					embeddedFields[fieldName] = true
				}
			}
		}

		sd := StateData{
			Name:        s.Name,
			Initial:     s.Initial,
			Terminal:    s.Terminal,
			Error:       s.Error,
			Deletion:    s.Deletion,
			Generated:   s.Generated,
			Requeue:     s.Requeue,
			FieldGroups: s.FieldGroups,
		}

		// Only add fields that are not in embedded field groups for THIS state
		for fieldName, fieldType := range s.Fields {
			if !embeddedFields[fieldName] {
				sd.Fields = append(sd.Fields, FieldData{Name: fieldName, Type: fieldType})
			}
		}

		data.States = append(data.States, sd)
	}

	// Add Unknown state if not defined
	hasUnknown := false
	for _, s := range data.States {
		if s.Name == "Unknown" {
			hasUnknown = true
			break
		}
	}
	if !hasUnknown {
		data.States = append(data.States, StateData{
			Name:      "Unknown",
			Error:     true,
			Generated: true,
			Fields: []FieldData{
				{Name: "observedPhase", Type: "string"},
			},
		})
	}

	// Convert transitions
	for _, t := range sm.Transitions {
		td := TransitionData{
			From:   t.From.States,
			To:     t.To,
			Action: t.Action,
			Guard:  t.Guard,
		}

		for _, p := range t.Params {
			td.Params = append(td.Params, FieldData{Name: p.Name, Type: p.Type})
		}

		data.Transitions = append(data.Transitions, td)

		// Organize by source state
		for _, from := range t.From.States {
			data.TransitionsByState[from] = append(data.TransitionsByState[from], td)
		}
	}

	return data
}

// Helper functions for templates

func camelToSnake(s string) string {
	var result strings.Builder
	for i, r := range s {
		if i > 0 && r >= 'A' && r <= 'Z' {
			result.WriteRune('_')
		}
		result.WriteRune(r)
	}
	return strings.ToLower(result.String())
}

func toEventName(action string) string {
	var result strings.Builder
	for i, r := range action {
		if i > 0 && r >= 'A' && r <= 'Z' {
			result.WriteRune('_')
		}
		if r >= 'a' && r <= 'z' {
			result.WriteRune(r - 32)
		} else {
			result.WriteRune(r)
		}
	}
	return result.String()
}

func goType(t string) string {
	switch t {
	case "string", "int", "int32", "int64", "bool", "float32", "float64":
		return t
	default:
		return t
	}
}

func defaultValue(t string) string {
	switch t {
	case "string":
		return `""`
	case "int", "int32", "int64":
		return "0"
	case "bool":
		return "false"
	case "float32", "float64":
		return "0.0"
	default:
		return "nil"
	}
}

func hasRequeue(s StateData) bool {
	return s.Requeue.Duration > 0
}

func durationLiteral(d schema.Duration) string {
	if d.Duration == 0 {
		return "0"
	}
	return fmt.Sprintf("time.Duration(%d)", d.Duration)
}

func fieldGroupName(name string) string {
	return strings.Title(name)
}

// hasFieldInGroup checks if a field is already defined in any of the field groups
func hasFieldInGroup(field FieldData, groups []FieldGroupData) bool {
	for _, g := range groups {
		for _, f := range g.Fields {
			if f.Name == field.Name {
				return true
			}
		}
	}
	return false
}

// contains checks if a string is in a slice
func contains(slice []string, str string) bool {
	for _, s := range slice {
		if s == str {
			return true
		}
	}
	return false
}
