package gazelle

import (
	"testing"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/language"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

// --- localDepName ---

func TestLocalDepName_LocalRef(t *testing.T) {
	got := localDepName(":foo")
	if got != "foo" {
		t.Errorf("localDepName(':foo') = %q, want 'foo'", got)
	}
}

func TestLocalDepName_ExternalRef(t *testing.T) {
	got := localDepName("//external:lib")
	if got != "" {
		t.Errorf("localDepName('//external:lib') = %q, want empty", got)
	}
}

func TestLocalDepName_CrossPackageRef(t *testing.T) {
	got := localDepName("//some/package:target")
	if got != "" {
		t.Errorf("localDepName('//some/package:target') = %q, want empty", got)
	}
}

func TestLocalDepName_EmptyString(t *testing.T) {
	got := localDepName("")
	if got != "" {
		t.Errorf("localDepName('') = %q, want empty", got)
	}
}

func TestLocalDepName_BareTarget(t *testing.T) {
	// A dep like "somefile.py" (no leading colon) is not a local ref.
	got := localDepName("somefile.py")
	if got != "" {
		t.Errorf("localDepName('somefile.py') = %q, want empty", got)
	}
}

// --- fileExtension ---

func TestFileExtension_Python(t *testing.T) {
	got := fileExtension("main.py")
	if got != ".py" {
		t.Errorf("fileExtension('main.py') = %q, want '.py'", got)
	}
}

func TestFileExtension_Go(t *testing.T) {
	got := fileExtension("server.go")
	if got != ".go" {
		t.Errorf("fileExtension('server.go') = %q, want '.go'", got)
	}
}

func TestFileExtension_NoExtension(t *testing.T) {
	got := fileExtension("Makefile")
	if got != "" {
		t.Errorf("fileExtension('Makefile') = %q, want empty", got)
	}
}

func TestFileExtension_MultiDot(t *testing.T) {
	// filepath.Ext returns only the last extension.
	got := fileExtension("archive.tar.gz")
	if got != ".gz" {
		t.Errorf("fileExtension('archive.tar.gz') = %q, want '.gz'", got)
	}
}

func TestFileExtension_DotFile(t *testing.T) {
	// filepath.Ext(".gitignore") returns ".gitignore" because the leading dot
	// is treated as the start of an extension (Go considers the final dot the
	// separator, which here is the first character).
	got := fileExtension(".gitignore")
	if got != ".gitignore" {
		t.Errorf("fileExtension('.gitignore') = %q, want '.gitignore'", got)
	}
}

// --- rulesForExtension ---

func TestRulesForExtension_Python(t *testing.T) {
	got := rulesForExtension(".py", []string{"py"})
	if len(got) != 1 || got[0] != "//bazel/semgrep/rules:python_rules" {
		t.Errorf("rulesForExtension('.py', ['py']) = %v, want [//bazel/semgrep/rules:python_rules]", got)
	}
}

func TestRulesForExtension_Go(t *testing.T) {
	got := rulesForExtension(".go", []string{"go"})
	if len(got) != 1 || got[0] != "//bazel/semgrep/rules:golang_rules" {
		t.Errorf("rulesForExtension('.go', ['go']) = %v, want [//bazel/semgrep/rules:golang_rules]", got)
	}
}

func TestRulesForExtension_UnknownExtension(t *testing.T) {
	got := rulesForExtension(".rs", []string{"py", "go"})
	if len(got) != 0 {
		t.Errorf("rulesForExtension('.rs', ...) = %v, want empty", got)
	}
}

func TestRulesForExtension_MultiLanguage_OnlyMatchingExt(t *testing.T) {
	// With both py and go configured, only the py rule should be returned for .py files.
	got := rulesForExtension(".py", []string{"py", "go"})
	if len(got) != 1 || got[0] != "//bazel/semgrep/rules:python_rules" {
		t.Errorf("rulesForExtension('.py', ['py','go']) = %v, want only python_rules", got)
	}
}

func TestRulesForExtension_EmptyLanguages(t *testing.T) {
	got := rulesForExtension(".py", []string{})
	if len(got) != 0 {
		t.Errorf("rulesForExtension('.py', []) = %v, want empty", got)
	}
}

// --- findTargets ---

func TestFindTargets_NilFile(t *testing.T) {
	got := findTargets(nil, map[string]string{"py_venv_binary": ""})
	if got != nil {
		t.Errorf("findTargets(nil, ...) = %v, want nil", got)
	}
}

func TestFindTargets_NoMatchingKinds(t *testing.T) {
	lib := rule.NewRule("py_library", "mylib")
	f := buildFileWithRules(lib)
	got := findTargets(f, map[string]string{"py_venv_binary": ""})
	if len(got) != 0 {
		t.Errorf("findTargets with no matching kinds: got %d rules, want 0", len(got))
	}
}

func TestFindTargets_MatchingKind(t *testing.T) {
	bin := rule.NewRule("py_venv_binary", "myapp")
	f := buildFileWithRules(bin)
	got := findTargets(f, map[string]string{"py_venv_binary": ""})
	if len(got) != 1 {
		t.Fatalf("findTargets: got %d rules, want 1", len(got))
	}
	if got[0].Name() != "myapp" {
		t.Errorf("findTargets: rule[0].Name() = %q, want 'myapp'", got[0].Name())
	}
}

func TestFindTargets_SortedByName(t *testing.T) {
	zbin := rule.NewRule("py_venv_binary", "z_server")
	abin := rule.NewRule("py_venv_binary", "a_server")
	mbin := rule.NewRule("py_venv_binary", "m_server")
	f := buildFileWithRules(zbin, abin, mbin)
	got := findTargets(f, map[string]string{"py_venv_binary": ""})
	if len(got) != 3 {
		t.Fatalf("findTargets: got %d rules, want 3", len(got))
	}
	wantNames := []string{"a_server", "m_server", "z_server"}
	for i, want := range wantNames {
		if got[i].Name() != want {
			t.Errorf("findTargets: got[%d].Name() = %q, want %q", i, got[i].Name(), want)
		}
	}
}

func TestFindTargets_MultipleKinds(t *testing.T) {
	pyBin := rule.NewRule("py_venv_binary", "server")
	goBin := rule.NewRule("go_binary", "worker")
	lib := rule.NewRule("py_library", "lib") // not in targetKinds
	f := buildFileWithRules(pyBin, goBin, lib)
	got := findTargets(f, map[string]string{"py_venv_binary": "", "go_binary": ""})
	if len(got) != 2 {
		t.Fatalf("findTargets: got %d rules, want 2", len(got))
	}
}

// --- resolveTarget ---

func TestResolveTarget_SelfTargeting(t *testing.T) {
	r := rule.NewRule("py_venv_binary", "myapp")
	got := resolveTarget(r, map[string]string{"py_venv_binary": ""})
	if got != ":myapp" {
		t.Errorf("resolveTarget (self-targeting) = %q, want ':myapp'", got)
	}
}

func TestResolveTarget_IndirectedKind(t *testing.T) {
	// Indirected kind: attr="binary" means follow the "binary" attr to the real target.
	r := rule.NewRule("py3_image", "myimage")
	r.SetAttr("binary", ":myapp")
	got := resolveTarget(r, map[string]string{"py3_image": "binary"})
	if got != ":myapp" {
		t.Errorf("resolveTarget (indirected) = %q, want ':myapp'", got)
	}
}

func TestResolveTarget_IndirectedKind_AttrNotSet(t *testing.T) {
	// Indirected kind where the attr is not present — returns empty string.
	r := rule.NewRule("py3_image", "myimage")
	got := resolveTarget(r, map[string]string{"py3_image": "binary"})
	if got != "" {
		t.Errorf("resolveTarget (indirected, no attr) = %q, want empty", got)
	}
}

// --- staleRules ---

func makeArgsWith(f *rule.File) language.GenerateArgs {
	return language.GenerateArgs{
		Config: &config.Config{Exts: make(map[string]interface{})},
		File:   f,
	}
}

func TestStaleRules_NilFile(t *testing.T) {
	got := staleRules(makeArgsWith(nil), nil)
	if got != nil {
		t.Errorf("staleRules(nil file) = %v, want nil", got)
	}
}

func TestStaleRules_NoExistingRules(t *testing.T) {
	f, _ := rule.LoadData("BUILD", "", nil)
	got := staleRules(makeArgsWith(f), nil)
	if len(got) != 0 {
		t.Errorf("staleRules (empty BUILD) = %v, want empty", got)
	}
}

func TestStaleRules_ActiveRuleNotStale(t *testing.T) {
	existing := rule.NewRule("semgrep_test", "main_semgrep_test")
	f := buildFileWithRules(existing)

	// Same rule appears in gen — not stale.
	gen := rule.NewRule("semgrep_test", "main_semgrep_test")
	got := staleRules(makeArgsWith(f), []*rule.Rule{gen})
	if len(got) != 0 {
		t.Errorf("staleRules: active rule should not be stale, got %v", got)
	}
}

func TestStaleRules_OrphanedRuleIsStale(t *testing.T) {
	existing := rule.NewRule("semgrep_test", "old_semgrep_test")
	f := buildFileWithRules(existing)

	// gen is empty — old rule should be stale.
	got := staleRules(makeArgsWith(f), nil)
	if len(got) != 1 {
		t.Fatalf("staleRules: want 1 stale rule, got %d", len(got))
	}
	if got[0].Name() != "old_semgrep_test" {
		t.Errorf("stale rule name = %q, want 'old_semgrep_test'", got[0].Name())
	}
}

func TestStaleRules_TargetTestIsAlsoDetected(t *testing.T) {
	existing := rule.NewRule("semgrep_target_test", "old_binary_semgrep_test")
	f := buildFileWithRules(existing)

	got := staleRules(makeArgsWith(f), nil)
	if len(got) != 1 || got[0].Kind() != "semgrep_target_test" {
		t.Errorf("staleRules: want 1 stale semgrep_target_test, got %v", got)
	}
}

func TestStaleRules_NonSemgrepRulesIgnored(t *testing.T) {
	lib := rule.NewRule("py_library", "mylib")
	f := buildFileWithRules(lib)

	got := staleRules(makeArgsWith(f), nil)
	if len(got) != 0 {
		t.Errorf("staleRules: non-semgrep rules should not appear in stale list, got %v", got)
	}
}

// --- coveredByTargets ---

func TestCoveredByTargets_NilFile(t *testing.T) {
	got := coveredByTargets(nil, nil, map[string]string{"py_venv_binary": ""})
	if got != nil {
		t.Errorf("coveredByTargets(nil, ...) = %v, want nil", got)
	}
}

func TestCoveredByTargets_NoSelfTargets(t *testing.T) {
	// Only indirected kinds (attr != "") — no self-targeting, so coverage is nil.
	img := rule.NewRule("py3_image", "myimage")
	img.SetAttr("binary", ":myapp")
	f := buildFileWithRules(img)

	got := coveredByTargets(f, []*rule.Rule{img}, map[string]string{"py3_image": "binary"})
	if got != nil {
		t.Errorf("coveredByTargets with only indirected kinds = %v, want nil", got)
	}
}

func TestCoveredByTargets_SelfTarget_MainAttrCovered(t *testing.T) {
	bin := newPyBinary("myapp", "main.py")
	f := buildFileWithRules(bin)

	got := coveredByTargets(f, []*rule.Rule{bin}, map[string]string{"py_venv_binary": ""})
	if got == nil {
		t.Fatal("coveredByTargets: expected non-nil covered set")
	}
	if !got["main.py"] {
		t.Errorf("coveredByTargets: expected 'main.py' (main attr) to be covered, got %v", got)
	}
}

func TestCoveredByTargets_TransitiveLocalDepsAreCovered(t *testing.T) {
	lib := newPyLibrary("utils", []string{"utils.py"})
	bin := newPyBinaryWithDeps("server", "server.py", []string{":utils"})
	f := buildFileWithRules(lib, bin)

	got := coveredByTargets(f, []*rule.Rule{bin}, map[string]string{"py_venv_binary": ""})
	if !got["utils.py"] {
		t.Errorf("coveredByTargets: expected 'utils.py' from transitive dep to be covered, got %v", got)
	}
}

// --- walkLocalDeps ---

func TestWalkLocalDeps_CycleDetection(t *testing.T) {
	// Two rules that mutually depend on each other (A → B → A).
	// walkLocalDeps must terminate via the visited guard.
	ruleA := rule.NewRule("py_library", "ruleA")
	ruleA.SetAttr("srcs", []string{"a.py"})
	ruleA.SetAttr("deps", []string{":ruleB"})

	ruleB := rule.NewRule("py_library", "ruleB")
	ruleB.SetAttr("srcs", []string{"b.py"})
	ruleB.SetAttr("deps", []string{":ruleA"})

	ruleByName := map[string]*rule.Rule{
		"ruleA": ruleA,
		"ruleB": ruleB,
	}
	srcsByName := map[string][]string{
		"ruleA": {"a.py"},
		"ruleB": {"b.py"},
	}

	covered := make(map[string]bool)
	visited := make(map[string]bool)

	// Must not panic or loop forever.
	walkLocalDeps(ruleA, ruleByName, srcsByName, covered, visited)

	if !covered["a.py"] {
		t.Error("walkLocalDeps cycle: expected 'a.py' to be covered")
	}
	if !covered["b.py"] {
		t.Error("walkLocalDeps cycle: expected 'b.py' to be covered")
	}
}

func TestWalkLocalDeps_AlreadyVisited_IsNoOp(t *testing.T) {
	// If a rule is already in visited, subsequent calls must be a no-op.
	r := rule.NewRule("py_library", "mylib")
	r.SetAttr("srcs", []string{"lib.py"})

	ruleByName := map[string]*rule.Rule{"mylib": r}
	srcsByName := map[string][]string{"mylib": {"lib.py"}}

	covered := make(map[string]bool)
	visited := map[string]bool{"mylib": true} // pre-mark as visited

	walkLocalDeps(r, ruleByName, srcsByName, covered, visited)

	if covered["lib.py"] {
		t.Error("walkLocalDeps: must not cover srcs when rule was already visited")
	}
}

func TestWalkLocalDeps_MainAttrCovered(t *testing.T) {
	// A binary has a "main" attr — walkLocalDeps must include it in covered.
	bin := rule.NewRule("py_venv_binary", "server")
	bin.SetAttr("main", "server.py")

	ruleByName := map[string]*rule.Rule{"server": bin}
	srcsByName := map[string][]string{}

	covered := make(map[string]bool)
	visited := make(map[string]bool)

	walkLocalDeps(bin, ruleByName, srcsByName, covered, visited)

	if !covered["server.py"] {
		t.Errorf("walkLocalDeps: expected 'server.py' (main attr) to be covered, got %v", covered)
	}
}

func TestWalkLocalDeps_ExternalDepsAreSkipped(t *testing.T) {
	// Non-local deps (no leading ":") must be silently skipped without panic.
	r := rule.NewRule("py_library", "mylib")
	r.SetAttr("srcs", []string{"lib.py"})
	r.SetAttr("deps", []string{"//external:somelib", "@pip//requests"})

	ruleByName := map[string]*rule.Rule{"mylib": r}
	srcsByName := map[string][]string{"mylib": {"lib.py"}}

	covered := make(map[string]bool)
	visited := make(map[string]bool)

	walkLocalDeps(r, ruleByName, srcsByName, covered, visited)

	if !covered["lib.py"] {
		t.Error("walkLocalDeps: own srcs should be covered even when all deps are external")
	}
}
