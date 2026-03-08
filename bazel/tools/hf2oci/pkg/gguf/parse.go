package gguf

import (
	"encoding/binary"
	"fmt"
	"io"
)

// countingReader wraps an io.Reader and tracks total bytes read.
type countingReader struct {
	r io.Reader
	n int64
}

func (cr *countingReader) Read(p []byte) (int, error) {
	n, err := cr.r.Read(p)
	cr.n += int64(n)
	return n, err
}

// Parse reads the GGUF header, metadata, and tensor info from r.
// It does not read the actual tensor data.
func Parse(r io.Reader) (*File, error) {
	cr := &countingReader{r: r}
	le := binary.LittleEndian

	// Read magic.
	var magic uint32
	if err := binary.Read(cr, le, &magic); err != nil {
		return nil, fmt.Errorf("reading magic: %w", err)
	}
	if magic != Magic {
		return nil, fmt.Errorf("invalid GGUF magic: 0x%08X", magic)
	}

	// Read version.
	var version uint32
	if err := binary.Read(cr, le, &version); err != nil {
		return nil, fmt.Errorf("reading version: %w", err)
	}
	if version < 2 || version > 3 {
		return nil, fmt.Errorf("unsupported GGUF version: %d", version)
	}

	// Read tensor count and metadata KV count.
	var tensorCount, metadataKVCount uint64
	if version == 3 {
		if err := binary.Read(cr, le, &tensorCount); err != nil {
			return nil, fmt.Errorf("reading tensor count: %w", err)
		}
		if err := binary.Read(cr, le, &metadataKVCount); err != nil {
			return nil, fmt.Errorf("reading metadata kv count: %w", err)
		}
	} else {
		var tc, mc uint32
		if err := binary.Read(cr, le, &tc); err != nil {
			return nil, fmt.Errorf("reading tensor count: %w", err)
		}
		if err := binary.Read(cr, le, &mc); err != nil {
			return nil, fmt.Errorf("reading metadata kv count: %w", err)
		}
		tensorCount = uint64(tc)
		metadataKVCount = uint64(mc)
	}

	f := &File{
		Header: Header{
			Magic:           magic,
			Version:         version,
			TensorCount:     tensorCount,
			MetadataKVCount: metadataKVCount,
		},
	}

	// Read metadata KVs.
	f.Metadata = make([]MetadataKV, 0, metadataKVCount)
	for i := uint64(0); i < metadataKVCount; i++ {
		kv, err := readMetadataKV(cr, le)
		if err != nil {
			return nil, fmt.Errorf("reading metadata kv %d: %w", i, err)
		}
		f.Metadata = append(f.Metadata, kv)
	}

	// Read tensor infos.
	f.Tensors = make([]TensorInfo, 0, tensorCount)
	for i := uint64(0); i < tensorCount; i++ {
		ti, err := readTensorInfo(cr, le)
		if err != nil {
			return nil, fmt.Errorf("reading tensor info %d: %w", i, err)
		}
		f.Tensors = append(f.Tensors, ti)
	}

	// Tensor data starts at the next 32-byte aligned position.
	f.TensorDataOffset = align(uint64(cr.n), 32)

	return f, nil
}

func readString(r io.Reader, le binary.ByteOrder) (string, error) {
	var length uint64
	if err := binary.Read(r, le, &length); err != nil {
		return "", err
	}
	buf := make([]byte, length)
	if _, err := io.ReadFull(r, buf); err != nil {
		return "", err
	}
	return string(buf), nil
}

func readMetadataKV(r io.Reader, le binary.ByteOrder) (MetadataKV, error) {
	key, err := readString(r, le)
	if err != nil {
		return MetadataKV{}, fmt.Errorf("reading key: %w", err)
	}

	var valueType MetadataValueType
	if err := binary.Read(r, le, &valueType); err != nil {
		return MetadataKV{}, fmt.Errorf("reading value type: %w", err)
	}

	val, err := readMetadataValue(r, le, valueType)
	if err != nil {
		return MetadataKV{}, fmt.Errorf("reading value for key %q: %w", key, err)
	}

	return MetadataKV{Key: key, ValueType: valueType, Value: val}, nil
}

func readMetadataValue(r io.Reader, le binary.ByteOrder, vt MetadataValueType) (any, error) {
	switch vt {
	case MetadataValueTypeUINT8:
		var v uint8
		return v, binary.Read(r, le, &v)
	case MetadataValueTypeINT8:
		var v int8
		return v, binary.Read(r, le, &v)
	case MetadataValueTypeUINT16:
		var v uint16
		return v, binary.Read(r, le, &v)
	case MetadataValueTypeINT16:
		var v int16
		return v, binary.Read(r, le, &v)
	case MetadataValueTypeUINT32:
		var v uint32
		return v, binary.Read(r, le, &v)
	case MetadataValueTypeINT32:
		var v int32
		return v, binary.Read(r, le, &v)
	case MetadataValueTypeFLOAT32:
		var v float32
		return v, binary.Read(r, le, &v)
	case MetadataValueTypeBOOL:
		var v uint8
		if err := binary.Read(r, le, &v); err != nil {
			return nil, err
		}
		return v != 0, nil
	case MetadataValueTypeSTRING:
		return readString(r, le)
	case MetadataValueTypeARRAY:
		var elemType MetadataValueType
		if err := binary.Read(r, le, &elemType); err != nil {
			return nil, err
		}
		var count uint64
		if err := binary.Read(r, le, &count); err != nil {
			return nil, err
		}
		arr := make([]any, 0, count)
		for i := uint64(0); i < count; i++ {
			v, err := readMetadataValue(r, le, elemType)
			if err != nil {
				return nil, err
			}
			arr = append(arr, v)
		}
		return arr, nil
	case MetadataValueTypeUINT64:
		var v uint64
		return v, binary.Read(r, le, &v)
	case MetadataValueTypeINT64:
		var v int64
		return v, binary.Read(r, le, &v)
	case MetadataValueTypeFLOAT64:
		var v float64
		return v, binary.Read(r, le, &v)
	default:
		return nil, fmt.Errorf("unknown metadata value type: %d", vt)
	}
}

func readTensorInfo(r io.Reader, le binary.ByteOrder) (TensorInfo, error) {
	name, err := readString(r, le)
	if err != nil {
		return TensorInfo{}, fmt.Errorf("reading tensor name: %w", err)
	}

	var nDim uint32
	if err := binary.Read(r, le, &nDim); err != nil {
		return TensorInfo{}, fmt.Errorf("reading n_dimensions: %w", err)
	}

	dims := make([]uint64, nDim)
	for i := uint32(0); i < nDim; i++ {
		if err := binary.Read(r, le, &dims[i]); err != nil {
			return TensorInfo{}, fmt.Errorf("reading dimension %d: %w", i, err)
		}
	}

	var ggmlType uint32
	if err := binary.Read(r, le, &ggmlType); err != nil {
		return TensorInfo{}, fmt.Errorf("reading ggml type: %w", err)
	}

	var offset uint64
	if err := binary.Read(r, le, &offset); err != nil {
		return TensorInfo{}, fmt.Errorf("reading offset: %w", err)
	}

	return TensorInfo{
		Name:        name,
		NDimensions: nDim,
		Dimensions:  dims,
		Type:        GGMLType(ggmlType),
		Offset:      offset,
	}, nil
}

// align rounds n up to the next multiple of a.
func align(n, a uint64) uint64 {
	return (n + a - 1) &^ (a - 1)
}
