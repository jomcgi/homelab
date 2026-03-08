package gguf

import (
	"bytes"
	"testing"
)

func TestWriteShardHeader_RoundTrip(t *testing.T) {
	source := &File{
		Header: Header{
			Magic:           Magic,
			Version:         3,
			TensorCount:     4,
			MetadataKVCount: 2,
		},
		Metadata: []MetadataKV{
			{Key: "general.architecture", ValueType: MetadataValueTypeSTRING, Value: "llama"},
			{Key: "general.name", ValueType: MetadataValueTypeSTRING, Value: "test"},
		},
		Tensors: []TensorInfo{
			{Name: "a", NDimensions: 1, Dimensions: []uint64{256}, Type: GGMLTypeF32, Offset: 0},
			{Name: "b", NDimensions: 1, Dimensions: []uint64{256}, Type: GGMLTypeF32, Offset: 1024},
			{Name: "c", NDimensions: 1, Dimensions: []uint64{256}, Type: GGMLTypeF32, Offset: 2048},
			{Name: "d", NDimensions: 1, Dimensions: []uint64{256}, Type: GGMLTypeF32, Offset: 3072},
		},
		TensorDataOffset: 4096,
	}

	shard := ShardPlan{
		Index: 0,
		Tensors: []TensorInfo{
			source.Tensors[0],
			source.Tensors[1],
		},
		DataStart: 4096,
		DataEnd:   6143,
	}

	var buf bytes.Buffer
	err := WriteShardHeader(&buf, source, shard, 2)
	if err != nil {
		t.Fatalf("WriteShardHeader failed: %v", err)
	}

	// Parse the written header.
	f, err := Parse(bytes.NewReader(buf.Bytes()))
	if err != nil {
		t.Fatalf("Parse of shard header failed: %v", err)
	}

	// Should have 2 tensors.
	if f.Header.TensorCount != 2 {
		t.Errorf("tensor count = %d, want 2", f.Header.TensorCount)
	}

	// Should have original metadata + 3 split keys = 5 total.
	if f.Header.MetadataKVCount != 5 {
		t.Errorf("metadata kv count = %d, want 5", f.Header.MetadataKVCount)
	}

	// Check split metadata.
	splitMeta := make(map[string]any)
	for _, kv := range f.Metadata {
		if kv.Key == "split.no" || kv.Key == "split.count" || kv.Key == "split.tensors.count" {
			splitMeta[kv.Key] = kv.Value
		}
	}
	if v, ok := splitMeta["split.no"].(uint16); !ok || v != 0 {
		t.Errorf("split.no = %v, want 0", splitMeta["split.no"])
	}
	if v, ok := splitMeta["split.count"].(uint16); !ok || v != 2 {
		t.Errorf("split.count = %v, want 2", splitMeta["split.count"])
	}
	if v, ok := splitMeta["split.tensors.count"].(int32); !ok || v != 4 {
		t.Errorf("split.tensors.count = %v, want 4", splitMeta["split.tensors.count"])
	}

	// Check re-based offsets: first tensor at 0, second at 1024.
	if f.Tensors[0].Offset != 0 {
		t.Errorf("tensor[0] offset = %d, want 0", f.Tensors[0].Offset)
	}
	if f.Tensors[1].Offset != 1024 {
		t.Errorf("tensor[1] offset = %d, want 1024", f.Tensors[1].Offset)
	}

	// TensorDataOffset should be 32-byte aligned.
	if f.TensorDataOffset%32 != 0 {
		t.Errorf("TensorDataOffset %d is not 32-byte aligned", f.TensorDataOffset)
	}
}

func TestWriteShardHeader_SecondShard(t *testing.T) {
	source := &File{
		Header: Header{
			Magic:           Magic,
			Version:         3,
			TensorCount:     4,
			MetadataKVCount: 1,
		},
		Metadata: []MetadataKV{
			{Key: "general.architecture", ValueType: MetadataValueTypeSTRING, Value: "llama"},
		},
		Tensors: []TensorInfo{
			{Name: "a", NDimensions: 1, Dimensions: []uint64{256}, Type: GGMLTypeF32, Offset: 0},
			{Name: "b", NDimensions: 1, Dimensions: []uint64{256}, Type: GGMLTypeF32, Offset: 1024},
			{Name: "c", NDimensions: 1, Dimensions: []uint64{256}, Type: GGMLTypeF32, Offset: 2048},
			{Name: "d", NDimensions: 1, Dimensions: []uint64{256}, Type: GGMLTypeF32, Offset: 3072},
		},
		TensorDataOffset: 4096,
	}

	shard := ShardPlan{
		Index: 1,
		Tensors: []TensorInfo{
			source.Tensors[2],
			source.Tensors[3],
		},
		DataStart: 6144,
		DataEnd:   8191,
	}

	var buf bytes.Buffer
	err := WriteShardHeader(&buf, source, shard, 2)
	if err != nil {
		t.Fatalf("WriteShardHeader failed: %v", err)
	}

	f, err := Parse(bytes.NewReader(buf.Bytes()))
	if err != nil {
		t.Fatalf("Parse of shard header failed: %v", err)
	}

	// Split index should be 1.
	for _, kv := range f.Metadata {
		if kv.Key == "split.no" {
			if v := kv.Value.(uint16); v != 1 {
				t.Errorf("split.no = %d, want 1", v)
			}
		}
	}

	// Re-based offsets: c was at 2048, d at 3072. After rebasing from 2048: 0 and 1024.
	if f.Tensors[0].Name != "c" || f.Tensors[0].Offset != 0 {
		t.Errorf("tensor[0] = (%q, %d), want (c, 0)", f.Tensors[0].Name, f.Tensors[0].Offset)
	}
	if f.Tensors[1].Name != "d" || f.Tensors[1].Offset != 1024 {
		t.Errorf("tensor[1] = (%q, %d), want (d, 1024)", f.Tensors[1].Name, f.Tensors[1].Offset)
	}
}

func TestWriteShardHeader_AllMetadataTypes(t *testing.T) {
	source := &File{
		Header: Header{
			Magic:           Magic,
			Version:         3,
			TensorCount:     1,
			MetadataKVCount: 5,
		},
		Metadata: []MetadataKV{
			{Key: "test.str", ValueType: MetadataValueTypeSTRING, Value: "hello"},
			{Key: "test.u32", ValueType: MetadataValueTypeUINT32, Value: uint32(42)},
			{Key: "test.bool", ValueType: MetadataValueTypeBOOL, Value: true},
			{Key: "test.f32", ValueType: MetadataValueTypeFLOAT32, Value: float32(3.14)},
			{Key: "test.i64", ValueType: MetadataValueTypeINT64, Value: int64(-999)},
		},
		Tensors: []TensorInfo{
			{Name: "t", NDimensions: 1, Dimensions: []uint64{32}, Type: GGMLTypeF32, Offset: 0},
		},
		TensorDataOffset: 4096,
	}

	shard := ShardPlan{
		Index:     0,
		Tensors:   source.Tensors,
		DataStart: 4096,
		DataEnd:   4096 + 128 - 1,
	}

	var buf bytes.Buffer
	err := WriteShardHeader(&buf, source, shard, 1)
	if err != nil {
		t.Fatalf("WriteShardHeader failed: %v", err)
	}

	f, err := Parse(bytes.NewReader(buf.Bytes()))
	if err != nil {
		t.Fatalf("Parse of shard header failed: %v", err)
	}

	// 5 original + 3 split = 8
	if len(f.Metadata) != 8 {
		t.Errorf("metadata count = %d, want 8", len(f.Metadata))
	}
}
