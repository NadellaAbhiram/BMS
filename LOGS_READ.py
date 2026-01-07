import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import io

st.set_page_config(page_title="BMS Multi-Log Visualizer", layout="wide")

st.title("🔋 Battery Log Comparator")
st.markdown("Upload multiple **bq40z80** log files to compare performance or analyze a single run.")

# --- Helper: Parse Log File ---
@st.cache_data
def parse_log_file(uploaded_file):
    metadata = {}
    content = uploaded_file.getvalue().decode("utf-8", errors='replace').splitlines()
    csv_start_index = 0
    header_found = False

    for i, line in enumerate(content):
        line = line.strip()
        if not header_found and '=' in line:
            parts = line.split('=', 1)
            if len(parts) == 2:
                metadata[parts[0].strip()] = parts[1].strip()
        if line.startswith("Sample,DateTime"):
            header_found = True
            csv_start_index = i
            break
            
    if not header_found:
        return None, None

    df = pd.read_csv(io.StringIO("\n".join(content[csv_start_index:])))
    
    # Cleanup and conversions
    if 'DateTime' in df.columns:
        df['DateTime'] = pd.to_datetime(df['DateTime'], errors='coerce')
    
    # Create a relative time column (Minutes) for easier comparison across files
    if 'ElapsedTime' in df.columns:
        df['Time (Min)'] = df['ElapsedTime'] / 60
    elif 'DateTime' in df.columns:
        start_time = df['DateTime'].iloc[0]
        df['Time (Min)'] = (df['DateTime'] - start_time).dt.total_seconds() / 60
        
    return metadata, df

# --- 1. File Uploader (Accepts Multiple) ---
uploaded_files = st.file_uploader(
    "Upload Log Files (.log, .csv)", 
    type=['log', 'csv', 'txt'], 
    accept_multiple_files=True  # <--- ENABLE MULTIPLE FILES
)

data_store = {}

if uploaded_files:
    # Parse all files
    for file in uploaded_files:
        meta, df = parse_log_file(file)
        if df is not None:
            data_store[file.name] = {"meta": meta, "df": df}
        else:
            st.error(f"Could not parse {file.name}")

    if data_store:
        # --- 2. Comparison View (If >1 file) ---
        if len(data_store) > 1:
            st.subheader("📊 Comparison Overlay")
            
            comp_metric = st.selectbox("Metric to Compare", 
                                       ['Voltage', 'Current', 'Temperature', 'RSOC', 'CellVolt1'])
            
            # Use 'Time (Min)' for x-axis to align different start times
            fig_comp = go.Figure()
            for name, data in data_store.items():
                # Check if metric needs scaling (e.g. mV to V)
                y_vals = data['df'][comp_metric]
                if comp_metric in ['Voltage', 'CellVolt1']: 
                    y_vals = y_vals / 1000
                elif comp_metric == 'Current':
                    y_vals = y_vals / 1000
                    
                fig_comp.add_trace(go.Scatter(
                    x=data['df']['Time (Min)'], 
                    y=y_vals, 
                    name=name,
                    mode='lines'
                ))
                
            fig_comp.update_layout(
                title=f"{comp_metric} Comparison over Time",
                xaxis_title="Duration (Minutes)",
                yaxis_title=comp_metric,
                hovermode="x unified"
            )
            st.plotly_chart(fig_comp, use_container_width=True)
            st.divider()

        # --- 3. Single File Deep Dive ---
        st.subheader("🔍 Single File Analysis")
        selected_file = st.selectbox("Select File to Inspect", list(data_store.keys()))
        
        current_data = data_store[selected_file]
        df_curr = current_data['df']
        meta_curr = current_data['meta']

        # Sidebar Metadata
        with st.sidebar:
            st.header(f"Metadata: {selected_file}")
            for k, v in meta_curr.items():
                st.text(f"{k}: {v}")

        # Summary Metrics
        last_row = df_curr.iloc[-1]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("End Voltage", f"{last_row.get('Voltage', 0)/1000:.2f} V")
        c2.metric("End RSOC", f"{last_row.get('RSOC', 0)} %")
        c3.metric("Max Temp", f"{df_curr['Temperature'].max():.1f} °C")
        c4.metric("Discharge Capacity", f"{df_curr.get('Unusable', 0)} mAh") # Placeholder if standard col missing

        # Main Plots
        tab1, tab2 = st.tabs(["Voltage/Current", "Cells"])
        
        with tab1:
            fig_vi = go.Figure()
            fig_vi.add_trace(go.Scatter(x=df_curr['DateTime'], y=df_curr['Voltage']/1000, name="Voltage (V)", line=dict(color='blue')))
            fig_vi.add_trace(go.Scatter(x=df_curr['DateTime'], y=df_curr['Current']/1000, name="Current (A)", line=dict(color='red'), yaxis='y2'))
            fig_vi.update_layout(
                yaxis=dict(title="Voltage (V)"),
                yaxis2=dict(title="Current (A)", overlaying='y', side='right'),
                hovermode="x unified"
            )
            st.plotly_chart(fig_vi, use_container_width=True)
            
        with tab2:
            cell_cols = [c for c in df_curr.columns if c.startswith('CellVolt')]
            if cell_cols:
                fig_cells = px.line(df_curr, x='DateTime', y=cell_cols, title="Cell Voltages")
                st.plotly_chart(fig_cells, use_container_width=True)
            else:
                st.info("No Cell Data")

else:
    st.info("Please upload one or more .log files to begin.")
  
