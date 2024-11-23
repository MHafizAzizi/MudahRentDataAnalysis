import streamlit as st
import pandas as pd
import plotly.express as px


st.set_page_config(layout="wide") # Set page config to always wide layout
st.title("Mudah Rental Analysis")
st.write("This is an reporting dashboard of rental properties scrape from Mudah Website, the data will be updated when I like it :P")
# st.write("another test")
# st.write("Data Table of Available Rental Properties")


def clean_data():
    df = pd.read_csv("MasterFile.csv")
    df['state'] = df['state'].fillna('Not Specified').str.strip().str.title()
    df['CPI'] = df['CPI'].fillna('Not Specified').str.strip()
    df['furnished'] = df['furnished'].fillna('Not Specified').str.strip()
    df['size'] = pd.to_numeric(df['size'], errors = 'coerce')

    return df
df = clean_data()
st.markdown("---")
col1, col2, col3 = st.columns(3)
st.markdown("---")
# Metric
st.header("Metrics", divider="rainbow")

with col1:
    st.metric(label="Total Properties for Rent", value=len(df['ads_id']))

with col2:
    st.metric(label="Average Monthly Rent (RM)", value=round(df["monthly_rent"].mean(),1))

with col3:
    st.metric(label="Average Property Size (sq.ft.)", value=round(df["size"].mean(),1))

# Hover_data
def total_prop_by_type():
    properties_count_by_type = df.groupby('CPI').size().reset_index(name='total_properties')
    avg_rent_by_type = df.groupby('CPI')['monthly_rent'].mean().reset_index()
    merged = pd.merge(avg_rent_by_type, properties_count_by_type, on='CPI')
    return merged

def total_prop_by_state():
    properties_count_by_state = df.groupby('state').size().reset_index(name='total_properties')
    avg_rent_by_state = df.groupby('state')['monthly_rent'].mean().reset_index()
    merged = pd.merge(avg_rent_by_state, properties_count_by_state, on='state')
    return merged


col1, col2 = st.columns(2)
# Bar Chart - Plotly
with col1:
    st.subheader("Average Rent By Property Type")
    merged_data = total_prop_by_type()
    figure_avg_rent = px.bar(merged_data,
                            color='CPI',
                            x='CPI', y='monthly_rent',
                            labels = {
                                'CPI': 'Property Type', 
                                'monthly_rent': 'Average Monthly Rent (RM)',
                                'total_properties': 'Total Properties',
                            },
                            hover_data=['total_properties'])
    figure_avg_rent.update(layout_showlegend=False) # Hide legend
    figure_avg_rent.update_layout(
        xaxis=dict(showgrid=False),  # Hide x-axis gridlines
        yaxis=dict(showgrid=False),   # Hide y-axis gridlines
        xaxis_title = '' # Hide x-axis title
    )
    st.plotly_chart(figure_avg_rent)

with col2:
#Pie Chart - Plotly
    st.subheader("Property Type Distribution")
    prop_stat = df['CPI'].value_counts()
    fig_prop = px.pie(values = prop_stat.values,
                    names = prop_stat.index)
    st.plotly_chart(fig_prop, use_container_width=True)


# #Bar Chart - Streamlit
# st.bar_chart(merged_data,
#              x='CPI', y='monthly_rent',
#              x_label='Property Type', y_label='Average Monthly Rent (RM)',
#              color = 'CPI',
#              use_container_width=True)



st.markdown("---")
# Bar Chart - Plotly
st.subheader("Average Rent By State",divider="rainbow")
state_merged_data = total_prop_by_state()
figure_avg_rent_state = px.bar(state_merged_data,
                               color='state',
                               x='state',y='monthly_rent',
                               labels = {'state':'State',
                                         'monthly_rent':'Average Monthly Rent (RM)',
                                         'total_properties':'Total Properties'},
                                         hover_data=['total_properties'])
figure_avg_rent_state.update(layout_showlegend=False)
figure_avg_rent_state.update_layout(
    xaxis=dict(showgrid=False),  # Hide x-axis gridlines
    yaxis=dict(showgrid=False),   # Hide y-axis gridlines
    xaxis_title = '' # Hide x-axis title
)
st.plotly_chart(figure_avg_rent_state)


st.subheader("Furnishing Status Distribution",divider="rainbow")
col1, col2 = st.columns(2)
# Pie Chart - Plotly
with col1:
    furnish_stat = df['furnished'].value_counts()
    pie_fig = px.pie(values = furnish_stat.values,
                    names = furnish_stat.index,
                    title = "Distribution by Furnishing Status")
    st.plotly_chart(pie_fig, use_container_width=True)
with col2:
    # st.subheader("Average Rent by Furnishing Status")
    fig_avg_by_status = px.bar(df.groupby('furnished')['monthly_rent'].mean().reset_index(),
                            x='furnished', y='monthly_rent',
                            color='furnished',
                            title = "Average Rent by Furnishing Status",
                            labels = {'furnished':'Furnished State', 'monthly_rent':'Average Monthly Rent (RM)'})
    fig_avg_by_status.update_layout(
        xaxis=dict(showgrid=False),  # Hide x-axis gridlines
        yaxis=dict(showgrid=False),   # Hide y-axis gridlines
        xaxis_title = '' # Hide x-axis title
    )
    fig_avg_by_status.update(layout_showlegend=False)
    st.plotly_chart(fig_avg_by_status, use_container_width=True)


# # First, create a function to get the breakdown
# def analyze_other_properties():
#     other_properties = df[df['CPI'] == 'Other']
#     # Get counts by property type
#     type_counts = other_properties['property_type'].value_counts().reset_index()
#     type_counts.columns = ['Property Type', 'Count']
    
#     # Get average rent by property type
#     avg_rent = other_properties.groupby('property_type')['monthly_rent'].mean().reset_index()
#     avg_rent.columns = ['Property Type', 'Average Rent']
    
#     # Merge the information
#     merged_analysis = pd.merge(type_counts, avg_rent, on='Property Type')
#     return merged_analysis

# # Create the visualization
# st.subheader("Analysis of 'Other' Property Categories")

# other_analysis = analyze_other_properties()

# # Create two columns for different visualizations

# st.write("Distribution of 'Other' Property Types")
# fig_count = px.pie(other_analysis, 
#                     values='Count', 
#                     names='Property Type',
#                     title='Distribution of Other Property Types')
# fig_count.update_traces(textposition='inside', textinfo='percent+label')
# st.plotly_chart(fig_count)


# st.write("Average Rent by 'Other' Property Types")
# fig_rent = px.bar(other_analysis,
#                     x='Property Type',
#                     y='Average Rent',
#                     title='Average Rent for Other Property Types',
#                     labels={'Property Type': '', 'Average Rent': 'Average Monthly Rent (RM)'},
#                     color='Property Type')
# fig_rent.update_layout(showlegend=False,
#                         xaxis_title='',
#                         yaxis_title='Average Monthly Rent (RM)')
# st.plotly_chart(fig_rent)

# # Display detailed statistics
# st.subheader("Detailed Statistics")
# st.dataframe(other_analysis.style.format({
#     'Average Rent': '{:,.2f} RM'}),
#     use_container_width=True)




st.markdown("---")
st.subheader("Property Table")
st.write(df,hide_index=True)
st.markdown("---")
#streamlit run general.py

