"""Protect consequential reconstruction rules with small, auditable histories."""
import sys
from pathlib import Path
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from clean import reconstruct, counter_summary, DIMS
from analyze import peer_comparison


def history():
    """Create a test fixture only; never included in the real dataset."""
    rows=[]
    for i, state in enumerate(['New','Resolved','Closed']):
        r=dict(number='TEST', incident_state=state, sys_updated_at=pd.Timestamp('2020-01-01')+pd.Timedelta(hours=i),
               opened_at=pd.Timestamp('2020-01-01'), resolved_at=pd.Timestamp('2020-01-01 01:00'),
               closed_at=pd.Timestamp('2020-01-01 02:00'), reassignment_count=i,
               reopen_count=0, sys_mod_count=i, knowledge=False)
        r.update({c:'Known' for c in DIMS})
        r['assignment_group']=['A','B','C'][i]
        rows.append(r)
    return pd.DataFrame(rows)


def test_grains_and_enriched_endpoint_not_state_entry():
    e,i,t=reconstruct(history())
    assert len(e)==3 and len(i)==1 and i.event_count.sum()==3
    assert i.iloc[0].resolution_hours==1 and i.iloc[0].closure_hours==2
    assert i.iloc[0].reassignment_count==2 and len(t)==2


@pytest.mark.parametrize('values',[[0,2,1],[1,2,3],[0,None,2],[0,-1,2],[0,.5,1]])
def test_invalid_counters_never_promoted_to_terminal(values):
    value, valid=counter_summary(pd.Series(values))
    assert not valid and pd.isna(value)


def test_missing_group_interrupts_sequence():
    d=history(); d.loc[1,'assignment_group']=None
    _,i,t=reconstruct(d)
    assert t.empty and i.iloc[0].missing_group


def test_ties_are_not_group_transitions():
    d=history(); d.loc[1,'sys_updated_at']=d.loc[0,'sys_updated_at']
    _,i,t=reconstruct(d)
    assert t.empty and i.iloc[0].tied_updates


@pytest.mark.parametrize('endpoint, value, reason',[
    ('resolved_at',None,'missing_or_conflicting_endpoint'),
    ('resolved_at',pd.Timestamp('2019-12-31'),'negative_duration'),
    ('resolved_at',pd.Timestamp('2020-01-02'),'closure_before_resolution')])
def test_ineligible_resolution_is_not_zero(endpoint,value,reason):
    d=history(); d[endpoint]=value
    _,i,_=reconstruct(d)
    assert pd.isna(i.iloc[0].resolution_hours) and i.iloc[0].resolution_eligibility==reason


def test_conflicting_endpoint_is_not_arbitrarily_maximum():
    d=history(); d.loc[0,'resolved_at']=pd.Timestamp('2020-01-01 00:30')
    _,i,_=reconstruct(d)
    assert i.iloc[0].resolved_at_conflict and pd.isna(i.iloc[0].resolution_hours)


def test_unknown_initial_dimension_never_backfilled():
    d=history(); d.loc[0,'category']=None; d.loc[1,'knowledge']=True
    _,i,_=reconstruct(d)
    assert pd.isna(i.iloc[0].initial_category) and i.iloc[0].category_changed
    assert i.iloc[0].knowledge_ever and i.iloc[0].knowledge_changed


def test_identical_snapshots_retained():
    d=history(); d=pd.concat([d,d.iloc[[-1]]],ignore_index=True)
    e,i,_=reconstruct(d)
    assert len(e)==4 and i.iloc[0].event_count==4


def test_endpoints_beyond_observation_are_not_eligible():
    d=history(); d['resolved_at']=pd.Timestamp('2020-01-01 03:00'); d['closed_at']=pd.Timestamp('2020-01-01 04:00')
    _,i,_=reconstruct(d)
    assert i.iloc[0].resolution_eligibility=='endpoint_after_observation'
    assert i.iloc[0].closure_eligibility=='endpoint_after_observation'


def test_unknown_update_invalidates_terminal_counter():
    d=history(); d.loc[2,'sys_updated_at']=pd.NaT
    _,i,_=reconstruct(d)
    assert not i.iloc[0].reassignment_count_valid and pd.isna(i.iloc[0].reassignment_count)


def test_peer_support_and_weighted_medians_have_explicit_estimand():
    d=pd.DataFrame({'cell':['A']*4+['B']*4+['C'],
                    'exposed':[True,True,False,False]*2+[True],
                    'resolution_hours':[10,20,1,3,100,200,50,100,999]})
    _,r=peer_comparison(d,'exposed',['cell'],minimum=2)
    assert r['supported_n']==8 and r['eligible_known_case_mix_n']==9
    assert r['weighted_within_stratum_median_difference_hours']==44
    assert r['supported_crude_median_difference_hours']==33.5
