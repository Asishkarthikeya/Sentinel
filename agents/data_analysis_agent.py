import pandas as pd
import numpy as np
import plotly.express as px
import json
import logging
import re
from typing import TypedDict, Dict, Any, List

from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AnalysisState(TypedDict):
    dataframe: pd.DataFrame
    dataset_info: Dict[str, Any]
    insights: str
    visualizations: List[Dict[str, Any]]
    charts: List[Any]

class DataAnalysisAgent:
    def __init__(self, llm: ChatGoogleGenerativeAI):
        self.llm = llm
        self.workflow = self._create_workflow()

    def _create_workflow(self):
        """Creates the graph workflow for the data analysis sub-agent."""
        workflow = StateGraph(AnalysisState)
        workflow.add_node("data_profiler", self._profile_dataset)
        # This new node will generate insights AND plan visualizations in one LLM call
        workflow.add_node("insight_and_viz_planner", self._generate_insights_and_plan_visualizations)
        workflow.add_node("chart_creator", self._create_charts)
        
        workflow.add_edge("data_profiler", "insight_and_viz_planner")
        workflow.add_edge("insight_and_viz_planner", "chart_creator")
        workflow.add_edge("chart_creator", END)
        
        workflow.set_entry_point("data_profiler")
        return workflow.compile()

    def _profile_dataset(self, state: AnalysisState):
        """Profiles the dataset to understand its structure for the LLM."""
        logger.info("--- 📊 (Sub-Agent) Profiling Data ---")
        df_for_profiling = state["dataframe"].copy().reset_index()
        
        profile = {
            "shape": df_for_profiling.shape,
            "columns": list(df_for_profiling.columns),
            "dtypes": {col: str(dtype) for col, dtype in df_for_profiling.dtypes.to_dict().items()},
            "numeric_columns": df_for_profiling.select_dtypes(include=[np.number]).columns.tolist(),
            "datetime_columns": df_for_profiling.select_dtypes(include=['datetime64']).columns.tolist()
        }
        logger.info("   Data profile created.")
        return {"dataset_info": profile}

    def _generate_insights_and_plan_visualizations(self, state: AnalysisState):
        """Generates key insights and plans visualizations in a single LLM call."""
        logger.info("--- 🧠 (Sub-Agent) Generating Insights & Visualization Plan ---")
        info = state["dataset_info"]
        datetime_col = info.get("datetime_columns", [None])[0] or info.get("columns", ["index"])[0]

        prompt = f"""
        You are an expert financial data scientist. Based on the following data profile from a time-series stock dataset,
        generate key insights and plan effective visualizations.

        Data Profile: {json.dumps(info, indent=2)}

        Instructions:
        Your response MUST be ONLY a single valid JSON object. Do not include any other text or markdown.
        The JSON object must have two keys: "insights" and "visualizations".
        - "insights": A list of 3-5 concise, bullet-point style strings focusing on trends, correlations, and anomalies.
        - "visualizations": A list of 3 JSON objects, each planning a chart.
            - Plan a line chart for the 'close' price over time using the '{datetime_col}' column.
            - Plan a histogram for the 'volume' column.
            - Plan one other relevant chart (e.g., scatter plot, bar chart).

        Example Response:
        {{
            "insights": [
                "The closing price shows a significant upward trend over the period.",
                "Trading volume spiked on dates corresponding to major news events.",
                "There is a strong positive correlation between opening and closing prices."
            ],
            "visualizations": [
                {{"type": "line", "columns": ["{datetime_col}", "close"], "title": "Closing Price Over Time"}},
                {{"type": "histogram", "columns": ["volume"], "title": "Trading Volume Distribution"}},
                {{"type": "scatter", "columns": ["open", "close"], "title": "Opening vs. Closing Price"}}
            ]
        }}
        """
        response_str = self.llm.invoke(prompt).content
        logger.info(f"   LLM raw output for insights & viz plan:\n{response_str}")

        try:
            json_match = re.search(r'\{.*\}', response_str, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON object found in the LLM response.")
            
            clean_json_str = json_match.group(0)
            response_json = json.loads(clean_json_str)
            
            insights_list = response_json.get("insights", [])
            insights_str = "\n".join(f"* {insight}" for insight in insights_list)
            viz_plan = response_json.get("visualizations", [])
            
            logger.info("   Successfully parsed insights and viz plan.")
            return {"insights": insights_str, "visualizations": viz_plan}

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse insights and visualization plan from LLM. Error: {e}")
            logger.info("   Using a default visualization plan as a fallback.")
            default_plan = [
                {"type": "line", "columns": [datetime_col, "close"], "title": "Closing Price Over Time (Default)"},
                {"type": "histogram", "columns": ["volume"], "title": "Trading Volume (Default)"}
            ]
            return {"insights": "Analysis generated, but detailed insights could not be parsed.", "visualizations": default_plan}

    def _create_charts(self, state: AnalysisState):
        """Creates Plotly charts based on the visualization plan."""
        logger.info("--- 🎨 (Sub-Agent) Creating Charts ---")
        df = state["dataframe"].reset_index()
        viz_plans = state.get("visualizations", [])
        charts = []

        if not viz_plans:
            logger.warning("   No visualization plans found. Skipping chart creation.")
            return {"charts": []}

        for viz in viz_plans:
            try:
                chart_type = viz.get("type", "").lower()
                columns = viz.get("columns", [])
                title = viz.get("title", "Generated Chart")

                if not all(col in df.columns for col in columns):
                    logger.warning(f"   Skipping chart '{title}': One or more columns {columns} not found in DataFrame.")
                    continue

                if chart_type == "line" and len(columns) >= 2:
                    fig = px.line(df, x=columns[0], y=columns[1], title=title, template="plotly_dark")
                    charts.append(fig)
                elif chart_type == "histogram" and len(columns) >= 1:
                    fig = px.histogram(df, x=columns[0], title=title, template="plotly_dark")
                    charts.append(fig)
                elif chart_type == "scatter" and len(columns) >= 2:
                    fig = px.scatter(df, x=columns[0], y=columns[1], title=title, template="plotly_dark")
                    charts.append(fig)
            except Exception as e:
                logger.error(f"   Failed to create chart of type {viz.get('type')}: {e}")
        
        logger.info(f"   Successfully created {len(charts)} charts.")
        return {"charts": charts}

    def run_analysis(self, dataframe: pd.DataFrame):
        """Runs the full analysis workflow on the given DataFrame."""
        if dataframe.empty:
            logger.warning("Input DataFrame is empty. Skipping analysis.")
            return {"insights": "No data available for analysis.", "charts": []}
        initial_state = {"dataframe": dataframe}
        # The final state will now contain insights and charts after the workflow runs
        final_state = self.workflow.invoke(initial_state)
        return final_state