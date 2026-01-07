import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import io

st.set_page_config(page_title="BMS Log Analyzer", layout="wide")

st.title("🔋 Battery Log & Error Analyzer")
st.markdown("Upload **Data Logs** (csv/log) AND/OR **Error Logs** (lines with `Error Code`). The app will auto-detect them.")

# --- Helper: Parse Log File ---
@st.cache_data
def parse_log_file(uploaded_file):
    metadata = {}
    content = uploaded_file.getvalue().decode("utf-8", errors='replace').splitlines()
    
    file_type = "unknown" # 'data' or 'error'
    header_index = 0
    df = None

    # 1. Detect File Type based on headers
    for i, line in enumerate(content[:50]): # Check first 50 lines
        line = line.strip()
        
        # Check for Data Log
        if line.startswith("Sample,DateTime"):
            file_type = "data"
            header_index = i
            break
        
        # Check for Error Log (Based on your snippet)
        if "Error Code,Error String" in line or "Time,LogCaption,Error Code" in line:
            file_type = "error"
            header_index = i
            break
            
        # Parse Metadata (Data logs only)
        if '=' in line and file_type == "unknown":
            parts = line.split('=', 1)
            if len(parts) == 2:
                metadata[parts[0].strip()] = parts[1].strip()

    if file_type == "unknown":
        return "unknown", {}, None

    # 2. Parse DataFrame
    try:
        raw_data = "\n".join(content[header_index:])
        df = pd.read_csv(io.StringIO(raw_data))
        
        # Cleanup Column Names (strip whitespace)
        df.columns = [c.strip() for c in df.columns]

        # DateTime Handling
        time_col = None
        if 'DateTime' in df.columns: time_col = 'DateTime'
        elif 'Time' in df.columns: time_col = 'Time'
        
        if time_col:
            df[time_col] = pd.to_datetime(df[time_col], errors='coerce')
            df = df.sort_values(by=time_col)
            
    except Exception as e:
        st.error(f"Error parsing {uploaded_file.name}: {e}")
        return "error_parsing", {}, None
        
    return file_type, metadata, df

# --- Main App Logic ---
uploaded_files = st.file_uploader(
    "Upload Files", 
    type=['log', 'csv', 'txt'], 
    accept_multiple_files=True
)

data_logs = {}
error_logs = {}

if uploaded_files:
    for file in uploaded_files:
        ftype, meta, df = parse_log_file(file)
        if ftype == "data":
            data_logs[file.name] = {"meta": meta, "df": df}
        elif ftype == "error":
            error_logs[file.name] = df
        else:
            st.warning(f"Skipped {file.name}: Format not recognized.")

    # ==========================================
    # 1. ERROR LOG ANALYSIS (Communication Errors)
    # ==========================================
    if error_logs:
        st.divider()
        st.header("⚠️ Communication Error Analysis")
        
        for name, df_err in error_logs.items():
            with st.expander(f"Error File: {name}", expanded=True):
                # Stats
                total_errs = len(df_err)
                unique_codes = df_err['Error Code'].unique() if 'Error Code' in df_err.columns else []
                
                c1, c2, c3 = st.columns(3)
                c1.metric("Total Errors", total_errs)
                c2.metric("Unique Error Codes", len(unique_codes))
                
                # Plot Frequency of Error Codes
                if 'Error Code' in df_err.columns:
                    # Count occurrences
                    err_counts = df_err['Error Code'].value_counts().reset_index()
                    err_counts.columns = ['Error Code', 'Count']
                    
                    fig_err = px.bar(err_counts, x='Error Code', y='Count', 
                                     title=f"Error Frequency in {name}", 
                                     text='Count', color='Count')
                    st.plotly_chart(fig_err, use_container_width=True)
                
                # Show Timeline of Errors if Time exists
                if 'Time' in df_err.columns:
                    st.subheader("Error Timeline")
                    # Scatter plot of errors over time
                    fig_time = px.scatter(df_err, x='Time', y='Error Code', 
                                          color='LogCaption', 
                                          hover_data=['Error String'],
                                          title="Errors over Time")
                    st.plotly_chart(fig_time, use_container_width=True)

                st.dataframe(df_err, height=200)

    # ==========================================
    # 2. DATA LOG ANALYSIS (Voltage/Current)
    # ==========================================
    if data_logs:
        st.divider()
        st.header("📈 Data Log Analysis")
        
        # File Selector for Detail View
        selected_file = st.selectbox("Select Data Log", list(data_logs.keys()))
        data = data_logs[selected_file]
        df = data['df']
        
        # --- Internal Safety Flags Checker ---
        # Checks columns like SafetyStat, PFStat for non-zero values
        st.subheader("Internal Safety Flags (BMS Registers)")
        flag_cols = [c for c in df.columns if 'Stat' in c or 'Alert' in c]
        active_flags = []
        
        for col in flag_cols:
            # Check if column has any non-zero values (assuming hex or int)
            # Some logs use hex strings like '0x00', others int 0
            try:
                # Convert to numeric, errors='coerce' turns hex strings to NaN usually, 
                # so we might need to handle hex explicitly if it's string 0x...
                is_nonzero = False
                if df[col].dtype == object:
                    # Check for hex strings that aren't 0x0 or 0x0000
                    unique_vals = df[col].unique()
                    for v in unique_vals:
                        if str(v) not in ['0', '0x0', '0x00', '0x0000', '0000', '00']:
                            is_nonzero = True
                            break
                else:
                    if (df[col] != 0).any():
                        is_nonzero = True
                
                if is_nonzero:
                    active_flags.append(col)
            except:
                pass

        if active_flags:
            st.error(f"⚠️ Non-zero Safety/Status Flags detected in: {', '.join(active_flags)}")
            # Plot specific flag over time
            flag_to_plot = st.selectbox("Visualize Flag", active_flags)
            fig_flag = px.scatter(df, x='DateTime', y=flag_to_plot, title=f"{flag_to_plot} Status Over Time")
            st.plotly_chart(fig_flag, use_container_width=True)
        else:
            st.success("No internal Safety/Permanent Fail flags detected (All 0).")

        # --- Standard Plots ---
        tab1, tab2, tab3 = st.tabs(["⚡ Voltage & Current", "🔋 Cell Balancing", "🌡️ Temp & Power"])
        
        with tab1:
            fig_vi = go.Figure()
            fig_vi.add_trace(go.Scatter(x=df['DateTime'], y=df['Voltage']/1000, name="Pack Voltage (V)", line=dict(color='blue')))
            fig_vi.add_trace(go.Scatter(x=df['DateTime'], y=df['Current']/1000, name="Current (A)", line=dict(color='red'), yaxis='y2'))
            fig_vi.update_layout(
                yaxis=dict(title="Voltage (V)"),
                yaxis2=dict(title="Current (A)", overlaying='y', side='right'),
                hovermode="x unified",
                legend=dict(x=0, y=1.1, orientation='h')
            )
            st.plotly_chart(fig_vi, use_container_width=True)

        with tab2:
            cell_cols = [c for c in df.columns if c.startswith('CellVolt')]
            if cell_cols:
                # Normalize cells to see drift
                normalize = st.checkbox("Normalize (Subtract Mean)")
                if normalize:
                    df_cells = df[cell_cols].sub(df[cell_cols].mean(axis=1), axis=0)
                    title = "Cell Voltage Deviation from Average (mV)"
                else:
                    df_cells = df[cell_cols]
                    title = "Cell Voltages (mV)"
                
                fig_cells = px.line(df, x='DateTime', y=df_cells.columns, title=title)
                st.plotly_chart(fig_cells, use_container_width=True)
            else:
                st.info("No Cell Voltage data found.")

        with tab3:
            col1, col2 = st.columns(2)
            with col1:
                 # Temp
                temp_cols = [c for c in df.columns if 'Temp' in c and 'Range' not in c]
                if temp_cols:
                    fig_temp = px.line(df, x='DateTime', y=temp_cols, title="Temperatures (°C)")
                    st.plotly_chart(fig_temp, use_container_width=True)
            with col2:
                # Power (Voltage * Current)
                df['Power_W'] = (df['Voltage']/1000) * (df['Current']/1000)
                fig_pwr = px.area(df, x='DateTime', y='Power_W', title="Power (Watts)")
                st.plotly_chart(fig_pwr, use_container_width=True)

else:
    st.info("Please upload your Log files (.log, .csv) to begin.")
    
