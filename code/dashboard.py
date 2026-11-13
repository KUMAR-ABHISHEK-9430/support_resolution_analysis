"""Three focused pages for an operational investigation, backed by qualified incidents."""
import json
import pandas as pd
import plotly.express as px
import streamlit as st
from analyze import summarize, grouped
from clean import PROCESSED, EVIDENCE

st.set_page_config(page_title='Closing the Resolution Gap',page_icon='◷',layout='wide')
st.markdown('''<style>.block-container{padding-top:4rem;max-width:1500px}
    h1{letter-spacing:-1px}
    [data-testid="stMetric"]{background:#eff5fa;color:#14263d;padding:16px;border-radius:10px;border:1px solid #cbd8e5}
    [data-testid="stMetric"] *{color:#14263d !important}
    </style>''',unsafe_allow_html=True)


@st.cache_data
def load():
    """Only small qualified tables are cached; raw snapshots load on demand."""
    return pd.read_parquet(PROCESSED/'incidents.parquet')


st.caption('ENTERPRISE SUPPORT WORKFLOW ANALYSIS · UCI SERVICENOW AUDIT RECORDS')
st.title('Closing the Resolution Gap')
st.write('Where should a support team investigate delays, handoffs and repeated resolution attempts?')
if not (PROCESSED/'incidents.parquet').exists():
    st.error('Run code/run.ps1 to download and prepare the dataset first.'); st.stop()
d=load()
page=st.sidebar.radio('Investigation',['Outcomes','Workflow patterns','Investigation priorities'])
categories=['All categories']+sorted(d.initial_category.dropna().unique().tolist())
selected=st.sidebar.selectbox('First-observed category',categories)
f=d if selected==categories[0] else d.loc[d.initial_category.eq(selected)]
st.sidebar.caption('Filters apply to outcome charts and counts. Peer comparisons and transition exports use the complete documented cohort and are labelled below.')
st.sidebar.markdown('[Dataset and CC BY 4.0 licence](https://archive.ics.uci.edu/dataset/498/incident%2Bmanagement%2Bprocess%2Benriched%2Bevent%2Blog)')
st.caption('Calendar elapsed hours · observational records from 2016–2017 · unknown values retained · no SLA or satisfaction KPI')
b=summarize(f)
c=st.columns(4)
for col,label,value in zip(c,['Incidents · counted once','Resolution median','Resolution p90','Recorded reopening'],
    [f'{b["incidents"]:,}',f'{b["resolution_median_hours"]:,.1f} h',f'{b["resolution_p90_hours"]:,.1f} h',f'{b["reopened_pct"]:.1f}%']):
    col.metric(label,value)
st.caption(f'Resolution eligible: {b["resolution_n"]:,}/{b["incidents"]:,}; reopen counter eligible: {b["reopen_eligible_n"]:,}. Missing endpoints are excluded from durations, never treated as zero.')

if page=='Outcomes':
    st.subheader('Typical and slow resolution times in high-volume categories')
    st.write('Compare the median with the 90th percentile to see where a typical ticket hides a much longer tail.')
    segments=grouped(f,['initial_category']).sort_values('incidents',ascending=False).head(12)
    segments['initial_category']=segments.initial_category.fillna('Unknown')
    long=segments.melt(id_vars=['initial_category','incidents','resolution_n'],value_vars=['resolution_median_hours','resolution_p90_hours'],var_name='metric',value_name='hours')
    long['metric']=long.metric.map({'resolution_median_hours':'Median','resolution_p90_hours':'90th percentile'})
    chart=px.bar(long,x='initial_category',y='hours',color='metric',barmode='group',
                 hover_data=['incidents','resolution_n'],labels={'initial_category':'First-observed category','hours':'Calendar elapsed hours'},
                 color_discrete_sequence=['#167d9a','#d58b36'])
    st.plotly_chart(chart,use_container_width=True)
    st.caption('The 12 busiest categories, not the 12 slowest. Hover for incident and eligible counts. The median is the midpoint; p90 is the duration at or below which roughly 90% of eligible incidents fall. These raw differences can reflect incident mix. See Investigation priorities for lower-volume categories with long tails, including Category 34.')
    a,z=st.columns([1,2])
    a.metric('Administrative closure median',f'{b["closure_median_hours"]:,.1f} h')
    a.caption(f'Closure eligible: {b["closure_n"]:,}. Closure and resolution describe different endpoints.')
    z.dataframe(segments[['initial_category','incidents','resolution_n','resolution_median_hours','resolution_p90_hours','reopened_pct']].rename(columns={'initial_category':'Category','incidents':'Incidents','resolution_n':'Eligible','resolution_median_hours':'Median h','resolution_p90_hours':'P90 h','reopened_pct':'Reopened %'}).round(1),hide_index=True,use_container_width=True)
    st.download_button('Download selected incident metrics',f.to_csv(index=False),'incident_metrics.csv','text/csv')

elif page=='Workflow patterns':
    st.subheader('Repeated handoffs are an investigation signal')
    workflow=f.copy()
    workflow['reassignment_band']=pd.cut(pd.to_numeric(workflow.reassignment_count),bins=[-1,0,1,2,4,float('inf')],labels=['0','1','2','3–4','5+']).astype(object).fillna('Unknown')
    distribution=grouped(workflow,['reassignment_band'])
    a,z=st.columns(2)
    with a:
        st.plotly_chart(px.bar(distribution,x='reassignment_band',y='incidents',labels={'reassignment_band':'Recorded reassignments'},color_discrete_sequence=['#167d9a']),use_container_width=True)
    with z:
        st.plotly_chart(px.line(distribution,x='reassignment_band',y='resolution_median_hours',markers=True,hover_data=['incidents','resolution_n'],labels={'reassignment_band':'Recorded reassignments','resolution_median_hours':'Median resolution hours'}),use_container_width=True)
    st.caption('Reassignment includes analyst changes and group changes. Difficult incidents may need specialists; an association does not establish that handoffs caused delay.')
    st.subheader('Comparable groups · complete cohort, unaffected by filter')
    peers=json.loads((EVIDENCE/'peer_comparisons.json').read_text())
    peer_table=pd.DataFrame([r for r in peers if r['variant']=='primary'])
    peer_table['exposure']=peer_table.exposure.map({'multi_reassignment':'2+ reassignments vs 0–1','reopened':'Reopened vs no reopening','knowledge_ever':'Recorded knowledge vs none'})
    st.dataframe(peer_table[['exposure','supported_strata','supported_n','coverage_pct','exposed_coverage_pct','comparison_coverage_pct','weighted_within_stratum_median_difference_hours']].rename(columns={'exposure':'Comparison','supported_strata':'Peer groups','supported_n':'Incidents','coverage_pct':'Coverage %','exposed_coverage_pct':'Exposed coverage %','comparison_coverage_pct':'Comparator coverage %','weighted_within_stratum_median_difference_hours':'Median contrast h'}).round(1),hide_index=True,use_container_width=True)
    st.caption('First-observed category × priority × opening month; ≥20 incidents in each arm. Weighted mean of within-stratum median differences, exposed minus comparison. Residual complexity and selection remain.')
    st.warning('Reopening comparison covers only one peer group: 22 reopened incidents and 951 others. It does not support a broad adjusted conclusion. Knowledge-use timing is unknown; no effectiveness claim follows.')
    st.subheader('Recurring observed group transitions · complete cohort')
    st.dataframe(pd.read_csv(EVIDENCE/'group_transitions.csv').head(8),hide_index=True,use_container_width=True)
    st.caption('Only adjacent, known groups at untied timestamps. This is an incomplete observed sequence, not a full routing trace or a team performance ranking.')

else:
    st.subheader('Start where investigative reach is substantial')
    p=grouped(f,['initial_category']).query('incidents >= 200')
    p['initial_category']=p.initial_category.fillna('Unknown')
    if len(p):
        p['label']=p.initial_category.where(p.initial_category.isin(['Category 34','Category 46']),'')
        chart=px.scatter(p,x='incidents',y='resolution_p90_hours',size='total_elapsed_incident_hours',color='reopened_pct',text='label',hover_name='initial_category',hover_data=['resolution_n','multi_reassignment_n'],color_continuous_scale=['#60a5fa','#8b5cf6','#db2777'],labels={'incidents':'Incident volume','resolution_p90_hours':'Resolution p90 · hours','reopened_pct':'Reopened %'})
        chart.update_traces(textposition='top center',marker=dict(opacity=0.95,line=dict(color='#64748b',width=0.8)))
        st.plotly_chart(chart,use_container_width=True)
        st.dataframe(p.sort_values('total_elapsed_incident_hours',ascending=False).head(6)[['initial_category','incidents','resolution_n','resolution_p90_hours','reopened_n','multi_reassignment_n','total_elapsed_incident_hours']].rename(columns={'initial_category':'Category','incidents':'Incidents','resolution_n':'Eligible','resolution_p90_hours':'P90 h','reopened_n':'Reopened','multi_reassignment_n':'2+ reassignments','total_elapsed_incident_hours':'Elapsed incident h'}).round(1),hide_index=True,use_container_width=True)
    st.caption('Categories with ≥200 incidents. Bubble size sums overlapping calendar durations, not labor effort, distinct customer waiting, or potential hours saved.')
    st.subheader('Inspect a real incident history')
    histories=pd.read_csv(EVIDENCE/'incident_histories.csv')
    options=histories[['example_type','number']].drop_duplicates()
    example_options=(options.example_type+' · '+options.number).tolist()
    default=next((i for i,x in enumerate(example_options) if x.startswith('priority_category')),0)
    option=st.selectbox('Audited examples',example_options,index=default)
    number=option.split(' · ')[1]
    h=histories.loc[histories.number.eq(number)]
    st.dataframe(h[['event_id','sys_updated_at','incident_state','assignment_group','sys_mod_count','reassignment_count','reopen_count','resolved_at','closed_at']],hide_index=True,use_container_width=True)
    st.caption('Endpoint dates are enriched into earlier rows. State update times need not match resolution dates. Exact state dwell, customer satisfaction and causal impact cannot be established.')

st.divider()
st.caption('Source: Amaral, Fantinato & Peres (2018), UCI Incident management process enriched event log, DOI 10.24432/C57S4H · CC BY 4.0. Analysis changes: parsed timestamps, qualified incident reconstruction and aggregation. Proposed investigations, no claimed business improvement.')
