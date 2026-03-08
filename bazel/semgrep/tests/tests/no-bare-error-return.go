package tests

import (
	"errors"
	"fmt"
)

// ruleid: no-bare-error-return
func doSomethingBad() error {
	err := someOperation()
	if err != nil {
		return err
	}
	return nil
}

// ok: nil return is always fine
func doSomethingOk1() error {
	return nil
}

// ok: wrapping with fmt.Errorf is correct
func doSomethingOk2() error {
	err := someOperation()
	if err != nil {
		return fmt.Errorf("someOperation failed: %w", err)
	}
	return nil
}

// ok: creating a new error is fine
func doSomethingOk3() error {
	return errors.New("static error message")
}

// ok: wrapping an existing error with additional context
func doSomethingOk4() error {
	err := someOperation()
	if err != nil {
		return fmt.Errorf("context about what failed: %w", err)
	}
	return nil
}

// Helper stub
func someOperation() error { return nil }
