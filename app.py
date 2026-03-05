import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Price Watchdog v1.0", layout="wide")

# --- 1. 侧边栏：实时行情 ---
st.sidebar.header("📡 Market Live Feed")
# 默认 2.85，你可以根据今天铝价手动改
live_price = st.sidebar.number_input("Current Market Price (USD/kg)", value=2.85)

st.title("🛡️ Raw Material Price Watchdog")

tab1, tab2, tab3 = st.tabs(["🚨 Variance Analysis", "📧 Email Generator", "📂 Data Management"])

# --- TAB 3: 数据上传（写实逻辑 - 终极装甲版） ---
with tab3:
    st.subheader("Upload Original Price Book")
    uploaded_file = st.file_uploader("Upload CSV", type="csv")
    
    if uploaded_file:
        # 建立一个编码测试清单：按最有可能的顺序排
        encodings_to_try = ['utf-8', 'gb18030', 'utf-8-sig', 'latin1']
        successful_encoding = None
        preview = None
        
        # --- 1. 终极编码探测循环 ---
        for enc in encodings_to_try:
            try:
                uploaded_file.seek(0) # 每次尝试前，把文件指针拨回开头
                preview = pd.read_csv(uploaded_file, header=None, nrows=50, encoding=enc)
                successful_encoding = enc
                break # 如果没报错，就立刻跳出循环！
            except Exception:
                continue # 如果报错了，就换下一个编码继续试
                
        if successful_encoding is None:
            st.error("文件编码过于特殊，无法自动解析。请在 Excel 中打开该文件，然后选择『另存为 -> CSV (UTF-8 逗号分隔)』后重新上传。")
        else:
            try:
                # --- 2. 自动找表头 ---
                header_idx = 0
                for i, row in preview.iterrows():
                    row_str = " ".join([str(x) for x in row.values])
                    if 'Part Number' in row_str or '料号' in row_str:
                        header_idx = i
                        break
                
                # --- 3. 读取完整数据 ---
                uploaded_file.seek(0) 
                df = pd.read_csv(uploaded_file, header=header_idx, encoding=successful_encoding)
                df.columns = df.columns.astype(str).str.replace('\n', ' ', regex=False).str.strip()
                
                # --- 4. 自动映射关键列 ---
                mapping = {'Part Number': 'Part_No', 'Material U/P': 'Contract_UP', 'Vendor': 'Supplier'}
                final_cols = {col: mapping[k] for col in df.columns for k in mapping if k in col}
                
                if len(final_cols) < 2:
                    st.error(f"成功读取文件 (编码: {successful_encoding})，但找不到 'Part Number' 和 'Material U/P' 列，请检查表头名是否匹配。")
                else:
                    df_clean = df[list(final_cols.keys())].rename(columns=final_cols)
                    df_clean['Contract_UP'] = pd.to_numeric(df_clean['Contract_UP'].astype(str).str.replace(r'[\$,]', '', regex=True), errors='coerce')
                    
                    # 存入 Session
                    st.session_state['master_data'] = df_clean.dropna(subset=['Part_No', 'Contract_UP'])
                    st.success(f"✅ Data Loaded Successfully! (Auto-detected encoding: {successful_encoding})")
                    st.dataframe(st.session_state['master_data'].head())
                    
            except Exception as e:
                st.error(f"处理数据时出错: {e}")

# --- TAB 1: 分析逻辑（连通 Tab 3） ---
with tab1:
    if 'master_data' in st.session_state:
        df = st.session_state['master_data'].copy()
        df['Market_Price'] = live_price
        # 计算差异百分比
        df['Variance_%'] = ((df['Market_Price'] - df['Contract_UP']) / df['Contract_UP'] * 100).round(2)
        
        st.subheader("Price Comparison Details")
        # 重点显示降价空间（Variance 为负数代表市场更便宜）
        st.dataframe(df.style.background_gradient(cmap='RdYlGn', subset=['Variance_%']))
        
        fig = px.bar(df, x='Part_No', y='Variance_%', title="Price Anomaly Heatmap")
        st.plotly_chart(fig)
    else:
        st.warning("Please upload a file in Data Management first.")

# --- TAB 2: 邮件生成 ---
with tab2:
    if 'master_data' in st.session_state:
        selected = st.selectbox("Select Part", st.session_state['master_data']['Part_No'])
        # 自动生成基于真实数据的邮件...
        st.write(f"Email draft for {selected} is ready.")