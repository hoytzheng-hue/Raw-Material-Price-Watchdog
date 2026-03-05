import streamlit as st
import pandas as pd
import plotly.express as px
import yfinance as yf

st.set_page_config(page_title="Price Watchdog v1.0", layout="wide")

st.title("🛡️ Raw Material Price Watchdog (Full Suite)")

SHEET_ID = "1qUorrvZ7aj-fRlrJxQpm_6rK2-HolwtWH86SqVcDUWU"

# API Mapping
API_TICKERS = {
    "A380": "ALI=F", "ADC12": "ALI=F", "6063": "ALI=F", "AL 7075": "ALI=F",
    "SPCC": "HRC=F", "SECC": "HRC=F", "SUS": "HRC=F", "PVC": "CL=F", "C3604": "HG=F"
}

# --- Data Engines ---
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
        mapping = {'Part Number': 'Part_No', 'Material U/P': 'Contract_UP', 'Raw material': 'Material'}
        final_cols = {col: mapping[k] for col in df.columns for k in mapping if k.lower() in str(col).lower()}
        df_clean = df[list(final_cols.keys())].rename(columns=final_cols)
        df_clean['Contract_UP'] = pd.to_numeric(df_clean['Contract_UP'].astype(str).str.replace(r'[\$,]', '', regex=True), errors='coerce')
        return df_clean.dropna(subset=['Part_No', 'Contract_UP'])
    except: return pd.DataFrame()

# --- App Logic ---
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
        df_valid['Variance_%'] = ((df_valid['Market_Price'] - df_valid['Contract_UP']) / df_valid['Contract_UP'] * 100).round(2)
        
        st.subheader("📝 Variance Details")
        # 隐藏索引列 (Row ID)
        st.dataframe(df_valid.style.background_gradient(cmap='RdYlGn_r', subset=['Variance_%']), 
                     use_container_width=True, hide_index=True)
        
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("##### 🎯 Negotiation Priority")
            fig1 = px.bar(df_valid.sort_values('Variance_%'), x='Part_No', y='Variance_%', color='Variance_%', 
                          color_continuous_scale='RdYlGn_r')
            st.plotly_chart(fig1, use_container_width=True)
        with col2:
            st.markdown("##### 📉 3-Month Market Trend")
            api_mats = [m for m in df_valid['Material'].unique() if any(k.lower() in str(m).lower() for k in API_TICKERS.keys())]
            if api_mats:
                sel = st.selectbox("Select material:", api_mats)
                tick = next(v for k, v in API_TICKERS.items() if k.lower() in str(sel).lower())
                tr = fetch_trend_history(tick)
                if not tr.empty:
                    fig2 = px.line(tr, y='Close', title=f"Trend: {tick}")
                    st.plotly_chart(fig2, use_container_width=True)

        st.markdown("##### 💰 Price Position: Market vs Contract")
        max_v = max(df_valid['Market_Price'].max(), df_valid['Contract_UP'].max()) * 1.1
        fig3 = px.scatter(df_valid, x='Market_Price', y='Contract_UP', color='Material', hover_data=['Part_No'],
                          range_x=[0, max_v], range_y=[0, max_v])
        # 绘制红绿背景
        fig3.add_shape(type="line", x0=0, y0=0, x1=max_v, y1=max_v, line=dict(color="Black", dash="dash"))
        # 上方红色区域 (Contract > Market)
        fig3.add_trace(px.scatter(x=[0, max_v], y=[0, max_v]).data[0]) # Dummy for legend if needed
        fig3.add_hrect(y0=0, y1=max_v, fillcolor="red", opacity=0.05, layer="below") 
        # 这里的逻辑通过背景色简单示意：上方危险，下方安全
        fig3.update_layout(margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig3, use_container_width=True)

# --- TAB 2: Email Generator ---
with tab2:
    st.subheader("📧 Professional Price Revision Request")
    if not df_valid.empty:
        target_parts = st.multiselect("Select parts to include in the email:", df_valid['Part_No'].unique())
        
        if target_parts:
            selected_df = df_valid[df_valid['Part_No'].isin(target_parts)]
            
            st.info("The system will generate a professional email based on the selected price gaps.")
            
            vendor_name = st.text_input("Vendor Contact Name:", "Valued Partner")
            
            # Email Template Logic
            email_body = f"Dear {vendor_name},\n\n"
            email_body += "I am writing to discuss the current pricing for the components we source from your company. "
            email_body += "Based on our latest market intelligence and global commodity index tracking, we have observed a significant downward trend in raw material costs.\n\n"
            email_body += "Specifically, the following parts show a notable variance compared to current market benchmarks:\n\n"
            
            for _, row in selected_df.iterrows():
                email_body += f"- Part: {row['Part_No']} ({row['Material']}) | Contract: ${row['Contract_UP']} | Market Ref: ${row['Market_Price']} | Variance: {row['Variance_%']}%\n"
            
            email_body += "\nGiven these market shifts, we kindly request a formal price review for these items to align with the current index. "
            email_body += "Could you please provide a revised quotation by the end of this week?\n\n"
            email_body += "Thank you for your continued partnership.\n\nBest Regards,\n[Your Name]\nProcurement Team"
            
            st.text_area("Generated Email Draft:", email_body, height=400)
            st.button("📋 Copy to Clipboard (Demo)")
        else:
            st.write("Please select at least one part from the list above.")
    else:
        st.warning("No data available to generate email.")

# --- TAB 3: Management ---
with tab3:
    st.markdown(f"### 🔗 [✏️ Edit Google Sheets](https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit)")
    if st.button("🔄 Force Refresh System"):
        st.cache_data.clear()
        st.rerun()
    with st.expander("📖 User Guide", expanded=True):
        st.markdown("""
        - **🚨 Variance Analytics**: Real-time gap analysis. Red means the market has dropped and you should ask for a discount.
        - **📧 Email Generator**: Select overpriced parts and get an instant professional draft.
        - **Scatter Plot**: Parts in the **Upper/Reddish area** are your top negotiation targets.
        """)