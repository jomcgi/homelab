package main

import (
	"context"
	"testing"
	"time"
)

func TestFindingsStore_ShouldEscalate_NewFinding(t *testing.T) {
	store := NewMemFindingsStore()
	ctx := context.Background()

	ok, err := store.ShouldEscalate(ctx, "fp-1")
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Error("expected new finding to be escalatable")
	}
}

func TestFindingsStore_ShouldEscalate_DuplicateFinding(t *testing.T) {
	store := NewMemFindingsStore()
	ctx := context.Background()

	store.MarkEscalated(ctx, "fp-1", 1*time.Hour)

	ok, err := store.ShouldEscalate(ctx, "fp-1")
	if err != nil {
		t.Fatal(err)
	}
	if ok {
		t.Error("expected escalated finding to be blocked")
	}
}

func TestFindingsStore_MarkResolved(t *testing.T) {
	store := NewMemFindingsStore()
	ctx := context.Background()

	store.MarkEscalated(ctx, "fp-1", 1*time.Hour)
	store.MarkResolved(ctx, "fp-1")

	ok, err := store.ShouldEscalate(ctx, "fp-1")
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Error("expected resolved finding to be escalatable again")
	}
}

func TestFindingsStore_TTLExpiry(t *testing.T) {
	store := NewMemFindingsStore()
	ctx := context.Background()

	store.MarkEscalated(ctx, "fp-1", 1*time.Millisecond)
	time.Sleep(5 * time.Millisecond)

	ok, err := store.ShouldEscalate(ctx, "fp-1")
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Error("expected expired finding to be escalatable")
	}
}
