package gguf

// PlanSplit divides a GGUF file's tensors into shards where each shard's
// total tensor data does not exceed maxBytes. Tensors are kept in order
// and never split across shards.
func PlanSplit(f *File, maxBytes uint64) []ShardPlan {
	if len(f.Tensors) == 0 {
		return []ShardPlan{{
			Index:     0,
			DataStart: f.TensorDataOffset,
			DataEnd:   f.TensorDataOffset,
		}}
	}

	// No splitting: single shard.
	if maxBytes == 0 {
		last := f.Tensors[len(f.Tensors)-1]
		return []ShardPlan{{
			Index:     0,
			Tensors:   f.Tensors,
			DataStart: f.TensorDataOffset + f.Tensors[0].Offset,
			DataEnd:   f.TensorDataOffset + last.Offset + TensorDataSize(last) - 1,
		}}
	}

	var shards []ShardPlan
	var current []TensorInfo
	var currentSize uint64

	for _, t := range f.Tensors {
		tSize := TensorDataSize(t)

		// If adding this tensor would exceed the limit and we already have tensors,
		// finalize the current shard.
		if currentSize+tSize > maxBytes && len(current) > 0 {
			shards = append(shards, makeShard(len(shards), current, f.TensorDataOffset))
			current = nil
			currentSize = 0
		}

		current = append(current, t)
		currentSize += tSize
	}

	// Finalize the last shard.
	if len(current) > 0 {
		shards = append(shards, makeShard(len(shards), current, f.TensorDataOffset))
	}

	return shards
}

func makeShard(index int, tensors []TensorInfo, dataOffset uint64) ShardPlan {
	first := tensors[0]
	last := tensors[len(tensors)-1]
	return ShardPlan{
		Index:     index,
		Tensors:   tensors,
		DataStart: dataOffset + first.Offset,
		DataEnd:   dataOffset + last.Offset + TensorDataSize(last) - 1,
	}
}
