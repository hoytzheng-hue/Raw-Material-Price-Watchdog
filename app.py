import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Price Watchdog v1.0", layout="wide")

st.title("🛡️ Raw Material Price Watchdog (Cloud Sync)")

# ==========================================
# 云端数据库配置 (Google Sheets)
# ==========================================
SHEET_ID = "1qUorrvZ7aj-fRlrJxQpm_6rK2-HolwtWH86SqVcDUWU"

# 读取市场行情表 (对应名为 'Market Price' 的分页，空格用 %20 替代)
@st.cache_data(ttl=600)
def load_market_data():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Market%20Price"
    try:
        df_market = pd.read_csv(url)
        mat_col = [c for c in df_market.columns if 'Material' in str(c) or 'Grade' in str(c)][0]
        price_col = [c for c in df_market.columns if 'USD' in str(c) or 'Cost' in str(c)][0]
        return dict(zip(df_market[mat_col].astype(str), df_market[price_col]))
    except Exception as e:
        st.error(f"Error loading Market Price sheet: {e}")
        return {}

# 读取历史报价单 (对应名为 'Quotation' 的分页)
@st.cache_data(ttl=600)
def load_price_book():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Quotation"
    try:
        df = pd.read_csv(url)
        
        # 自动定位表头逻辑
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

        mapping = {
            'Part Number': 'Part_No', 
            'Material U/P': 'Contract_UP', 
            'Vendor': 'Supplier',
            'Raw material': 'Material',
            'Material Spec': 'Material',
            '材质': 'Material'
        }
        
        final_cols = {}
        for col in df.columns:
            for k in mapping:
                if k.lower() in str(col).lower():
                    final_cols[col] = mapping[k]
                    break 
        
        if 'Part_No' not in final_cols.values():
            return pd.DataFrame()
            
        df_clean = df[list(final_cols.keys())].rename(columns=final_cols)
        df_clean['Contract_UP'] = pd.to_numeric(df_clean['Contract_UP'].astype(str).str.replace(r'[\$,]', '', regex=True), errors='coerce')
        return df_clean.dropna(subset=['Part_No', 'Contract_UP'])
    except Exception as e:
        st.error(f"Error loading Quotation sheet: {e}")
        return pd.DataFrame()

# ----------------------------------------
# 网页启动时，自动在后台拉取数据
# ----------------------------------------
with st.spinner('Syncing data from Google Sheets...'):
    market_dict_db = load_market_data()
    master_data = load_price_book()

tab1, tab2, tab3 = st.tabs(["🚨 Variance Analysis", "📧 Email Generator", "📂 Data Management"])

# ==========================================
# Sidebar: Dynamic Market Board
# ==========================================
st.sidebar.header("📡 Market Live Feed")
market_prices = {} 

if not master_data.empty and 'Material' in master_data.columns:
    st.sidebar.markdown("Auto-matched Market Prices (USD/kg):")
    unique_materials = master_data['Material'].dropna().unique()
    
    for mat in unique_materials:
        matched_price = 2.95 
        for db_mat, db_price in market_dict_db.items():
            if str(mat).lower() in str(db_mat).lower() or str(db_mat).lower() in str(mat).lower():
                try:
                    matched_price = float(db_price)
                    break
                except:
                    pass
        market_prices[mat] = st.sidebar.number_input(f"{mat}", value=matched_price, step=0.01)
else:
    st.sidebar.warning("Could not sync data. Please check your Google Sheet tabs and permissions.")

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
            df['Variance_%'] = ((df['Market_Price'] - df['Contract_UP']) / df['Contract_UP'] * 100).round(2)
            
            st.subheader("Price Comparison Details")
            st.write("Note: A **negative, red Variance** means the current market price is lower than the contract price.")
            st.dataframe(df.style.background_gradient(cmap='RdYlGn', subset=['Variance_%']))
    else:
        st.info("Loading data or database is empty. Check Tab 3 for details.")

# ==========================================
# TAB 3: Data Management
# ==========================================
with tab3:
    st.subheader("Database Connection Status")
    st.success("✅ Connected to Google Sheets Database configured.")
    
    st.write("Your team no longer needs to upload CSVs here. The app will automatically sync with the cloud database.")
    st.markdown(f"[✏️ **Click Here to Edit the Google Sheets Database**](https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit)")
    
    if st.button("Manual Force Sync (强制刷新)"):
        st.cache_data.clear()
        st.rerun()

# ==========================================
# TAB 2: Email Generator
# ==========================================
with tab2:
    st.write("Email generator is ready for the next phase.")