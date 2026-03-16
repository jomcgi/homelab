package main

import (
	"context"
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"math/big"
	"net/http"
	"testing"
	"time"
)

// TestUserEmail_FromContext verifies userEmail extracts the email stored in the request context.
func TestUserEmail_FromContext(t *testing.T) {
	req, _ := http.NewRequest("GET", "/", nil)
	ctx := context.WithValue(req.Context(), userEmailKey, "test@example.com")
	req = req.WithContext(ctx)

	email := userEmail(req)
	if email != "test@example.com" {
		t.Errorf("userEmail got %q, want %q", email, "test@example.com")
	}
}

// TestUserEmail_Missing verifies userEmail returns an empty string when no email is in context.
func TestUserEmail_Missing(t *testing.T) {
	req, _ := http.NewRequest("GET", "/", nil)
	email := userEmail(req)
	if email != "" {
		t.Errorf("userEmail should return empty string when not set, got %q", email)
	}
}

// TestParseRSAPublicKey_Valid verifies parsing a valid RSA public key from base64url JWK components.
func TestParseRSAPublicKey_Valid(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generating RSA key: %v", err)
	}

	nB64 := base64.RawURLEncoding.EncodeToString(key.PublicKey.N.Bytes())
	eVal := big.NewInt(int64(key.PublicKey.E))
	eB64 := base64.RawURLEncoding.EncodeToString(eVal.Bytes())

	pub, err := parseRSAPublicKey(nB64, eB64)
	if err != nil {
		t.Fatalf("parseRSAPublicKey error: %v", err)
	}
	if pub.N.Cmp(key.PublicKey.N) != 0 {
		t.Error("N does not match original key")
	}
	if pub.E != key.PublicKey.E {
		t.Errorf("E got %d, want %d", pub.E, key.PublicKey.E)
	}
}

// TestParseRSAPublicKey_InvalidN verifies an error is returned for invalid base64 N.
func TestParseRSAPublicKey_InvalidN(t *testing.T) {
	_, err := parseRSAPublicKey("!!!invalid!!!", "AQAB")
	if err == nil {
		t.Error("expected error for invalid N base64, got nil")
	}
}

// TestParseRSAPublicKey_InvalidE verifies an error is returned for invalid base64 E.
func TestParseRSAPublicKey_InvalidE(t *testing.T) {
	_, err := parseRSAPublicKey("AQAB", "!!!invalid!!!")
	if err == nil {
		t.Error("expected error for invalid E base64, got nil")
	}
}

// makeSignedJWT creates a signed RS256 JWT for use in middleware tests.
func makeSignedJWT(t *testing.T, key *rsa.PrivateKey, kid, alg, email, issuer string, expDelta time.Duration) string {
	t.Helper()

	header := map[string]string{"alg": alg, "kid": kid, "typ": "JWT"}
	headerJSON, _ := json.Marshal(header)
	headerB64 := base64.RawURLEncoding.EncodeToString(headerJSON)

	claims := map[string]any{
		"email": email,
		"iss":   issuer,
		"exp":   time.Now().Add(expDelta).Unix(),
		"iat":   time.Now().Unix(),
	}
	claimsJSON, _ := json.Marshal(claims)
	claimsB64 := base64.RawURLEncoding.EncodeToString(claimsJSON)

	signingInput := headerB64 + "." + claimsB64
	h := sha256.Sum256([]byte(signingInput))
	sig, err := rsa.SignPKCS1v15(rand.Reader, key, crypto.SHA256, h[:])
	if err != nil {
		t.Fatalf("signing JWT: %v", err)
	}
	return signingInput + "." + base64.RawURLEncoding.EncodeToString(sig)
}

// TestValidateCFAccessJWT_MalformedJWT verifies an error for a token without 3 dot-separated parts.
func TestValidateCFAccessJWT_MalformedJWT(t *testing.T) {
	cache := &jwksCache{keys: make(map[string]*rsa.PublicKey)}
	_, err := validateCFAccessJWT("not-a-jwt", cache, "team.example.com")
	if err == nil {
		t.Error("expected error for malformed JWT, got nil")
	}
}

// TestValidateCFAccessJWT_WrongAlgorithm verifies an error for a non-RS256 algorithm.
func TestValidateCFAccessJWT_WrongAlgorithm(t *testing.T) {
	header := map[string]string{"alg": "HS256", "kid": "test-kid"}
	headerJSON, _ := json.Marshal(header)
	headerB64 := base64.RawURLEncoding.EncodeToString(headerJSON)
	token := headerB64 + ".payload.signature"

	cache := &jwksCache{keys: make(map[string]*rsa.PublicKey)}
	_, err := validateCFAccessJWT(token, cache, "team.example.com")
	if err == nil {
		t.Error("expected error for HS256 algorithm, got nil")
	}
}

// TestValidateCFAccessJWT_ValidToken verifies a correctly signed RS256 JWT is accepted.
func TestValidateCFAccessJWT_ValidToken(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generating key: %v", err)
	}

	teamDomain := "team.cloudflareaccess.com"
	issuer := fmt.Sprintf("https://%s", teamDomain)
	token := makeSignedJWT(t, key, "key1", "RS256", "user@example.com", issuer, time.Hour)

	cache := &jwksCache{
		keys:    map[string]*rsa.PublicKey{"key1": &key.PublicKey},
		fetched: time.Now(),
	}

	email, err := validateCFAccessJWT(token, cache, teamDomain)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if email != "user@example.com" {
		t.Errorf("email got %q, want %q", email, "user@example.com")
	}
}

// TestValidateCFAccessJWT_Expired verifies an error for a token with exp in the past.
func TestValidateCFAccessJWT_Expired(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generating key: %v", err)
	}

	teamDomain := "team.cloudflareaccess.com"
	issuer := fmt.Sprintf("https://%s", teamDomain)
	token := makeSignedJWT(t, key, "key1", "RS256", "user@example.com", issuer, -time.Hour)

	cache := &jwksCache{
		keys:    map[string]*rsa.PublicKey{"key1": &key.PublicKey},
		fetched: time.Now(),
	}

	_, err = validateCFAccessJWT(token, cache, teamDomain)
	if err == nil {
		t.Error("expected error for expired token, got nil")
	}
}

// TestValidateCFAccessJWT_WrongIssuer verifies an error when the issuer claim doesn't match the team domain.
func TestValidateCFAccessJWT_WrongIssuer(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generating key: %v", err)
	}

	teamDomain := "team.cloudflareaccess.com"
	token := makeSignedJWT(t, key, "key1", "RS256", "user@example.com", "https://evil.example.com", time.Hour)

	cache := &jwksCache{
		keys:    map[string]*rsa.PublicKey{"key1": &key.PublicKey},
		fetched: time.Now(),
	}

	_, err = validateCFAccessJWT(token, cache, teamDomain)
	if err == nil {
		t.Error("expected error for wrong issuer, got nil")
	}
}

// TestValidateCFAccessJWT_MissingEmail verifies an error when the email claim is absent.
func TestValidateCFAccessJWT_MissingEmail(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generating key: %v", err)
	}

	teamDomain := "team.cloudflareaccess.com"
	issuer := fmt.Sprintf("https://%s", teamDomain)

	// Build a token without an email claim.
	header := map[string]string{"alg": "RS256", "kid": "key1", "typ": "JWT"}
	headerJSON, _ := json.Marshal(header)
	headerB64 := base64.RawURLEncoding.EncodeToString(headerJSON)
	claims := map[string]any{
		"iss": issuer,
		"exp": time.Now().Add(time.Hour).Unix(),
		"iat": time.Now().Unix(),
	}
	claimsJSON, _ := json.Marshal(claims)
	claimsB64 := base64.RawURLEncoding.EncodeToString(claimsJSON)
	signingInput := headerB64 + "." + claimsB64
	h := sha256.Sum256([]byte(signingInput))
	sig, _ := rsa.SignPKCS1v15(rand.Reader, key, crypto.SHA256, h[:])
	token := signingInput + "." + base64.RawURLEncoding.EncodeToString(sig)

	cache := &jwksCache{
		keys:    map[string]*rsa.PublicKey{"key1": &key.PublicKey},
		fetched: time.Now(),
	}

	_, err = validateCFAccessJWT(token, cache, teamDomain)
	if err == nil {
		t.Error("expected error for missing email claim, got nil")
	}
}

// TestVerifyRS256_Valid verifies that a correct RS256 signature passes verification.
func TestVerifyRS256_Valid(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generating key: %v", err)
	}

	input := "header.payload"
	h := sha256.Sum256([]byte(input))
	sig, err := rsa.SignPKCS1v15(rand.Reader, key, crypto.SHA256, h[:])
	if err != nil {
		t.Fatalf("signing: %v", err)
	}
	sigB64 := base64.RawURLEncoding.EncodeToString(sig)

	if err := verifyRS256(input, sigB64, &key.PublicKey); err != nil {
		t.Errorf("unexpected error verifying valid signature: %v", err)
	}
}

// TestVerifyRS256_Invalid verifies that a tampered signature fails verification.
func TestVerifyRS256_Invalid(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generating key: %v", err)
	}

	// Sign different content — signature won't match the input.
	h := sha256.Sum256([]byte("different.content"))
	sig, _ := rsa.SignPKCS1v15(rand.Reader, key, crypto.SHA256, h[:])
	sigB64 := base64.RawURLEncoding.EncodeToString(sig)

	if err := verifyRS256("header.payload", sigB64, &key.PublicKey); err == nil {
		t.Error("expected error for invalid signature, got nil")
	}
}
