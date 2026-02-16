package gguf

import (
	"encoding/binary"
	"fmt"
	"io"
)

// WriteShardHeader writes a valid GGUF v3 header for a shard file.
// It includes all original metadata plus split metadata keys,
// followed by tensor infos with re-based offsets, padded to 32-byte alignment.
func WriteShardHeader(w io.Writer, source *File, shard ShardPlan, shardCount int) error {
	le := binary.LittleEndian
	cw := &countingWriter{w: w}

	// Build the full metadata list: original + split keys.
	splitMeta := []MetadataKV{
		{Key: "split.no", ValueType: MetadataValueTypeUINT16, Value: uint16(shard.Index)},
		{Key: "split.count", ValueType: MetadataValueTypeUINT16, Value: uint16(shardCount)},
		{Key: "split.tensors.count", ValueType: MetadataValueTypeINT32, Value: int32(source.Header.TensorCount)},
	}
	allMeta := append(source.Metadata, splitMeta...)

	// Write header.
	if err := binary.Write(cw, le, Magic); err != nil {
		return fmt.Errorf("writing magic: %w", err)
	}
	if err := binary.Write(cw, le, uint32(3)); err != nil { // always v3
		return fmt.Errorf("writing version: %w", err)
	}
	if err := binary.Write(cw, le, uint64(len(shard.Tensors))); err != nil {
		return fmt.Errorf("writing tensor count: %w", err)
	}
	if err := binary.Write(cw, le, uint64(len(allMeta))); err != nil {
		return fmt.Errorf("writing metadata kv count: %w", err)
	}

	// Write metadata.
	for _, kv := range allMeta {
		if err := writeString(cw, le, kv.Key); err != nil {
			return fmt.Errorf("writing metadata key %q: %w", kv.Key, err)
		}
		if err := binary.Write(cw, le, kv.ValueType); err != nil {
			return fmt.Errorf("writing metadata value type for %q: %w", kv.Key, err)
		}
		if err := writeMetadataValue(cw, le, kv); err != nil {
			return fmt.Errorf("writing metadata value for %q: %w", kv.Key, err)
		}
	}

	// Re-base tensor offsets so the first tensor in this shard starts at 0.
	baseOffset := uint64(0)
	if len(shard.Tensors) > 0 {
		baseOffset = shard.Tensors[0].Offset
	}

	// Write tensor infos.
	for _, ti := range shard.Tensors {
		if err := writeString(cw, le, ti.Name); err != nil {
			return fmt.Errorf("writing tensor name %q: %w", ti.Name, err)
		}
		if err := binary.Write(cw, le, ti.NDimensions); err != nil {
			return err
		}
		for _, d := range ti.Dimensions {
			if err := binary.Write(cw, le, d); err != nil {
				return err
			}
		}
		if err := binary.Write(cw, le, uint32(ti.Type)); err != nil {
			return err
		}
		if err := binary.Write(cw, le, ti.Offset-baseOffset); err != nil {
			return err
		}
	}

	// Pad to 32-byte alignment.
	padLen := align(uint64(cw.n), 32) - uint64(cw.n)
	if padLen > 0 {
		pad := make([]byte, padLen)
		if _, err := cw.Write(pad); err != nil {
			return fmt.Errorf("writing alignment padding: %w", err)
		}
	}

	return nil
}

func writeString(w io.Writer, le binary.ByteOrder, s string) error {
	if err := binary.Write(w, le, uint64(len(s))); err != nil {
		return err
	}
	_, err := w.Write([]byte(s))
	return err
}

func writeMetadataValue(w io.Writer, le binary.ByteOrder, kv MetadataKV) error {
	switch kv.ValueType {
	case MetadataValueTypeUINT8:
		return binary.Write(w, le, kv.Value.(uint8))
	case MetadataValueTypeINT8:
		return binary.Write(w, le, kv.Value.(int8))
	case MetadataValueTypeUINT16:
		return binary.Write(w, le, kv.Value.(uint16))
	case MetadataValueTypeINT16:
		return binary.Write(w, le, kv.Value.(int16))
	case MetadataValueTypeUINT32:
		return binary.Write(w, le, kv.Value.(uint32))
	case MetadataValueTypeINT32:
		return binary.Write(w, le, kv.Value.(int32))
	case MetadataValueTypeFLOAT32:
		return binary.Write(w, le, kv.Value.(float32))
	case MetadataValueTypeBOOL:
		v := uint8(0)
		if kv.Value.(bool) {
			v = 1
		}
		return binary.Write(w, le, v)
	case MetadataValueTypeSTRING:
		return writeString(w, le, kv.Value.(string))
	case MetadataValueTypeARRAY:
		arr := kv.Value.([]any)
		// Determine element type from the first element, or default to UINT8 for empty.
		elemType := MetadataValueTypeUINT8
		if len(arr) > 0 {
			elemType = inferMetadataValueType(arr[0])
		}
		if err := binary.Write(w, le, elemType); err != nil {
			return err
		}
		if err := binary.Write(w, le, uint64(len(arr))); err != nil {
			return err
		}
		for _, elem := range arr {
			if err := writeMetadataValue(w, le, MetadataKV{ValueType: elemType, Value: elem}); err != nil {
				return err
			}
		}
		return nil
	case MetadataValueTypeUINT64:
		return binary.Write(w, le, kv.Value.(uint64))
	case MetadataValueTypeINT64:
		return binary.Write(w, le, kv.Value.(int64))
	case MetadataValueTypeFLOAT64:
		return binary.Write(w, le, kv.Value.(float64))
	default:
		return fmt.Errorf("unknown metadata value type: %d", kv.ValueType)
	}
}

func inferMetadataValueType(v any) MetadataValueType {
	switch v.(type) {
	case uint8:
		return MetadataValueTypeUINT8
	case int8:
		return MetadataValueTypeINT8
	case uint16:
		return MetadataValueTypeUINT16
	case int16:
		return MetadataValueTypeINT16
	case uint32:
		return MetadataValueTypeUINT32
	case int32:
		return MetadataValueTypeINT32
	case float32:
		return MetadataValueTypeFLOAT32
	case bool:
		return MetadataValueTypeBOOL
	case string:
		return MetadataValueTypeSTRING
	case uint64:
		return MetadataValueTypeUINT64
	case int64:
		return MetadataValueTypeINT64
	case float64:
		return MetadataValueTypeFLOAT64
	default:
		return MetadataValueTypeUINT8
	}
}

// countingWriter wraps an io.Writer and tracks total bytes written.
type countingWriter struct {
	w io.Writer
	n int64
}

func (cw *countingWriter) Write(p []byte) (int, error) {
	n, err := cw.w.Write(p)
	cw.n += int64(n)
	return n, err
}
