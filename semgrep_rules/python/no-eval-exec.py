import ast
import json

# ruleid: no-eval-exec
eval("1 + 2")

# ruleid: no-eval-exec
eval(user_input)

# ruleid: no-eval-exec
exec("print('hello')")

# ruleid: no-eval-exec
exec(code_string)

# ok: no-eval-exec
ast.literal_eval("{'key': 'value'}")

# ok: no-eval-exec
json.loads('{"key": "value"}')

# ok: no-eval-exec
result = 1 + 2
