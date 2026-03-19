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

func TestCleanOutput_MultipleBanners(t *testing.T) {
	raw := "   L L\tgoose is ready\nStep 0 output\n\n--- pipeline step 0: research ---\n  __( O)>  blah\n \\____)\t20260318_1\n   L L\tgoose is ready\nStep 1 output\n"
	got := cleanOutput(raw)
	want := "Step 0 output\n\n--- pipeline step 0: research ---\nStep 1 output\n"
	if got != want {
		t.Errorf("cleanOutput() = %q, want %q", got, want)
	}
}

func TestCleanOutput_StripsGooseResult(t *testing.T) {
	raw := "Some analysis here\n\n```goose-result\ntype: pr\nurl: https://github.com/jomcgi/homelab/pull/42\nsummary: Fixed the thing\n```\n"
	got := cleanOutput(raw)
	want := "Some analysis here\n"
	if got != want {
		t.Errorf("cleanOutput() = %q, want %q", got, want)
	}
}

func TestCleanOutput_StripsRecipeLoading(t *testing.T) {
	raw := "Loading recipe: Deep Plan\nDescription: Analyse a goal and propose an optimal agent pipeline\nParameters used to load this recipe:\n   task_description: do something\n\n\n    __( O)>  new session\n   \\____)\t20260319_1 · /workspace/homelab\n     L L     goose is ready\n\nLet me discover the available agents.\n"
	got := cleanOutput(raw)
	want := "Let me discover the available agents.\n"
	if got != want {
		t.Errorf("cleanOutput() = %q, want %q", got, want)
	}
}

func TestCleanOutput_StripsMultipleRecipes(t *testing.T) {
	raw := "Loading recipe: Deep Plan\nDescription: plan things\nParameters:\n  x: y\n\n    __( O)>\n   \\____)\n     L L     goose is ready\nStep 0\n\n--- pipeline step 0: agent ---\nLoading recipe: Research\nDescription: do research\nParams:\n  q: z\n\n    __( O)>\n   \\____)\n     L L     goose is ready\nStep 1\n"
	got := cleanOutput(raw)
	want := "Step 0\n\n--- pipeline step 0: agent ---\nStep 1\n"
	if got != want {
		t.Errorf("cleanOutput() = %q, want %q", got, want)
	}
}

func TestCleanOutput_StripsMultipleGooseResults(t *testing.T) {
	raw := "Step 0\n```goose-result\ntype: gist\nurl: https://gist.github.com/abc\nsummary: Research\n```\n\n--- pipeline step 0: research ---\nStep 1\n```goose-result\ntype: pr\nurl: https://github.com/jomcgi/homelab/pull/1\nsummary: Fix\n```\n"
	got := cleanOutput(raw)
	want := "Step 0\n\n--- pipeline step 0: research ---\nStep 1\n"
	if got != want {
		t.Errorf("cleanOutput() = %q, want %q", got, want)
	}
}
