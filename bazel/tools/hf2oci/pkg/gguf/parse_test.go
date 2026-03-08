package gguf

import (
	"bytes"
	"encoding/binary"
	"testing"
)

// buildMinimalGGUF constructs a minimal GGUF v3 binary with the given metadata and tensors.
func buildMinimalGGUF(t *testing.T, metadata []MetadataKV, tensors []TensorInfo) []byte {
	t.Helper()
	var buf bytes.Buffer
	le := binary.LittleEndian

	// Header.
	binary.Write(&buf, le, Magic)
	binary.Write(&buf, le, uint32(3)) // version
	binary.Write(&buf, le, uint64(len(tensors)))
	binary.Write(&buf, le, uint64(len(metadata)))

	// Metadata.
	for _, kv := range metadata {
		writeTestString(&buf, le, kv.Key)
		binary.Write(&buf, le, kv.ValueType)
		writeTestMetadataValue(t, &buf, le, kv)
	}

	// Tensor infos.
	for _, ti := range tensors {
		writeTestString(&buf, le, ti.Name)
		binary.Write(&buf, le, ti.NDimensions)
		for _, d := range ti.Dimensions {
			binary.Write(&buf, le, d)
		}
		binary.Write(&buf, le, uint32(ti.Type))
		binary.Write(&buf, le, ti.Offset)
	}

	return buf.Bytes()
}

func writeTestString(buf *bytes.Buffer, le binary.ByteOrder, s string) {
	binary.Write(buf, le, uint64(len(s)))
	buf.WriteString(s)
}

func writeTestMetadataValue(t *testing.T, buf *bytes.Buffer, le binary.ByteOrder, kv MetadataKV) {
	t.Helper()
	switch kv.ValueType {
	case MetadataValueTypeUINT8:
		binary.Write(buf, le, kv.Value.(uint8))
	case MetadataValueTypeINT8:
		binary.Write(buf, le, kv.Value.(int8))
	case MetadataValueTypeUINT16:
		binary.Write(buf, le, kv.Value.(uint16))
	case MetadataValueTypeINT16:
		binary.Write(buf, le, kv.Value.(int16))
	case MetadataValueTypeUINT32:
		binary.Write(buf, le, kv.Value.(uint32))
	case MetadataValueTypeINT32:
		binary.Write(buf, le, kv.Value.(int32))
	case MetadataValueTypeFLOAT32:
		binary.Write(buf, le, kv.Value.(float32))
	case MetadataValueTypeBOOL:
		v := uint8(0)
		if kv.Value.(bool) {
			v = 1
		}
		binary.Write(buf, le, v)
	case MetadataValueTypeSTRING:
		writeTestString(buf, le, kv.Value.(string))
	case MetadataValueTypeUINT64:
		binary.Write(buf, le, kv.Value.(uint64))
	case MetadataValueTypeINT64:
		binary.Write(buf, le, kv.Value.(int64))
	case MetadataValueTypeFLOAT64:
		binary.Write(buf, le, kv.Value.(float64))
	default:
		t.Fatalf("unsupported metadata type in test: %d", kv.ValueType)
	}
}

func TestParse_BasicFile(t *testing.T) {
	metadata := []MetadataKV{
		{Key: "general.architecture", ValueType: MetadataValueTypeSTRING, Value: "llama"},
		{Key: "general.name", ValueType: MetadataValueTypeSTRING, Value: "test-model"},
		{Key: "llama.context_length", ValueType: MetadataValueTypeUINT32, Value: uint32(4096)},
	}
	tensors := []TensorInfo{
		{Name: "token_embd.weight", NDimensions: 2, Dimensions: []uint64{4096, 32000}, Type: GGMLTypeF16, Offset: 0},
		{Name: "blk.0.attn_q.weight", NDimensions: 2, Dimensions: []uint64{4096, 4096}, Type: GGMLTypeQ4_0, Offset: 4096 * 32000 * 2},
	}

	data := buildMinimalGGUF(t, metadata, tensors)
	f, err := Parse(bytes.NewReader(data))
	if err != nil {
		t.Fatalf("Parse failed: %v", err)
	}

	// Verify header.
	if f.Header.Magic != Magic {
		t.Errorf("magic = 0x%X, want 0x%X", f.Header.Magic, Magic)
	}
	if f.Header.Version != 3 {
		t.Errorf("version = %d, want 3", f.Header.Version)
	}
	if f.Header.TensorCount != 2 {
		t.Errorf("tensor count = %d, want 2", f.Header.TensorCount)
	}
	if f.Header.MetadataKVCount != 3 {
		t.Errorf("metadata kv count = %d, want 3", f.Header.MetadataKVCount)
	}

	// Verify metadata.
	if len(f.Metadata) != 3 {
		t.Fatalf("metadata length = %d, want 3", len(f.Metadata))
	}
	if f.Metadata[0].Key != "general.architecture" || f.Metadata[0].Value.(string) != "llama" {
		t.Errorf("metadata[0] = %v, want general.architecture=llama", f.Metadata[0])
	}
	if f.Metadata[2].Value.(uint32) != 4096 {
		t.Errorf("metadata[2] value = %v, want 4096", f.Metadata[2].Value)
	}

	// Verify tensors.
	if len(f.Tensors) != 2 {
		t.Fatalf("tensor count = %d, want 2", len(f.Tensors))
	}
	if f.Tensors[0].Name != "token_embd.weight" {
		t.Errorf("tensor[0] name = %q, want %q", f.Tensors[0].Name, "token_embd.weight")
	}
	if f.Tensors[0].Type != GGMLTypeF16 {
		t.Errorf("tensor[0] type = %d, want %d", f.Tensors[0].Type, GGMLTypeF16)
	}
	if f.Tensors[1].NDimensions != 2 || f.Tensors[1].Dimensions[0] != 4096 {
		t.Errorf("tensor[1] dims = %v, want [4096 4096]", f.Tensors[1].Dimensions)
	}

	// Verify alignment: TensorDataOffset should be 32-byte aligned.
	if f.TensorDataOffset%32 != 0 {
		t.Errorf("TensorDataOffset %d is not 32-byte aligned", f.TensorDataOffset)
	}
}

func TestParse_EmptyFile(t *testing.T) {
	data := buildMinimalGGUF(t, nil, nil)
	f, err := Parse(bytes.NewReader(data))
	if err != nil {
		t.Fatalf("Parse failed: %v", err)
	}
	if f.Header.TensorCount != 0 {
		t.Errorf("tensor count = %d, want 0", f.Header.TensorCount)
	}
	if len(f.Metadata) != 0 {
		t.Errorf("metadata length = %d, want 0", len(f.Metadata))
	}
}

func TestMagic_MatchesGGUFSpec(t *testing.T) {
	// GGUF spec: first 4 bytes are ASCII 'G','G','U','F'.
	// Validate the constant matches, not just round-trip consistency.
	specBytes := []byte{'G', 'G', 'U', 'F'}
	specMagic := binary.LittleEndian.Uint32(specBytes)
	if Magic != specMagic {
		t.Errorf("Magic constant 0x%08X doesn't match GGUF spec bytes %q (expected 0x%08X)", Magic, specBytes, specMagic)
	}
}

func TestParse_InvalidMagic(t *testing.T) {
	var buf bytes.Buffer
	binary.Write(&buf, binary.LittleEndian, uint32(0xDEADBEEF))
	_, err := Parse(&buf)
	if err == nil {
		t.Fatal("expected error for invalid magic, got nil")
	}
}

func TestParse_RealGGUFMagicBytes(t *testing.T) {
	// Verify the parser accepts the raw GGUF spec magic bytes (not our constant).
	var buf bytes.Buffer
	buf.Write([]byte{'G', 'G', 'U', 'F'}) // raw spec bytes
	binary.Write(&buf, binary.LittleEndian, uint32(3))
	binary.Write(&buf, binary.LittleEndian, uint64(0))
	binary.Write(&buf, binary.LittleEndian, uint64(0))
	f, err := Parse(bytes.NewReader(buf.Bytes()))
	if err != nil {
		t.Fatalf("Parse rejected valid GGUF magic bytes: %v", err)
	}
	if f.Header.Magic != Magic {
		t.Errorf("parsed magic 0x%08X != Magic constant 0x%08X", f.Header.Magic, Magic)
	}
}

func TestParse_BoolMetadata(t *testing.T) {
	metadata := []MetadataKV{
		{Key: "test.flag", ValueType: MetadataValueTypeBOOL, Value: true},
	}
	data := buildMinimalGGUF(t, metadata, nil)
	f, err := Parse(bytes.NewReader(data))
	if err != nil {
		t.Fatalf("Parse failed: %v", err)
	}
	if v := f.Metadata[0].Value.(bool); !v {
		t.Errorf("bool value = %v, want true", v)
	}
}

func TestParse_NumericMetadataTypes(t *testing.T) {
	metadata := []MetadataKV{
		{Key: "test.u8", ValueType: MetadataValueTypeUINT8, Value: uint8(42)},
		{Key: "test.i8", ValueType: MetadataValueTypeINT8, Value: int8(-1)},
		{Key: "test.u16", ValueType: MetadataValueTypeUINT16, Value: uint16(1000)},
		{Key: "test.i16", ValueType: MetadataValueTypeINT16, Value: int16(-500)},
		{Key: "test.u32", ValueType: MetadataValueTypeUINT32, Value: uint32(100000)},
		{Key: "test.i32", ValueType: MetadataValueTypeINT32, Value: int32(-100000)},
		{Key: "test.f32", ValueType: MetadataValueTypeFLOAT32, Value: float32(3.14)},
		{Key: "test.u64", ValueType: MetadataValueTypeUINT64, Value: uint64(999999999)},
		{Key: "test.i64", ValueType: MetadataValueTypeINT64, Value: int64(-999999999)},
		{Key: "test.f64", ValueType: MetadataValueTypeFLOAT64, Value: float64(2.718281828)},
	}
	data := buildMinimalGGUF(t, metadata, nil)
	f, err := Parse(bytes.NewReader(data))
	if err != nil {
		t.Fatalf("Parse failed: %v", err)
	}
	if len(f.Metadata) != len(metadata) {
		t.Fatalf("metadata length = %d, want %d", len(f.Metadata), len(metadata))
	}
	if f.Metadata[0].Value.(uint8) != 42 {
		t.Errorf("u8 = %v, want 42", f.Metadata[0].Value)
	}
	if f.Metadata[1].Value.(int8) != -1 {
		t.Errorf("i8 = %v, want -1", f.Metadata[1].Value)
	}
}
