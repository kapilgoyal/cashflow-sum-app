from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SumRequest(BaseModel):
    a: float
    b: float


@app.get("/api/sum")
def sum_get(a: float, b: float):
    return {"sum": a + b}


@app.post("/api/sum")
def sum_post(body: SumRequest):
    return {"sum": body.a + body.b}
