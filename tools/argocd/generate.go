package argocd

import (
	"os"
	"path/filepath"
	"strings"

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
			Chart          string `yaml:"chart"` // For remote Helm charts
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

// generateRules generates BUILD rules for ArgoCD applications and chart directories.
func generateRules(args language.GenerateArgs) language.GenerateResult {
	cfg := getArgoCDConfig(args.Config)

	var result language.GenerateResult

	// Only generate rules if enabled
	if !cfg.enabled {
		return result
	}

	// Check if this is a chart directory (has Chart.yaml)
	chartFile := filepath.Join(args.Dir, "Chart.yaml")
	if _, err := os.Stat(chartFile); err == nil {
		// This is a Helm chart directory - create exports_files rule
		exportsRule := rule.NewRule("exports_files", "")

		// Collect files to export
		var exports []string
		exports = append(exports, "Chart.yaml")

		// Check if values.yaml exists
		if _, err := os.Stat(filepath.Join(args.Dir, "values.yaml")); err == nil {
			exports = append(exports, "values.yaml")
		}

		exportsRule.SetAttr("srcs", exports)
		result.Gen = append(result.Gen, exportsRule)
		result.Imports = append(result.Imports, nil)

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

	// Generate live ArgoCD diff rule (opt-in only with pre-rendered manifests)
	// With pre-rendered manifests, use `git diff manifests/all.yaml` instead
	if cfg.generateDiff {
		diffRule := generateLiveDiffRule(app, args.Rel, args.Dir)
		if diffRule != nil {
			result.Gen = append(result.Gen, diffRule)
			result.Imports = append(result.Imports, nil)
		}
	}

	// Generate manifest rendering rule if enabled
	// Generate if the application has a Helm source (helm.valueFiles present)
	// Note: releaseName is optional in ArgoCD (defaults to app name if not specified)
	if cfg.generateManifests && len(app.Spec.Source.Helm.ValueFiles) > 0 {
		manifestRule := generateManifestRule(app, args.Rel, args.Dir)
		if manifestRule != nil {
			result.Gen = append(result.Gen, manifestRule)
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

// generateLiveDiffRule creates a sh_binary rule that wraps the ArgoCD live server diff.
func generateLiveDiffRule(app *ArgoCDApplication, currentPackage string, currentDir string) *rule.Rule {
	r := rule.NewRule("sh_binary", "diff")

	// Reference the live diff script
	r.SetAttr("srcs", []string{"//tools/argocd:argocd-live-diff.sh"})

	// Collect all file dependencies for deterministic caching
	var dataFiles []string

	// 1. Add the application.yaml itself
	dataFiles = append(dataFiles, "application.yaml")

	// 2. Add chart files (always from a different package)
	chartPath := app.Spec.Source.Path
	if chartPath != "" {
		// Add Chart.yaml from the chart (format: //package:target)
		dataFiles = append(dataFiles, "//"+filepath.ToSlash(chartPath)+":Chart.yaml")

		// Add chart's default values.yaml
		dataFiles = append(dataFiles, "//"+filepath.ToSlash(chartPath)+":values.yaml")
	}

	// 3. Add all valueFiles referenced in the Application spec
	for _, vf := range app.Spec.Source.Helm.ValueFiles {
		if strings.HasPrefix(vf, "../") {
			// Relative path - resolve it relative to chart path
			resolvedPath := filepath.Join(chartPath, vf)
			cleanPath := filepath.Clean(resolvedPath)

			// Skip paths that escape workspace root
			if strings.HasPrefix(cleanPath, "..") {
				continue
			}

			// Check if this file is in the current package
			fileDir := filepath.Dir(cleanPath)
			fileName := filepath.Base(cleanPath)

			if filepath.ToSlash(fileDir) == currentPackage {
				// File is in current package, use relative reference
				dataFiles = append(dataFiles, fileName)
			} else {
				// File is in different package, use absolute label
				dataFiles = append(dataFiles, "//"+filepath.ToSlash(fileDir)+":"+fileName)
			}
		} else if !strings.Contains(vf, "/") {
			// Simple filename in chart directory
			dataFiles = append(dataFiles, "//"+filepath.ToSlash(chartPath)+":"+vf)
		}
	}

	// 4. Add local values.yaml if it exists in the overlay directory
	// This is relative to the BUILD file location
	localValuesPath := filepath.Join(currentDir, "values.yaml")
	if _, err := os.Stat(localValuesPath); err == nil {
		dataFiles = append(dataFiles, "values.yaml")
	}

	// Add argocd and op CLIs as dependencies
	dataFiles = append(dataFiles, "@multitool//tools/argocd")
	dataFiles = append(dataFiles, "@multitool//tools/op")

	// Deduplicate data files
	seen := make(map[string]bool)
	var uniqueDataFiles []string
	for _, f := range dataFiles {
		if !seen[f] {
			seen[f] = true
			uniqueDataFiles = append(uniqueDataFiles, f)
		}
	}

	// Set data dependencies for caching
	r.SetAttr("data", uniqueDataFiles)

	// Set environment variables to identify this application
	env := make(map[string]string)
	env["ARGOCD_APP_NAME"] = app.Metadata.Name
	env["ARGOCD"] = "$(rootpath @multitool//tools/argocd)"
	env["OP"] = "$(rootpath @multitool//tools/op)"

	if app.Spec.Destination.Namespace != "" {
		env["ARGOCD_APP_NAMESPACE"] = app.Spec.Destination.Namespace
	}

	r.SetAttr("env", env)

	return r
}

// generateManifestRule creates a genrule that pre-renders Helm manifests to manifests/all.yaml.
// Using genrule instead of sh_binary enables proper Bazel caching based on input file hashes.
// Bazel will only re-render when chart files, values files, or helm binary change.
func generateManifestRule(app *ArgoCDApplication, currentPackage string, currentDir string) *rule.Rule {
	r := rule.NewRule("genrule", "render_manifests")

	// The render script is used as a tool (not a source)
	tools := []string{"//tools/argocd:render-manifests.sh", "@multitool//tools/helm"}

	// Collect all file dependencies (genrule uses 'srcs' instead of 'data')
	var srcFiles []string

	// 1. Add the application.yaml itself
	srcFiles = append(srcFiles, "application.yaml")

	// 2. Add chart files (entire chart directory)
	chartPath := app.Spec.Source.Path
	if chartPath != "" {
		// Add Chart.yaml from the chart
		srcFiles = append(srcFiles, "//"+filepath.ToSlash(chartPath)+":Chart.yaml")

		// Add chart's default values.yaml
		srcFiles = append(srcFiles, "//"+filepath.ToSlash(chartPath)+":values.yaml")
	}

	// 3. Build the VALUES_FILES environment variable (space-separated paths)
	var valuesFilePaths []string

	// Add chart's default values.yaml first
	if chartPath != "" {
		valuesFilePaths = append(valuesFilePaths, filepath.ToSlash(chartPath)+"/values.yaml")
	}

	// 4. Add all valueFiles referenced in the Application spec
	for _, vf := range app.Spec.Source.Helm.ValueFiles {
		if strings.HasPrefix(vf, "../") {
			// Relative path - resolve it relative to chart path
			resolvedPath := filepath.Join(chartPath, vf)
			cleanPath := filepath.Clean(resolvedPath)

			// Skip paths that escape workspace root
			if strings.HasPrefix(cleanPath, "..") {
				continue
			}

			// Check if this file is in the current package
			fileDir := filepath.Dir(cleanPath)
			fileName := filepath.Base(cleanPath)

			if filepath.ToSlash(fileDir) == currentPackage {
				// File is in current package, use relative reference
				srcFiles = append(srcFiles, fileName)
			} else {
				// File is in different package, use absolute label
				srcFiles = append(srcFiles, "//"+filepath.ToSlash(fileDir)+":"+fileName)
			}

			// Add to values file paths list
			valuesFilePaths = append(valuesFilePaths, filepath.ToSlash(cleanPath))
		} else if !strings.Contains(vf, "/") {
			// Simple filename in chart directory
			srcFiles = append(srcFiles, "//"+filepath.ToSlash(chartPath)+":"+vf)
			valuesFilePaths = append(valuesFilePaths, filepath.ToSlash(chartPath)+"/"+vf)
		}
	}

	// 5. Add local values.yaml if it exists
	localValuesPath := filepath.Join(currentDir, "values.yaml")
	if _, err := os.Stat(localValuesPath); err == nil {
		srcFiles = append(srcFiles, "values.yaml")
	}

	// Deduplicate source files
	seen := make(map[string]bool)
	var uniqueSrcFiles []string
	for _, f := range srcFiles {
		if !seen[f] {
			seen[f] = true
			uniqueSrcFiles = append(uniqueSrcFiles, f)
		}
	}

	// Set source dependencies and tools
	r.SetAttr("srcs", uniqueSrcFiles)
	r.SetAttr("tools", tools)

	// releaseName defaults to app name if not specified (ArgoCD behavior)
	releaseName := app.Spec.Source.Helm.ReleaseName
	if releaseName == "" {
		releaseName = app.Metadata.Name
	}

	// Set the output file declaration (critical for caching!)
	r.SetAttr("outs", []string{"manifests/all.yaml"})

	// Build the command to run helm template directly
	// Note: genrule with local=True runs in the workspace root, allowing direct path access
	helmCmd := []string{
		"$(location @multitool//tools/helm)",
		"template",
		releaseName,
		app.Spec.Source.Path,
		"--namespace", app.Spec.Destination.Namespace,
	}

	// Add values files
	for _, vf := range valuesFilePaths {
		helmCmd = append(helmCmd, "--values", vf)
	}

	// Redirect output to declared file
	helmCmd = append(helmCmd, ">", "$@")

	r.SetAttr("cmd", strings.Join(helmCmd, " "))

	// Make the target publicly visible so it can be referenced by parallel rendering
	r.SetAttr("visibility", []string{"//visibility:public"})

	// Set message for better progress reporting
	r.SetAttr("message", "Rendering Helm manifests for "+app.Metadata.Name)

	// Use local execution to avoid sandbox restrictions and access full chart directory
	// This enables caching while allowing helm to read template files not explicitly declared
	r.SetAttr("local", true)

	// Tag as manual so it doesn't run on bazel build //...
	r.SetAttr("tags", []string{"manual"})

	return r
}
