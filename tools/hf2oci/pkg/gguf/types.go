// Package gguf implements a minimal parser and writer for the GGUF v3 binary format
// used by llama.cpp and compatible inference engines.
package gguf

// Magic is the GGUF magic number: "GGUF" in little-endian.
const Magic uint32 = 0x46475547

// GGMLType identifies a tensor element quantization type.
type GGMLType uint32

const (
	GGMLTypeF32     GGMLType = 0
	GGMLTypeF16     GGMLType = 1
	GGMLTypeQ4_0    GGMLType = 2
	GGMLTypeQ4_1    GGMLType = 3
	GGMLTypeQ5_0    GGMLType = 6
	GGMLTypeQ5_1    GGMLType = 7
	GGMLTypeQ8_0    GGMLType = 8
	GGMLTypeQ8_1    GGMLType = 9
	GGMLTypeQ2_K    GGMLType = 10
	GGMLTypeQ3_K    GGMLType = 11
	GGMLTypeQ4_K    GGMLType = 12
	GGMLTypeQ5_K    GGMLType = 13
	GGMLTypeQ6_K    GGMLType = 14
	GGMLTypeIQ2_XXS GGMLType = 16
	GGMLTypeIQ2_XS  GGMLType = 17
	GGMLTypeIQ3_XXS GGMLType = 18
	GGMLTypeIQ1_S   GGMLType = 19
	GGMLTypeIQ4_NL  GGMLType = 20
	GGMLTypeIQ3_S   GGMLType = 21
	GGMLTypeIQ2_S   GGMLType = 22
	GGMLTypeIQ4_XS  GGMLType = 23
	GGMLTypeI8      GGMLType = 24
	GGMLTypeI16     GGMLType = 25
	GGMLTypeI32     GGMLType = 26
	GGMLTypeI64     GGMLType = 27
	GGMLTypeF64     GGMLType = 28
	GGMLTypeIQ1_M   GGMLType = 29
	GGMLTypeBF16    GGMLType = 30
)

// MetadataValueType identifies the type of a GGUF metadata value.
type MetadataValueType uint32

const (
	MetadataValueTypeUINT8   MetadataValueType = 0
	MetadataValueTypeINT8    MetadataValueType = 1
	MetadataValueTypeUINT16  MetadataValueType = 2
	MetadataValueTypeINT16   MetadataValueType = 3
	MetadataValueTypeUINT32  MetadataValueType = 4
	MetadataValueTypeINT32   MetadataValueType = 5
	MetadataValueTypeFLOAT32 MetadataValueType = 6
	MetadataValueTypeBOOL    MetadataValueType = 7
	MetadataValueTypeSTRING  MetadataValueType = 8
	MetadataValueTypeARRAY   MetadataValueType = 9
	MetadataValueTypeUINT64  MetadataValueType = 10
	MetadataValueTypeINT64   MetadataValueType = 11
	MetadataValueTypeFLOAT64 MetadataValueType = 12
)

// Header is the fixed-size header at the start of a GGUF file.
type Header struct {
	Magic           uint32
	Version         uint32
	TensorCount     uint64
	MetadataKVCount uint64
}

// MetadataKV is a single metadata key-value pair.
type MetadataKV struct {
	Key       string
	ValueType MetadataValueType
	Value     any
}

// TensorInfo describes a single tensor in the GGUF file.
type TensorInfo struct {
	Name        string
	NDimensions uint32
	Dimensions  []uint64
	Type        GGMLType
	Offset      uint64
}

// File is a parsed GGUF file (header + metadata + tensor info, not tensor data).
type File struct {
	Header           Header
	Metadata         []MetadataKV
	Tensors          []TensorInfo
	TensorDataOffset uint64
}

// ShardPlan describes one shard in a split GGUF file.
type ShardPlan struct {
	Index     int
	Tensors   []TensorInfo
	DataStart uint64 // byte offset in the original file
	DataEnd   uint64 // inclusive byte offset in the original file
}
