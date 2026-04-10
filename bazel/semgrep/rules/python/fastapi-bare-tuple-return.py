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


# ok: using HTTPException raises a proper HTTP response with correct status code
@app.get("/good-404")
async def good_404_route():
    raise HTTPException(status_code=404, detail="Not found")


# ok: 2xx status codes are not error responses and are not caught by this rule
@app.get("/good-200")
async def good_200_route():
    return {"data": "ok"}, 200


# ok: 3xx status codes are redirects and not caught by this rule
@app.get("/good-301")
async def good_301_route():
    return {"location": "/new"}, 301
