# monitor.py
import time
import json
import os
import sys
import logging
from datetime import datetime
from agents.tool_calling_agents import MarketDataAgent, WebResearchAgent

# --- Configuration ---
WATCHLIST_FILE = "watchlist.json"
ALERTS_FILE = "alerts.json"
CHECK_INTERVAL = 10  # 10 seconds (Real-time feel)
PRICE_ALERT_THRESHOLD = 0.5  # More sensitive alerts

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("Aegis_Monitor")

# --- Initialize Agents ---
market_agent = MarketDataAgent()
web_agent = WebResearchAgent()

def load_watchlist():
    if not os.path.exists(WATCHLIST_FILE):
        return []
    try:
        with open(WATCHLIST_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading watchlist: {e}")
        return []

def save_alert(alert):
    alerts = []
    if os.path.exists(ALERTS_FILE):
        try:
            with open(ALERTS_FILE, 'r') as f:
                alerts = json.load(f)
        except:
            pass
    
    # Prepend new alert
    alerts.insert(0, alert)
    # Keep only last 100 alerts (increased from 50)
    alerts = alerts[:100]
    
    with open(ALERTS_FILE, 'w') as f:
        json.dump(alerts, f, indent=2)

def check_market_data(symbol):
    try:
        logger.info(f"Checking market data for {symbol}...")
        # Get compact intraday data (Corrected method call)
        result = market_agent.get_market_data(symbol=symbol, time_range="INTRADAY")
        
        if result.get("status") != "success":
            logger.warning(f"Failed to get market data for {symbol}")
            return None

        data = result.get("data", {})
        if not data:
            return None

        # Get latest and 15-minute-ago data points to calculate change
        timestamps = sorted(list(data.keys()), reverse=True)
        if len(timestamps) < 4:  # Need at least 4 points (15 mins = 3 intervals)
            return None
            
        latest = data[timestamps[0]]
        baseline = data[timestamps[min(3, len(timestamps)-1)]]  # 15 mins ago
        
        close_latest = float(latest.get("4. close", 0))
        close_baseline = float(baseline.get("4. close", 0))
        
        if close_baseline == 0:
            return None
            
        pct_change = ((close_latest - close_baseline) / close_baseline) * 100
        
        return {
            "price": close_latest,
            "change": pct_change,
            "timestamp": timestamps[0]
        }
    except Exception as e:
        logger.error(f"Error checking market data for {symbol}: {e}")
        return None

def check_news(symbol):
    try:
        logger.info(f"Checking news for {symbol}...")
        query = f"breaking news {symbol} stock today"
        result = web_agent.research(queries=[query], search_depth="basic")
        
        if result.get("status") != "success":
            return None
            
        # Just return the first result title for now as a "headline"
        data = result.get("data", [])
        if data and data[0].get("results"):
            first_hit = data[0]["results"][0]
            return {
                "title": first_hit.get("title"),
                "url": first_hit.get("url"),
                "content": first_hit.get("content")[:200] + "..."
            }
        return None
    except Exception as e:
        logger.error(f"Error checking news for {symbol}: {e}")
        return None

def run_monitor_loop():
    logger.info("--- 🛡️ Aegis Proactive Monitor Started ---")
    logger.info(f"Monitoring watchlist every {CHECK_INTERVAL} seconds ({CHECK_INTERVAL/60:.0f} minutes).")
    logger.info(f"Price alert threshold: {PRICE_ALERT_THRESHOLD}%")
    
    while True:
        watchlist = load_watchlist()
        if not watchlist:
            logger.info("Watchlist is empty. Waiting...")
        
        for symbol in watchlist:
            try:
                # 1. Market Check
                market_info = check_market_data(symbol)
                if market_info:
                    # Alert Logic: Price moved more than threshold
                    if abs(market_info['change']) > PRICE_ALERT_THRESHOLD:
                        direction = "📈 UP" if market_info['change'] > 0 else "📉 DOWN"
                        alert_msg = f"{direction} ALERT: {symbol} moved {market_info['change']:+.2f}% to ${market_info['price']:.2f}"
                        logger.info(alert_msg)
                        
                        save_alert({
                            "timestamp": datetime.now().isoformat(),
                            "type": "MARKET",
                            "symbol": symbol,
                            "message": alert_msg,
                            "details": market_info
                        })

                # 2. News Check (Simplified: Just log latest headline)
                news_info = check_news(symbol)
                if news_info:
                    # Check if this is "significant" news based on keywords
                    keywords = [
                        "acquisition", "merger", "earnings", "crash", "surge", "plunge",
                        "fda", "lawsuit", "sec", "filing", "8-k", "10-k", "insider",
                        "partnership", "deal", "bankruptcy", "recall", "investigation",
                        "upgrade", "downgrade", "target", "buyback", "dividend"
                    ]
                    if any(k in news_info['title'].lower() for k in keywords):
                        alert_msg = f"📰 NEWS ALERT: {symbol} - {news_info['title']}"
                        logger.info(alert_msg)
                        
                        save_alert({
                            "timestamp": datetime.now().isoformat(),
                            "type": "NEWS",
                            "symbol": symbol,
                            "message": alert_msg,
                            "details": news_info
                        })
                        
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
                
        logger.info(f"Cycle complete. Sleeping for {CHECK_INTERVAL}s...")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    # Ensure we can import agents
    sys.path.append(os.path.abspath(os.path.dirname(__file__)))
    run_monitor_loop()
