package helm

import (
	"fmt"
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
		Source struct {
			RepoURL        string `yaml:"repoURL"`
			Path           string `yaml:"path"`
			TargetRevision string `yaml:"targetRevision"`
			Helm           struct {
				ReleaseName string   `yaml:"releaseName"`
				ValueFiles  []string `yaml:"valueFiles"`
			} `yaml:"helm"`
		} `yaml:"source"`
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

	// Generate helm_render rule
	renderRule := generateRenderRule(app, args.Rel, cfg)
	if renderRule != nil {
		result.Gen = append(result.Gen, renderRule)
		result.Imports = append(result.Imports, nil)
	}

	// Generate helm_diff_script rule if enabled
	if cfg.generateDiff {
		diffRule := generateDiffRule(app, cfg)
		if diffRule != nil {
			result.Gen = append(result.Gen, diffRule)
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

// generateRenderRule creates a helm_render rule from an ArgoCD Application.
func generateRenderRule(app *ArgoCDApplication, rel string, cfg *argoCDConfig) *rule.Rule {
	r := rule.NewRule("helm_render", "render")

	// Set the chart path
	chartPath := app.Spec.Source.Path
	if chartPath == "" {
		return nil
	}

	// Convert to Bazel label (relative to workspace root)
	// Example: charts/n8n -> //charts/n8n:Chart.yaml
	chartLabel := fmt.Sprintf("//%s:Chart.yaml", chartPath)
	r.SetAttr("chart", chartLabel)

	// Set release name
	releaseName := app.Spec.Source.Helm.ReleaseName
	if releaseName == "" {
		releaseName = app.Metadata.Name
	}
	r.SetAttr("release_name", releaseName)

	// Set namespace
	namespace := app.Spec.Destination.Namespace
	if namespace == "" {
		namespace = "default"
	}
	r.SetAttr("namespace", namespace)

	// Set values files
	if len(app.Spec.Source.Helm.ValueFiles) > 0 {
		var valueLabels []string
		for _, vf := range app.Spec.Source.Helm.ValueFiles {
			// Handle different value file path formats
			if strings.HasPrefix(vf, "../../") {
				// Path like ../../overlays/prod/n8n/values.yaml
				// Make it relative to current directory
				relPath := strings.TrimPrefix(vf, "../../")
				// Convert overlays/prod/n8n/values.yaml to //overlays/prod/n8n:values.yaml
				parts := strings.Split(relPath, "/")
				if len(parts) > 1 {
					dir := strings.Join(parts[:len(parts)-1], "/")
					file := parts[len(parts)-1]
					valueLabels = append(valueLabels, fmt.Sprintf("//%s:%s", dir, file))
				}
			} else if !strings.Contains(vf, "/") {
				// Simple filename like values.yaml in chart directory
				// First add chart's default values
				if vf == "values.yaml" {
					valueLabels = append(valueLabels, fmt.Sprintf("//%s:values.yaml", chartPath))
				}
			}
		}

		// Also look for values.yaml in the current directory (overlay)
		localValues := filepath.Join(rel, "values.yaml")
		if _, err := os.Stat(localValues); err == nil {
			valueLabels = append(valueLabels, "values.yaml")
		}

		if len(valueLabels) > 0 {
			r.SetAttr("values", valueLabels)
		}
	}

	return r
}

// generateDiffRule creates a helm_diff_script rule.
func generateDiffRule(app *ArgoCDApplication, cfg *argoCDConfig) *rule.Rule {
	r := rule.NewRule("helm_diff_script", "diff")

	// Reference the render target
	r.SetAttr("rendered", ":render")

	// Set namespace
	namespace := app.Spec.Destination.Namespace
	if namespace == "" {
		namespace = "default"
	}
	r.SetAttr("namespace", namespace)

	// Set kubectl context if specified
	if cfg.kubectlContext != "" && cfg.kubectlContext != "current" {
		r.SetAttr("kubectl_context", cfg.kubectlContext)
	}

	return r
}
