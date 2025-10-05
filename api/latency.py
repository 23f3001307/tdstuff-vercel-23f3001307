from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
import statistics
import json
import os

app = FastAPI()

# Enable CORS for POST requests from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["POST"],
    allow_headers=["*"],
)

class LatencyRequest(BaseModel):
    regions: List[str]
    threshold_ms: int

class RegionMetrics(BaseModel):
    avg_latency: float
    p95_latency: float
    avg_uptime: float
    breaches: int

class LatencyResponse(BaseModel):
    regions: Dict[str, RegionMetrics]

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
            raise HTTPException(status_code=500, detail="Latency data file not found")

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

@app.post("/latency", response_model=LatencyResponse)
async def get_latency_metrics(request: LatencyRequest):
    """
    Calculate latency metrics for specified regions
    
    Returns per-region metrics including:
    - avg_latency: mean latency in milliseconds
    - p95_latency: 95th percentile latency
    - avg_uptime: mean uptime percentage
    - breaches: count of records above threshold
    """
    try:
        # Load the latency data
        latency_data = load_latency_data()
        
        # Filter data for requested regions
        filtered_data = [record for record in latency_data 
                        if record["region"] in request.regions]
        
        if not filtered_data:
            raise HTTPException(status_code=400, detail=f"No data found for regions: {request.regions}")
        
        # Group data by region
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
            
            # Count breaches (latency above threshold)
            if record["latency_ms"] > request.threshold_ms:
                region_data[region]["breaches"] += 1
        
        # Calculate metrics for each region
        response_regions = {}
        for region, data in region_data.items():
            if not data["latencies"]:
                continue
                
            avg_latency = statistics.mean(data["latencies"])
            p95_latency = calculate_percentile(data["latencies"], 95)
            avg_uptime = statistics.mean(data["uptimes"])
            breaches = data["breaches"]
            
            response_regions[region] = RegionMetrics(
                avg_latency=round(avg_latency, 2),
                p95_latency=round(p95_latency, 2),
                avg_uptime=round(avg_uptime, 2),
                breaches=breaches
            )
        
        return LatencyResponse(regions=response_regions)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "Latency monitoring service is running"}

# For Vercel deployment
def handler(request, response):
    """Vercel serverless function handler"""
    import asyncio
    from fastapi.responses import JSONResponse
    
    # Handle CORS preflight
    if request.method == "OPTIONS":
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.status_code = 200
        return
    
    # Process the request
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(app(request, response))
        return result
    finally:
        loop.close()
