package tests

import "encoding/json"

type Payload struct {
	Name string `json:"name"`
}

// ruleid: no-discarded-json-marshal
func badShortDecl(p Payload) []byte {
	data, _ := json.Marshal(p)
	return data
}

// ruleid: no-discarded-json-marshal
func badAssign(p Payload) []byte {
	var data []byte
	data, _ = json.Marshal(p)
	return data
}

// ok: error is properly checked
func goodCheckErr(p Payload) ([]byte, error) {
	data, err := json.Marshal(p)
	if err != nil {
		return nil, err
	}
	return data, nil
}

// ok: both return values captured and error returned
func goodBothValues(p Payload) ([]byte, error) {
	return json.Marshal(p)
}
