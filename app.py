import streamlit as st
import pandas as pd
import plotly.express as px
import yfinance as yf

st.set_page_config(page_title="Price Watchdog v1.0", layout="wide")

st.title("🛡️ Raw Material Price Watchdog (Full Suite v1.1)")

SHEET_ID = "1qUorrvZ7aj-fRlrJxQpm_6rK2-HolwtWH86SqVcDUWU"

# --- 1. Global Configurations ---
API_TICKERS = {
    "A380": "ALI=F", "ADC12": "ALI=F", "6063": "ALI=F", "AL 7075": "ALI=F",
    "SPCC": "HRC=F", "SECC": "HRC=F", "SUS": "HRC=F", "PVC": "CL=F", "C3604": "HG=F"
}

# --- 2. Data Fetching Engines ---
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
        # Search for Header Row
        if not any('Part Number' in str(c) or '料号' in str(c) for c in df.columns):
            header_idx = -1
            for i, row in df.iterrows():
                if 'Part Number' in " ".join([str(x) for x in row.values]):
                    header_idx = i; break
            if header_idx != -1:
                df.columns = df.iloc[header_idx].astype(str).str.replace('\n', ' ', regex=False).str.strip()
                df = df.iloc[header_idx+1:].reset_index(drop=True)
        
        # Expanded mapping to include Vendor
        mapping = {
            'Part Number': 'Part_No', 
            'Material U/P': 'Current_UP', 
            'Raw material': 'Material',
            'Vendor': 'Vendor',
            'Supplier': 'Vendor',
            '供应商': 'Vendor'
        }
        final_cols = {col: mapping[k] for col in df.columns for k in mapping if k.lower() in str(col).lower()}
        df_clean = df[list(final_cols.keys())].rename(columns=final_cols)
        df_clean['Current_UP'] = pd.to_numeric(df_clean['Current_UP'].astype(str).str.replace(r'[\$,]', '', regex=True), errors='coerce')
        if 'Vendor' not in df_clean.columns: df_clean['Vendor'] = 'Unknown'
        return df_clean.dropna(subset=['Part_No', 'Current_UP'])
    except: return pd.DataFrame()

# --- 3. Sidebar Logic ---
market_dict_db = load_market_data()
master_data = load_price_book()

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

tab1, tab2, tab3 = st.tabs(["🚨 Variance Analytics", "📧 Email Generator", "📂 Data Management"])

# --- TAB 1: Analytics & Charts ---
with tab1:
    if not master_data.empty:
        df = master_data.copy()
        df['Market_Price'] = df['Material'].map(market_prices)
        df_valid = df[df['Market_Price'] > 0].copy()
        df_valid['Variance_%'] = ((df_valid['Current_UP'] - df_valid['Market_Price']) / df_valid['Market_Price'] * 100).round(2)
        
        st.subheader("📝 Variance Details")
        st.dataframe(df_valid.style.background_gradient(cmap='RdYlGn_r', subset=['Variance_%']), 
                     use_container_width=True, hide_index=True)
        
        st.divider()
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.markdown("##### 🎯 Negotiation Targets")
            fig1 = px.bar(df_valid.sort_values('Variance_%', ascending=False), x='Part_No', y='Variance_%', 
                          color='Variance_%', color_continuous_scale='RdYlGn_r', hover_data=['Vendor'])
            st.plotly_chart(fig1, use_container_width=True)
        with col_c2:
            st.markdown("##### 📉 Market History (3M)")
            api_mats = [m for m in df_valid['Material'].unique() if any(k.lower() in str(m).lower() for k in API_TICKERS.keys())]
            if api_mats:
                sel = st.selectbox("Select material:", api_mats)
                tick = next(v for k, v in API_TICKERS.items() if k.lower() in str(sel).lower())
                tr = fetch_trend_history(tick)
                if not tr.empty:
                    fig2 = px.line(tr, y='Close', title=f"Index: {tick}")
                    st.plotly_chart(fig2, use_container_width=True)

        st.divider()
        st.markdown("##### 💰 Price Positioning Matrix")
        max_v = max(df_valid['Market_Price'].max(), df_valid['Current_UP'].max()) * 1.1
        fig3 = px.scatter(df_valid, x='Market_Price', y='Current_UP', color='Material', 
                          hover_data=['Part_No', 'Vendor', 'Variance_%'], size_max=15, range_x=[0, max_v], range_y=[0, max_v])
        fig3.add_shape(type="line", x0=0, y0=0, x1=max_v, y1=max_v, line=dict(color="Black", dash="dash"))
        fig3.add_annotation(x=max_v*0.2, y=max_v*0.8, text="🔴 OVERPRICED", showarrow=False, font=dict(color="red", size=14))
        fig3.add_annotation(x=max_v*0.8, y=max_v*0.2, text="🟢 SAFE", showarrow=False, font=dict(color="green", size=14))
        st.plotly_chart(fig3, use_container_width=True)

# --- TAB 2: Email Generator ---
with tab2:
    st.subheader("📧 Smart Negotiation Assistant")
    if not df_valid.empty:
        red_zone = df_valid[df_valid['Variance_%'] >= 5].sort_values('Variance_%', ascending=False)
        green_zone = df_valid[df_valid['Variance_%'] < 5].sort_values('Variance_%', ascending=False)
        
        # Selection UI
        red_options = [f"{row['Part_No']} | {row['Vendor']} | Gap: +{row['Variance_%']}%" for _, row in red_zone.iterrows()]
        selected_red = st.multiselect("🔴 High Priority (Auto-selected)", options=red_options, default=red_options)
        
        green_options = [f"{row['Part_No']} | {row['Vendor']} | Gap: {row['Variance_%']}%" for _, row in green_zone.iterrows()]
        selected_green = st.multiselect("🟢 Stable Prices", options=green_options)
        
        final_ids = [s.split(" | ")[0] for s in (selected_red + selected_green)]
        
        if final_ids:
            selected_df = df_valid[df_valid['Part_No'].isin(final_ids)]
            v_contact = st.text_input("Vendor Contact:", selected_df['Vendor'].iloc[0] if not selected_df.empty else "Partner")
            
            email_text = f"Dear {v_contact} Team,\n\n"
            email_text += "We are reviewing our current procurement costs. Based on live market indices, the following parts show a gap that requires realignment:\n\n"
            for _, row in selected_df.iterrows():
                email_text += f"- {row['Part_No']} ({row['Material']}): Current ${row['Current_UP']} vs Market ${row['Market_Price']} (Gap: {row['Variance_%']}%)\n"
            email_text += "\nWe request a revised quotation to reflect these market shifts.\n\nBest Regards,\nProcurement Dept."
            st.text_area("Draft:", email_text, height=300)

# --- TAB 3: Management & Manual ---
with tab3:
    st.markdown(f"### 🔗 [✏️ Open Google Sheets](https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit)")
    if st.button("🔄 Force Data Sync"):
        st.cache_data.clear()
        st.rerun()
    
    st.divider()
    with st.expander("📖 User Manual & System Logic", expanded=True):
        st.markdown("""
        ### **1. Terminology**
        * **Current_UP**: Your active purchase price from the 'Quotation' tab.
        * **Market Price**: Benchmark from Yahoo API (🔥) or Sheet (📊).
        * **Variance (%)**: `(Current_UP - Market Price) / Market Price`.
        
        ### **2. Visual Guides**
        * **Bar Chart**: Priority targets for cost reduction.
        * **Scatter Plot**: Parts above the dash line are **Red Zone (Overpriced)**.
        
        ### **3. Data Management**
        * **Quotation Tab**: Ensure columns `Part Number`, `Material U/P`, and `Vendor` exist.
        * **Market Price Tab**: For materials like Zamak 3, update `Material` and `USD` columns.
        """)