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
