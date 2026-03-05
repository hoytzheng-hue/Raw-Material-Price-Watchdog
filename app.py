import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

# --- 1. Page Config ---
st.set_page_config(page_title="Price Monitor v1.0", layout="wide")

# --- 2. Sidebar: Real-time Market Data (Simulating Scraper Group) ---
st.sidebar.header("📊 Market Live Feed")
st.sidebar.write(f"Last Scraped: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# These values will later be pulled from the Scraper group's database
live_alu_adc12 = st.sidebar.number_input("Live ADC12 Price ($/kg)", value=2.85)
live_alu_6063 = st.sidebar.number_input("Live AL6063 Price ($/kg)", value=2.90)

st.sidebar.markdown("---")
st.sidebar.subheader("Threshold Setting")
alert_threshold = st.sidebar.slider("Price Drop Alert (%)", 0, 20, 5, 
                                    help="Alert when market price is X% lower than contract price")

# --- 3. Main Logic: Title & Metrics ---
st.title("🛡️ Raw Material Price Watchdog")

# Top Metrics
m1, m2, m3 = st.columns(3)
m1.metric("ADC12 Market", f"${live_alu_adc12}", "-2.4%")
m2.metric("AL6063 Market", f"${live_alu_6063}", "+1.1%")
m3.metric("Pending Email Analysis", "3 High Risk")

# --- 4. Tabs Reconstruction ---
tab1, tab2, tab3 = st.tabs(["🚨 Price Variance Analysis", "📧 Email Generator", "📂 Database Management"])

# --- TAB 1: Comparison Logic ---
with tab1:
    st.subheader("Contract vs. Market Comparison")
    
    # Mocking the data from your uploaded CSVs (e.g., XY or Wisefull)
    # In reality, this will be the output from the Cleaning group
    data = {
        'Vendor': ['XY', 'Wisefull', '3NOD', 'XY'],
        'Part_Number': ['DCM-112973', 'EXM-115723', 'MACM-113289', 'DCM-111493'],
        'Material': ['A380', 'ADC12', 'AL6063', 'ADC12'],
        'Contract_Material_UP': [3.38, 3.00, 3.00, 3.23], # From your Price Book
        'Weight_g': [2000, 111, 3418, 20]
    }
    df = pd.DataFrame(data)
    
    # Calculate Variance
    df['Current_Market_UP'] = df['Material'].apply(lambda x: live_alu_6063 if '6063' in x else live_alu_adc12)
    df['Price_Diff_%'] = ((df['Current_Market_UP'] - df['Contract_Material_UP']) / df['Contract_Material_UP'] * 100).round(2)
    
    # Identify Savings (The "Gap")
    df['Potential_Saving_USD'] = ((df['Contract_Material_UP'] - df['Current_Market_UP']) * (df['Weight_g'] / 1000)).round(3)
    
    # Highlight Logic: If Price_Diff_% < -alert_threshold, it means market is much cheaper = we are overpaying
    def color_coding(val):
        color = 'red' if val <= -alert_threshold else 'white'
        return f'color: {color}'

    st.write("Targeting parts where market price dropped significantly:")
    st.dataframe(df.style.applymap(color_coding, subset=['Price_Diff_%']), use_container_width=True)

    # Visualization
    fig = px.bar(df, x='Part_Number', y='Potential_Saving_USD', color='Vendor', 
                 title="Estimated Potential Savings per Unit (USD)")
    st.plotly_chart(fig, use_container_width=True)

# --- TAB 2: Email Generator ---
with tab2:
    st.subheader("Auto-Analysis Email Draft")
    
    selected_part = st.selectbox("Select Anomaly Part to Analyze", df['Part_Number'].unique())
    part_info = df[df['Part_Number'] == selected_part].iloc[0]
    
    if part_info['Price_Diff_%'] < 0:
        status = "Lower than Contract"
        tone = "Request for price reduction"
    else:
        status = "Higher than Contract"
        tone = "Monitor only"

    email_template = f"""
Subject: Request for Quotation Update - {part_info['Part_Number']}

Dear {part_info['Vendor']} Sales Team,

Our Raw Material Dynamic Monitor shows a significant shift in the market.
For {part_info['Material']}, the current market price is ${part_info['Current_Market_UP']}/kg, 
which is {abs(part_info['Price_Diff_%'])}% {status} compared to our last Price Book (${part_info['Contract_Material_UP']}/kg).

Part Number: {part_info['Part_Number']}
Impact: ${abs(part_info['Potential_Saving_USD'])} per unit.

Please review and provide an updated quotation based on the current market trend.

Best Regards,
Procurement Team
    """
    st.text_area("Draft Content (Copy to Outlook)", value=email_template, height=300)

# --- TAB 3: Database Management ---
with tab3:
    st.subheader("Data Input Center")
    col_a, col_b = st.columns(2)
    with col_a:
        st.file_uploader("Upload Scraper Feed (Market)", type="csv")
    with col_b:
        st.file_uploader("Upload Historical Price Book (Contract)", type="csv")