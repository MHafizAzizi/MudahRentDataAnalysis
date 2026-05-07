import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

import sqlite3
import streamlit as st
import pandas as pd
import plotly.express as px


st.set_page_config(layout="wide")
st.title("Mudah Rental Analysis")
st.write("Reporting dashboard of rental properties scraped from Mudah Website. Data updates periodically.")


_DB_COLS = [
    "ads_id", "monthly_rent", "property_type", "CPI", "state", "region",
    "rooms", "bathroom", "size", "furnished", "facilities",
    "additional_facilities", "address", "latitude", "longitude",
    "publishedDatetime", "scrape_date", "adviewUrl",
]

@st.cache_data(ttl=3600)
def load_data() -> pd.DataFrame:
    if not config.DB_FILE.exists():
        st.error(f"Database not found: {config.DB_FILE}. Run scripts 1 → 2 → 3 first.")
        st.stop()

    cols = ", ".join(_DB_COLS)
    with sqlite3.connect(config.DB_FILE) as conn:
        df = pd.read_sql(f"SELECT {cols} FROM {config.DB_TABLE}", conn)

    df['state'] = df['state'].fillna('Not Specified').str.strip().str.title()
    df['CPI'] = df['CPI'].fillna('Not Specified').str.strip()
    df['furnished'] = df['furnished'].fillna('Not Specified').str.strip()
    df['size'] = pd.to_numeric(df['size'], errors='coerce')
    df['monthly_rent'] = pd.to_numeric(df['monthly_rent'], errors='coerce')

    return df


df = load_data()

st.markdown("---")
col1, col2, col3 = st.columns(3)
st.markdown("---")

st.header("Metrics", divider="rainbow")
with col1:
    st.metric(label="Total Properties for Rent", value=len(df['ads_id']))
with col2:
    st.metric(label="Average Monthly Rent (RM)", value=round(df["monthly_rent"].mean(), 1))
with col3:
    st.metric(label="Average Property Size (sq.ft.)", value=round(df["size"].mean(), 1))


@st.cache_data
def total_prop_by_type(df: pd.DataFrame) -> pd.DataFrame:
    count = df.groupby('CPI').size().reset_index(name='total_properties')
    avg = df.groupby('CPI')['monthly_rent'].mean().reset_index()
    return pd.merge(avg, count, on='CPI')


@st.cache_data
def total_prop_by_state(df: pd.DataFrame) -> pd.DataFrame:
    count = df.groupby('state').size().reset_index(name='total_properties')
    avg = df.groupby('state')['monthly_rent'].mean().reset_index()
    return pd.merge(avg, count, on='state')


col1, col2 = st.columns(2)
with col1:
    st.subheader("Average Rent By Property Type")
    merged_data = total_prop_by_type(df)
    fig = px.bar(merged_data,
                 color='CPI', x='CPI', y='monthly_rent',
                 labels={'CPI': 'Property Type',
                         'monthly_rent': 'Average Monthly Rent (RM)',
                         'total_properties': 'Total Properties'},
                 hover_data=['total_properties'])
    fig.update(layout_showlegend=False)
    fig.update_layout(xaxis=dict(showgrid=False), yaxis=dict(showgrid=False), xaxis_title='')
    st.plotly_chart(fig)

with col2:
    st.subheader("Property Type Distribution")
    prop_stat = df['CPI'].value_counts()
    fig_pie = px.pie(values=prop_stat.values, names=prop_stat.index)
    st.plotly_chart(fig_pie, use_container_width=True)


st.markdown("---")
st.subheader("Average Rent By State", divider="rainbow")
state_data = total_prop_by_state(df)
fig_state = px.bar(state_data,
                   color='state', x='state', y='monthly_rent',
                   labels={'state': 'State',
                           'monthly_rent': 'Average Monthly Rent (RM)',
                           'total_properties': 'Total Properties'},
                   hover_data=['total_properties'])
fig_state.update(layout_showlegend=False)
fig_state.update_layout(xaxis=dict(showgrid=False), yaxis=dict(showgrid=False), xaxis_title='')
st.plotly_chart(fig_state)


st.subheader("Furnishing Status Distribution", divider="rainbow")
col1, col2 = st.columns(2)
with col1:
    furnish_stat = df['furnished'].value_counts()
    fig_furnish = px.pie(values=furnish_stat.values, names=furnish_stat.index,
                         title="Distribution by Furnishing Status")
    st.plotly_chart(fig_furnish, use_container_width=True)
with col2:
    fig_furnish_rent = px.bar(df.groupby('furnished')['monthly_rent'].mean().reset_index(),
                              x='furnished', y='monthly_rent', color='furnished',
                              title="Average Rent by Furnishing Status",
                              labels={'furnished': 'Furnished State',
                                      'monthly_rent': 'Average Monthly Rent (RM)'})
    fig_furnish_rent.update_layout(xaxis=dict(showgrid=False), yaxis=dict(showgrid=False), xaxis_title='')
    fig_furnish_rent.update(layout_showlegend=False)
    st.plotly_chart(fig_furnish_rent, use_container_width=True)


st.markdown("---")
st.subheader("Property Map", divider="rainbow")
map_df = df.dropna(subset=['latitude', 'longitude'])
if map_df.empty:
    st.info("No geocoded properties available. Run scraper to collect lat/lon data.")
else:
    fig_map = px.scatter_map(
        map_df,
        lat='latitude',
        lon='longitude',
        color='CPI',
        hover_data={
            'ads_id': True,
            'monthly_rent': True,
            'state': True,
            'property_type': True,
            'furnished': True,
            'latitude': False,
            'longitude': False,
        },
        labels={'monthly_rent': 'Monthly Rent (RM)', 'CPI': 'Property Type'},
        zoom=6,
        center={"lat": 4.2105, "lon": 101.9758},  # Malaysia center
        map_style='open-street-map',
        height=600
    )
    st.plotly_chart(fig_map, use_container_width=True)

st.markdown("---")
st.subheader("Property Table")
st.dataframe(df, hide_index=True)
st.markdown("---")
