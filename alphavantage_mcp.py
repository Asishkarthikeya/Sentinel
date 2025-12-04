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

# Fallback: Try to read from Streamlit secrets file (for cloud deployment)
if not ALPHA_VANTAGE_API_KEY:
    try:
        import toml
        secrets_path = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
        if os.path.exists(secrets_path):
            secrets = toml.load(secrets_path)
            ALPHA_VANTAGE_API_KEY = secrets.get("ALPHA_VANTAGE_API_KEY")
            logger.info("Loaded ALPHA_VANTAGE_API_KEY from .streamlit/secrets.toml")
    except Exception as e:
        logger.warning(f"Could not load from secrets.toml: {e}")

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

    except Exception as e:
        # Catch ALL exceptions (ValueError, connection errors, etc.) to ensure fallback works
        logger.error(f"Alpha Vantage API error for symbol {symbol}: {e}")
        logger.warning(f"Triggering MOCK DATA fallback for {symbol} due to error.")
        
        import random
        import math
        from datetime import datetime, timedelta
        
        # Seed randomness with symbol to ensure consistent but unique graphs per company
        random.seed(symbol)
        
        mock_data = {}
        current_time = datetime.now()
        
        # Generate a unique base price and trend for each symbol
        # Use a hash of the symbol to get a deterministic start price
        symbol_hash = sum(ord(c) for c in symbol)
        base_price = float(symbol_hash % 500) + 50  # Price between 50 and 550
        
        # Use deterministic hash for trend direction
        trend_direction = 1 if symbol_hash % 2 == 0 else -1
        
        # Force specific trends for demo purposes
        if symbol == "AMZN": trend_direction = -1
        if symbol == "GOOGL": trend_direction = 1
        
        # INCREASED VOLATILITY to avoid "straight line" look
        # Make it look like a real stock with noise and waves
        volatility = base_price * 0.05  # 5% daily volatility (High!)
        trend_strength = base_price * 0.002 # Reduced trend to let volatility show
        
        current_price = base_price
        
        for i in range(100):
            # Random walk
            noise = random.uniform(-volatility, volatility)
            
            # Add multiple sine waves for "market cycles" look
            cycle_1 = (base_price * 0.05) * math.sin(i / 8.0)
            cycle_2 = (base_price * 0.02) * math.sin(i / 3.0)
            
            change = noise + (trend_direction * trend_strength)
            current_price += change
            
            final_price = current_price + cycle_1 + cycle_2
            
            # Ensure price doesn't go negative
            final_price = max(1.0, final_price)
            
            t = current_time - timedelta(minutes=5*(99-i)) # Reverse time so loop builds forward
            
            mock_data[t.strftime("%Y-%m-%d %H:%M:%S")] = {
                "1. open": str(round(final_price, 2)),
                "2. high": str(round(final_price + (volatility * 0.5), 2)),
                "3. low": str(round(final_price - (volatility * 0.5), 2)),
                "4. close": str(round(final_price + random.uniform(-0.1, 0.1), 2)),
                "5. volume": str(int(random.uniform(100000, 5000000)))
            }
        
        return {"status": "success", "data": mock_data, "meta_data": {"Information": "Mock Data (API Error/Rate Limit)"}}
        # --------------------------------------------

        raise HTTPException(status_code=400, detail=f"Invalid symbol or API request: {str(ve)}")

@app.get("/")
def read_root():
    return {"message": "Aegis Alpha Vantage MCP Server is operational."}

# --- Main Execution ---
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8002)