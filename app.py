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
        df_valid['Variance_%'] = ((df_valid['Current_UP'] - df_valid['Market_Price']) / df_valid['Market_Price'] * 100).round(2)
        
        st.subheader("📝 Real-time Variance Details")
        st.dataframe(df_valid.style.background_gradient(cmap='RdYlGn_r', subset=['Variance_%']), 
                     use_container_width=True, hide_index=True)
        
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("##### 🎯 Negotiation Targets")
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
                    st.plotly_chart(fig2, use_container_width=True)

# --- TAB 2: Smart Email Generator ---
with tab2:
    st.subheader("📧 Smart Negotiation Assistant")
    if not df_valid.empty:
        # --- SMART RECOMMENDATION LOGIC ---
        red_zone = df_valid[df_valid['Variance_%'] >= 5].sort_values('Variance_%', ascending=False)
        green_zone = df_valid[df_valid['Variance_%'] < 5].sort_values('Variance_%', ascending=False)
        
        st.markdown("#### 🤖 AI Recommendation")
        
        # UI for Red Zone
        if not red_zone.empty:
            st.error(f"Found {len(red_zone)} parts with significant overpricing (>= 5% variance).")
            # Create selection labels with price info
            red_options = [f"{row['Part_No']} ({row['Material']}) | Gap: +{row['Variance_%']}%" for _, row in red_zone.iterrows()]
            selected_red = st.multiselect("🔴 Priority: Negotiation Needed (Auto-selected)", 
                                          options=red_options, 
                                          default=red_options)
        
        # UI for Green/Low Variance Zone
        if not green_zone.empty:
            st.success(f"Found {len(green_zone)} parts within or below market average.")
            green_options = [f"{row['Part_No']} ({row['Material']}) | Gap: {row['Variance_%']}%" for _, row in green_zone.iterrows()]
            selected_green = st.multiselect("🟢 Info: Stable or Competitive Prices", 
                                            options=green_options)
        
        # Combine selections for email
        final_selection_ids = [s.split(" ")[0] for s in (selected_red + selected_green)]
        
        if final_selection_ids:
            selected_df = df_valid[df_valid['Part_No'].isin(final_selection_ids)]
            avg_gap = selected_df['Variance_%'].mean().round(2)
            
            st.divider()
            st.markdown(f"**Email Preview** (Average Reduction Opportunity: `{avg_gap}%`)")
            
            vendor_name = st.text_input("Vendor Contact Person:", "Account Manager")
            email_body = f"Dear {vendor_name},\n\n"
            email_body += "I am writing to formally request a price review for the components listed below. "
            email_body += "Our supply chain intelligence system, which tracks live global commodity indices, indicates a significant shift in market benchmarks.\n\n"
            
            for _, row in selected_df.iterrows():
                email_body += f"- Part No: {row['Part_No']} ({row['Material']}) | Current UP: ${row['Current_UP']} | Market Reference: ${row['Market_Price']} | Variance: {row['Variance_%']}%\n"
            
            email_body += f"\nOn average, these items show a {avg_gap}% variance compared to the current market index. "
            email_body += "We value our long-term partnership and expect our pricing to reflect these market improvements.\n\n"
            email_body += "Please provide a revised quotation and a proposal for price realignment by the end of this week.\n\nBest Regards,\n[Your Name]\nProcurement Department"
            
            st.text_area("Final Draft:", email_body, height=350)
        else:
            st.info("Select parts above to generate the negotiation email.")
    else:
        st.warning("No data available.")

# --- TAB 3: Documentation ---
with tab3:
    st.subheader("📂 System Configuration")
    st.markdown(f"### 🔗 [✏️ Open Google Sheets](https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit)")
    if st.button("🔄 Clear Cache & Sync Data"):
        st.cache_data.clear()
        st.rerun()
    with st.expander("📖 Detailed Operational Manual", expanded=True):
        st.markdown("""
        - **🔴 Priority List**: Parts where Current UP is >5% higher than Market. These are auto-selected for negotiation.
        - **🟢 Stable List**: Parts where you are either at or below market price. 
        - **Smart Email**: Automatically calculates the average gap to give you a strong opening line for negotiation.
        """)