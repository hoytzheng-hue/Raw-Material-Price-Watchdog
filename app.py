import streamlit as st
import pandas as pd
import plotly.express as px
import yfinance as yf
import io

# ==========================================
# MODULE A: SYSTEM SETUP & CONFIG
# ==========================================
st.set_page_config(page_title="Price Watchdog v1.2", layout="wide")
st.title("🛡️ Raw Material Price Watchdog (V1.0)")

SHEET_ID = "1qUorrvZ7aj-fRlrJxQpm_6rK2-HolwtWH86SqVcDUWU"

# API Tickers Mapping
API_TICKERS = {
    "A380": "ALI=F", "ADC12": "ALI=F", "6063": "ALI=F", "AL 7075": "ALI=F",
    "SPCC": "HRC=F", "SECC": "HRC=F", "SUS": "HRC=F", "PVC": "CL=F", "C3604": "HG=F"
}

# ==========================================
# MODULE B: CORE DATA ENGINES
# ==========================================

@st.cache_data(ttl=3600)
def fetch_live_price(ticker):
    """Fetch 1D Close price from Yahoo Finance."""
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
    """Fetch 3-month historical trend."""
    try: return yf.Ticker(ticker).history(period="3mo")[['Close']]
    except: return pd.DataFrame()

@st.cache_data(ttl=600)
def load_market_data():
    """Load benchmark prices from Google Sheets 'Market Price' tab."""
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Market%20Price"
    try:
        df = pd.read_csv(url)
        mat_col = [c for c in df.columns if 'Material' in str(c) or 'Grade' in str(c)][0]
        price_col = [c for c in df.columns if 'USD' in str(c) or 'Cost' in str(c)][0]
        return dict(zip(df[mat_col].astype(str), df[price_col]))
    except: return {}

@st.cache_data(ttl=600)
def load_price_book():
    """Load and clean current quotations from Google Sheets 'Quotation' tab."""
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Quotation"
    try:
        df = pd.read_csv(url)
        # Automatic header detection
        if not any('Part Number' in str(c) or '料号' in str(c) for c in df.columns):
            header_idx = -1
            for i, row in df.iterrows():
                if 'Part Number' in " ".join([str(x) for x in row.values]):
                    header_idx = i; break
            if header_idx != -1:
                df.columns = df.iloc[header_idx].astype(str).str.replace('\n', ' ', regex=False).str.strip()
                df = df.iloc[header_idx+1:].reset_index(drop=True)
        
        # Strictly map columns including Vendor
        mapping = {
            'Part Number': 'Part_No', 'Material U/P': 'Current_UP', 
            'Raw material': 'Material', 'Vendor': 'Vendor', '供应商': 'Vendor'
        }
        final_cols = {col: mapping[k] for col in df.columns for k in mapping if k.lower() in str(col).lower()}
        df_clean = df[list(final_cols.keys())].rename(columns=final_cols)
        
        # Clean price format (remove $ and ,)
        df_clean['Current_UP'] = pd.to_numeric(df_clean['Current_UP'].astype(str).str.replace(r'[\$,]', '', regex=True), errors='coerce')
        if 'Vendor' not in df_clean.columns: df_clean['Vendor'] = 'Unknown'
        
        return df_clean.dropna(subset=['Part_No', 'Current_UP'])
    except: return pd.DataFrame()

def smart_clean_file(uploaded_file):
    """Universal cleaning logic for arbitrary vendor files."""
    try:
        df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
        new_df = pd.DataFrame()
        col_map = {
            'Part_No': ['part', 'pn', '料号', '项目'],
            'Current_UP': ['price', 'cost', 'up', '单价', '金额'],
            'Material': ['material', 'spec', '材质', '原料'],
            'Vendor': ['vendor', 'supplier', '供应商', '厂家']
        }
        for target, keywords in col_map.items():
            for col in df.columns:
                if any(key in str(col).lower() for key in keywords):
                    new_df[target] = df[col]
                    break
        if 'Current_UP' in new_df.columns:
            new_df['Current_UP'] = pd.to_numeric(new_df['Current_UP'].astype(str).str.replace(r'[\$,]', '', regex=True), errors='coerce')
        return new_df
    except Exception as e:
        st.error(f"Cleaning Error: {e}")
        return pd.DataFrame()

# ==========================================
# MODULE C: UI & TABS
# ==========================================

# Pre-load data
market_dict_db = load_market_data()
master_data = load_price_book()

# Sidebar for live adjustments
st.sidebar.header("📡 Live Market Feed")
market_prices = {} 
if not master_data.empty:
    for mat in master_data['Material'].dropna().unique():
        p, label = 0.0, "⚠️ (No Data)"
        # Check Sheet first, then API
        for db_m, db_p in market_dict_db.items():
            if str(mat).lower() in str(db_m).lower(): p, label = float(db_p), "📊 (Sheet)"; break
        for k, v in API_TICKERS.items():
            if k.lower() in str(mat).lower():
                live = fetch_live_price(v)
                if live: p, label = live, f"🔥 (Yahoo: {v})"
                break
        market_prices[mat] = st.sidebar.number_input(f"{mat} {label}", value=p, step=0.01)

tab1, tab2, tab3, tab4 = st.tabs(["🚨 Variance Analytics", "📧 Email Generator", "📂 Data Management", "🚀 Data Smart-Uploader"])

# --- TAB 1: Analytics ---
with tab1:
    if not master_data.empty:
        df = master_data.copy()
        df['Market_Price'] = df['Material'].map(market_prices)
        df_valid = df[df['Market_Price'] > 0].copy()
        # Variance: Positive = Current Price is higher (NEGOTIATE)
        df_valid['Variance_%'] = ((df_valid['Current_UP'] - df_valid['Market_Price']) / df_valid['Market_Price'] * 100).round(2)
        
        st.subheader("📝 Real-time Variance Details")
        st.dataframe(df_valid.style.background_gradient(cmap='RdYlGn_r', subset=['Variance_%']), 
                     use_container_width=True, hide_index=True)
        
        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 🎯 Negotiation Targets")
            fig1 = px.bar(df_valid.sort_values('Variance_%', ascending=False), x='Part_No', y='Variance_%', 
                          color='Variance_%', color_continuous_scale='RdYlGn_r', hover_data=['Vendor'])
            st.plotly_chart(fig1, use_container_width=True)
        with c2:
            st.markdown("##### 📉 Market History (3M)")
            api_mats = [m for m in df_valid['Material'].unique() if any(k.lower() in str(m).lower() for k in API_TICKERS.keys())]
            if api_mats:
                sel_m = st.selectbox("Select material:", api_mats)
                tick = next(v for k, v in API_TICKERS.items() if k.lower() in str(sel_m).lower())
                tr_df = fetch_trend_history(tick)
                if not tr_df.empty:
                    fig2 = px.line(tr_df, y='Close', title=f"Trend: {tick}")
                    st.plotly_chart(fig2, use_container_width=True)

        st.divider()
        st.markdown("##### 💰 Price Positioning Matrix")
        max_v = max(df_valid['Market_Price'].max(), df_valid['Current_UP'].max()) * 1.1
        fig3 = px.scatter(df_valid, x='Market_Price', y='Current_UP', color='Material', 
                          hover_data=['Part_No', 'Vendor', 'Variance_%'], size_max=15, range_x=[0, max_v], range_y=[0, max_v])
        fig3.add_shape(type="line", x0=0, y0=0, x1=max_v, y1=max_v, line=dict(color="Black", dash="dash"))
        fig3.add_annotation(x=max_v*0.2, y=max_v*0.8, text="🔴 OVERPRICED (Negotiate!)", showarrow=False, font=dict(color="red", size=14))
        fig3.add_annotation(x=max_v*0.8, y=max_v*0.2, text="🟢 SAFE (Better than Market)", showarrow=False, font=dict(color="green", size=14))
        st.plotly_chart(fig3, use_container_width=True)

# --- TAB 2: Email Generator ---
with tab2:
    st.subheader("📧 Smart Negotiation Assistant")
    if not df_valid.empty:
        red_zone = df_valid[df_valid['Variance_%'] >= 5].sort_values('Variance_%', ascending=False)
        green_zone = df_valid[df_valid['Variance_%'] < 5].sort_values('Variance_%', ascending=False)
        
        red_opts = [f"{row['Part_No']} | {row['Vendor']} | +{row['Variance_%']}%" for _, row in red_zone.iterrows()]
        selected_red = st.multiselect("🔴 Priority: High Variance (Auto-selected)", options=red_opts, default=red_opts)
        
        green_opts = [f"{row['Part_No']} | {row['Vendor']} | {row['Variance_%']}%" for _, row in green_zone.iterrows()]
        selected_green = st.multiselect("🟢 Stable Prices", options=green_opts)
        
        f_ids = [s.split(" | ")[0] for s in (selected_red + selected_green)]
        if f_ids:
            sel_df = df_valid[df_valid['Part_No'].isin(f_ids)]
            v_contact = st.text_input("Vendor Contact Person:", sel_df['Vendor'].iloc[0])
            email_b = f"Dear {v_contact},\n\nOur system has identified a gap between our current unit prices and global market indices.\n\n"
            for _, row in sel_df.iterrows():
                email_b += f"- Part: {row['Part_No']} | Current: ${row['Current_UP']} | Market: ${row['Market_Price']} | Gap: {row['Variance_%']}%\n"
            email_b += "\nPlease provide a revised quotation reflecting these market shifts.\n\nRegards,\nProcurement Team"
            st.text_area("Email Draft:", email_b, height=300)

# --- TAB 4: Data Uploader ---
with tab4:
    st.subheader("🚀 Data Smart-Uploader")
    st.info("Upload any raw quotation (Excel/CSV). The system will auto-format it for Google Sheets.")
    up_file = st.file_uploader("Upload File", type=['csv', 'xlsx'])
    if up_file:
        cleaned_df = smart_clean_file(up_file)
        st.write("✨ **Cleaned Result Preview:**")
        st.dataframe(cleaned_df, use_container_width=True, hide_index=True)
        
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
            cleaned_df.to_excel(writer, index=False)
        st.download_button("📥 Download for Google Sheets", buf.getvalue(), "ready_to_paste.xlsx")

# --- TAB 3: Documentation ---
with tab3:
    st.subheader("📂 System Configuration")
    st.markdown(f"### 🔗 [✏️ Open Master Google Sheet](https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit)")
    if st.button("🔄 Clear Cache & Sync"):
        st.cache_data.clear()
        st.rerun()
    
    st.divider()
    with st.expander("📖 User Manual & Data Governance", expanded=True):
        st.markdown("""
        #### **1. Data Governance (STRICT)**
        - **Column Names**: Must contain `Part Number`, `Vendor`, `Material`, and `Material U/P`.
        - **Current UP**: Numeric only. No currency symbols like "$" or commas in the cell.
        - **Material**: Use API keywords (e.g., ADC12, A380, SPCC).

        #### **2. Visual Logic**
        - **Red Color**: Current Price > Market Price (Opportunity to save money).
        - **Green Color**: Current Price < Market Price (Competitive contract).
        - **Scatter Plot**: Top-left area is the "Negotiation Zone".
        """)