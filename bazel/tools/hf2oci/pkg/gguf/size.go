package gguf

// ggmlTypeSizes maps each GGMLType to its (blockSize, typeSize) pair.
// Block size is the number of elements per quantization block.
// Type size is the number of bytes per block.
var ggmlTypeSizes = map[GGMLType][2]uint64{
	GGMLTypeF32:     {1, 4},
	GGMLTypeF16:     {1, 2},
	GGMLTypeBF16:    {1, 2},
	GGMLTypeQ4_0:    {32, 18},
	GGMLTypeQ4_1:    {32, 20},
	GGMLTypeQ5_0:    {32, 22},
	GGMLTypeQ5_1:    {32, 24},
	GGMLTypeQ8_0:    {32, 34},
	GGMLTypeQ8_1:    {32, 40},
	GGMLTypeQ2_K:    {256, 84},
	GGMLTypeQ3_K:    {256, 110},
	GGMLTypeQ4_K:    {256, 144},
	GGMLTypeQ5_K:    {256, 176},
	GGMLTypeQ6_K:    {256, 210},
	GGMLTypeIQ2_XXS: {256, 66},
	GGMLTypeIQ2_XS:  {256, 74},
	GGMLTypeIQ2_S:   {256, 82},
	GGMLTypeIQ3_XXS: {256, 98},
	GGMLTypeIQ3_S:   {256, 110},
	GGMLTypeIQ4_NL:  {32, 18},
	GGMLTypeIQ4_XS:  {256, 136},
	GGMLTypeIQ1_S:   {256, 50},
	GGMLTypeIQ1_M:   {256, 56},
	GGMLTypeI8:      {1, 1},
	GGMLTypeI16:     {1, 2},
	GGMLTypeI32:     {1, 4},
	GGMLTypeI64:     {1, 8},
	GGMLTypeF64:     {1, 8},
}

// GGMLTypeSize returns the block size and type size (in bytes) for a GGML type.
// Unknown types return (0, 0).
func GGMLTypeSize(t GGMLType) (blockSize, typeSize uint64) {
	if s, ok := ggmlTypeSizes[t]; ok {
		return s[0], s[1]
	}
	return 0, 0
}

// TensorDataSize computes the total byte size of a tensor's data.
func TensorDataSize(t TensorInfo) uint64 {
	blockSize, typeSize := GGMLTypeSize(t.Type)
	if blockSize == 0 {
		return 0
	}
	nElements := uint64(1)
	for _, d := range t.Dimensions {
		nElements *= d
	}
	return (nElements / blockSize) * typeSize
}
