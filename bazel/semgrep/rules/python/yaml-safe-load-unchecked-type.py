# Tests for yaml-safe-load-unchecked-type rule.
import yaml


# ruleid: yaml-safe-load-unchecked-type
def bad_get_without_check(content: str):
    data = yaml.safe_load(content)
    return data.get("key", "default")  # AttributeError if data is None or a list


# ruleid: yaml-safe-load-unchecked-type
def bad_subscript_without_check(content: str):
    data = yaml.safe_load(content)
    return data["key"]  # TypeError if data is None, AttributeError if list


# ruleid: yaml-safe-load-unchecked-type
def bad_items_without_check(content: str):
    data = yaml.safe_load(content)
    for k, v in data.items():  # AttributeError if data is not a dict
        print(k, v)


# ruleid: yaml-safe-load-unchecked-type
def bad_values_without_check(content: str):
    data = yaml.safe_load(content)
    return list(data.values())  # AttributeError if data is not a dict


# ruleid: yaml-safe-load-unchecked-type
def bad_keys_without_check(content: str):
    data = yaml.safe_load(content)
    return list(data.keys())  # AttributeError if data is not a dict


# ok: isinstance check before dict access
def ok_isinstance_before_get(content: str):
    data = yaml.safe_load(content)
    if not isinstance(data, dict):
        raise ValueError("expected a YAML mapping")
    return data.get("key", "default")


# ok: isinstance guard before subscript
def ok_isinstance_before_subscript(content: str):
    data = yaml.safe_load(content)
    if not isinstance(data, dict):
        raise ValueError("expected a YAML mapping")
    return data["key"]


# ok: access inside isinstance guard
def ok_isinstance_guard_block(content: str):
    data = yaml.safe_load(content)
    if isinstance(data, dict):
        return data.get("key")
    return None
