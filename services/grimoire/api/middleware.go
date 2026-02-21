package main

import (
	"context"
	"crypto"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"math/big"
	"net/http"
	"strings"
	"sync"
	"time"
)

type contextKey string

const userEmailKey contextKey = "user_email"

// cfAccessMiddleware validates the Cloudflare Access JWT on incoming requests.
// It extracts the user's email from the JWT and stores it in the request context.
func cfAccessMiddleware(teamDomain string, next http.Handler) http.Handler {
	certsURL := fmt.Sprintf("https://%s/cdn-cgi/access/certs", teamDomain)
	cache := &jwksCache{url: certsURL}

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		token := r.Header.Get("Cf-Access-Jwt-Assertion")
		if token == "" {
			httpError(w, http.StatusUnauthorized, "missing Cf-Access-Jwt-Assertion header")
			return
		}

		email, err := validateCFAccessJWT(token, cache, teamDomain)
		if err != nil {
			httpError(w, http.StatusUnauthorized, "invalid token: "+err.Error())
			return
		}

		ctx := context.WithValue(r.Context(), userEmailKey, email)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func userEmail(r *http.Request) string {
	v, _ := r.Context().Value(userEmailKey).(string)
	return v
}

// --- Minimal JWT validation for CF Access ---
// CF Access JWTs are RS256-signed. We fetch the public keys from the team's
// JWKS endpoint and validate the signature, expiry, and audience.

type jwksCache struct {
	url     string
	mu      sync.Mutex
	keys    map[string]*rsa.PublicKey
	fetched time.Time
}

func (c *jwksCache) getKey(kid string) (*rsa.PublicKey, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if time.Since(c.fetched) > 5*time.Minute || c.keys == nil {
		keys, err := fetchJWKS(c.url)
		if err != nil {
			return nil, err
		}
		c.keys = keys
		c.fetched = time.Now()
	}

	key, ok := c.keys[kid]
	if !ok {
		return nil, fmt.Errorf("unknown key id: %s", kid)
	}
	return key, nil
}

type jwksResponse struct {
	Keys []jwkKey `json:"keys"`
}

type jwkKey struct {
	Kid string `json:"kid"`
	Kty string `json:"kty"`
	N   string `json:"n"`
	E   string `json:"e"`
}

func fetchJWKS(url string) (map[string]*rsa.PublicKey, error) {
	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Get(url)
	if err != nil {
		return nil, fmt.Errorf("fetching JWKS: %w", err)
	}
	defer resp.Body.Close()

	var jwks jwksResponse
	if err := json.NewDecoder(io.LimitReader(resp.Body, 1<<20)).Decode(&jwks); err != nil {
		return nil, fmt.Errorf("decoding JWKS: %w", err)
	}

	keys := make(map[string]*rsa.PublicKey, len(jwks.Keys))
	for _, k := range jwks.Keys {
		if k.Kty != "RSA" {
			continue
		}
		pub, err := parseRSAPublicKey(k.N, k.E)
		if err != nil {
			continue
		}
		keys[k.Kid] = pub
	}
	return keys, nil
}

func parseRSAPublicKey(nStr, eStr string) (*rsa.PublicKey, error) {
	nBytes, err := base64.RawURLEncoding.DecodeString(nStr)
	if err != nil {
		return nil, err
	}
	eBytes, err := base64.RawURLEncoding.DecodeString(eStr)
	if err != nil {
		return nil, err
	}

	n := new(big.Int).SetBytes(nBytes)
	e := new(big.Int).SetBytes(eBytes)

	return &rsa.PublicKey{
		N: n,
		E: int(e.Int64()),
	}, nil
}

func validateCFAccessJWT(tokenStr string, cache *jwksCache, teamDomain string) (string, error) {
	parts := strings.SplitN(tokenStr, ".", 3)
	if len(parts) != 3 {
		return "", fmt.Errorf("malformed JWT")
	}

	headerJSON, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return "", fmt.Errorf("decoding header: %w", err)
	}
	var header struct {
		Kid string `json:"kid"`
		Alg string `json:"alg"`
	}
	if err := json.Unmarshal(headerJSON, &header); err != nil {
		return "", fmt.Errorf("parsing header: %w", err)
	}
	if header.Alg != "RS256" {
		return "", fmt.Errorf("unsupported algorithm: %s", header.Alg)
	}

	// Verify signature BEFORE trusting claims.
	key, err := cache.getKey(header.Kid)
	if err != nil {
		return "", err
	}

	if err := verifyRS256(parts[0]+"."+parts[1], parts[2], key); err != nil {
		return "", fmt.Errorf("signature verification failed: %w", err)
	}

	// Now that signature is verified, parse and validate claims.
	payloadJSON, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return "", fmt.Errorf("decoding payload: %w", err)
	}
	var claims struct {
		Email string `json:"email"`
		Iss   string `json:"iss"`
		Exp   int64  `json:"exp"`
		Iat   int64  `json:"iat"`
	}
	if err := json.Unmarshal(payloadJSON, &claims); err != nil {
		return "", fmt.Errorf("parsing claims: %w", err)
	}

	if time.Now().Unix() > claims.Exp {
		return "", fmt.Errorf("token expired")
	}

	expectedIss := fmt.Sprintf("https://%s", teamDomain)
	if claims.Iss != expectedIss {
		return "", fmt.Errorf("issuer mismatch: got %s, want %s", claims.Iss, expectedIss)
	}

	if claims.Email == "" {
		return "", fmt.Errorf("missing email claim")
	}

	return claims.Email, nil
}

func verifyRS256(signingInput, signatureB64 string, key *rsa.PublicKey) error {
	signature, err := base64.RawURLEncoding.DecodeString(signatureB64)
	if err != nil {
		return err
	}

	h := sha256.Sum256([]byte(signingInput))
	return rsa.VerifyPKCS1v15(key, crypto.SHA256, h[:], signature)
}
