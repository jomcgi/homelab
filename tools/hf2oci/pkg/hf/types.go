package hf

// TreeEntry represents a file or directory in a HuggingFace repository.
type TreeEntry struct {
	Type string   `json:"type"` // "file" or "directory"
	Path string   `json:"path"`
	Size int64    `json:"size"`
	LFS  *LFSInfo `json:"lfs,omitempty"`
}

// LFSInfo contains Git LFS metadata for large files.
type LFSInfo struct {
	OID  string `json:"oid"` // "sha256:abc..."
	Size int64  `json:"size"`
}

// ModelInfo holds metadata from the /api/models/{repo} endpoint.
type ModelInfo struct {
	ID         string      `json:"id"`
	BaseModels *BaseModels `json:"baseModels,omitempty"`
}

// BaseModels describes the lineage relationship to a parent model.
type BaseModels struct {
	Relation string      `json:"relation"` // "quantized", "finetune", "adapter", "merge"
	Models   []BaseModel `json:"models"`
}

// BaseModel identifies a parent model.
type BaseModel struct {
	ID string `json:"id"` // HF repo identifier (e.g. "facebook/nllb-200-distilled-1.3B")
}
