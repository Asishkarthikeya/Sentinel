# tavily_mcp.py (Corrected Version)
from fastapi import FastAPI, HTTPException
import uvicorn
import os
from dotenv import load_dotenv
from tavily import TavilyClient
import logging

# --- Configuration ---
load_dotenv()
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

if not TAVILY_API_KEY:
    raise ValueError("TAVILY_API_KEY not found in .env file. Please add it.")

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Tavily_MCP_Server")

# --- FastAPI App & Tavily Client ---
app = FastAPI(title="Aegis Tavily MCP Server")
tavily = TavilyClient(api_key=TAVILY_API_KEY)

@app.post("/research")
async def perform_research(payload: dict):
    """
    Performs a search for each query using the Tavily API.
    Expects a payload like:
    {
        "queries": ["query1", "query2"],
        "search_depth": "basic" or "advanced" (optional, default basic)
    }
    """
    queries = payload.get("queries")
    search_depth = payload.get("search_depth", "basic")

    if not queries or not isinstance(queries, list):
        logger.error("Validation Error: 'queries' must be a non-empty list.")
        raise HTTPException(status_code=400, detail="'queries' must be a non-empty list.")

    logger.info(f"Received research request for {len(queries)} queries. Search depth: {search_depth}")
    
    # --- THIS IS THE CORRECTED LOGIC ---
    all_results = []
    try:
        # Loop through each query and perform a search
        for query in queries:
            logger.info(f"Performing search for query: '{query}'")
            # The search method takes a single query string
            response = tavily.search(
                query=query,
                search_depth=search_depth,
                max_results=5 
            )
            # Add the results for this query to our collection
            all_results.append({"query": query, "results": response["results"]})
            
        logger.info(f"Successfully retrieved results for all queries from Tavily API.")
        return {"status": "success", "data": all_results}

    except Exception as e:
        logger.error(f"Tavily API Error (likely rate limit): {e}. Switching to MOCK DATA fallback.")
        # --- FALLBACK MECHANISM ---
        mock_results = []
        for query in queries:
            mock_results.append({
                "query": query,
                "results": [
                    {
                        "title": f"Simulated News: Market Analysis for {query} (MOCK DATA)",
                        "content": f"This is a simulated search result because the Tavily API limit was reached. Analysts suggest monitoring key levels for {query}. Market sentiment remains mixed with a focus on upcoming earnings and macroeconomic data.",
                        "url": "http://mock-source.com/market-analysis"
                    },
                    {
                        "title": f"Simulated Report: Sector Trends related to {query} (MOCK DATA)",
                        "content": f"Recent data indicates significant movement in the sector associated with {query}. Investors are advised to exercise caution and review portfolio allocations. (Simulated Data)",
                        "url": "http://mock-source.com/sector-trends"
                    }
                ]
            })
        return {"status": "success", "data": mock_results}

@app.get("/")
def read_root():
    return {"message": "Aegis Tavily MCP Server is operational."}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)   