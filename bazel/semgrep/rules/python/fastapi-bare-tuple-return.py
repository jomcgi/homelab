# Tests for fastapi-bare-tuple-return rule.
from fastapi import FastAPI, HTTPException

app = FastAPI()


# ruleid: fastapi-bare-tuple-return
@app.get("/bad-404")
async def bad_404_route():
    return {"error": "not found"}, 404


# ruleid: fastapi-bare-tuple-return
@app.get("/bad-500")
async def bad_500_route():
    return {"error": "server error"}, 500


# ruleid: fastapi-bare-tuple-return
@app.get("/bad-403")
async def bad_403_route():
    return {"error": "forbidden"}, 403


# ruleid: fastapi-bare-tuple-return
@app.get("/vessels/{mmsi}")
async def get_vessel(mmsi: str):
    return {"error": "Vessel not found"}, 404


# ruleid: fastapi-bare-tuple-return
@app.get("/sync-bad-404")
def sync_bad_404_route():
    # Synchronous handlers are equally affected — FastAPI silently ignores the
    # integer element of the tuple and returns HTTP 200 with a JSON array.
    return {"error": "not found"}, 404


# ok: using HTTPException raises a proper HTTP response with correct status code
@app.get("/good-404")
async def good_404_route():
    raise HTTPException(status_code=404, detail="Not found")


# ok: plain dict return (no status code) — not a bare-tuple pattern
@app.get("/good-plain-dict")
async def good_plain_dict_route():
    return {"data": "value"}


# ok: 2xx and 3xx codes are not matched — note that returning (dict, 200) is
# also a FastAPI anti-pattern (produces a JSON array instead of a plain dict),
# but it is out of scope for this rule which targets error-status misuse
@app.get("/good-200")
async def good_200_route():
    return {"data": "ok"}, 200


# ok: 3xx status codes are redirects and not caught by this rule
@app.get("/good-301")
async def good_301_route():
    return {"location": "/new"}, 301
