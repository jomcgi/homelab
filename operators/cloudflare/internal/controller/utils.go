package controller

import (
	"crypto/sha256"
	"fmt"
)

// containsString checks if a string slice contains a specific string
func containsString(slice []string, s string) bool {
	for _, item := range slice {
		if item == s {
			return true
		}
	}
	return false
}

// removeString removes all occurrences of a string from a slice
func removeString(slice []string, s string) []string {
	var result []string
	for _, item := range slice {
		if item != s {
			result = append(result, item)
		}
	}
	return result
}

// calculateConfigMapChecksum calculates a checksum for ConfigMap data to trigger deployment rollouts
func calculateConfigMapChecksum(configData string) string {
	hash := sha256.Sum256([]byte(configData))
	return fmt.Sprintf("%x", hash)[:8] // Use first 8 characters
}