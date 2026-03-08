package copy

import "errors"

// PermanentError wraps an error that should not be retried.
// Examples: 404 repo not found, 401 bad token, mixed formats, no weights.
type PermanentError struct {
	Err error
}

func (e *PermanentError) Error() string { return e.Err.Error() }
func (e *PermanentError) Unwrap() error { return e.Err }

// Permanent wraps err as a PermanentError.
func Permanent(err error) error {
	return &PermanentError{Err: err}
}

// IsPermanent reports whether err (or any error in its chain) is a PermanentError.
func IsPermanent(err error) bool {
	var pe *PermanentError
	return errors.As(err, &pe)
}
