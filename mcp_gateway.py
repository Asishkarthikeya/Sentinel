# mcp_gateway.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn
import httpx
import logging
import os
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
TAVILY_MCP_URL = os.getenv("TAVILY_MCP_URL", "http://127.0.0.1:8001/research")
ALPHAVANTAGE_MCP_URL = os.getenv("ALPHAVANTAGE_MCP_URL", "http://127.0.0.1:8002/market_data")
PRIVATE_MCP_URL = os.getenv("PRIVATE_MCP_URL", "http://127.0.0.1:8003/portfolio_data")

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MCP_Gateway")

# --- FastAPI App ---
app = FastAPI(title="Aegis MCP Gateway")
client = httpx.AsyncClient()

@app.middleware("http")
async def audit_log_middleware(request: Request, call_next):
    logger.info(f"Request received: {request.method} {request.url} from {request.client.host}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response

@app.post("/route_agent_request")
async def route_agent_request(request_data: dict):
    target_service = request_data.get("target_service")
    payload = request_data.get("payload", {})
    
    logger.info(f"Routing request for target service: {target_service}")

    url_map = {
        "tavily_research": TAVILY_MCP_URL,
        "alpha_vantage_market_data": ALPHAVANTAGE_MCP_URL,
        "internal_portfolio_data": PRIVATE_MCP_URL,
    }

    target_url = url_map.get(target_service)

    if not target_url:
        logger.error(f"Invalid target service specified: {target_service}")
        raise HTTPException(status_code=400, detail=f"Invalid target service: {target_service}")

    try:
        response = await client.post(target_url, json=payload, timeout=180.0)
        response.raise_for_status()
        return JSONResponse(content=response.json(), status_code=response.status_code)

    except httpx.HTTPStatusError as e:
        logger.error(f"Error from microservice {target_service}: {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=e.response.json())
    except httpx.RequestError as e:
        logger.error(f"Could not connect to microservice {target_service}: {e}")
        raise HTTPException(status_code=503, detail=f"Service '{target_service}' is unavailable.")
    except Exception as e:
        logger.critical(f"An unexpected error occurred during routing: {e}")
        raise HTTPException(status_code=500, detail="Internal server error in MCP Gateway.")

@app.get("/")
def read_root():
    return {"message": "Aegis MCP Gateway is operational."}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
    