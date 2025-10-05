import json
import statistics
import os
from typing import List, Dict, Any

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

def handler(request, response):
    """Main Vercel serverless function handler"""
    
    # Set CORS headers
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    
    # Handle CORS preflight
    if request.method == "OPTIONS":
        response.status_code = 200
        return {"message": "CORS preflight handled"}
    
    try:
        if request.method == "GET":
            # Health check endpoint
            response.status_code = 200
            return {"message": "Latency monitoring service is running"}
        
        elif request.method == "POST":
            # Parse request body
            try:
                body = request.json
            except:
                response.status_code = 400
                return {"error": "Invalid JSON in request body"}
            
            # Validate request structure
            if not isinstance(body, dict):
                response.status_code = 400
                return {"error": "Request body must be a JSON object"}
            
            if "regions" not in body or "threshold_ms" not in body:
                response.status_code = 400
                return {"error": "Request must contain 'regions' and 'threshold_ms' fields"}
            
            regions = body["regions"]
            threshold_ms = body["threshold_ms"]
            
            if not isinstance(regions, list) or not isinstance(threshold_ms, (int, float)):
                response.status_code = 400
                return {"error": "Invalid data types for regions or threshold_ms"}
            
            # Load the latency data
            try:
                latency_data = load_latency_data()
            except Exception as e:
                response.status_code = 500
                return {"error": f"Failed to load latency data: {str(e)}"}
            
            # Filter data for requested regions
            filtered_data = [record for record in latency_data 
                           if record["region"] in regions]
            
            if not filtered_data:
                response.status_code = 400
                return {"error": f"No data found for regions: {regions}"}
            
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
                if record["latency_ms"] > threshold_ms:
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
                
                response_regions[region] = {
                    "avg_latency": round(avg_latency, 2),
                    "p95_latency": round(p95_latency, 2),
                    "avg_uptime": round(avg_uptime, 2),
                    "breaches": breaches
                }
            
            response.status_code = 200
            return {"regions": response_regions}
        
        else:
            response.status_code = 405
            return {"error": "Method not allowed"}
            
    except Exception as e:
        response.status_code = 500
        return {"error": f"Internal server error: {str(e)}"}
