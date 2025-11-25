# alphavantage_mcp.py (Corrected for Free Tier)
from fastapi import FastAPI, HTTPException
import uvicorn
import os
from dotenv import load_dotenv
from alpha_vantage.timeseries import TimeSeries
import logging

# --- Configuration ---
load_dotenv()

# --- Logging Setup (MUST be before we use logger) ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AlphaVantage_MCP_Server")

# --- Get API Key ---
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")

if not ALPHA_VANTAGE_API_KEY:
    logger.warning("ALPHA_VANTAGE_API_KEY not found in environment. Market data features will fail.")
else:
    logger.info(f"ALPHA_VANTAGE_API_KEY found: {ALPHA_VANTAGE_API_KEY[:4]}...")

# --- FastAPI App & Alpha Vantage Client ---
app = FastAPI(title="Aegis Alpha Vantage MCP Server")
ts = TimeSeries(key=ALPHA_VANTAGE_API_KEY, output_format='json')

@app.post("/market_data")
async def get_market_data(payload: dict):
    """
    Fetches market data using the Alpha Vantage API.
    We will now use the free INTRADAY endpoint.
    Expects a payload like:
    {
        "symbol": "NVDA",
        "interval": "5min" 
    }
    """
    symbol = payload.get("symbol")
    # --- CHANGE: We now require an interval for the intraday endpoint ---
    interval = payload.get("interval") 

    if not symbol or not interval:
        logger.error("Validation Error: 'symbol' and 'interval' are required fields.")
        raise HTTPException(status_code=400, detail="'symbol' and 'interval' are required fields.")

    logger.info(f"Received market data request for symbol: {symbol} with interval: {interval}")
    logger.info(f"DEBUG: Payload received - symbol='{symbol}', interval='{interval}'")

    try:
        # --- CHANGE: Switched to the free get_intraday function ---
        data, meta_data = ts.get_intraday(symbol=symbol, interval=interval, outputsize='compact')
        logger.info(f"Successfully retrieved intraday data for {symbol}")
        return {"status": "success", "data": data, "meta_data": meta_data}

    except ValueError as ve:
        # The alpha_vantage library often raises a ValueError for API errors like invalid symbols
        logger.error(f"Alpha Vantage API error for symbol {symbol}: {ve}")
        
        # --- MOCK DATA FALLBACK FOR DEMO PURPOSES ---
        if "rate limit" in str(ve).lower():
            logger.warning(f"Rate limit hit for {symbol}. Returning MOCK DATA.")
            import random
            import math
            from datetime import datetime, timedelta
            
            # Seed randomness with symbol to ensure consistent but unique graphs per company
            random.seed(symbol)
            
            mock_data = {}
            current_time = datetime.now()
            
            # Generate a unique base price and trend for each symbol
            base_price = float(ord(symbol[0]) * 2 + ord(symbol[-1])) # e.g., A=65, Z=90 -> ~200-300 range
            
            # Use deterministic hash for trend direction
            symbol_sum = sum(ord(c) for c in symbol)
            trend_direction = 1 if symbol_sum % 2 == 0 else -1
            
            # Force specific trends for demo purposes if needed, or rely on the deterministic hash
            # Let's ensure AMZN is DOWN and GOOGL is UP for testing
            if symbol == "AMZN": trend_direction = -1
            if symbol == "GOOGL": trend_direction = 1
            
            volatility = 1.5
            trend_strength = 0.3 # Increased from 0.1 to make trends obvious
            
            current_price = base_price
            
            for i in range(100):
                # Create a random walk with a stronger trend
                change = random.uniform(-volatility, volatility) + (trend_direction * trend_strength)
                current_price += change
                
                # Add some sine wave seasonality
                seasonality = 5 * math.sin(i / 10.0)
                final_price = current_price + seasonality
                
                t = current_time - timedelta(minutes=5*(99-i)) # Reverse time so loop builds forward
                
                mock_data[t.strftime("%Y-%m-%d %H:%M:%S")] = {
                    "1. open": str(round(final_price, 2)),
                    "2. high": str(round(final_price + volatility, 2)),
                    "3. low": str(round(final_price - volatility, 2)),
                    "4. close": str(round(final_price + random.uniform(-0.5, 0.5), 2)),
                    "5. volume": str(int(random.uniform(100000, 5000000)))
                }
            
            return {"status": "success", "data": mock_data, "meta_data": {"Information": "Mock Data (Rate Limit Hit)"}}
        # --------------------------------------------

        raise HTTPException(status_code=400, detail=f"Invalid symbol or API request: {str(ve)}")

@app.get("/")
def read_root():
    return {"message": "Aegis Alpha Vantage MCP Server is operational."}

# --- Main Execution ---
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8002)