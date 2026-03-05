import streamlit as st
import pandas as pd
import plotly.express as px
import yfinance as yf

st.set_page_config(page_title="Price Watchdog v1.0", layout="wide")

st.title("🛡️ Raw Material Price Watchdog (Visual Analytics)")

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
# 1. API 与 数据抓取模块
# ==========================================
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

# 专门用于抓取 3个月历史走势 的新函数
@st.cache_data(ttl=86400) # 缓存一天
def fetch_trend_history(ticker):
    try:
        hist = yf.Ticker(ticker).history(period="3mo")
        return hist[['Close']]
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
                row_str = " ".join([str(x) for x in row.values])
                if 'Part Number' in row_str or '料号' in row_str:
                    header_idx = i; break
            if header_idx != -1:
                df.columns = df.iloc[header_idx].astype(str).str.replace('\n', ' ', regex=False).str.strip()
                df = df.iloc[header_idx+1:].reset_index(drop=True)

        mapping = {'Part Number': 'Part_No', 'Material U/P': 'Contract_UP', 'Raw material': 'Material', 'Material Spec': 'Material', '材质': 'Material'}
        final_cols = {col: mapping[k] for col in df.columns for k in mapping if k.lower() in str(col).lower()}
        if 'Part_No' not in final_cols.values(): return pd.DataFrame()
        df_clean = df[list(final_cols.keys())].rename(columns=final_cols)
        df_clean['Contract_UP'] = pd.to_numeric(df_clean['Contract_UP'].astype(str).str.replace(r'[\$,]', '', regex=True), errors='coerce')
        return df_clean.dropna(subset=['Part_No', 'Contract_UP'])
    except: return pd.DataFrame()

# ==========================================
# 网页主逻辑
# ==========================================
with st.spinner('Loading APIs and Data...'):
    market_dict_db = load_market_data()
    master_data = load_price_book()

tab1, tab2, tab3 = st.tabs(["🚨 Variance Analytics", "📧 Email Generator", "📂 Data Management"])

# 侧边栏
st.sidebar.header("📡 Live Market Feed")
market_prices = {} 
if not master_data.empty and 'Material' in master_data.columns:
    for mat in master_data['Material'].dropna().unique():
        matched_price, source_label = 0.00, "⚠️ (No Data)"
        for db_mat, db_price in market_dict_db.items():
            if str(mat).lower() in str(db_mat).lower() or str(db_mat).lower() in str(mat).lower():
                try: matched_price, source_label = float(db_price), "📊 (Google Sheet)"; break
                except: pass
        for known_mat, ticker in API_TICKERS.items():
            if known_mat.lower() in str(mat).lower():
                live_price = fetch_live_price(ticker)
                if live_price is not None: matched_price, source_label = live_price, f"🔥 (Yahoo: {ticker})"
                elif source_label == "📊 (Google Sheet)": source_label = "⚠️ (API Down, Used Sheet)"
                break
        market_prices[mat] = st.sidebar.number_input(f"{mat} {source_label}", value=matched_price, step=0.01)

# ==========================================
# TAB 1: Variance Analytics (图表大升级)
# ==========================================
with tab1:
    if not master_data.empty and 'Material' in master_data.columns:
        df = master_data.copy()
        df['Market_Price'] = df['Material'].map(market_prices)
        cols = ['Part_No', 'Material', 'Contract_UP', 'Market_Price']
        df = df[cols + [c for c in df.columns if c not in cols]]
        df_valid = df[df['Market_Price'] > 0].copy()
        
        if not df_valid.empty:
            df_valid['Variance_%'] = ((df_valid['Market_Price'] - df_valid['Contract_UP']) / df_valid['Contract_UP'] * 100).round(2)
            
            # 1. 核心数据表
            st.subheader("📝 Variance Details (Data Table)")
            st.dataframe(df_valid.style.background_gradient(cmap='RdYlGn', subset=['Variance_%']), use_container_width=True)
            
            st.markdown("---")
            st.subheader("📊 Visual Analytics Dashboard")
            
            # 将屏幕分为左右两栏显示图表
            col1, col2 = st.columns(2)
            
            # 图表 1: 降价谈判优先级 (左侧)
            with col1:
                st.markdown("##### 🎯 Negotiation Priority (Variance by Part)")
                df_chart = df_valid.sort_values(by='Variance_%')
                # 越红越是我们要优先杀价的
                fig1 = px.bar(df_chart, x='Part_No', y='Variance_%', color='Variance_%', 
                              color_continuous_scale=['#FF4B4B', '#F0F2F6', '#09AB3B'], 
                              labels={'Variance_%': 'Variance (%)', 'Part_No': 'Part Number'})
                fig1.update_layout(margin=dict(l=0, r=0, t=30, b=0))
                st.plotly_chart(fig1, use_container_width=True)
            
            # 图表 2: 3个月市场大盘走势 (右侧)
            with col2:
                st.markdown("##### 📉 3-Month Market Trend (API Source)")
                # 找出当前表里连接了 API 的材料
                api_mats = [m for m in df_valid['Material'].unique() if any(k.lower() in str(m).lower() for k in API_TICKERS.keys())]
                
                if api_mats:
                    selected_mat = st.selectbox("Select material to view historical trend:", api_mats, label_visibility="collapsed")
                    # 找出对应的 Ticker
                    matched_ticker = next(v for k, v in API_TICKERS.items() if k.lower() in str(selected_mat).lower())
                    
                    trend_df = fetch_trend_history(matched_ticker)
                    if not trend_df.empty:
                        fig2 = px.line(trend_df, x=trend_df.index, y='Close', 
                                       title=f"Global Trend for {matched_ticker}",
                                       labels={'Close': 'Commodity Index Price', 'Date': 'Date'})
                        fig2.update_traces(line_color='#FF4B4B')
                        fig2.update_layout(margin=dict(l=0, r=0, t=40, b=0))
                        st.plotly_chart(fig2, use_container_width=True)
                else:
                    st.info("No API-linked materials found to display trend.")
                    
            # 图表 3: 价格散点矩阵 (底部全宽)
            st.markdown("##### 💰 Price Position: Market vs Contract")
            st.caption("Parts located above the dotted line are overpriced compared to the current market benchmark.")
            fig3 = px.scatter(df_valid, x='Market_Price', y='Contract_UP', color='Material', 
                              hover_data=['Part_No', 'Variance_%'], size_max=15,
                              labels={'Market_Price': 'Live Market Price (USD/kg)', 'Contract_UP': 'Original Contract Price (USD/kg)'})
            
            # 添加一条 x=y 的虚线辅助线 (在这条线上的表示市场价=合同价)
            max_val = max(df_valid['Market_Price'].max(), df_valid['Contract_UP'].max())
            fig3.add_shape(type="line", line=dict(dash='dash', color='gray'), x0=0, y0=0, x1=max_val, y1=max_val)
            fig3.update_layout(margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig3, use_container_width=True)
            
        else:
            st.warning("Data loaded, but waiting for valid Market Prices. Please configure Google Sheet or APIs.")

# ==========================================
# TAB 3: Data Management & Documentation
# ==========================================
with tab3:
    st.subheader("Database & API Status")
    st.success("✅ Connected to Google Sheets & Yahoo Finance Global API.")
    st.markdown(f"### 🔗 [✏️ **Click Here to Edit the Google Sheets Database**](https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit)")
    
    if st.button("🔄 Force Refresh System (Clear Cache)"):
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")
    with st.expander("📖 User Guide & System Logic", expanded=True):
        st.markdown("""
        ### 1. Hybrid Data Architecture
        * **Priority A (API)**: Fetches live global commodity futures from Yahoo Finance (🔥 label).
        * **Priority B (Google Sheet)**: Falls back to local spot prices in `Market Price` tab (📊 label).
        """)

# ==========================================
# TAB 2: Email Generator
# ==========================================
with tab2: 
    st.write("Ready for email module.")