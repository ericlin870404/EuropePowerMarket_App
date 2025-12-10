import pandas as pd
import plotly.graph_objects as go
import streamlit as st

def plot_line_chart(file):
    df = pd.read_csv(file)

    fig = go.Figure()
    for col in df.columns[1:]:
        fig.add_trace(go.Scatter(x=df["Date"], y=df[col], mode="lines", name=col))

    fig.update_layout(
        template="plotly_white",
        height=600
    )
    st.plotly_chart(fig, use_container_width=True)
