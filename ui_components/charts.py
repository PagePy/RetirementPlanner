import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

# ==================== GRAPHIQUES SIMPLES ====================
def plot_income(df, label="Revenu net"):
    """Graphique du revenu net sur la période"""
    if "net_income" in df.columns:
        fig = px.line(
            df, x="year", y="net_income",
            title=f"{label} - Évolution du revenu net",
            labels={"year": "Année", "net_income": "Revenu net ($)"},
            markers=True
        )
        fig.update_layout(template="plotly_white", hovermode="x unified")
        return fig
    elif "household_income" in df.columns:
        fig = px.line(
            df, x="year", y="household_income",
            title=f"{label} - Revenu net du ménage",
            labels={"year": "Année", "household_income": "Revenu net ($)"},
            markers=True
        )
        fig.update_layout(template="plotly_white", hovermode="x unified")
        return fig

def plot_wealth(df, label="Patrimoine"):
    """Graphique du patrimoine sur la période"""
    if "wealth" in df.columns:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["year"],
            y=df["wealth"],
            fill="tozeroy",
            mode="lines",
            name="Patrimoine",
            line=dict(color="#17becf")
        ))
        fig.update_layout(
            title=f"{label} - Évolution du patrimoine",
            xaxis_title="Année",
            yaxis_title="Patrimoine net ($)",
            template="plotly_white",
            hovermode="x unified"
        )
        return fig
    elif "household_wealth" in df.columns:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["year"],
            y=df["household_wealth"],
            fill="tozeroy",
            mode="lines",
            name="Patrimoine",
            line=dict(color="#17becf")
        ))
        fig.update_layout(
            title=f"{label} - Patrimoine du ménage",
            xaxis_title="Année",
            yaxis_title="Patrimoine ($)",
            template="plotly_white",
            hovermode="x unified"
        )
        return fig

def plot_taxes(df, label="Fiscalité"):
    """Graphique des impôts sur la période"""
    if "taxes" in df.columns:
        fig = px.bar(
            df, x="year", y="taxes",
            title=f"{label} - Impôts annuels",
            labels={"year": "Année", "taxes": "Impôts ($)"},
            color_discrete_sequence=["#d62728"]
        )
        fig.update_layout(template="plotly_white", hovermode="x unified")
        return fig
    elif "household_taxes" in df.columns:
        fig = px.bar(
            df, x="year", y="household_taxes",
            title=f"{label} - Impôts du ménage",
            labels={"year": "Année", "household_taxes": "Impôts ($)"},
            color_discrete_sequence=["#d62728"]
        )
        fig.update_layout(template="plotly_white", hovermode="x unified")
        return fig

# ==================== GRAPHIQUES AVANCÉS ====================
def plot_comparison(results_dict):
    """Comparaison entre scénarios"""
    fig = go.Figure()
    
    for scenario_name, df in results_dict.items():
        if "net_income" in df.columns:
            fig.add_trace(go.Scatter(
                x=df["year"],
                y=df["net_income"],
                mode="lines+markers",
                name=scenario_name,
                hovertemplate=f"<b>{scenario_name}</b><br>Année: %{{x}}<br>Revenu: $%{{y:,.0f}}<extra></extra>"
            ))
    
    fig.update_layout(
        title="Comparaison des scénarios - Revenu net",
        xaxis_title="Année",
        yaxis_title="Revenu net ($)",
        template="plotly_white",
        hovermode="x unified",
        height=500
    )
    return fig

def plot_detailed_breakdown(df):
    """Ventilation détaillée du revenu et patrimoine"""
    if "gross_income" in df.columns and "taxes" in df.columns and "net_income" in df.columns:
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=("Composition du revenu", "Évolution du patrimoine"),
            specs=[[{"type": "scatter"}, {"type": "scatter"}]]
        )
        
        # Revenu brut vs net
        fig.add_trace(
            go.Scatter(x=df["year"], y=df["gross_income"], name="Revenu brut",
                      line=dict(color="#1f77b4"), mode="lines+markers"),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(x=df["year"], y=df["taxes"], name="Impôts",
                      fill="tozeroy", line=dict(color="#d62728")),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(x=df["year"], y=df["net_income"], name="Revenu net",
                      line=dict(color="#2ca02c", dash="dash"), mode="lines+markers"),
            row=1, col=1
        )
        
        # Patrimoine
        if "wealth" in df.columns:
            fig.add_trace(
                go.Scatter(x=df["year"], y=df["wealth"], name="Patrimoine",
                          fill="tozeroy", line=dict(color="#17becf"), mode="lines+markers"),
                row=1, col=2
            )
        
        fig.update_xaxes(title_text="Année", row=1, col=1)
        fig.update_xaxes(title_text="Année", row=1, col=2)
        fig.update_yaxes(title_text="Montant ($)", row=1, col=1)
        fig.update_yaxes(title_text="Patrimoine ($)", row=1, col=2)
        fig.update_layout(height=500, template="plotly_white", hovermode="x unified")
        
        return fig

def plot_stress_test(results_dict):
    """Visualisation des stress tests"""
    fig = go.Figure()
    
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
    
    for idx, (scenario_name, df) in enumerate(results_dict.items()):
        if "wealth" in df.columns:
            fig.add_trace(go.Scatter(
                x=df["year"],
                y=df["wealth"],
                mode="lines",
                name=scenario_name,
                line=dict(color=colors[idx % len(colors)]),
                hovertemplate=f"<b>{scenario_name}</b><br>Année: %{{x}}<br>Patrimoine: $%{{y:,.0f}}<extra></extra>"
            ))
    
    fig.update_layout(
        title="Stress Tests - Évolution du patrimoine",
        xaxis_title="Année",
        yaxis_title="Patrimoine ($)",
        template="plotly_white",
        hovermode="x unified",
        height=500
    )
    return fig

def plot_income_sources(df):
    """Ventilation des sources de revenu"""
    if "salary" in df.columns and "investment_income" in df.columns:
        fig = px.area(
            df, x="year",
            y=["salary", "investment_income"],
            title="Sources de revenu",
            labels={"value": "Montant ($)", "variable": "Source"},
            color_discrete_map={"salary": "#1f77b4", "investment_income": "#2ca02c"}
        )
        fig.update_layout(template="plotly_white", hovermode="x unified")
        return fig

# ==================== MÉTRIQUES CLÉS ====================
def calculate_key_metrics(df):
    """Calcul des métriques principales"""
    metrics = {
        "Revenu moyen": df["net_income"].mean() if "net_income" in df.columns else 0,
        "Patrimoine final": df["wealth"].iloc[-1] if "wealth" in df.columns else 0,
        "Impôts totaux": df["taxes"].sum() if "taxes" in df.columns else 0,
        "Rendement moyen": ((df["wealth"].iloc[-1] / df["wealth"].iloc[0]) ** (1/len(df)) - 1) * 100 if "wealth" in df.columns and len(df) > 0 else 0
    }
    return metrics
