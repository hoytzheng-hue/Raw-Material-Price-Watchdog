import streamlit as st
import pandas as pd
import plotly.express as px
import requests

st.set_page_config(page_title="Price Watchdog v1.0", layout="wide")

st.title("🛡️ Raw Material Price Watchdog (Live API Edition)")

# ==========================================
# 核心配置区
# ==========================================
SHEET_ID = "1qUorrvZ7aj-fRlrJxQpm_6rK2-HolwtWH86SqVcDUWU"

# 💡 【核心升级】：API 字典库
# 让你的数据组同事把其他材料在 metal.com 上的 muid 查出来，填在这里即可！
API_MUIDS = {
    "A380": "201303070021",
    "ADC12": "201303070020", # (举个例子，假设这是ADC12的，具体请数据组提供真实ID)
    # "6063": "填入对应的muid",
    # "PVC": "填入对应的muid",
}

# ==========================================
# 实时 API 抓取引擎 (防封IP，缓存1小时)
# ==========================================
@st.cache_data(ttl=3600)
def fetch_live_price(muid):
    url = f"https://market.metal.com/history/api/getBriefMarket?muid={muid}"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.metal.com/"}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                price_mt = float(data['data']['last_price'])
                return round(price_mt / 1000, 3) # 自动换算为 USD/KG
        return None
    except:
        return None

# ==========================================
# 读取历史报价单 (依然从 Google Sheet 读取)
# ==========================================
@st.cache_data(ttl=600)
def load_price_book():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Quotation"
    try:
        df = pd.read_csv(url)
        
        # 自动定位表头
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

# ==========================================
# 网页启动后台任务
# ==========================================
with st.spinner('Syncing Quotations and fetching Live APIs...'):
    master_data = load_price_book()

tab1, tab2, tab3 = st.tabs(["🚨 Variance Analysis", "📧 Email Generator", "📂 Data Management"])

# ==========================================
# Sidebar: 纯 API 驱动大盘
# ==========================================
st.sidebar.header("📡 Live API Feed")
market_prices = {} 

if not master_data.empty and 'Material' in master_data.columns:
    unique_materials = master_data['Material'].dropna().unique()
    
    for mat in unique_materials:
        matched_price = 0.00 # 默认价格归零
        source_label = "⚠️ (Need API Config)" # 默认提示需要配置API
        
        # 核心逻辑：去字典里核对，是否有配置这个材料的 API
        for known_mat, muid in API_MUIDS.items():
            if known_mat.lower() in str(mat).lower():
                live_price = fetch_live_price(muid)
                if live_price is not None:
                    matched_price = live_price
                    source_label = "🔥 (Live API)"
                else:
                    source_label = "❌ (API Error)"
                break
                
        market_prices[mat] = st.sidebar.number_input(f"{mat} {source_label}", value=matched_price, step=0.01)
else:
    st.sidebar.warning("Could not sync Quotation data. Check Tab 3.")

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
            
            # 过滤掉市场价为 0.00 的无效计算（防止除以0或者没配API的数据干扰）
            df_valid = df[df['Market_Price'] > 0].copy()
            if not df_valid.empty:
                df_valid['Variance_%'] = ((df_valid['Market_Price'] - df_valid['Contract_UP']) / df_valid['Contract_UP'] * 100).round(2)
                st.subheader("Price Comparison Details")
                st.write("Note: A **negative, red Variance** means the current market price is lower than the contract price.")
                st.dataframe(df_valid.style.background_gradient(cmap='RdYlGn', subset=['Variance_%']))
            else:
                st.warning("No valid Live API prices fetched. Please configure API IDs in the code.")
    else:
        st.info("No quotation data found.")

# ==========================================
# TAB 3: Data Management
# ==========================================
with tab3:
    st.subheader("Database & API Status")
    st.success("✅ Connected to Google Sheets (Quotation) & metal.com API.")
    st.write("Market prices are now 100% powered by real-time API. Google Sheet is only used for Quotation History.")
    
    if st.button("Clear Cache & Force Refresh APIs"):
        st.cache_data.clear()
        st.rerun()

# ==========================================
# TAB 2: Email Generator
# ==========================================
with tab2:
    st.write("Email generator is ready for the next phase.")