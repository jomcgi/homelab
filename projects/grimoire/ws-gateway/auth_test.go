package main

import (
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"math/big"
	"net/http"
	"testing"
	"time"
)

// TestSplitJWT_Valid verifies a standard 3-part JWT is split into header, payload, signature.
func TestSplitJWT_Valid(t *testing.T) {
	parts := splitJWT("header.payload.signature")
	if parts == nil {
		t.Fatal("expected non-nil parts for valid JWT")
	}
	if len(parts) != 3 {
		t.Fatalf("expected 3 parts, got %d", len(parts))
	}
	if parts[0] != "header" || parts[1] != "payload" || parts[2] != "signature" {
		t.Errorf("unexpected parts: %v", parts)
	}
}

// TestSplitJWT_TwoParts verifies that a token with only one dot returns nil.
func TestSplitJWT_TwoParts(t *testing.T) {
	if splitJWT("header.payload") != nil {
		t.Error("expected nil for only 2 parts (1 dot)")
	}
}

// TestSplitJWT_NoParts verifies that a token with no dots returns nil.
func TestSplitJWT_NoParts(t *testing.T) {
	if splitJWT("nodots") != nil {
		t.Error("expected nil for no dots")
	}
}

// TestSplitJWT_FourParts verifies that a token with 3 dots (4 segments) returns nil.
func TestSplitJWT_FourParts(t *testing.T) {
	if splitJWT("a.b.c.d") != nil {
		t.Error("expected nil for 4 parts (3 dots)")
	}
}

// TestSplitJWT_EmptyParts verifies that an empty string returns nil.
func TestSplitJWT_EmptyString(t *testing.T) {
	if splitJWT("") != nil {
		t.Error("expected nil for empty string")
	}
}

// TestParseRSAPublicKey_Valid verifies converting a valid JWK to an *rsa.PublicKey.
func TestParseRSAPublicKey_GatewayValid(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generating RSA key: %v", err)
	}

	eVal := big.NewInt(int64(key.PublicKey.E))
	k := jwk{
		Kid: "test-key",
		Kty: "RSA",
		N:   base64.RawURLEncoding.EncodeToString(key.PublicKey.N.Bytes()),
		E:   base64.RawURLEncoding.EncodeToString(eVal.Bytes()),
	}

	pub, err := parseRSAPublicKey(k)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if pub.N.Cmp(key.PublicKey.N) != 0 {
		t.Error("N does not match original key")
	}
	if pub.E != key.PublicKey.E {
		t.Errorf("E got %d, want %d", pub.E, key.PublicKey.E)
	}
}

// TestParseRSAPublicKey_InvalidN verifies an error for an invalid base64 N component.
func TestParseRSAPublicKey_GatewayInvalidN(t *testing.T) {
	k := jwk{N: "!!!invalid!!!", E: "AQAB"}
	if _, err := parseRSAPublicKey(k); err == nil {
		t.Error("expected error for invalid N, got nil")
	}
}

// TestParseRSAPublicKey_InvalidE verifies an error for an invalid base64 E component.
func TestParseRSAPublicKey_GatewayInvalidE(t *testing.T) {
	k := jwk{N: "AQAB", E: "!!!invalid!!!"}
	if _, err := parseRSAPublicKey(k); err == nil {
		t.Error("expected error for invalid E, got nil")
	}
}

// makeGatewayJWT creates a signed JWT for use in ws-gateway auth tests.
func makeGatewayJWT(t *testing.T, key *rsa.PrivateKey, kid, alg, email, issuer string, expDelta time.Duration, audList []any) string {
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
	if audList != nil {
		claims["aud"] = audList
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

// TestValidateToken_MalformedJWT verifies an error for a token that isn't 3 dot-separated parts.
func TestValidateToken_MalformedJWT(t *testing.T) {
	a := NewCFAccessAuth("team.example.com")
	_, err := a.validateToken("not.a.valid.jwt.with.too.many.dots")
	if err == nil {
		t.Error("expected error for malformed JWT, got nil")
	}
}

// TestValidateToken_WrongAlgorithm verifies an error for a non-RS256 algorithm header.
func TestValidateToken_WrongAlgorithm(t *testing.T) {
	header := map[string]string{"alg": "HS256", "kid": "k1"}
	headerJSON, _ := json.Marshal(header)
	headerB64 := base64.RawURLEncoding.EncodeToString(headerJSON)
	token := headerB64 + ".payload.signature"

	a := NewCFAccessAuth("team.example.com")
	_, err := a.validateToken(token)
	if err == nil {
		t.Error("expected error for HS256 algorithm, got nil")
	}
}

// TestValidateToken_ValidToken verifies a correctly signed RS256 token with valid claims is accepted.
func TestValidateToken_ValidToken(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generating key: %v", err)
	}

	a := NewCFAccessAuth("team.cloudflareaccess.com")
	// Inject the key directly to bypass the HTTP JWKS fetch.
	a.mu.Lock()
	a.keys["key1"] = &key.PublicKey
	a.fetched = time.Now()
	a.mu.Unlock()

	token := makeGatewayJWT(t, key, "key1", "RS256", "user@example.com", "https://team.cloudflareaccess.com", time.Hour, nil)

	email, err := a.validateToken(token)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if email != "user@example.com" {
		t.Errorf("email got %q, want %q", email, "user@example.com")
	}
}

// TestValidateToken_Expired verifies that a token with exp in the past is rejected.
func TestValidateToken_Expired(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generating key: %v", err)
	}

	a := NewCFAccessAuth("team.cloudflareaccess.com")
	a.mu.Lock()
	a.keys["key1"] = &key.PublicKey
	a.fetched = time.Now()
	a.mu.Unlock()

	token := makeGatewayJWT(t, key, "key1", "RS256", "user@example.com", "https://team.cloudflareaccess.com", -time.Hour, nil)

	_, err = a.validateToken(token)
	if err == nil {
		t.Error("expected error for expired token, got nil")
	}
}

// TestValidateToken_MissingEmail verifies that a token without an email claim is rejected.
func TestValidateToken_MissingEmail(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generating key: %v", err)
	}

	a := NewCFAccessAuth("team.cloudflareaccess.com")
	a.mu.Lock()
	a.keys["key1"] = &key.PublicKey
	a.fetched = time.Now()
	a.mu.Unlock()

	// Build a token without the email claim.
	header := map[string]string{"alg": "RS256", "kid": "key1"}
	headerJSON, _ := json.Marshal(header)
	headerB64 := base64.RawURLEncoding.EncodeToString(headerJSON)
	claims := map[string]any{
		"iss": "https://team.cloudflareaccess.com",
		"exp": time.Now().Add(time.Hour).Unix(),
	}
	claimsJSON, _ := json.Marshal(claims)
	claimsB64 := base64.RawURLEncoding.EncodeToString(claimsJSON)
	signingInput := headerB64 + "." + claimsB64
	h := sha256.Sum256([]byte(signingInput))
	sig, _ := rsa.SignPKCS1v15(rand.Reader, key, crypto.SHA256, h[:])
	token := signingInput + "." + base64.RawURLEncoding.EncodeToString(sig)

	_, err = a.validateToken(token)
	if err == nil {
		t.Error("expected error for missing email claim, got nil")
	}
}

// TestValidateToken_AudienceMismatch verifies rejection when CF_ACCESS_AUD is set but doesn't match.
func TestValidateToken_AudienceMismatch(t *testing.T) {
	t.Setenv("CF_ACCESS_AUD", "expected-audience")

	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generating key: %v", err)
	}

	a := NewCFAccessAuth("team.cloudflareaccess.com")
	a.mu.Lock()
	a.keys["key1"] = &key.PublicKey
	a.fetched = time.Now()
	a.mu.Unlock()

	token := makeGatewayJWT(t, key, "key1", "RS256", "user@example.com", "https://team.cloudflareaccess.com", time.Hour, []any{"wrong-audience"})

	_, err = a.validateToken(token)
	if err == nil {
		t.Error("expected error for audience mismatch, got nil")
	}
}

// TestValidateToken_AudienceMatch verifies acceptance when the token audience matches CF_ACCESS_AUD.
func TestValidateToken_AudienceMatch(t *testing.T) {
	t.Setenv("CF_ACCESS_AUD", "my-app-audience")

	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generating key: %v", err)
	}

	a := NewCFAccessAuth("team.cloudflareaccess.com")
	a.mu.Lock()
	a.keys["key1"] = &key.PublicKey
	a.fetched = time.Now()
	a.mu.Unlock()

	token := makeGatewayJWT(t, key, "key1", "RS256", "user@example.com", "https://team.cloudflareaccess.com", time.Hour, []any{"my-app-audience"})

	email, err := a.validateToken(token)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if email != "user@example.com" {
		t.Errorf("email got %q, want %q", email, "user@example.com")
	}
}

// TestValidate_MissingHeader verifies Validate returns an error when the JWT header is absent.
func TestValidate_MissingHeader(t *testing.T) {
	a := NewCFAccessAuth("team.example.com")
	req, _ := http.NewRequest("GET", "/ws", nil)

	_, err := a.Validate(req)
	if err == nil {
		t.Error("expected error when Cf-Access-Jwt-Assertion header is missing, got nil")
	}
}

// TestValidate_HeaderPresent verifies Validate reads the JWT from the correct header name.
func TestValidate_HeaderPresent(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generating key: %v", err)
	}

	a := NewCFAccessAuth("team.cloudflareaccess.com")
	a.mu.Lock()
	a.keys["key1"] = &key.PublicKey
	a.fetched = time.Now()
	a.mu.Unlock()

	token := makeGatewayJWT(t, key, "key1", "RS256", "user@example.com", "https://team.cloudflareaccess.com", time.Hour, nil)

	req, _ := http.NewRequest("GET", "/ws", nil)
	req.Header.Set("Cf-Access-Jwt-Assertion", token)

	email, err := a.Validate(req)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if email != "user@example.com" {
		t.Errorf("email got %q, want %q", email, "user@example.com")
	}
}
