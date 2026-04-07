package statemachine

// Dedicated tests for model_cache_visit.go.
//
// The shared test files already cover FuncVisitor behaviour (Default callbacks,
// nil handler zero-values, per-state specific handler precedence) and the
// Visit dispatching function.
//
// This file adds:
//   - A custom struct that implements ModelCacheVisitor[T] directly (not via
//     FuncVisitor) to verify the sealed interface works with user-defined types.
//   - Per-Visit-method unit tests on ModelCacheFuncVisitor to confirm the
//     if-chain precedence holds for every method individually.
//   - Verify the state value passed to Visit is forwarded unchanged to the
//     visitor method (identity preservation).

import (
	"testing"
)

// =============================================================================
// Custom struct implementing ModelCacheVisitor[T]
// =============================================================================

// phaseCollector implements ModelCacheVisitor[string] and returns the Phase()
// string for each state.  This exercises the interface directly without going
// through ModelCacheFuncVisitor.
type phaseCollector struct{}

func (phaseCollector) VisitPending(s ModelCachePending) string   { return s.Phase() }
func (phaseCollector) VisitResolving(s ModelCacheResolving) string { return s.Phase() }
func (phaseCollector) VisitSyncing(s ModelCacheSyncing) string   { return s.Phase() }
func (phaseCollector) VisitReady(s ModelCacheReady) string       { return s.Phase() }
func (phaseCollector) VisitFailed(s ModelCacheFailed) string     { return s.Phase() }
func (phaseCollector) VisitUnknown(s ModelCacheUnknown) string   { return s.Phase() }

// Visit must dispatch to the correct VisitX method for every concrete type.
func TestVisit_CustomVisitorStruct_DispatchesCorrectly(t *testing.T) {
	mc := newMC("")
	visitor := phaseCollector{}

	cases := []struct {
		state    ModelCacheState
		wantPhase string
	}{
		{ModelCachePending{resource: mc}, PhasePending},
		{ModelCacheResolving{resource: mc}, PhaseResolving},
		{ModelCacheSyncing{resource: mc}, PhaseSyncing},
		{ModelCacheReady{resource: mc}, PhaseReady},
		{ModelCacheFailed{resource: mc}, PhaseFailed},
		{ModelCacheUnknown{resource: mc, ObservedPhase: "x"}, PhaseUnknown},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.wantPhase, func(t *testing.T) {
			got := Visit(tc.state, visitor)
			if got != tc.wantPhase {
				t.Errorf("Visit(%T) = %q, want %q", tc.state, got, tc.wantPhase)
			}
		})
	}
}

// =============================================================================
// FuncVisitor: per-method handler-vs-Default if-chain (unit level)
// =============================================================================

// These tests call each VisitX method directly on *ModelCacheFuncVisitor to
// isolate the if-chain in that method: handler set → returns handler result,
// handler nil + Default set → returns Default, both nil → zero value.

func TestFuncVisitor_VisitPending_HandlerChain(t *testing.T) {
	mc := newMC("")
	s := ModelCachePending{resource: mc}

	// handler set
	v1 := &ModelCacheFuncVisitor[string]{
		OnPending: func(_ ModelCachePending) string { return "handler" },
		Default:   func(_ ModelCacheState) string { return "default" },
	}
	if got := v1.VisitPending(s); got != "handler" {
		t.Errorf("VisitPending with handler: got %q, want \"handler\"", got)
	}

	// handler nil, Default set
	v2 := &ModelCacheFuncVisitor[string]{
		Default: func(_ ModelCacheState) string { return "default" },
	}
	if got := v2.VisitPending(s); got != "default" {
		t.Errorf("VisitPending nil handler+Default: got %q, want \"default\"", got)
	}

	// both nil → zero value
	v3 := &ModelCacheFuncVisitor[string]{}
	if got := v3.VisitPending(s); got != "" {
		t.Errorf("VisitPending nil handler+nil Default: got %q, want \"\"", got)
	}
}

func TestFuncVisitor_VisitResolving_HandlerChain(t *testing.T) {
	mc := newMC("")
	s := ModelCacheResolving{resource: mc}

	v1 := &ModelCacheFuncVisitor[string]{
		OnResolving: func(_ ModelCacheResolving) string { return "handler" },
		Default:     func(_ ModelCacheState) string { return "default" },
	}
	if got := v1.VisitResolving(s); got != "handler" {
		t.Errorf("VisitResolving with handler: got %q", got)
	}

	v2 := &ModelCacheFuncVisitor[string]{
		Default: func(_ ModelCacheState) string { return "default" },
	}
	if got := v2.VisitResolving(s); got != "default" {
		t.Errorf("VisitResolving nil handler+Default: got %q", got)
	}

	v3 := &ModelCacheFuncVisitor[string]{}
	if got := v3.VisitResolving(s); got != "" {
		t.Errorf("VisitResolving nil+nil: got %q", got)
	}
}

func TestFuncVisitor_VisitSyncing_HandlerChain(t *testing.T) {
	mc := newMC("")
	s := ModelCacheSyncing{resource: mc}

	v1 := &ModelCacheFuncVisitor[string]{
		OnSyncing: func(_ ModelCacheSyncing) string { return "handler" },
		Default:   func(_ ModelCacheState) string { return "default" },
	}
	if got := v1.VisitSyncing(s); got != "handler" {
		t.Errorf("VisitSyncing with handler: got %q", got)
	}

	v2 := &ModelCacheFuncVisitor[string]{
		Default: func(_ ModelCacheState) string { return "default" },
	}
	if got := v2.VisitSyncing(s); got != "default" {
		t.Errorf("VisitSyncing nil handler+Default: got %q", got)
	}

	v3 := &ModelCacheFuncVisitor[string]{}
	if got := v3.VisitSyncing(s); got != "" {
		t.Errorf("VisitSyncing nil+nil: got %q", got)
	}
}

func TestFuncVisitor_VisitReady_HandlerChain(t *testing.T) {
	mc := newMC("")
	s := ModelCacheReady{resource: mc}

	v1 := &ModelCacheFuncVisitor[string]{
		OnReady: func(_ ModelCacheReady) string { return "handler" },
		Default: func(_ ModelCacheState) string { return "default" },
	}
	if got := v1.VisitReady(s); got != "handler" {
		t.Errorf("VisitReady with handler: got %q", got)
	}

	v2 := &ModelCacheFuncVisitor[string]{
		Default: func(_ ModelCacheState) string { return "default" },
	}
	if got := v2.VisitReady(s); got != "default" {
		t.Errorf("VisitReady nil handler+Default: got %q", got)
	}

	v3 := &ModelCacheFuncVisitor[string]{}
	if got := v3.VisitReady(s); got != "" {
		t.Errorf("VisitReady nil+nil: got %q", got)
	}
}

func TestFuncVisitor_VisitFailed_HandlerChain(t *testing.T) {
	mc := newMC("")
	s := ModelCacheFailed{resource: mc}

	v1 := &ModelCacheFuncVisitor[string]{
		OnFailed: func(_ ModelCacheFailed) string { return "handler" },
		Default:  func(_ ModelCacheState) string { return "default" },
	}
	if got := v1.VisitFailed(s); got != "handler" {
		t.Errorf("VisitFailed with handler: got %q", got)
	}

	v2 := &ModelCacheFuncVisitor[string]{
		Default: func(_ ModelCacheState) string { return "default" },
	}
	if got := v2.VisitFailed(s); got != "default" {
		t.Errorf("VisitFailed nil handler+Default: got %q", got)
	}

	v3 := &ModelCacheFuncVisitor[string]{}
	if got := v3.VisitFailed(s); got != "" {
		t.Errorf("VisitFailed nil+nil: got %q", got)
	}
}

func TestFuncVisitor_VisitUnknown_HandlerChain(t *testing.T) {
	mc := newMC("")
	s := ModelCacheUnknown{resource: mc, ObservedPhase: "x"}

	v1 := &ModelCacheFuncVisitor[string]{
		OnUnknown: func(_ ModelCacheUnknown) string { return "handler" },
		Default:   func(_ ModelCacheState) string { return "default" },
	}
	if got := v1.VisitUnknown(s); got != "handler" {
		t.Errorf("VisitUnknown with handler: got %q", got)
	}

	v2 := &ModelCacheFuncVisitor[string]{
		Default: func(_ ModelCacheState) string { return "default" },
	}
	if got := v2.VisitUnknown(s); got != "default" {
		t.Errorf("VisitUnknown nil handler+Default: got %q", got)
	}

	v3 := &ModelCacheFuncVisitor[string]{}
	if got := v3.VisitUnknown(s); got != "" {
		t.Errorf("VisitUnknown nil+nil: got %q", got)
	}
}

// =============================================================================
// State identity: Visit forwards the exact concrete state value
// =============================================================================

// The state passed to Visit must arrive unmodified at the visitor method.
// We verify this by extracting a field from the received state inside the handler.
func TestVisit_StateIdentityPreserved_Resolving(t *testing.T) {
	mc := newMC(PhaseResolving)
	input := ModelCacheResolving{
		resource: mc,
		ResolveResult: ResolveResult{
			ResolvedRef:      "ghcr.io/sentinel/model:v1",
			ResolvedRevision: "v1.0.0",
			Format:           "gguf",
			Digest:           "sha256:sentinel",
			FileCount:        42,
			TotalSize:        999999,
		},
	}

	var received ModelCacheResolving
	visitor := &ModelCacheFuncVisitor[string]{
		OnResolving: func(s ModelCacheResolving) string {
			received = s
			return "ok"
		},
	}

	got := Visit[string](input, visitor)
	if got != "ok" {
		t.Fatalf("Visit returned %q, want \"ok\"", got)
	}
	if received.ResolvedRef != input.ResolvedRef {
		t.Errorf("ResolvedRef: received %q, want %q", received.ResolvedRef, input.ResolvedRef)
	}
	if received.FileCount != input.FileCount {
		t.Errorf("FileCount: received %d, want %d", received.FileCount, input.FileCount)
	}
	if received.TotalSize != input.TotalSize {
		t.Errorf("TotalSize: received %d, want %d", received.TotalSize, input.TotalSize)
	}
}

func TestVisit_StateIdentityPreserved_Failed(t *testing.T) {
	mc := newMC(PhaseFailed)
	input := ModelCacheFailed{
		resource: mc,
		ErrorInfo: ErrorInfo{
			Permanent:    true,
			LastState:    "Syncing",
			ErrorMessage: "sentinel error",
		},
	}

	var received ModelCacheFailed
	visitor := &ModelCacheFuncVisitor[bool]{
		OnFailed: func(s ModelCacheFailed) bool {
			received = s
			return s.Permanent
		},
	}

	got := Visit[bool](input, visitor)
	if !got {
		t.Error("Visit should return Permanent=true")
	}
	if received.ErrorMessage != input.ErrorMessage {
		t.Errorf("ErrorMessage: received %q, want %q", received.ErrorMessage, input.ErrorMessage)
	}
	if received.LastState != input.LastState {
		t.Errorf("LastState: received %q, want %q", received.LastState, input.LastState)
	}
}
