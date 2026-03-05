import streamlit as st
import pandas as pd
import plotly.express as px
import yfinance as yf

st.set_page_config(page_title="Price Watchdog v1.0", layout="wide")

st.title("🛡️ Raw Material Price Watchdog (Enterprise Edition)")

SHEET_ID = "1qUorrvZ7aj-fRlrJxQpm_6rK2-HolwtWH86SqVcDUWU"

# API Settings
API_TICKERS = {
    "A380": "ALI=F", "ADC12": "ALI=F", "6063": "ALI=F", "AL 7075": "ALI=F",
    "SPCC": "HRC=F", "SECC": "HRC=F", "SUS": "HRC=F", "PVC": "CL=F", "C3604": "HG=F"
}

# --- Core Data Engines ---
@st.cache_data(ttl=3600)
def fetch_live_price(ticker):
    try:
        data = yf.Ticker(ticker).history(period="1d")
        if not data.empty:
            price = float(data['Close'].iloc[-1])
            if ticker in ["ALI=F", "HRC=F"]: return round(price / 1000, 3) 
            elif ticker == "HG=F": return round(price * 2.2046, 3) 
            elif ticker == "CL=F": return round(price / 159, 3) 
            return round(price, 3)
        return None
    except: return None

@st.cache_data(ttl=86400)
def fetch_trend_history(ticker):
    try: return yf.Ticker(ticker).history(period="3mo")[['Close']]
    except: return pd.DataFrame()

@st.cache_data(ttl=600)
def load_market_data():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Market%20Price"
    try:
        df = pd.read_csv(url)
        mat_col = [c for c in df.columns if 'Material' in str(c) or 'Grade' in str(c)][0]
        price_col = [c for c in df.columns if 'USD' in str(c) or 'Cost' in str(c)][0]
        return dict(zip(df[mat_col].astype(str), df[price_col]))
    except: return {}

@st.cache_data(ttl=600)
def load_price_book():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Quotation"
    try:
        df = pd.read_csv(url)
        if not any('Part Number' in str(c) or '料号' in str(c) for c in df.columns):
            header_idx = -1
            for i, row in df.iterrows():
                if 'Part Number' in " ".join([str(x) for x in row.values]):
                    header_idx = i; break
            if header_idx != -1:
                df.columns = df.iloc[header_idx].astype(str).str.replace('\n', ' ', regex=False).str.strip()
                df = df.iloc[header_idx+1:].reset_index(drop=True)
        # Updated mapping to 'Current_UP'
        mapping = {'Part Number': 'Part_No', 'Material U/P': 'Current_UP', 'Raw material': 'Material'}
        final_cols = {col: mapping[k] for col in df.columns for k in mapping if k.lower() in str(col).lower()}
        df_clean = df[list(final_cols.keys())].rename(columns=final_cols)
        df_clean['Current_UP'] = pd.to_numeric(df_clean['Current_UP'].astype(str).str.replace(r'[\$,]', '', regex=True), errors='coerce')
        return df_clean.dropna(subset=['Part_No', 'Current_UP'])
    except: return pd.DataFrame()

# --- Logic Processing ---
market_dict_db = load_market_data()
master_data = load_price_book()

tab1, tab2, tab3 = st.tabs(["🚨 Variance Analytics", "📧 Email Generator", "📂 Data Management"])

# Sidebar Feed
st.sidebar.header("📡 Live Market Feed")
market_prices = {} 
if not master_data.empty:
    for mat in master_data['Material'].dropna().unique():
        p, label = 0.0, "⚠️ (No Data)"
        for db_m, db_p in market_dict_db.items():
            if str(mat).lower() in str(db_m).lower(): p, label = float(db_p), "📊 (Sheet)"; break
        for k, v in API_TICKERS.items():
            if k.lower() in str(mat).lower():
                live = fetch_live_price(v)
                if live: p, label = live, f"🔥 (Yahoo: {v})"
                break
        market_prices[mat] = st.sidebar.number_input(f"{mat} {label}", value=p, step=0.01)

# --- TAB 1: Analytics ---
with tab1:
    if not master_data.empty:
        df = master_data.copy()
        df['Market_Price'] = df['Material'].map(market_prices)
        df_valid = df[df['Market_Price'] > 0].copy()
        # Variance calculation: If Current_UP is higher than Market, it's a positive gap (Needs negotiation)
        df_valid['Variance_%'] = ((df_valid['Current_UP'] - df_valid['Market_Price']) / df_valid['Market_Price'] * 100).round(2)
        
        st.subheader("📝 Real-time Variance Details")
        st.caption("Positive Variance (Red) indicates your current price is higher than the market benchmark.")
        
        # Color Logic: Red for buying expensive (High Variance), Green for cheap
        st.dataframe(df_valid.style.background_gradient(cmap='RdYlGn_r', subset=['Variance_%']), 
                     use_container_width=True, hide_index=True)
        
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("##### 🎯 Negotiation Targets (High Variance = High Priority)")
            # Higher bar = Bigger negotiation opportunity
            fig1 = px.bar(df_valid.sort_values('Variance_%', ascending=False), x='Part_No', y='Variance_%', 
                          color='Variance_%', color_continuous_scale='RdYlGn_r')
            st.plotly_chart(fig1, use_container_width=True)
        with col2:
            st.markdown("##### 📉 3-Month Market Trend")
            api_mats = [m for m in df_valid['Material'].unique() if any(k.lower() in str(m).lower() for k in API_TICKERS.keys())]
            if api_mats:
                sel = st.selectbox("Select material:", api_mats)
                tick = next(v for k, v in API_TICKERS.items() if k.lower() in str(sel).lower())
                tr = fetch_trend_history(tick)
                if not tr.empty:
                    fig2 = px.line(tr, y='Close', title=f"Index Trend: {tick}")
                    fig2.update_traces(line_color='#2E7D32')
                    st.plotly_chart(fig2, use_container_width=True)

        st.markdown("##### 💰 Price Positioning Matrix")
        max_v = max(df_valid['Market_Price'].max(), df_valid['Current_UP'].max()) * 1.1
        fig3 = px.scatter(df_valid, x='Market_Price', y='Current_UP', color='Material', 
                          hover_data=['Part_No', 'Variance_%'], size_max=15,
                          range_x=[0, max_v], range_y=[0, max_v])
        
        # Diagonal line
        fig3.add_shape(type="line", x0=0, y0=0, x1=max_v, y1=max_v, line=dict(color="Black", dash="dash"))
        
        # Annotate Areas: Above line = Overpriced (Red Zone), Below line = Good Deal (Green Zone)
        fig3.add_annotation(x=max_v*0.2, y=max_v*0.8, text="🔴 OVERPRICED (Negotiate!)", showarrow=False, font=dict(color="red", size=14))
        fig3.add_annotation(x=max_v*0.8, y=max_v*0.2, text="🟢 SAFE (Better than Market)", showarrow=False, font=dict(color="green", size=14))
        
        fig3.update_layout(xaxis_title="Live Market Price (USD/KG)", yaxis_title="Your Current UP (USD/KG)")
        st.plotly_chart(fig3, use_container_width=True)

# --- TAB 2: Email Generator ---
with tab2:
    st.subheader("📧 Cost Reduction Request Generator")
    if not df_valid.empty:
        target_parts = st.multiselect("Select parts to include in the negotiation email:", df_valid['Part_No'].unique())
        if target_parts:
            selected_df = df_valid[df_valid['Part_No'].isin(target_parts)]
            vendor_name = st.text_input("Vendor Contact Person:", "Account Manager")
            
            email_body = f"Dear {vendor_name},\n\n"
            email_body += "We have been reviewing our current purchasing costs against global commodity indices. "
            email_body += "Our records indicate that the raw material market has shifted significantly, creating a gap between our current unit prices and market benchmarks.\n\n"
            email_body += "The following items have been identified for price realignment:\n\n"
            
            for _, row in selected_df.iterrows():
                email_body += f"- Part No: {row['Part_No']} | Current UP: ${row['Current_UP']} | Market Index: ${row['Market_Price']} | Gap: {row['Variance_%']}%\n"
            
            email_body += "\nWe value our partnership and request your support in adjusting these prices to reflect the current market conditions. "
            email_body += "Please provide us with a revised quotation for these parts by the end of the week.\n\n"
            email_body += "Looking forward to your prompt response.\n\nBest Regards,\n[Your Name]\nSupply Chain Dept."
            
            st.text_area("Email Draft:", email_body, height=350)
            st.caption("Tip: Highlight and copy the text above to your email client.")
        else:
            st.info("Select parts from the dropdown to generate an email draft.")
    else:
        st.warning("No valid data available.")

# --- TAB 3: Documentation ---
with tab3:
    st.subheader("📂 System Configuration & User Guide")
    st.markdown(f"### 🔗 [✏️ Open Database (Google Sheets)](https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit)")
    
    if st.button("🔄 Clear Cache & Sync Data"):
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")
    with st.expander("📖 Detailed Operational Manual", expanded=True):
        st.markdown("""
        #### **1. Understanding the Logic**
        * **Current UP**: This is the price you are currently paying (sourced from the 'Quotation' tab in Google Sheets).
        * **Market Price**: The benchmark price. It comes from **Yahoo Finance API** (Live Futures) or your **Google Sheets 'Market Price' tab** (Spot prices).
        * **Variance (%)**: Calculated as `(Current UP - Market Price) / Market Price`. 
            * **High Positive % (RED)**: You are overpaying. Negotiation is needed.
            * **Negative % (GREEN)**: Your contract is better than the current market rate.

        #### **2. Visual Dashboard Guide**
        * **Bar Chart**: Sorted by Variance. The tallest bars on the left are your **highest priority** for cost saving.
        * **Price Positioning Matrix**: 
            * **Red Zone (Top-Left)**: Parts in this area have a high `Current UP` despite low `Market Price`. 
            * **Diagonal Line**: This represents the 'Breakeven' where your price equals the market.
        
        #### **3. Data Maintenance (Google Sheets)**
        To keep the system accurate, ensure your Google Sheet follows these rules:
        * **'Quotation' Tab**: Must contain `Part Number` and `Material U/P`. This is your price book.
        * **'Market Price' Tab**: Use this for materials that don't have a live API (like Zamak 3). Ensure the columns contain `Material` and `USD`.
        
        #### **4. API Refresh**
        Prices from Yahoo Finance update every hour. If you suspect data is stale, use the **'Clear Cache'** button above to force a fresh pull.
        """)