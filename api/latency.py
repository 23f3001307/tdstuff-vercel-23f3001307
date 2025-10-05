import json
import statistics
import os
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel

# Initialize FastAPI app
app = FastAPI()

from starlette.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("CORS middleware added successfully.")

class LatencyRequest(BaseModel):
    regions: List[str]
    threshold_ms: float

class RegionLatencyResponse(BaseModel):
    avg_latency: float
    p95_latency: float
    avg_uptime: float
    breaches: int

class LatencyResponse(BaseModel):
    regions: Dict[str, RegionLatencyResponse]

def load_latency_data():
    """Load latency data from the JSON file"""
    try:
        # Try to load from the same directory as the script
        current_dir = os.path.dirname(os.path.abspath(__file__))
        data_path = os.path.join(current_dir, "..", "latency.json")
        
        with open(data_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        # Fallback: try loading from current directory
        try:
            with open("latency.json", 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            raise Exception("Latency data file not found")

def calculate_percentile(data: List[float], percentile: float) -> float:
    """Calculate the specified percentile of the data"""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    index = (percentile / 100) * (len(sorted_data) - 1)
    if index.is_integer():
        return sorted_data[int(index)]
    else:
        lower = sorted_data[int(index)]
        upper = sorted_data[int(index) + 1]
        return lower + (upper - lower) * (index - int(index))


@app.options("/api/latency")
async def options_handler():
    return {"message": "OK"}

@app.get("/api/latency")
async def health_check():
    return {"message": "Latency monitoring service is running"}

@app.post("/api/latency", response_model=LatencyResponse)
async def process_latency_data(request: LatencyRequest):
    try:
        latency_data = load_latency_data()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load latency data: {str(e)}")

    filtered_data = [record for record in latency_data 
                     if record["region"] in request.regions]

    if not filtered_data:
        raise HTTPException(status_code=400, detail=f"No data found for regions: {request.regions}")

    region_data = {}
    for record in filtered_data:
        region = record["region"]
        if region not in region_data:
            region_data[region] = {
                "latencies": [],
                "uptimes": [],
                "breaches": 0
            }
        
        region_data[region]["latencies"].append(record["latency_ms"])
        region_data[region]["uptimes"].append(record["uptime_pct"])
        
        if record["latency_ms"] > request.threshold_ms:
            region_data[region]["breaches"] += 1

    response_regions = {}
    for region, data in region_data.items():
        if not data["latencies"]:
            continue
            
        avg_latency = statistics.mean(data["latencies"])
        p95_latency = calculate_percentile(data["latencies"], 95)
        avg_uptime = statistics.mean(data["uptimes"])
        breaches = data["breaches"]
        
        response_regions[region] = {
            "avg_latency": round(avg_latency, 2),
            "p95_latency": round(p95_latency, 2),
            "avg_uptime": round(avg_uptime, 2),
            "breaches": breaches
        }
    
    return {"regions": response_regions}
