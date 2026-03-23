package gguf

import (
	"testing"
)

func TestGGMLTypeSize(t *testing.T) {
	tests := []struct {
		name          string
		typ           GGMLType
		wantBlockSize uint64
		wantTypeSize  uint64
	}{
		// 32-bit and 16-bit floats — one element per block
		{name: "F32", typ: GGMLTypeF32, wantBlockSize: 1, wantTypeSize: 4},
		{name: "F16", typ: GGMLTypeF16, wantBlockSize: 1, wantTypeSize: 2},
		{name: "BF16", typ: GGMLTypeBF16, wantBlockSize: 1, wantTypeSize: 2},
		{name: "F64", typ: GGMLTypeF64, wantBlockSize: 1, wantTypeSize: 8},

		// Integer types
		{name: "I8", typ: GGMLTypeI8, wantBlockSize: 1, wantTypeSize: 1},
		{name: "I16", typ: GGMLTypeI16, wantBlockSize: 1, wantTypeSize: 2},
		{name: "I32", typ: GGMLTypeI32, wantBlockSize: 1, wantTypeSize: 4},
		{name: "I64", typ: GGMLTypeI64, wantBlockSize: 1, wantTypeSize: 8},

		// Q4 quantization types (block size 32)
		{name: "Q4_0", typ: GGMLTypeQ4_0, wantBlockSize: 32, wantTypeSize: 18},
		{name: "Q4_1", typ: GGMLTypeQ4_1, wantBlockSize: 32, wantTypeSize: 20},

		// Q5 quantization types (block size 32)
		{name: "Q5_0", typ: GGMLTypeQ5_0, wantBlockSize: 32, wantTypeSize: 22},
		{name: "Q5_1", typ: GGMLTypeQ5_1, wantBlockSize: 32, wantTypeSize: 24},

		// Q8 quantization types (block size 32)
		{name: "Q8_0", typ: GGMLTypeQ8_0, wantBlockSize: 32, wantTypeSize: 34},
		{name: "Q8_1", typ: GGMLTypeQ8_1, wantBlockSize: 32, wantTypeSize: 40},

		// K-quant types (block size 256)
		{name: "Q2_K", typ: GGMLTypeQ2_K, wantBlockSize: 256, wantTypeSize: 84},
		{name: "Q3_K", typ: GGMLTypeQ3_K, wantBlockSize: 256, wantTypeSize: 110},
		{name: "Q4_K", typ: GGMLTypeQ4_K, wantBlockSize: 256, wantTypeSize: 144},
		{name: "Q5_K", typ: GGMLTypeQ5_K, wantBlockSize: 256, wantTypeSize: 176},
		{name: "Q6_K", typ: GGMLTypeQ6_K, wantBlockSize: 256, wantTypeSize: 210},

		// IQ types with block size 256
		{name: "IQ2_XXS", typ: GGMLTypeIQ2_XXS, wantBlockSize: 256, wantTypeSize: 66},
		{name: "IQ2_XS", typ: GGMLTypeIQ2_XS, wantBlockSize: 256, wantTypeSize: 74},
		{name: "IQ2_S", typ: GGMLTypeIQ2_S, wantBlockSize: 256, wantTypeSize: 82},
		{name: "IQ3_XXS", typ: GGMLTypeIQ3_XXS, wantBlockSize: 256, wantTypeSize: 98},
		{name: "IQ3_S", typ: GGMLTypeIQ3_S, wantBlockSize: 256, wantTypeSize: 110},
		{name: "IQ4_XS", typ: GGMLTypeIQ4_XS, wantBlockSize: 256, wantTypeSize: 136},
		{name: "IQ1_S", typ: GGMLTypeIQ1_S, wantBlockSize: 256, wantTypeSize: 50},
		{name: "IQ1_M", typ: GGMLTypeIQ1_M, wantBlockSize: 256, wantTypeSize: 56},

		// IQ4_NL uses block size 32 (same as Q4_0)
		{name: "IQ4_NL", typ: GGMLTypeIQ4_NL, wantBlockSize: 32, wantTypeSize: 18},

		// Unknown type returns (0, 0)
		{name: "unknown_type", typ: GGMLType(999), wantBlockSize: 0, wantTypeSize: 0},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			blockSize, typeSize := GGMLTypeSize(tt.typ)
			if blockSize != tt.wantBlockSize {
				t.Errorf("GGMLTypeSize(%d) blockSize = %d, want %d", tt.typ, blockSize, tt.wantBlockSize)
			}
			if typeSize != tt.wantTypeSize {
				t.Errorf("GGMLTypeSize(%d) typeSize = %d, want %d", tt.typ, typeSize, tt.wantTypeSize)
			}
		})
	}
}

func TestTensorDataSize(t *testing.T) {
	tests := []struct {
		name     string
		tensor   TensorInfo
		wantSize uint64
	}{
		{
			name: "F32 1D tensor",
			tensor: TensorInfo{
				Type:       GGMLTypeF32,
				Dimensions: []uint64{256},
			},
			// 256 elements * 4 bytes/elem = 1024 bytes
			wantSize: 1024,
		},
		{
			name: "F16 2D tensor",
			tensor: TensorInfo{
				Type:       GGMLTypeF16,
				Dimensions: []uint64{128, 64},
			},
			// 128*64=8192 elements * 2 bytes/elem = 16384 bytes
			wantSize: 16384,
		},
		{
			name: "Q4_0 quantized 1D tensor",
			tensor: TensorInfo{
				Type:       GGMLTypeQ4_0,
				Dimensions: []uint64{256},
			},
			// 256 elements / 32 block_size * 18 bytes/block = 8 * 18 = 144
			wantSize: 144,
		},
		{
			name: "Q4_K large 2D tensor",
			tensor: TensorInfo{
				Type:       GGMLTypeQ4_K,
				Dimensions: []uint64{4096, 4096},
			},
			// 4096*4096=16777216 elements / 256 block_size * 144 bytes/block = 65536 * 144 = 9437184
			wantSize: 9437184,
		},
		{
			name: "I8 single element",
			tensor: TensorInfo{
				Type:       GGMLTypeI8,
				Dimensions: []uint64{1},
			},
			// 1 element * 1 byte/elem = 1
			wantSize: 1,
		},
		{
			name: "F64 3D tensor",
			tensor: TensorInfo{
				Type:       GGMLTypeF64,
				Dimensions: []uint64{2, 3, 4},
			},
			// 2*3*4=24 elements * 8 bytes/elem = 192
			wantSize: 192,
		},
		{
			name: "unknown type returns zero",
			tensor: TensorInfo{
				Type:       GGMLType(999),
				Dimensions: []uint64{256},
			},
			wantSize: 0,
		},
		{
			name: "zero dimensions (scalar — treated as 1 element)",
			tensor: TensorInfo{
				Type:       GGMLTypeF32,
				Dimensions: []uint64{},
			},
			// nElements starts at 1, no dims to multiply, so 1/1*4 = 4
			wantSize: 4,
		},
		{
			name: "Q2_K tensor divisible by block size",
			tensor: TensorInfo{
				Type:       GGMLTypeQ2_K,
				Dimensions: []uint64{512},
			},
			// 512 / 256 * 84 = 2 * 84 = 168
			wantSize: 168,
		},
		{
			name: "IQ1_S tensor",
			tensor: TensorInfo{
				Type:       GGMLTypeIQ1_S,
				Dimensions: []uint64{1024},
			},
			// 1024 / 256 * 50 = 4 * 50 = 200
			wantSize: 200,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := TensorDataSize(tt.tensor)
			if got != tt.wantSize {
				t.Errorf("TensorDataSize() = %d, want %d", got, tt.wantSize)
			}
		})
	}
}
