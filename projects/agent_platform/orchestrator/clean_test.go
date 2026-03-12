package main

import "testing"

func TestCleanOutput_StripsBanner(t *testing.T) {
	raw := "  \\___)\t20260312_1 · /workspace/homelab\n   L L\tgoose is ready\nActual output here\n"
	got := cleanOutput(raw)
	want := "Actual output here\n"
	if got != want {
		t.Errorf("cleanOutput() = %q, want %q", got, want)
	}
}

func TestCleanOutput_StripsANSI(t *testing.T) {
	raw := "\x1b[32mSuccess\x1b[0m: done\n"
	got := cleanOutput(raw)
	want := "Success: done\n"
	if got != want {
		t.Errorf("cleanOutput() = %q, want %q", got, want)
	}
}

func TestCleanOutput_NormalizesCarriageReturns(t *testing.T) {
	raw := "line1\r\nline2\rline3\n"
	got := cleanOutput(raw)
	want := "line1\nline2\nline3\n"
	if got != want {
		t.Errorf("cleanOutput() = %q, want %q", got, want)
	}
}

func TestCleanOutput_NoBanner(t *testing.T) {
	raw := "Just regular output\nwith multiple lines\n"
	got := cleanOutput(raw)
	if got != raw {
		t.Errorf("cleanOutput() = %q, want %q", got, raw)
	}
}

func TestCleanOutput_BannerAndANSI(t *testing.T) {
	raw := "\x1b[1m  \\___)\x1b[0m\t20260312_1\n   L L\tgoose is ready\n\x1b[36mLet me look at the code\x1b[0m\n"
	got := cleanOutput(raw)
	want := "Let me look at the code\n"
	if got != want {
		t.Errorf("cleanOutput() = %q, want %q", got, want)
	}
}

func TestCleanOutput_Empty(t *testing.T) {
	got := cleanOutput("")
	if got != "" {
		t.Errorf("cleanOutput(\"\") = %q, want \"\"", got)
	}
}

func TestCleanOutput_TrimsLeadingNewlinesAfterBanner(t *testing.T) {
	raw := "   L L\tgoose is ready\n\n\nActual output\n"
	got := cleanOutput(raw)
	want := "Actual output\n"
	if got != want {
		t.Errorf("cleanOutput() = %q, want %q", got, want)
	}
}
