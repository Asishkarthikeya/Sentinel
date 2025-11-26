import os
import sys
import pandas as pd
import ast
from dotenv import load_dotenv
from typing import TypedDict, List, Dict, Any

from langgraph.graph import StateGraph, END

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.tool_calling_agents import WebResearchAgent, MarketDataAgent, InternalPortfolioAgent
from agents.data_analysis_agent import DataAnalysisAgent

from langchain_google_genai import ChatGoogleGenerativeAI

# --- Configuration ---
load_dotenv()

# --- Initialize workers (Stateless) ---
web_agent = WebResearchAgent()
market_agent = MarketDataAgent()
portfolio_agent = InternalPortfolioAgent()

# --- Define the Enhanced State ---
class AgentState(TypedDict):
    task: str
    symbol: str
    web_research_results: str
    market_data_results: str
    portfolio_data_results: str
    scan_intent: str # "DOWNWARD", "UPWARD", "ALL", or None
    # --- NEW FIELDS FOR ANALYSIS ---
    analysis_dataframe: pd.DataFrame
    analysis_results: Dict[str, Any]
    final_report: str
    # Debug fields
    debug_market_data_raw: Any
    debug_dataframe_head: Any
    debug_analysis_results_full: Any

def get_orchestrator(llm_provider="gemini", api_key=None):
    """
    Factory function to create the orchestrator graph with a specific LLM.
    """
    
    # 1. Initialize LLM (Gemini Only)
    if not api_key:
        api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("Google Gemini API Key is missing.")
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=api_key, temperature=0)

    # 2. Initialize Data Analyzer with the chosen LLM
    data_analyzer = DataAnalysisAgent(llm=llm)

    # 3. Define Nodes (Closure captures 'llm' and 'data_analyzer')

    # 3. Define Nodes (Closure captures 'llm' and 'data_analyzer')

    def extract_symbol_step(state: AgentState):
        print("--- 🔬 Symbol Extraction ---")
        prompt = f"""
        Analyze the user's request: "{state['task']}"
        
        1. If the user wants to analyze a specific stock, extract the ticker symbol (e.g., AAPL).
        2. If the user wants to SCAN the market for companies matching a criteria (e.g., "companies that are downward", "top gainers", "market scan"), output 'SCAN: <CRITERIA>' (e.g., SCAN: DOWNWARD, SCAN: UPWARD, SCAN: ALL).
        
        Respond with ONLY the symbol or the SCAN command. If nothing matches, respond 'NONE'.
        """
        raw_response = llm.invoke(prompt).content.strip()
        
        symbol = None
        scan_intent = None
        
        if "SCAN:" in raw_response.upper():
            scan_intent = raw_response.upper().split("SCAN:")[1].strip()
        else:
            # Clean up the response
            import re
            # Look for a sequence of 1-5 uppercase letters, possibly starting with $
            match = re.search(r'\$?[A-Z]{1,5}', raw_response.upper())
            if match and "NONE" not in raw_response.upper():
                symbol = match.group(0).lstrip('$')
        
        print(f"   Raw LLM Response: {raw_response}")
        print(f"   Extracted Symbol: {symbol}")
        print(f"   Scan Intent: {scan_intent}")
        
        # Store scan intent in state (needs to be added to AgentState definition if strict typing is enforced, but TypedDict allows extras at runtime usually, or we can overload 'symbol')
        # Better to overload 'symbol' or add a new key. Let's add 'scan_intent' to the return dict.
        return {"symbol": symbol, "scan_intent": scan_intent}

    def web_research_step(state: AgentState):
        print("--- 🔎 Web Research ---")
        if state.get("scan_intent"):
            return {"web_research_results": "Market Scan initiated. Web research skipped for individual stock."}
        results = web_agent.research(queries=[state['task']])
        return {"web_research_results": results}

    def market_data_step(state: AgentState):
        print("--- 📈 Market Data ---")
        scan_intent = state.get("scan_intent")
        
        if scan_intent:
            print(f"   Executing Market Scan: {scan_intent}")
            import json
            watchlist_path = "watchlist.json"
            if not os.path.exists(watchlist_path):
                return {"market_data_results": "Watchlist not found."}
            
            try:
                with open(watchlist_path, 'r') as f:
                    watchlist = json.load(f)
                
                scan_results = []
                for sym in watchlist:
                    # Get compact data for speed
                    data = market_agent.get_intraday_data(symbol=sym)
                    if isinstance(data, dict) and 'data' in data:
                        ts = data['data']
                        # Calculate simple change (latest close - first open of the retrieved window)
                        # Note: This is a rough approximation using the available 100 points
                        sorted_times = sorted(ts.keys())
                        if len(sorted_times) > 0:
                            latest_time = sorted_times[-1]
                            earliest_time = sorted_times[0]
                            latest_close = float(ts[latest_time]['4. close'])
                            earliest_open = float(ts[earliest_time]['1. open'])
                            pct_change = ((latest_close - earliest_open) / earliest_open) * 100
                            
                            print(f"   DEBUG: {sym} -> Change: {pct_change:.2f}% (Intent: {scan_intent})")
                            
                            # Filter based on intent
                            if scan_intent == "DOWNWARD" and pct_change < 0:
                                scan_results.append({'symbol': sym, 'price': latest_close, 'change': pct_change})
                            elif scan_intent == "UPWARD" and pct_change > 0:
                                scan_results.append({'symbol': sym, 'price': latest_close, 'change': pct_change})
                            elif scan_intent == "ALL":
                                scan_results.append({'symbol': sym, 'price': latest_close, 'change': pct_change})
                
                return {"market_data_results": {"scan_results": scan_results}}
            except Exception as e:
                print(f"   Error during scan: {e}")
                return {"market_data_results": "Error executing scan."}

        if not state.get("symbol"):
            return {"market_data_results": "Skipped."}
        results = market_agent.get_intraday_data(symbol=state["symbol"])
        return {"market_data_results": results, "debug_market_data_raw": results}

    def portfolio_data_step(state: AgentState):
        print("--- 💼 Internal Portfolio Data ---")
        if state.get("scan_intent"):
             return {"portfolio_data_results": "Market Scan initiated. Portfolio context skipped."}
             
        if not state.get("symbol"):
            return {"portfolio_data_results": "Skipped: No symbol provided."}
        
        results = portfolio_agent.query_portfolio(question=f"What is the current exposure to {state['symbol']}?")
        return {"portfolio_data_results": results}

    def transform_data_step(state: AgentState):
        print("--- 🔀 Transforming Data for Analysis ---")
        if state.get("scan_intent"):
            return {"analysis_dataframe": pd.DataFrame()} # Skip transformation for scan
            
        market_data = state.get("market_data_results")
        
        if not isinstance(market_data, dict) or not market_data.get('data'):
            print("   Skipping transformation: No valid market data received.")
            return {"analysis_dataframe": pd.DataFrame()}
            
        try:
            time_series_data = market_data.get('data')
            if not time_series_data:
                raise ValueError("The 'data' key is empty.")

            df = pd.DataFrame.from_dict(time_series_data, orient='index')
            df.index = pd.to_datetime(df.index)
            df.index.name = "timestamp"
            df.rename(columns={
                '1. open': 'open', '2. high': 'high', '3. low': 'low',
                '4. close': 'close', '5. volume': 'volume'
            }, inplace=True)
            df = df.apply(pd.to_numeric).sort_index()
            
            print(f"   Successfully created DataFrame with shape {df.shape}")
            return {"analysis_dataframe": df, "debug_dataframe_head": df.head().to_dict()}
        except Exception as e:
            print(f"   CRITICAL ERROR during data transformation: {e}")
            return {"analysis_dataframe": pd.DataFrame()}

    def run_data_analysis_step(state: AgentState):
        print("--- 🔬 Running Deep-Dive Data Analysis ---")
        if state.get("scan_intent"):
            return {"analysis_results": {}} # Skip analysis for scan
            
        df = state.get("analysis_dataframe")
        if df is not None and not df.empty:
            analysis_results = data_analyzer.run_analysis(df)
            return {"analysis_results": analysis_results, "debug_analysis_results_full": analysis_results}
        else:
            print("   Skipping analysis: No data to analyze.")
            return {"analysis_results": {}}

    def synthesize_report_step(state: AgentState):
        print("--- 📝 Synthesizing Final Report ---")
        
        # Helper to truncate text to avoid Rate Limits
        def truncate(text, max_chars=3000):
            s = str(text)
            if len(s) > max_chars:
                return s[:max_chars] + "... (truncated)"
            return s

        # Check for Scan Results
        market_data_res = state.get("market_data_results", {})
        if isinstance(market_data_res, dict) and "scan_results" in market_data_res:
            scan_results = market_data_res["scan_results"]
            # Truncate scan results if necessary (though usually small)
            scan_results_str = truncate(scan_results, 4000)
            
            report_prompt = f"""
            You are a senior financial analyst. The user requested a market scan: "{state['task']}".
            
            Scan Results (from Watchlist):
            {scan_results_str}
            
            Generate a "Market Scan Report".
            1. Summary: Briefly explain the criteria and the overall market status based on these results.
            2. Results Table: Create a markdown table with columns: Symbol | Price | % Change.
            3. Conclusion: Highlight the most significant movers.
            """
            final_report = llm.invoke(report_prompt).content
            return {"final_report": final_report}

        analysis_insights = state.get("analysis_results", {}).get("insights", "Not available.")
        
        # Truncate inputs for the main report
        web_data = truncate(state.get('web_research_results', 'Not available.'), 3000)
        market_summary = truncate(state.get('market_data_results', 'Not available'), 2000)
        portfolio_data = truncate(state.get('portfolio_data_results', 'Not available.'), 2000)
        
        report_prompt = f"""
        You are a senior financial analyst writing a comprehensive "Alpha Report".
        Your task is to synthesize all available information into a structured report.

        Original User Task: {state['task']}
        Target Symbol: {state.get('symbol', 'Unknown')}
        ---
        Available Information:
        - Web Intelligence: {web_data}
        - Market Data Summary: {market_summary}
        - Deep-Dive Data Analysis Insights: {analysis_insights}
        - Internal Portfolio Context: {portfolio_data}
        ---

        CRITICAL INSTRUCTION:
        First, evaluate the "Available Information".
        - If the Target Symbol is 'Unknown' OR if the Web Intelligence and Market Data contain no meaningful information about the company:
          You MUST respond with: "I am not sure about this company as I could not find sufficient data."
          Do NOT generate the rest of the report.

        Otherwise, generate the "Alpha Report" with the following sections. Ensure the report is concise, cited, and directly addresses the user's task.

        1. Summary: A brief overview of the key findings and current situation.
        2. Internal Context: Detail the firm's current exposure. 
           - IF the firm has shares > 0: Present the data in a markdown table (Symbol | Shares | Average Cost).
           - IF the firm has 0 shares: State clearly in text that there is no exposure (e.g. "The firm has no current exposure to [Symbol]."). CRITICAL: DO NOT create a markdown table if shares are 0.
        3. Market Data: Summarize key market data points. ALWAYS present this section as a markdown table (Metric | Value | Implication).
        4. Real-Time Intelligence:
            - News: Highlight significant news (Source...)
            - Filing: Mention any relevant filings (Source...)
        5. Sentiment Analysis: Categorize the overall sentiment as "Positive", "Negative", or "Neutral" and provide a brief explanation.
        6. Synthesis: Combine all information to provide actionable insights or conclusions.
        """
        final_report = llm.invoke(report_prompt).content
        return {"final_report": final_report}

    # 4. Build the Graph
    workflow = StateGraph(AgentState)

    workflow.add_node("extract_symbol", extract_symbol_step)
    workflow.add_node("web_researcher", web_research_step)
    workflow.add_node("market_data_analyst", market_data_step)
    workflow.add_node("portfolio_data_fetcher", portfolio_data_step)
    workflow.add_node("transform_data", transform_data_step)
    workflow.add_node("data_analyzer", run_data_analysis_step)
    workflow.add_node("report_synthesizer", synthesize_report_step)

    workflow.set_entry_point("extract_symbol")
    workflow.add_edge("extract_symbol", "web_researcher")
    workflow.add_edge("web_researcher", "market_data_analyst")
    workflow.add_edge("market_data_analyst", "portfolio_data_fetcher")
    workflow.add_edge("portfolio_data_fetcher", "transform_data")
    workflow.add_edge("transform_data", "data_analyzer")
    workflow.add_edge("data_analyzer", "report_synthesizer")
    workflow.add_edge("report_synthesizer", END)

    return workflow.compile()