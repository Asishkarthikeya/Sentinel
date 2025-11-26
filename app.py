import streamlit as st
import sys
import os
import httpx
import pandas as pd
import json
import time
from datetime import datetime

# --- Path Setup ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))
# from agents.orchestrator_v3 import SentinelOrchestratorV3 # Removed in favor of dynamic import

# --- Configuration ---
WATCHLIST_FILE = "watchlist.json"
ALERTS_FILE = "alerts.json"

# --- Page Configuration ---
st.set_page_config(
    page_title="Sentinel",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom CSS (Premium Financial Terminal) ---
def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

load_css("style.css")

# --- Auto-Start Backend Services (For Streamlit Cloud) ---
import subprocess

@st.cache_resource
def start_background_services():
    """Checks if backend services are running and starts them if needed."""
    # Try to connect to the Gateway
    try:
        with httpx.Client(timeout=1.0) as client:
            response = client.get("http://127.0.0.1:8000/")
            if response.status_code == 200:
                print("✅ Gateway is already running. Skipping startup.")
                return
    except:
        print("⚠️ Gateway not found. Starting backend services...")

    # Define services to start
    services = [
        ["mcp_gateway.py", "8000"],
        ["tavily_mcp.py", "8001"],
        ["alphavantage_mcp.py", "8002"],
        ["private_mcp.py", "8003"]
    ]

    # Create logs directory if it doesn't exist
    if not os.path.exists("logs"):
        os.makedirs("logs")

    # Prepare environment variables
    # Streamlit Cloud stores secrets in st.secrets, which might not be fully propagated to os.environ for subprocesses
    env = os.environ.copy()
    try:
        # Flatten st.secrets into env vars
        def flatten_secrets(secrets, prefix=""):
            for key, value in secrets.items():
                if isinstance(value, dict):
                    flatten_secrets(value, f"{prefix}{key}_")
                else:
                    env[f"{prefix}{key}"] = str(value)
        
        if hasattr(st, "secrets"):
            flatten_secrets(st.secrets)
            print("✅ Injected st.secrets into subprocess environment.")
    except Exception as e:
        print(f"⚠️ Failed to process st.secrets: {e}")

    for script, port in services:
        print(f"🚀 Starting {script} on port {port}...")
        log_file = open(f"logs/{script.replace('.py', '.log')}", "w")
        # Use sys.executable to ensure we use the same Python environment
        subprocess.Popen(
            [sys.executable, script],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stdout=log_file, 
            stderr=subprocess.STDOUT, # Capture stderr in the same file
            env=env # Explicitly pass the environment with secrets
        )
    
    # Start Monitor separately
    print("🚀 Starting Monitor...")
    monitor_log = open("logs/monitor.log", "w")
    subprocess.Popen(
        [sys.executable, "monitor.py"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stdout=monitor_log,
        stderr=subprocess.STDOUT
    )

    # Wait a moment for services to initialize
    time.sleep(10)

# Initialize services once
start_background_services()


# --- Helper Functions ---
@st.cache_data(ttl=60)
def check_server_status():
    urls = {"Gateway": "http://127.0.0.1:8000/", "Tavily": "http://127.0.0.1:8001/", "Alpha Vantage": "http://127.0.0.1:8002/", "Private DB": "http://127.0.0.1:8003/"}
    statuses = {}
    with httpx.Client(timeout=2.0) as client:
        for name, url in urls.items():
            try:
                response = client.get(url)
                statuses[name] = "✅ Online" if response.status_code == 200 else "⚠️ Error"
            except: statuses[name] = "❌ Offline"
    return statuses

def load_watchlist():
    if not os.path.exists(WATCHLIST_FILE): return []
    try:
        with open(WATCHLIST_FILE, 'r') as f: return json.load(f)
    except: return []

def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, 'w') as f: json.dump(watchlist, f)

def load_alerts():
    if not os.path.exists(ALERTS_FILE): return []
    try:
        with open(ALERTS_FILE, 'r') as f: return json.load(f)
    except: return []

# --- Session State ---
if 'analysis_complete' not in st.session_state:
    st.session_state.analysis_complete = False
if 'final_state' not in st.session_state:
    st.session_state.final_state = None
if 'error_message' not in st.session_state:
    st.session_state.error_message = None

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("### 📡 System Status")
    server_statuses = check_server_status()
    all_online = all(s == "✅ Online" for s in server_statuses.values())
    
    for name, status in server_statuses.items():
        dot_class = "status-ok" if status == "✅ Online" else "status-err"
        st.markdown(f"""
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; padding: 8px; background: #15191e; border-radius: 4px;">
            <span style="font-size: 0.9rem;">{name}</span>
            <div><span class="status-dot {dot_class}"></span><span style="font-size: 0.8rem; color: #94a3b8;">{status.split(' ')[1]}</span></div>
        </div>
        """, unsafe_allow_html=True)
        
        # Auto-Show Logs if Offline
        if status == "⚠️ Error" or status == "❌ Offline":
            log_map = {
                "Gateway": "mcp_gateway.log",
                "Tavily": "tavily_mcp.log",
                "Alpha Vantage": "alphavantage_mcp.log",
                "Private DB": "private_mcp.log"
            }
            log_file = log_map.get(name)
            if log_file and os.path.exists(f"logs/{log_file}"):
                with st.expander(f"⚠️ {name} Logs", expanded=False):
                    try:
                        with open(f"logs/{log_file}", "r") as f:
                            st.code("".join(f.readlines()[-20:]), language="text")
                    except Exception as e:
                        st.caption(f"Could not read logs: {e}")

    st.markdown("---")
    
    # Watchlist Manager
    st.markdown("### 🛡️ Watchlist")
    watchlist = load_watchlist()
    
    # Display Watchlist Items
    if watchlist:
        for symbol in watchlist:
            st.markdown(f"""
            <div style="display: flex; justify-content: space-between; padding: 8px; border-bottom: 1px solid #2d3748;">
                <span style="font-family: 'JetBrains Mono'; font-weight: bold; color: #3b82f6;">{symbol}</span>
                <span style="font-size: 0.8rem; color: #10b981;">Active</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("Watchlist empty.")

    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("Manage Watchlist"):
        new_symbol = st.text_input("Add Symbol:", placeholder="e.g. MSFT").upper()
        if st.button("Add Asset"):
            if new_symbol and new_symbol not in watchlist:
                watchlist.append(new_symbol)
                save_watchlist(watchlist)
                st.rerun()

        symbol_to_remove = st.selectbox("Remove Symbol:", ["Select..."] + watchlist)
        if symbol_to_remove != "Select..." and st.button("Remove Asset"):
            watchlist.remove(symbol_to_remove)
            save_watchlist(watchlist)
            st.rerun()

    st.markdown("---")
    st.markdown("### 🧠 Model Configuration")

    # Defaulting to Google Gemini as requested
    llm_provider = "Google Gemini"
    provider_code = "gemini"
    
    api_key_input = st.text_input("Gemini API Key (Optional if in .env):", type="password")

    st.markdown("---")
    with st.expander("🛠️ Admin Dashboard (Logs)"):
        log_file = st.selectbox("Select Log File:", ["mcp_gateway.log", "tavily_mcp.log", "alphavantage_mcp.log", "private_mcp.log", "monitor.log", "streamlit.log"])
        if st.button("Refresh Logs"):
            if os.path.exists(log_file):
                with open(log_file, "r") as f:
                    lines = f.readlines()
                    st.code("".join(lines[-50:]), language="text")
            else:
                st.warning("Log file not found.")

# --- MAIN LAYOUT ---

# Header
st.markdown("""
<div class="main-header">
    <div class="logo-container">
        <div class="cube">
            <div class="face front">🛡️</div>
            <div class="face back">⚡</div>
            <div class="face right">S</div>
            <div class="face left">AI</div>
            <div class="face top"></div>
            <div class="face bottom"></div>
        </div>
    </div>
    <span class="header-title">SENTINEL</span>
</div>
""", unsafe_allow_html=True)

# --- Error Display ---
if st.session_state.error_message:
    st.error(st.session_state.error_message)
    if st.button("Dismiss Error"):
        st.session_state.error_message = None
        st.rerun()

col_main, col_alerts = st.columns([3, 1.2])

with col_main:
    st.markdown("### ⚡ Intelligence Directive")
    with st.form("research_form", clear_on_submit=False):
        task_input = st.text_area("Enter directive:", placeholder="e.g., Analyze the recent volatility for Tesla ($TSLA) and summarize news.", height=100)
        submitted = st.form_submit_button("EXECUTE ANALYSIS", use_container_width=True)

    if submitted and task_input:
        st.session_state.error_message = None # Clear previous errors
        if not all_online:
            st.error("SYSTEM HALTED: Core services offline.")
        else:
            with st.status("🚀 SENTINEL ORCHESTRATOR ENGAGED...", expanded=True) as status:
                try:
                    # Initialize Orchestrator with selected provider
                    from agents.orchestrator_v3 import get_orchestrator
                    orchestrator = get_orchestrator(llm_provider=provider_code, api_key=api_key_input if api_key_input else None)
                    
                    final_state_result = {}
                    for event in orchestrator.stream({"task": task_input}):
                        agent_name = list(event.keys())[0]
                        state_update = list(event.values())[0]
                        final_state_result.update(state_update)
                        
                        # Log the agent activity
                        if agent_name == "extract_symbol":
                            status.write("🔍 Extracting Symbol...")
                        elif agent_name == "web_researcher":
                            status.write("🌐 Gathering Web Intelligence...")
                        elif agent_name == "market_data_analyst":
                            status.write("📈 Querying Market Data...")
                        elif agent_name == "portfolio_data_fetcher":
                            status.write("💼 Analyzing Internal Portfolio...")
                        elif agent_name == "transform_data":
                            status.write("🔄 Processing Data...")
                        elif agent_name == "data_analyzer":
                            status.write("🧠 Running Deep-Dive Analysis...")
                        elif agent_name == "report_synthesizer":
                            status.write("📝 Synthesizing Final Report...")
                        
                    status.update(label="✅ Analysis Complete!", state="complete", expanded=False)
                    st.session_state.final_state = final_state_result
                    st.session_state.analysis_complete = True
                    st.rerun()
                except Exception as e:
                    status.update(label="❌ System Failure", state="error")
                    st.session_state.error_message = f"RUNTIME ERROR: {e}"
                    # import traceback
                    # st.code(traceback.format_exc())
                    st.rerun()

    if st.session_state.analysis_complete:
        final_state = st.session_state.final_state
        symbol = "N/A"
        if final_state and isinstance(final_state, dict):
            symbol = final_state.get('symbol', 'N/A')
            if symbol:
                symbol = str(symbol).upper()
            else:
                symbol = "N/A"
        
        st.markdown(f"""
        <div style="margin-top: 2rem; margin-bottom: 1rem; display: flex; align-items: baseline; gap: 1rem;">
            <h2 style="margin: 0;">REPORT: {symbol}</h2>
            <span style="color: #94a3b8; font-family: 'JetBrains Mono';">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span>
        </div>
        """, unsafe_allow_html=True)
        
        # Executive Summary
        with st.container():
            st.markdown("#### 📝 Executive Summary")
            st.info(final_state.get("final_report", "No report generated."))
        
        # Deep-Dive Insights
        with st.expander("🔍 Deep-Dive Insights", expanded=True):
            insights = final_state.get("analysis_results", {}).get("insights")
            if insights:
                st.markdown(insights)
            else:
                st.warning("No deep-dive insights available.")
        
        # Charts
        with st.expander("📊 Market Telemetry"):
            charts = final_state.get("analysis_results", {}).get("charts", [])
            if charts:
                for chart in charts:
                    st.plotly_chart(chart, use_container_width=True)
            else:
                st.caption("No telemetry data available.")
        
        # Raw Data
        with st.expander("💾 Raw Intelligence Logs"):
            tab1, tab2, tab3 = st.tabs(["Web Intelligence", "Market Data", "Internal Portfolio"])
            with tab1: st.json(final_state.get('web_research_results', '{}'))
            with tab2: st.json(final_state.get('market_data_results', '{}'))
            with tab3: st.json(final_state.get('portfolio_data_results', '{}'))

        if st.button("🔄 Reset Terminal", use_container_width=True):
            st.session_state.analysis_complete = False
            st.session_state.final_state = None
            st.rerun()

# --- LIVE ALERTS FEED ---
with col_alerts:
    st.markdown("### 🚨 Live Wire")
    
    alerts_container = st.container(height=700)
    
    # Auto-refresh logic
    if 'last_refresh' not in st.session_state:
        st.session_state.last_refresh = time.time()

    if time.time() - st.session_state.last_refresh > 10:
        st.session_state.last_refresh = time.time()
        st.rerun()

    alerts = load_alerts()
    if not alerts:
        alerts_container.caption("No active alerts in feed.")
    else:
        # Show latest first
        for alert in reversed(alerts[-20:]):
            alert_type = alert.get("type", "INFO")
            css_class = "alert-market" if alert_type == "MARKET" else "alert-news" if alert_type == "NEWS" else ""
            icon = "📉" if alert_type == "MARKET" else "📰"
            
            timestamp = datetime.fromisoformat(alert.get("timestamp", datetime.now().isoformat())).strftime("%H:%M:%S")
            
            html = f"""
            <div class="alert-card {css_class}">
                <div class="alert-header">
                    <span>{icon} {alert.get("symbol")}</span>
                    <span>{timestamp}</span>
                </div>
                <div class="alert-body">
                    {alert.get("message")}
                </div>
            </div>
            """
            alerts_container.markdown(html, unsafe_allow_html=True)