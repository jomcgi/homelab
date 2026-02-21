package main

import (
	"crypto"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math/big"
	"net/http"
	"os"
	"sync"
	"time"
)

// CFAccessAuth validates Cloudflare Access JWTs.
// It fetches the team's public JWKS and caches them.
type CFAccessAuth struct {
	teamDomain string // e.g. "your-team.cloudflareaccess.com"

	mu      sync.RWMutex
	keys    map[string]*rsa.PublicKey
	fetched time.Time
}

// JWKS response structures.
type jwks struct {
	Keys []jwk `json:"keys"`
}

type jwk struct {
	Kid string `json:"kid"`
	Kty string `json:"kty"`
	N   string `json:"n"`
	E   string `json:"e"`
}

// jwtHeader is the decoded JWT header.
type jwtHeader struct {
	Kid string `json:"kid"`
	Alg string `json:"alg"`
}

// jwtClaims holds the subset of JWT claims we need.
type jwtClaims struct {
	Sub   string `json:"sub"`
	Email string `json:"email"`
	Aud   []any  `json:"aud"`
	Exp   int64  `json:"exp"`
	Iat   int64  `json:"iat"`
}

const (
	keyRefreshInterval = 1 * time.Hour
	cfAccessJWTHeader  = "Cf-Access-Jwt-Assertion"
)

// NewCFAccessAuth creates a validator for the given Cloudflare Access team domain.
func NewCFAccessAuth(teamDomain string) *CFAccessAuth {
	return &CFAccessAuth{
		teamDomain: teamDomain,
		keys:       make(map[string]*rsa.PublicKey),
	}
}

// Validate checks the Cf-Access-Jwt-Assertion header and returns the user email.
func (a *CFAccessAuth) Validate(r *http.Request) (email string, err error) {
	token := r.Header.Get(cfAccessJWTHeader)
	if token == "" {
		return "", errors.New("missing Cf-Access-Jwt-Assertion header")
	}
	return a.validateToken(token)
}

// validateToken decodes and verifies a Cloudflare Access JWT.
func (a *CFAccessAuth) validateToken(token string) (string, error) {
	parts := splitJWT(token)
	if parts == nil {
		return "", errors.New("malformed JWT")
	}

	// Decode header to find the key ID.
	headerJSON, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return "", fmt.Errorf("decode JWT header: %w", err)
	}
	var header jwtHeader
	if err := json.Unmarshal(headerJSON, &header); err != nil {
		return "", fmt.Errorf("parse JWT header: %w", err)
	}
	if header.Alg != "RS256" {
		return "", fmt.Errorf("unsupported JWT algorithm: %s", header.Alg)
	}

	// Look up the public key.
	key, err := a.getKey(header.Kid)
	if err != nil {
		return "", err
	}

	// Verify RS256 signature.
	signingInput := parts[0] + "." + parts[1]
	signature, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil {
		return "", fmt.Errorf("decode JWT signature: %w", err)
	}
	hash := sha256.Sum256([]byte(signingInput))
	if err := rsa.VerifyPKCS1v15(key, crypto.SHA256, hash[:], signature); err != nil {
		return "", fmt.Errorf("JWT signature verification failed: %w", err)
	}

	// Decode claims.
	claimsJSON, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return "", fmt.Errorf("decode JWT claims: %w", err)
	}
	var claims jwtClaims
	if err := json.Unmarshal(claimsJSON, &claims); err != nil {
		return "", fmt.Errorf("parse JWT claims: %w", err)
	}

	// Check expiry.
	if time.Now().Unix() > claims.Exp {
		return "", errors.New("JWT expired")
	}

	if claims.Email == "" {
		return "", errors.New("JWT missing email claim")
	}

	// Validate audience if CF_ACCESS_AUD is configured.
	expectedAud := os.Getenv("CF_ACCESS_AUD")
	if expectedAud != "" {
		found := false
		for _, a := range claims.Aud {
			if s, ok := a.(string); ok && s == expectedAud {
				found = true
				break
			}
		}
		if !found {
			return "", errors.New("JWT audience mismatch")
		}
	}

	return claims.Email, nil
}

// getKey returns the RSA public key for the given kid, fetching JWKS if needed.
func (a *CFAccessAuth) getKey(kid string) (*rsa.PublicKey, error) {
	a.mu.RLock()
	key, ok := a.keys[kid]
	stale := time.Since(a.fetched) > keyRefreshInterval
	a.mu.RUnlock()

	if ok && !stale {
		return key, nil
	}

	// Fetch fresh keys.
	if err := a.fetchKeys(); err != nil {
		return nil, fmt.Errorf("fetch JWKS: %w", err)
	}

	a.mu.RLock()
	key, ok = a.keys[kid]
	a.mu.RUnlock()

	if !ok {
		return nil, fmt.Errorf("unknown key ID: %s", kid)
	}
	return key, nil
}

// fetchKeys retrieves the Cloudflare Access JWKS endpoint and caches the keys.
func (a *CFAccessAuth) fetchKeys() error {
	url := fmt.Sprintf("https://%s/cdn-cgi/access/certs", a.teamDomain)
	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Get(url) //nolint:noctx // one-off key fetch
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("JWKS endpoint returned %d", resp.StatusCode)
	}

	var ks jwks
	if err := json.NewDecoder(io.LimitReader(resp.Body, 1<<20)).Decode(&ks); err != nil {
		return err
	}

	newKeys := make(map[string]*rsa.PublicKey, len(ks.Keys))
	for _, k := range ks.Keys {
		if k.Kty != "RSA" {
			continue
		}
		pub, err := parseRSAPublicKey(k)
		if err != nil {
			continue
		}
		newKeys[k.Kid] = pub
	}

	a.mu.Lock()
	a.keys = newKeys
	a.fetched = time.Now()
	a.mu.Unlock()

	return nil
}

// parseRSAPublicKey converts a JWK to an *rsa.PublicKey.
func parseRSAPublicKey(k jwk) (*rsa.PublicKey, error) {
	nBytes, err := base64.RawURLEncoding.DecodeString(k.N)
	if err != nil {
		return nil, err
	}
	eBytes, err := base64.RawURLEncoding.DecodeString(k.E)
	if err != nil {
		return nil, err
	}
	n := new(big.Int).SetBytes(nBytes)
	e := new(big.Int).SetBytes(eBytes)
	return &rsa.PublicKey{N: n, E: int(e.Int64())}, nil
}

// splitJWT splits a JWT into its three base64url parts.
func splitJWT(token string) []string {
	var parts []string
	start := 0
	count := 0
	for i := range len(token) {
		if token[i] == '.' {
			parts = append(parts, token[start:i])
			start = i + 1
			count++
		}
	}
	if count != 2 {
		return nil
	}
	parts = append(parts, token[start:])
	return parts
}
