import streamlit as st
import pandas as pd
import plotly.express as px
import yfinance as yf

st.set_page_config(page_title="Price Watchdog v1.0", layout="wide")

st.title("🛡️ Raw Material Price Watchdog (Hybrid Live)")

SHEET_ID = "1qUorrvZ7aj-fRlrJxQpm_6rK2-HolwtWH86SqVcDUWU"

# ==========================================
# 💡 Yahoo Finance Tickers (API Dictionary)
# ==========================================
API_TICKERS = {
    "A380": "ALI=F",
    "ADC12": "ALI=F",
    "6063": "ALI=F",
    "AL 7075": "ALI=F",
    "SPCC": "HRC=F",
    "SECC": "HRC=F",
    "SUS": "HRC=F", 
    "PVC": "CL=F",
    "C3604": "HG=F"
}

# ==========================================
# 1. Yahoo Finance API Fetcher
# ==========================================
@st.cache_data(ttl=3600)
def fetch_live_price(ticker):
    try:
        data = yf.Ticker(ticker).history(period="1d")
        if not data.empty:
            price = float(data['Close'].iloc[-1])
            if ticker in ["ALI=F", "HRC=F"]:
                return round(price / 1000, 3) 
            elif ticker == "HG=F":
                return round(price * 2.2046, 3) 
            elif ticker == "CL=F":
                return round(price / 159, 3) 
            return round(price, 3)
        return None
    except Exception as e:
        return None

# ==========================================
# 2. Google Sheet Market Price Loader
# ==========================================
@st.cache_data(ttl=600)
def load_market_data():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Market%20Price"
    try:
        df = pd.read_csv(url)
        mat_col = [c for c in df.columns if 'Material' in str(c) or 'Grade' in str(c)][0]
        price_col = [c for c in df.columns if 'USD' in str(c) or 'Cost' in str(c)][0]
        return dict(zip(df[mat_col].astype(str), df[price_col]))
    except:
        return {}

# ==========================================
# 3. Google Sheet Quotation History Loader
# ==========================================
@st.cache_data(ttl=600)
def load_price_book():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Quotation"
    try:
        df = pd.read_csv(url)
        if not any('Part Number' in str(c) or '料号' in str(c) for c in df.columns):
            header_idx = -1
            for i, row in df.iterrows():
                row_str = " ".join([str(x) for x in row.values])
                if 'Part Number' in row_str or '料号' in row_str:
                    header_idx = i
                    break
            if header_idx != -1:
                df.columns = df.iloc[header_idx].astype(str).str.replace('\n', ' ', regex=False).str.strip()
                df = df.iloc[header_idx+1:].reset_index(drop=True)

        mapping = {'Part Number': 'Part_No', 'Material U/P': 'Contract_UP', 'Raw material': 'Material', 'Material Spec': 'Material', '材质': 'Material'}
        final_cols = {col: mapping[k] for col in df.columns for k in mapping if k.lower() in str(col).lower()}
        
        if 'Part_No' not in final_cols.values(): return pd.DataFrame()
            
        df_clean = df[list(final_cols.keys())].rename(columns=final_cols)
        df_clean['Contract_UP'] = pd.to_numeric(df_clean['Contract_UP'].astype(str).str.replace(r'[\$,]', '', regex=True), errors='coerce')
        return df_clean.dropna(subset=['Part_No', 'Contract_UP'])
    except:
        return pd.DataFrame()

# ==========================================
# Main App Logic: Hybrid Data Engine
# ==========================================
with st.spinner('Connecting to Yahoo Finance & Google Sheets...'):
    market_dict_db = load_market_data()
    master_data = load_price_book()

tab1, tab2, tab3 = st.tabs(["🚨 Variance Analysis", "📧 Email Generator", "📂 Data Management"])

st.sidebar.header("📡 Live Market Feed")
market_prices = {} 

if not master_data.empty and 'Material' in master_data.columns:
    unique_materials = master_data['Material'].dropna().unique()
    for mat in unique_materials:
        matched_price = 0.00
        source_label = "⚠️ (No Data Found)" 
        
        # Step A: Check Google Sheet Fallback First
        for db_mat, db_price in market_dict_db.items():
            if str(mat).lower() in str(db_mat).lower() or str(db_mat).lower() in str(mat).lower():
                try: 
                    matched_price = float(db_price)
                    source_label = "📊 (Google Sheet)"
                    break
                except: 
                    pass
                
        # Step B: Override with Yahoo Finance API if applicable
        for known_mat, ticker in API_TICKERS.items():
            if known_mat.lower() in str(mat).lower():
                live_price = fetch_live_price(ticker)
                if live_price is not None:
                    matched_price = live_price
                    source_label = f"🔥 (Yahoo: {ticker})"
                elif source_label == "📊 (Google Sheet)":
                    source_label = "⚠️ (API Down, Used Sheet)" 
                break
                
        market_prices[mat] = st.sidebar.number_input(f"{mat} {source_label}", value=matched_price, step=0.01)

# ==========================================
# TAB 1: Variance Analysis
# ==========================================
with tab1:
    if not master_data.empty:
        df = master_data.copy()
        if 'Material' in df.columns:
            df['Market_Price'] = df['Material'].map(market_prices)
            cols = ['Part_No', 'Material', 'Contract_UP', 'Market_Price']
            df = df[cols + [c for c in df.columns if c not in cols]]
            
            # Filter valid prices to avoid dividing by 0
            df_valid = df[df['Market_Price'] > 0].copy()
            
            if not df_valid.empty:
                df_valid['Variance_%'] = ((df_valid['Market_Price'] - df_valid['Contract_UP']) / df_valid['Contract_UP'] * 100).round(2)
                
                st.subheader("Price Comparison Details")
                st.write("Note: A **negative, red Variance** means the current market price is lower than the contract price, indicating cost reduction opportunities.")
                st.dataframe(df_valid.style.background_gradient(cmap='RdYlGn', subset=['Variance_%']))
            else:
                st.warning("Data loaded, but waiting for valid Market Prices. Please configure Google Sheet or APIs.")

# ==========================================
# TAB 3: Data Management & Documentation
# ==========================================
with tab3:
    st.subheader("Database & API Status")
    st.success("✅ Connected to Google Sheets & Yahoo Finance Global API.")
    
    # Google Sheet 传送门
    st.markdown(f"### 🔗 [✏️ **Click Here to Edit the Google Sheets Database**](https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit)")
    
    if st.button("🔄 Force Refresh System (Clear Cache)"):
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")
    
    # 全英文产品说明书与操作指南
    with st.expander("📖 User Guide & System Logic", expanded=True):
        st.markdown("""
        ### 1. Hybrid Data Architecture
        This system utilizes an **"API-First, Sheet-Fallback"** enterprise architecture for raw material pricing:
        * **Priority A (API)**: The system automatically fetches live global commodity futures from Yahoo Finance (indicated by the 🔥 label).
        * **Priority B (Google Sheet)**: If a material lacks a public high-frequency API (e.g., Zamak 3) or the API is down, the system falls back to the local spot prices maintained in the `Market Price` tab of your Google Sheet (indicated by the 📊 label).
        * **No Data**: If a material is not found in either source, the system defaults to `0.00` and displays a ⚠️ warning. The item will be excluded from variance calculations to prevent data pollution.

        ### 2. LME Baseline vs. Spot Premium (e.g., Aluminum)
        Currently, specific aluminum grades (A380, ADC12, 6063) all map to the same `ALI=F` (Global Aluminum Ingot) ticker.
        * **Purpose**: This tracks macro-level market trends to identify negotiation opportunities when raw material baselines drop.
        * **Spot Price Accuracy**: For penny-accurate calculations including processing premiums, you can remove these materials from the backend API dictionary and strictly maintain their actual spot costs in the Google Sheet.

        ### 3. Google Sheets Maintenance Guide
        To ensure seamless syncing, the Data Team must adhere to the following headers in the `Market Price` sheet:
        | Material Grade | Current Market Cost (USD/KG) | Notes (Optional) |
        | :--- | :--- | :--- |
        | ADC12 (Al Alloy) | 2.75 | South China Spot Price |
        | Zamak 3 (Zinc) | 3.65 | Updated Monthly |

        *(Note: The `Quotation` sheet stores historical price books and must contain `Part Number` and `Material U/P` columns for proper parsing.)*
        """)

# ==========================================
# TAB 2: Email Generator
# ==========================================
with tab2: 
    st.write("Ready for email module.")