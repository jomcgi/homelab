package gguf

import (
	"testing"
)

func TestPlanSplit_SingleShard(t *testing.T) {
	f := &File{
		Header: Header{TensorCount: 2},
		Tensors: []TensorInfo{
			{Name: "a", NDimensions: 1, Dimensions: []uint64{256}, Type: GGMLTypeF32, Offset: 0},    // 1024 bytes
			{Name: "b", NDimensions: 1, Dimensions: []uint64{256}, Type: GGMLTypeF32, Offset: 1024}, // 1024 bytes
		},
		TensorDataOffset: 4096,
	}

	shards := PlanSplit(f, 10000) // plenty of room
	if len(shards) != 1 {
		t.Fatalf("shard count = %d, want 1", len(shards))
	}
	if len(shards[0].Tensors) != 2 {
		t.Errorf("shard[0] tensor count = %d, want 2", len(shards[0].Tensors))
	}
	if shards[0].DataStart != 4096 {
		t.Errorf("DataStart = %d, want 4096", shards[0].DataStart)
	}
	// DataEnd = 4096 + 1024 + 1024 - 1 = 6143
	if shards[0].DataEnd != 6143 {
		t.Errorf("DataEnd = %d, want 6143", shards[0].DataEnd)
	}
}

func TestPlanSplit_MultipleShardsEvenSplit(t *testing.T) {
	f := &File{
		Header: Header{TensorCount: 4},
		Tensors: []TensorInfo{
			{Name: "a", NDimensions: 1, Dimensions: []uint64{256}, Type: GGMLTypeF32, Offset: 0},
			{Name: "b", NDimensions: 1, Dimensions: []uint64{256}, Type: GGMLTypeF32, Offset: 1024},
			{Name: "c", NDimensions: 1, Dimensions: []uint64{256}, Type: GGMLTypeF32, Offset: 2048},
			{Name: "d", NDimensions: 1, Dimensions: []uint64{256}, Type: GGMLTypeF32, Offset: 3072},
		},
		TensorDataOffset: 4096,
	}

	// Each tensor is 1024 bytes; max 2048 means 2 tensors per shard.
	shards := PlanSplit(f, 2048)
	if len(shards) != 2 {
		t.Fatalf("shard count = %d, want 2", len(shards))
	}
	if len(shards[0].Tensors) != 2 {
		t.Errorf("shard[0] tensor count = %d, want 2", len(shards[0].Tensors))
	}
	if len(shards[1].Tensors) != 2 {
		t.Errorf("shard[1] tensor count = %d, want 2", len(shards[1].Tensors))
	}
	if shards[0].Index != 0 || shards[1].Index != 1 {
		t.Errorf("shard indices = [%d, %d], want [0, 1]", shards[0].Index, shards[1].Index)
	}

	// Shard 0: tensors a, b. DataStart = 4096+0 = 4096, DataEnd = 4096+1024+1024-1 = 6143
	if shards[0].DataStart != 4096 {
		t.Errorf("shard[0].DataStart = %d, want 4096", shards[0].DataStart)
	}
	if shards[0].DataEnd != 6143 {
		t.Errorf("shard[0].DataEnd = %d, want 6143", shards[0].DataEnd)
	}
	// Shard 1: tensors c, d. DataStart = 4096+2048 = 6144, DataEnd = 4096+3072+1024-1 = 8191
	if shards[1].DataStart != 6144 {
		t.Errorf("shard[1].DataStart = %d, want 6144", shards[1].DataStart)
	}
	if shards[1].DataEnd != 8191 {
		t.Errorf("shard[1].DataEnd = %d, want 8191", shards[1].DataEnd)
	}
}

func TestPlanSplit_OversizedTensor(t *testing.T) {
	f := &File{
		Header: Header{TensorCount: 3},
		Tensors: []TensorInfo{
			{Name: "small1", NDimensions: 1, Dimensions: []uint64{64}, Type: GGMLTypeF32, Offset: 0},     // 256 bytes
			{Name: "big", NDimensions: 1, Dimensions: []uint64{4096}, Type: GGMLTypeF32, Offset: 256},    // 16384 bytes
			{Name: "small2", NDimensions: 1, Dimensions: []uint64{64}, Type: GGMLTypeF32, Offset: 16640}, // 256 bytes
		},
		TensorDataOffset: 1024,
	}

	// maxBytes=1000 is smaller than "big" tensor. big gets its own shard.
	shards := PlanSplit(f, 1000)
	if len(shards) != 3 {
		t.Fatalf("shard count = %d, want 3", len(shards))
	}
	if shards[0].Tensors[0].Name != "small1" {
		t.Errorf("shard[0] = %q, want small1", shards[0].Tensors[0].Name)
	}
	if shards[1].Tensors[0].Name != "big" {
		t.Errorf("shard[1] = %q, want big", shards[1].Tensors[0].Name)
	}
	if shards[2].Tensors[0].Name != "small2" {
		t.Errorf("shard[2] = %q, want small2", shards[2].Tensors[0].Name)
	}
}

func TestPlanSplit_ZeroMaxBytes(t *testing.T) {
	f := &File{
		Header: Header{TensorCount: 2},
		Tensors: []TensorInfo{
			{Name: "a", NDimensions: 1, Dimensions: []uint64{256}, Type: GGMLTypeF32, Offset: 0},
			{Name: "b", NDimensions: 1, Dimensions: []uint64{256}, Type: GGMLTypeF32, Offset: 1024},
		},
		TensorDataOffset: 4096,
	}
	shards := PlanSplit(f, 0) // no splitting
	if len(shards) != 1 {
		t.Fatalf("shard count = %d, want 1", len(shards))
	}
	if len(shards[0].Tensors) != 2 {
		t.Errorf("shard[0] tensor count = %d, want 2", len(shards[0].Tensors))
	}
}

func TestPlanSplit_EmptyFile(t *testing.T) {
	f := &File{
		Header:           Header{TensorCount: 0},
		TensorDataOffset: 4096,
	}
	shards := PlanSplit(f, 1000)
	if len(shards) != 1 {
		t.Fatalf("shard count = %d, want 1", len(shards))
	}
	if len(shards[0].Tensors) != 0 {
		t.Errorf("shard[0] tensor count = %d, want 0", len(shards[0].Tensors))
	}
}
