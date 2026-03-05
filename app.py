import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Price Watchdog v1.0", layout="wide")

st.title("🛡️ Raw Material Price Watchdog")

tab1, tab2, tab3 = st.tabs(["🚨 Variance Analysis", "📧 Email Generator", "📂 Data Management"])

# ==========================================
# TAB 3: 数据上传与解析 (升级了材料列抓取)
# ==========================================
with tab3:
    st.subheader("Upload Original Price Book")
    uploaded_file = st.file_uploader("Upload CSV", type="csv")
    
    if uploaded_file:
        encodings_to_try = ['utf-8', 'gb18030', 'utf-8-sig', 'latin1']
        successful_encoding = None
        preview = None
        
        for enc in encodings_to_try:
            try:
                uploaded_file.seek(0)
                preview = pd.read_csv(uploaded_file, header=None, nrows=50, encoding=enc)
                successful_encoding = enc
                break
            except Exception:
                continue
                
        if successful_encoding is None:
            st.error("文件编码特殊，请在Excel另存为UTF-8格式的CSV。")
        else:
            try:
                header_idx = 0
                for i, row in preview.iterrows():
                    row_str = " ".join([str(x) for x in row.values])
                    if 'Part Number' in row_str or '料号' in row_str:
                        header_idx = i
                        break
                
                uploaded_file.seek(0) 
                df = pd.read_csv(uploaded_file, header=header_idx, encoding=successful_encoding)
                df.columns = df.columns.astype(str).str.replace('\n', ' ', regex=False).str.strip()
                
                # 💡【核心升级】：加入了对 Raw Material 的模糊匹配
                mapping = {
                    'Part Number': 'Part_No', 
                    'Material U/P': 'Contract_UP', 
                    'Vendor': 'Supplier',
                    'Raw material': 'Material',  # 对应 Wisefull/XY 的表头
                    'Material Spec': 'Material',
                    '材质': 'Material'
                }
                
                final_cols = {}
                for col in df.columns:
                    for k in mapping:
                        if k.lower() in col.lower():
                            final_cols[col] = mapping[k]
                            break 
                
                if 'Part_No' not in final_cols.values():
                    st.error("找不到核心列 'Part Number'。")
                else:
                    df_clean = df[list(final_cols.keys())].rename(columns=final_cols)
                    df_clean['Contract_UP'] = pd.to_numeric(df_clean['Contract_UP'].astype(str).str.replace(r'[\$,]', '', regex=True), errors='coerce')
                    
                    st.session_state['master_data'] = df_clean.dropna(subset=['Part_No', 'Contract_UP'])
                    st.success("✅ 数据与原材料型号解析成功！")
                    
            except Exception as e:
                st.error(f"处理数据时出错: {e}")

# ==========================================
# 侧边栏：动态市场行情板
# ==========================================
st.sidebar.header("📡 Market Live Feed")
market_prices = {} # 用来装不同材料的市场价

if 'master_data' in st.session_state and 'Material' in st.session_state['master_data'].columns:
    st.sidebar.markdown("请更新以下**实时原材料价格 (USD/kg)**：")
    
    # 自动找出表格里所有不重复的原材料型号
    unique_materials = st.session_state['master_data']['Material'].dropna().unique()
    
    # 为每种材料自动生成一个输入框
    for mat in unique_materials:
        # 默认先给个 2.95，你可以自己调
        market_prices[mat] = st.sidebar.number_input(f"{mat}", value=2.95, step=0.01)
else:
    st.sidebar.info("上传数据后，此处将自动生成对应原材料的报价单。")
    universal_price = st.sidebar.number_input("Global Price (USD/kg)", value=2.95, step=0.01)

# ==========================================
# TAB 1: 分析图表
# ==========================================
with tab1:
    if 'master_data' in st.session_state:
        df = st.session_state['master_data'].copy()
        
        # 💡【核心升级】：根据每行零件的具体材质，去查字典填入对应的市场价
        if 'Material' in df.columns:
            df['Market_Price'] = df['Material'].map(market_prices)
            
            # 重新排一下列的顺序，把 Material 放在显眼的位置
            cols = ['Part_No', 'Material', 'Contract_UP', 'Market_Price']
            df = df[cols + [c for c in df.columns if c not in cols]]
        else:
            df['Market_Price'] = universal_price
            
        # 计算差异（负数表示市场比合同便宜 = 我们亏了，有杀价空间）
        df['Variance_%'] = ((df['Market_Price'] - df['Contract_UP']) / df['Contract_UP'] * 100).round(2)
        
        st.subheader("Price Comparison Details")
        st.write("注：Variance 为 **负数且标红**，代表当前市场价远低于当初的合同价，**存在杀价空间**。")
        
        # 显示带颜色的表格
        st.dataframe(df.style.background_gradient(cmap='RdYlGn', subset=['Variance_%']))
        
    else:
        st.warning("Please upload a file in Data Management first.")

# ==========================================
# TAB 2: 邮件生成
# ==========================================
with tab2:
    st.write("Email generator is ready for next phase.")