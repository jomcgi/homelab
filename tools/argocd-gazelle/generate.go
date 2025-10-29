package argocd

import (
	"os"
	"path/filepath"
	"strings"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/language"
	"github.com/bazelbuild/bazel-gazelle/rule"
	"sigs.k8s.io/yaml"
)

// ArgoCDApplication represents the structure of an ArgoCD Application manifest.
type ArgoCDApplication struct {
	APIVersion string `yaml:"apiVersion"`
	Kind       string `yaml:"kind"`
	Metadata   struct {
		Name      string `yaml:"name"`
		Namespace string `yaml:"namespace"`
	} `yaml:"metadata"`
	Spec struct {
		Destination struct {
			Server    string `yaml:"server"`
			Namespace string `yaml:"namespace"`
		} `yaml:"destination"`
	} `yaml:"spec"`
}

// generateRules generates BUILD rules for ArgoCD applications.
func generateRules(args language.GenerateArgs) language.GenerateResult {
	cfg := getArgoCDConfig(args.Config)

	var result language.GenerateResult

	// Only generate rules if enabled
	if !cfg.enabled {
		return result
	}

	// Look for application.yaml files
	applicationFile := filepath.Join(args.Dir, "application.yaml")
	if _, err := os.Stat(applicationFile); os.IsNotExist(err) {
		return result
	}

	// Parse the application.yaml
	app, err := parseApplication(applicationFile)
	if err != nil {
		// If we can't parse it, skip generation
		return result
	}

	// Only process ArgoCD Applications
	if app.Kind != "Application" || !strings.HasPrefix(app.APIVersion, "argoproj.io/") {
		return result
	}

	// Generate default argocd_diff rule
	diffRule := generateDiffRule(app, "", cfg)
	if diffRule != nil {
		result.Gen = append(result.Gen, diffRule)
		result.Imports = append(result.Imports, nil)
	}

	// Generate cluster-specific diff rules if clusters are configured
	for _, cluster := range cfg.clusters {
		clusterDiffRule := generateDiffRule(app, cluster, cfg)
		if clusterDiffRule != nil {
			result.Gen = append(result.Gen, clusterDiffRule)
			result.Imports = append(result.Imports, nil)
		}
	}

	return result
}

// parseApplication reads and parses an ArgoCD Application YAML file.
func parseApplication(path string) (*ArgoCDApplication, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	var app ArgoCDApplication
	if err := yaml.Unmarshal(data, &app); err != nil {
		return nil, err
	}

	return &app, nil
}

// generateDiffRule creates an argocd_diff rule.
func generateDiffRule(app *ArgoCDApplication, cluster string, cfg *argoCDConfig) *rule.Rule {
	ruleName := "diff"
	if cluster != "" {
		ruleName = "diff_" + cluster
	}

	r := rule.NewRule("argocd_diff", ruleName)

	// Set the application file
	r.SetAttr("application", "application.yaml")

	// Set base branch (default: origin/main)
	baseBranch := cfg.baseBranch
	if baseBranch == "" {
		baseBranch = "origin/main"
	}
	r.SetAttr("base_branch", baseBranch)

	// Set cluster if specified
	if cluster != "" {
		r.SetAttr("cluster", cluster)

		// Set cluster-specific snapshot image if configured
		if snapshotImage, ok := cfg.clusterSnapshotImages[cluster]; ok {
			r.SetAttr("snapshot_image", snapshotImage)
		}
	}

	return r
}
