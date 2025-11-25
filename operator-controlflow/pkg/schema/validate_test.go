package schema_test

import (
	"strings"
	"testing"

	"github.com/jomcgi/homelab/operator-controlflow/pkg/schema"
)

func TestParse(t *testing.T) {
	yaml := `
apiVersion: controlflow.io/v1alpha1
kind: StateMachine
metadata:
  name: TestResource
  group: test.io
  version: v1alpha1
status:
  phaseField: phase
states:
  - name: Pending
    initial: true
  - name: Ready
    terminal: true
transitions:
  - from: Pending
    to: Ready
    action: MarkReady
`
	sm, err := schema.Parse([]byte(yaml))
	if err != nil {
		t.Fatalf("Parse failed: %v", err)
	}

	if sm.Metadata.Name != "TestResource" {
		t.Errorf("Expected name 'TestResource', got %q", sm.Metadata.Name)
	}

	if len(sm.States) != 2 {
		t.Errorf("Expected 2 states, got %d", len(sm.States))
	}

	if len(sm.Transitions) != 1 {
		t.Errorf("Expected 1 transition, got %d", len(sm.Transitions))
	}
}

func TestValidate_ValidMachine(t *testing.T) {
	yaml := `
apiVersion: controlflow.io/v1alpha1
kind: StateMachine
metadata:
  name: TestResource
  group: test.io
  version: v1alpha1
status:
  phaseField: phase
states:
  - name: Pending
    initial: true
  - name: Ready
    terminal: true
transitions:
  - from: Pending
    to: Ready
    action: MarkReady
`
	sm, err := schema.Parse([]byte(yaml))
	if err != nil {
		t.Fatalf("Parse failed: %v", err)
	}

	if err := schema.Validate(sm); err != nil {
		t.Fatalf("Validate failed: %v", err)
	}
}

func TestValidate_MissingInitialState(t *testing.T) {
	yaml := `
apiVersion: controlflow.io/v1alpha1
kind: StateMachine
metadata:
  name: TestResource
  group: test.io
  version: v1alpha1
status:
  phaseField: phase
states:
  - name: Pending
  - name: Ready
    terminal: true
transitions:
  - from: Pending
    to: Ready
    action: MarkReady
`
	sm, err := schema.Parse([]byte(yaml))
	if err != nil {
		t.Fatalf("Parse failed: %v", err)
	}

	err = schema.Validate(sm)
	if err == nil {
		t.Fatal("Expected validation error for missing initial state")
	}

	if !strings.Contains(err.Error(), "initial state") {
		t.Errorf("Expected error about initial state, got: %v", err)
	}
}

func TestValidate_MultipleInitialStates(t *testing.T) {
	yaml := `
apiVersion: controlflow.io/v1alpha1
kind: StateMachine
metadata:
  name: TestResource
  group: test.io
  version: v1alpha1
status:
  phaseField: phase
states:
  - name: Pending
    initial: true
  - name: Other
    initial: true
  - name: Ready
    terminal: true
transitions:
  - from: Pending
    to: Ready
    action: MarkReady
`
	sm, err := schema.Parse([]byte(yaml))
	if err != nil {
		t.Fatalf("Parse failed: %v", err)
	}

	err = schema.Validate(sm)
	if err == nil {
		t.Fatal("Expected validation error for multiple initial states")
	}

	if !strings.Contains(err.Error(), "initial state") {
		t.Errorf("Expected error about initial state, got: %v", err)
	}
}

func TestValidate_ReservedFieldName(t *testing.T) {
	yaml := `
apiVersion: controlflow.io/v1alpha1
kind: StateMachine
metadata:
  name: TestResource
  group: test.io
  version: v1alpha1
status:
  phaseField: phase
states:
  - name: Pending
    initial: true
    fields:
      Phase: string
  - name: Ready
    terminal: true
transitions:
  - from: Pending
    to: Ready
    action: MarkReady
`
	sm, err := schema.Parse([]byte(yaml))
	if err != nil {
		t.Fatalf("Parse failed: %v", err)
	}

	err = schema.Validate(sm)
	if err == nil {
		t.Fatal("Expected validation error for reserved field name 'Phase'")
	}

	if !strings.Contains(err.Error(), "Phase") {
		t.Errorf("Expected error about 'Phase', got: %v", err)
	}
}

func TestValidate_ReservedStateName(t *testing.T) {
	yaml := `
apiVersion: controlflow.io/v1alpha1
kind: StateMachine
metadata:
  name: TestResource
  group: test.io
  version: v1alpha1
status:
  phaseField: phase
states:
  - name: Pending
    initial: true
  - name: Unknown
  - name: Ready
    terminal: true
transitions:
  - from: Pending
    to: Ready
    action: MarkReady
`
	sm, err := schema.Parse([]byte(yaml))
	if err != nil {
		t.Fatalf("Parse failed: %v", err)
	}

	err = schema.Validate(sm)
	if err == nil {
		t.Fatal("Expected validation error for reserved state name 'Unknown'")
	}

	if !strings.Contains(err.Error(), "Unknown") {
		t.Errorf("Expected error about 'Unknown', got: %v", err)
	}
}

func TestValidate_UndefinedFieldGroup(t *testing.T) {
	yaml := `
apiVersion: controlflow.io/v1alpha1
kind: StateMachine
metadata:
  name: TestResource
  group: test.io
  version: v1alpha1
status:
  phaseField: phase
states:
  - name: Pending
    initial: true
    fieldGroups: [nonexistent]
  - name: Ready
    terminal: true
transitions:
  - from: Pending
    to: Ready
    action: MarkReady
`
	sm, err := schema.Parse([]byte(yaml))
	if err != nil {
		t.Fatalf("Parse failed: %v", err)
	}

	err = schema.Validate(sm)
	if err == nil {
		t.Fatal("Expected validation error for undefined field group")
	}

	if !strings.Contains(err.Error(), "nonexistent") {
		t.Errorf("Expected error about 'nonexistent', got: %v", err)
	}
}

func TestValidate_UndefinedTransitionState(t *testing.T) {
	yaml := `
apiVersion: controlflow.io/v1alpha1
kind: StateMachine
metadata:
  name: TestResource
  group: test.io
  version: v1alpha1
status:
  phaseField: phase
states:
  - name: Pending
    initial: true
  - name: Ready
    terminal: true
transitions:
  - from: Pending
    to: NonExistent
    action: MarkReady
`
	sm, err := schema.Parse([]byte(yaml))
	if err != nil {
		t.Fatalf("Parse failed: %v", err)
	}

	err = schema.Validate(sm)
	if err == nil {
		t.Fatal("Expected validation error for undefined destination state")
	}

	if !strings.Contains(err.Error(), "NonExistent") {
		t.Errorf("Expected error about 'NonExistent', got: %v", err)
	}
}

func TestValidate_UndefinedGuard(t *testing.T) {
	yaml := `
apiVersion: controlflow.io/v1alpha1
kind: StateMachine
metadata:
  name: TestResource
  group: test.io
  version: v1alpha1
status:
  phaseField: phase
states:
  - name: Pending
    initial: true
  - name: Ready
    terminal: true
transitions:
  - from: Pending
    to: Ready
    action: MarkReady
    guard: nonexistent
`
	sm, err := schema.Parse([]byte(yaml))
	if err != nil {
		t.Fatalf("Parse failed: %v", err)
	}

	err = schema.Validate(sm)
	if err == nil {
		t.Fatal("Expected validation error for undefined guard")
	}

	if !strings.Contains(err.Error(), "nonexistent") {
		t.Errorf("Expected error about 'nonexistent', got: %v", err)
	}
}

func TestValidate_DuplicateStateName(t *testing.T) {
	yaml := `
apiVersion: controlflow.io/v1alpha1
kind: StateMachine
metadata:
  name: TestResource
  group: test.io
  version: v1alpha1
status:
  phaseField: phase
states:
  - name: Pending
    initial: true
  - name: Pending
  - name: Ready
    terminal: true
transitions:
  - from: Pending
    to: Ready
    action: MarkReady
`
	sm, err := schema.Parse([]byte(yaml))
	if err != nil {
		t.Fatalf("Parse failed: %v", err)
	}

	err = schema.Validate(sm)
	if err == nil {
		t.Fatal("Expected validation error for duplicate state name")
	}

	if !strings.Contains(err.Error(), "duplicate") {
		t.Errorf("Expected error about 'duplicate', got: %v", err)
	}
}

func TestValidate_TransitionFromMultipleStates(t *testing.T) {
	yaml := `
apiVersion: controlflow.io/v1alpha1
kind: StateMachine
metadata:
  name: TestResource
  group: test.io
  version: v1alpha1
status:
  phaseField: phase
states:
  - name: Pending
    initial: true
  - name: Creating
  - name: Ready
    terminal: true
  - name: Failed
    error: true
transitions:
  - from: Pending
    to: Creating
    action: StartCreation
  - from: Creating
    to: Ready
    action: MarkReady
  - from: [Pending, Creating]
    to: Failed
    action: MarkFailed
`
	sm, err := schema.Parse([]byte(yaml))
	if err != nil {
		t.Fatalf("Parse failed: %v", err)
	}

	if err := schema.Validate(sm); err != nil {
		t.Fatalf("Validate failed: %v", err)
	}

	// Verify the multi-source transition was parsed correctly
	found := false
	for _, tr := range sm.Transitions {
		if tr.Action == "MarkFailed" {
			if len(tr.From.States) != 2 {
				t.Errorf("Expected 2 source states for MarkFailed, got %d", len(tr.From.States))
			}
			found = true
		}
	}
	if !found {
		t.Error("MarkFailed transition not found")
	}
}

func TestValidate_FieldGroups(t *testing.T) {
	yaml := `
apiVersion: controlflow.io/v1alpha1
kind: StateMachine
metadata:
  name: TestResource
  group: test.io
  version: v1alpha1
status:
  phaseField: phase
fieldGroups:
  commonData:
    resourceID: string
    resourceName: string
states:
  - name: Pending
    initial: true
  - name: Ready
    terminal: true
    fieldGroups: [commonData]
    fields:
      extraField: int
transitions:
  - from: Pending
    to: Ready
    action: MarkReady
`
	sm, err := schema.Parse([]byte(yaml))
	if err != nil {
		t.Fatalf("Parse failed: %v", err)
	}

	if err := schema.Validate(sm); err != nil {
		t.Fatalf("Validate failed: %v", err)
	}

	// Verify field group resolution
	var readyState schema.State
	for _, s := range sm.States {
		if s.Name == "Ready" {
			readyState = s
			break
		}
	}

	resolved := readyState.Resolve(sm.FieldGroups)
	if len(resolved.AllFields) != 3 {
		t.Errorf("Expected 3 total fields, got %d: %v", len(resolved.AllFields), resolved.AllFields)
	}

	if _, ok := resolved.AllFields["resourceID"]; !ok {
		t.Error("Expected 'resourceID' from field group")
	}

	if _, ok := resolved.AllFields["extraField"]; !ok {
		t.Error("Expected 'extraField' from direct fields")
	}
}

func TestValidate_GoKeywordAsStateName(t *testing.T) {
	yaml := `
apiVersion: controlflow.io/v1alpha1
kind: StateMachine
metadata:
  name: TestResource
  group: test.io
  version: v1alpha1
status:
  phaseField: phase
states:
  - name: Pending
    initial: true
  - name: func
  - name: Ready
    terminal: true
transitions:
  - from: Pending
    to: Ready
    action: MarkReady
`
	sm, err := schema.Parse([]byte(yaml))
	if err != nil {
		t.Fatalf("Parse failed: %v", err)
	}

	err = schema.Validate(sm)
	if err == nil {
		t.Fatal("Expected validation error for Go keyword as state name")
	}

	if !strings.Contains(err.Error(), "func") {
		t.Errorf("Expected error about 'func', got: %v", err)
	}
}

func TestValidate_LowercaseMetadataName(t *testing.T) {
	yaml := `
apiVersion: controlflow.io/v1alpha1
kind: StateMachine
metadata:
  name: testResource
  group: test.io
  version: v1alpha1
status:
  phaseField: phase
states:
  - name: Pending
    initial: true
  - name: Ready
    terminal: true
transitions:
  - from: Pending
    to: Ready
    action: MarkReady
`
	sm, err := schema.Parse([]byte(yaml))
	if err != nil {
		t.Fatalf("Parse failed: %v", err)
	}

	err = schema.Validate(sm)
	if err == nil {
		t.Fatal("Expected validation error for lowercase metadata name")
	}

	if !strings.Contains(err.Error(), "uppercase") {
		t.Errorf("Expected error about uppercase, got: %v", err)
	}
}

func TestValidate_RequeueDuration(t *testing.T) {
	yaml := `
apiVersion: controlflow.io/v1alpha1
kind: StateMachine
metadata:
  name: TestResource
  group: test.io
  version: v1alpha1
status:
  phaseField: phase
states:
  - name: Pending
    initial: true
    requeue: 5s
  - name: Creating
    requeue: 1m30s
  - name: Ready
    terminal: true
transitions:
  - from: Pending
    to: Creating
    action: StartCreation
  - from: Creating
    to: Ready
    action: MarkReady
`
	sm, err := schema.Parse([]byte(yaml))
	if err != nil {
		t.Fatalf("Parse failed: %v", err)
	}

	if err := schema.Validate(sm); err != nil {
		t.Fatalf("Validate failed: %v", err)
	}

	// Verify durations were parsed
	for _, s := range sm.States {
		switch s.Name {
		case "Pending":
			if s.Requeue.Seconds() != 5 {
				t.Errorf("Expected Pending requeue 5s, got %v", s.Requeue)
			}
		case "Creating":
			if s.Requeue.Seconds() != 90 {
				t.Errorf("Expected Creating requeue 90s, got %v", s.Requeue)
			}
		}
	}
}
