package copy

import (
	"errors"
	"fmt"
	"testing"
)

func TestPermanent_IsPermanent(t *testing.T) {
	inner := errors.New("not found (HTTP 404)")
	err := Permanent(inner)

	if !IsPermanent(err) {
		t.Error("IsPermanent(Permanent(err)) = false, want true")
	}
}

func TestIsPermanent_PlainError(t *testing.T) {
	err := errors.New("connection refused")

	if IsPermanent(err) {
		t.Error("IsPermanent(plain error) = true, want false")
	}
}

func TestIsPermanent_Nil(t *testing.T) {
	if IsPermanent(nil) {
		t.Error("IsPermanent(nil) = true, want false")
	}
}

func TestPermanent_ErrorMessagePreserved(t *testing.T) {
	msg := "unauthorized (HTTP 401): bad token"
	err := Permanent(errors.New(msg))

	if err.Error() != msg {
		t.Errorf("Permanent(err).Error() = %q, want %q", err.Error(), msg)
	}
}

func TestPermanent_Unwrap(t *testing.T) {
	inner := errors.New("repo not found")
	err := Permanent(inner)

	if !errors.Is(err, inner) {
		t.Error("errors.Is(Permanent(inner), inner) = false, want true (Unwrap must return inner)")
	}
}

func TestIsPermanent_WrappedInFmt(t *testing.T) {
	// Wrapping a PermanentError in fmt.Errorf with %w should still be detected
	// because errors.As traverses the chain.
	inner := errors.New("no weight files")
	perm := Permanent(inner)
	wrapped := fmt.Errorf("copy failed: %w", perm)

	if !IsPermanent(wrapped) {
		t.Error("IsPermanent(fmt.Errorf wrapped PermanentError) = false, want true")
	}
}

func TestIsPermanent_NonPermanentWrapped(t *testing.T) {
	// Wrapping a plain error in fmt.Errorf should still not be permanent.
	plain := errors.New("timeout")
	wrapped := fmt.Errorf("operation failed: %w", plain)

	if IsPermanent(wrapped) {
		t.Error("IsPermanent(fmt.Errorf wrapped plain error) = true, want false")
	}
}

func TestPermanentError_TypeAssertion(t *testing.T) {
	inner := errors.New("mixed model formats")
	err := Permanent(inner)

	var pe *PermanentError
	if !errors.As(err, &pe) {
		t.Error("errors.As(Permanent(err), *PermanentError) = false, want true")
	}
	if pe.Err != inner {
		t.Errorf("PermanentError.Err = %v, want %v", pe.Err, inner)
	}
}
