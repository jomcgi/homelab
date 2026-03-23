package cmd

import (
	"testing"
)

func TestParseByteSize(t *testing.T) {
	tests := []struct {
		input   string
		want    int64
		wantErr bool
	}{
		// Zero — special case, disables splitting
		{input: "0", want: 0},

		// Bare integer (no suffix) — treated as bytes
		{input: "1000", want: 1000},

		// Kibibyte (K / KB / KiB)
		{input: "1K", want: 1 << 10},
		{input: "1KB", want: 1 << 10},
		{input: "1KiB", want: 1 << 10},
		{input: "512K", want: 512 << 10},

		// Mebibyte (M / MB / MiB)
		{input: "1M", want: 1 << 20},
		{input: "1MB", want: 1 << 20},
		{input: "1MiB", want: 1 << 20},
		{input: "500M", want: 500 << 20},

		// Gibibyte (G / GB / GiB)
		{input: "1G", want: 1 << 30},
		{input: "1GB", want: 1 << 30},
		{input: "1GiB", want: 1 << 30},
		{input: "4G", want: 4 << 30},

		// Case-insensitive suffix
		{input: "2g", want: 2 << 30},
		{input: "256m", want: 256 << 20},
		{input: "8k", want: 8 << 10},

		// Whitespace is trimmed
		{input: "  512M  ", want: 512 << 20},

		// Error cases
		{input: "", wantErr: true},
		{input: "abc", wantErr: true},
		{input: "-1G", wantErr: true},
		// Fractional sizes cannot be parsed (ParseInt does not support floats)
		{input: "4.5G", wantErr: true},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			got, err := parseByteSize(tt.input)
			if tt.wantErr {
				if err == nil {
					t.Errorf("parseByteSize(%q) = %d, want error", tt.input, got)
				}
				return
			}
			if err != nil {
				t.Errorf("parseByteSize(%q) returned unexpected error: %v", tt.input, err)
				return
			}
			if got != tt.want {
				t.Errorf("parseByteSize(%q) = %d, want %d", tt.input, got, tt.want)
			}
		})
	}
}
