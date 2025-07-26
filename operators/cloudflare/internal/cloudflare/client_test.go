/*
Copyright 2025.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package cloudflare

import (
	"errors"
	"net/http"
	"testing"

	"github.com/cloudflare/cloudflare-go"
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
)

func TestClient(t *testing.T) {
	RegisterFailHandler(Fail)
	RunSpecs(t, "Cloudflare Client Suite")
}

var _ = Describe("TunnelClient", func() {
	Describe("NewTunnelClient", func() {
		It("should create a new client with valid API token", func() {
			client, err := NewTunnelClient("test-token")
			Expect(err).NotTo(HaveOccurred())
			Expect(client).NotTo(BeNil())
			Expect(client.api).NotTo(BeNil())
			Expect(client.limiter).NotTo(BeNil())
		})

		It("should return error with invalid API token", func() {
			client, err := NewTunnelClient("")
			Expect(err).To(HaveOccurred())
			Expect(client).To(BeNil())
		})
	})

	Describe("IsRetryableError", func() {
		It("should return true for retryable HTTP status codes", func() {
			retryableErrors := []int{
				http.StatusTooManyRequests,
				http.StatusInternalServerError,
				http.StatusBadGateway,
				http.StatusServiceUnavailable,
				http.StatusGatewayTimeout,
			}

			for _, statusCode := range retryableErrors {
				err := &cloudflare.Error{StatusCode: statusCode}
				Expect(IsRetryableError(err)).To(BeTrue(), "Status code %d should be retryable", statusCode)
			}
		})

		It("should return false for non-retryable HTTP status codes", func() {
			nonRetryableErrors := []int{
				http.StatusBadRequest,
				http.StatusUnauthorized,
				http.StatusForbidden,
				http.StatusNotFound,
				http.StatusConflict,
			}

			for _, statusCode := range nonRetryableErrors {
				err := &cloudflare.Error{StatusCode: statusCode}
				Expect(IsRetryableError(err)).To(BeFalse(), "Status code %d should not be retryable", statusCode)
			}
		})

		It("should return false for nil error", func() {
			Expect(IsRetryableError(nil)).To(BeFalse())
		})

		It("should return false for non-Cloudflare errors", func() {
			err := errors.New("test error")
			Expect(IsRetryableError(err)).To(BeFalse())
		})
	})

	Describe("IsNotFoundError", func() {
		It("should return true for 404 status code", func() {
			err := &cloudflare.Error{StatusCode: http.StatusNotFound}
			Expect(IsNotFoundError(err)).To(BeTrue())
		})

		It("should return false for other status codes", func() {
			otherErrors := []int{
				http.StatusBadRequest,
				http.StatusUnauthorized,
				http.StatusForbidden,
				http.StatusInternalServerError,
			}

			for _, statusCode := range otherErrors {
				err := &cloudflare.Error{StatusCode: statusCode}
				Expect(IsNotFoundError(err)).To(BeFalse(), "Status code %d should not be NotFound", statusCode)
			}
		})

		It("should return false for nil error", func() {
			Expect(IsNotFoundError(nil)).To(BeFalse())
		})

		It("should return false for non-Cloudflare errors", func() {
			err := errors.New("test error")
			Expect(IsNotFoundError(err)).To(BeFalse())
		})
	})
})
