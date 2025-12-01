// Package cookies provides session cookie retrieval for adventofcode.com
package cookies

import (
	"errors"
	"os"
	"strings"
)

var ErrSessionNotSet = errors.New("AOC_SESSION environment variable not set")

// GetSession retrieves the AOC session from environment variable or .env file
func GetSession() (string, error) {
	// Check environment variable
	if session := os.Getenv("AOC_SESSION"); session != "" {
		return session, nil
	}

	// Check .env file in current directory
	if data, err := os.ReadFile(".env"); err == nil {
		for _, line := range strings.Split(string(data), "\n") {
			line = strings.TrimSpace(line)
			if strings.HasPrefix(line, "AOC_SESSION=") {
				value := strings.TrimPrefix(line, "AOC_SESSION=")
				value = strings.Trim(value, "\"'") // Remove quotes if present
				if value != "" {
					return value, nil
				}
			}
		}
	}

	return "", ErrSessionNotSet
}
