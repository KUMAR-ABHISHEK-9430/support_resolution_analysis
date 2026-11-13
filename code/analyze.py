"""Export incident-level evidence, peer comparisons and sensitivity checks."""
import json
import math
import numpy as np
import pandas as pd
from clean import PROCESSED, EVIDENCE


def summarize(g):
    """Compute outcomes with explicit, separate denominators."""
    valid_reopen = g.reopen_count.dropna().astype(float)
    n, reopened = len(valid_reopen), int(valid_reopen.gt(0).sum())
    # Wilson interval describes binomial sampling uncertainty, not extraction bias.
    p = reopened/n if n else np.nan
    z = 1.96
    center = (p+z*z/(2*n))/(1+z*z/n) if n else np.nan
    half = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n) if n else np.nan
    return dict(incidents=len(g), resolution_n=int(g.resolution_hours.notna().sum()),
                resolution_median_hours=g.resolution_hours.median(),
                resolution_p90_hours=g.resolution_hours.quantile(.9),
                closure_n=int(g.closure_hours.notna().sum()),
                closure_median_hours=g.closure_hours.median(),
                closure_p90_hours=g.closure_hours.quantile(.9),
                total_elapsed_incident_hours=g.resolution_hours.sum(min_count=1),
                reopen_eligible_n=n, reopened_n=reopened, reopened_pct=100*p,
                reopen_wilson_low_pct=100*(center-half), reopen_wilson_high_pct=100*(center+half),
                multi_reassignment_n=int(g.reassignment_count.dropna().astype(float).ge(2).sum()),
                reassignment_eligible_n=int(g.reassignment_count.notna().sum()),
                knowledge_true_n=int(g.knowledge_ever.eq(True).sum()),
                knowledge_known_n=int(g.knowledge_ever.notna().sum()))


def grouped(d, dimensions):
    """Retain unknown dimensions as an explicit reporting bucket."""
    rows = []
    for key, g in d.groupby(dimensions, dropna=False, observed=True):
        key = key if isinstance(key, tuple) else (key,)
        rows.append(dict(zip(dimensions, key)) | summarize(g))
    return pd.DataFrame(rows)


def peer_comparison(d, exposure, dimensions, minimum=20):
    """Contrast stratum medians with common weights on groups with both arms."""
    eligible = d.loc[d.resolution_hours.notna() & d[exposure].notna()].dropna(subset=dimensions).copy()
    rows, supported_indexes = [], []
    for key, g in eligible.groupby(dimensions, observed=True):
        a, b = g.loc[g[exposure].eq(True),'resolution_hours'], g.loc[g[exposure].eq(False),'resolution_hours']
        if min(len(a),len(b)) < minimum:
            continue
        supported_indexes.extend(g.index.tolist())
        rows.append(dict(zip(dimensions, key if isinstance(key, tuple) else (key,))) |
                    dict(exposed_n=len(a), comparison_n=len(b), exposed_median=a.median(),
                         comparison_median=b.median(), median_difference_hours=a.median()-b.median(), weight=len(g)))
    strata = pd.DataFrame(rows,columns=dimensions+['exposed_n','comparison_n','exposed_median','comparison_median','median_difference_hours','weight'])
    raw_a = eligible.loc[eligible[exposure].eq(True),'resolution_hours']
    raw_b = eligible.loc[eligible[exposure].eq(False),'resolution_hours']
    result = dict(exposure=exposure, dimensions=dimensions, minimum_per_arm=minimum,
                  eligible_known_case_mix_n=len(eligible), eligible_before_case_mix_n=int((d.resolution_hours.notna() & d[exposure].notna()).sum()),
                  crude_exposed_n=len(raw_a), crude_comparison_n=len(raw_b),
                  crude_median_difference_hours=raw_a.median()-raw_b.median(),
                  supported_strata=len(strata), supported_n=int(strata.weight.sum()) if len(strata) else 0,
                  weighted_within_stratum_median_difference_hours=float(np.average(strata.median_difference_hours, weights=strata.weight)) if len(strata) else None)
    result['coverage_pct'] = 100*result['supported_n']/len(eligible) if len(eligible) else 0
    supported=eligible.loc[supported_indexes]
    supported_a=supported.loc[supported[exposure].eq(True),'resolution_hours']
    supported_b=supported.loc[supported[exposure].eq(False),'resolution_hours']
    result.update(supported_exposed_n=len(supported_a),supported_comparison_n=len(supported_b),
                  exposed_coverage_pct=100*len(supported_a)/len(raw_a) if len(raw_a) else 0,
                  comparison_coverage_pct=100*len(supported_b)/len(raw_b) if len(raw_b) else 0,
                  supported_crude_median_difference_hours=supported_a.median()-supported_b.median() if len(supported) else None)
    return strata, result


def main():
    """Run all portable analyses, retaining all incidents in the baseline denominator."""
    d = pd.read_parquet(PROCESSED/'incidents.parquet')
    d['opened_month'] = d.opened_at.dt.strftime('%Y-%m')
    d['multi_reassignment'] = d.reassignment_count.map(lambda x: pd.NA if pd.isna(x) else x>=2)
    d['reopened'] = d.reopen_count.map(lambda x: pd.NA if pd.isna(x) else x>0)
    overall = summarize(d)
    (EVIDENCE/'baseline.json').write_text(json.dumps(overall, indent=2), encoding='utf-8')
    for dimension in ['category','priority','location','contact_type','assignment_group']:
        grouped(d, ['initial_'+dimension]).sort_values('incidents', ascending=False).to_csv(EVIDENCE/f'by_{dimension}.csv', index=False)
    categories = grouped(d,['initial_category']).query('incidents >= 200').sort_values('total_elapsed_incident_hours', ascending=False)
    categories['elapsed_share_pct'] = categories.total_elapsed_incident_hours / d.resolution_hours.sum() * 100
    categories.to_csv(EVIDENCE/'priorities.csv', index=False)
    rankings=[]
    for label, cohort in [('primary',d),('stable_case_mix',d.loc[~d.category_changed&~d.priority_changed]),('no_reopens',d.loc[d.reopen_count.eq(0)])]:
        r=grouped(cohort,['initial_category']).query('incidents >= 200').sort_values('total_elapsed_incident_hours',ascending=False)
        r['rule']=label
        r['rank']=range(1,len(r)+1)
        rankings.append(r.head(5))
    capped=d.copy()
    capped['resolution_hours']=capped.resolution_hours.clip(upper=d.resolution_hours.quantile(.99))
    r=grouped(capped,['initial_category']).query('incidents >= 200').sort_values('total_elapsed_incident_hours',ascending=False)
    r['rule']='p99_cap_for_ranking_only'; r['rank']=range(1,len(r)+1)
    rankings.append(r.head(5))
    pd.concat(rankings).to_csv(EVIDENCE/'priority_sensitivity.csv',index=False)
    grouped(d,['knowledge_ever']).to_csv(EVIDENCE/'by_knowledge.csv',index=False)
    # Missing endpoints need a separate composition check, not a zero-duration fill.
    missing=d.assign(resolution_missing=d.resolution_hours.isna())
    missing.groupby(['initial_category','resolution_missing'],dropna=False).size().unstack(fill_value=0).to_csv(EVIDENCE/'missing_resolution_by_category.csv')
    category_contrasts=[]
    for category in categories.initial_category.head(3):
        comparison=d.copy()
        comparison['target_category']=comparison.initial_category.eq(category).where(comparison.initial_category.notna(),pd.NA)
        strata,result=peer_comparison(comparison,'target_category',['initial_priority','opened_month'],20)
        result['target_category']=category
        strata.to_csv(EVIDENCE/f'category_peers_{category.replace(" ","_")}.csv',index=False)
        category_contrasts.append(result)
    (EVIDENCE/'category_comparisons.json').write_text(json.dumps(category_contrasts,indent=2),encoding='utf-8')
    comparisons = []
    for exposure in ['multi_reassignment','reopened','knowledge_ever']:
        for variant, dimensions, minimum in [
            ('primary',['initial_category','initial_priority','opened_month'],20),
            ('location',['initial_category','initial_priority','opened_month','initial_location'],10),
            ('larger_cells',['initial_category','initial_priority','opened_month'],40)]:
            strata, result = peer_comparison(d,exposure,dimensions,minimum)
            result['variant'] = variant
            strata.to_csv(EVIDENCE/f'peers_{exposure}_{variant}.csv', index=False)
            comparisons.append(result)
    (EVIDENCE/'peer_comparisons.json').write_text(json.dumps(comparisons, indent=2), encoding='utf-8')
    events = pd.read_parquet(PROCESSED/'events.parquet')
    initial_knowledge=events.drop_duplicates('number').set_index('number').knowledge
    d['knowledge_initial']=d.number.map(initial_knowledge)
    d['knowledge_stable']=d.knowledge_ever.where(~d.knowledge_changed,pd.NA)
    extra=[]
    for exposure in ['knowledge_initial','knowledge_stable']:
        _,r=peer_comparison(d,exposure,['initial_category','initial_priority','opened_month'],20)
        extra.append(r)
    for threshold in [1,3]:
        exposure=f'reassignments_at_least_{threshold}'
        d[exposure]=d.reassignment_count.ge(threshold).where(d.reassignment_count.notna(),pd.NA)
        _,r=peer_comparison(d,exposure,['initial_category','initial_priority','opened_month'],20)
        extra.append(r)
    (EVIDENCE/'exposure_sensitivity.json').write_text(json.dumps(extra,indent=2),encoding='utf-8')
    sensitivity=[]
    for name, subset in [('primary',d), ('no_reopens',d.loc[d.reopen_count.eq(0)]),
                         ('stable_case_mix',d.loc[~d.category_changed & ~d.priority_changed]),
                         ('no_timestamp_ties',d.loc[~d.tied_updates]),
                         ('no_observed_counter_gaps',d.loc[~d.mod_count_gap & ~d.mod_count_decrease])]:
        sensitivity.append(dict(rule=name) | summarize(subset))
    # Missing endpoint sensitivity is deliberately closure, never a resolution imputation.
    pd.DataFrame(sensitivity).to_csv(EVIDENCE/'sensitivity.csv',index=False)
    for c in ['reassignment_count','reopen_count']:
        grouped(d,[c]).to_csv(EVIDENCE/f'distribution_{c}.csv',index=False)
    transitions = pd.read_parquet(PROCESSED/'transitions.parquet')
    transitions.groupby(['from_group','to_group']).agg(observed_changes=('number','size'), distinct_incidents=('number','nunique')).reset_index().sort_values('observed_changes',ascending=False).to_csv(EVIDENCE/'group_transitions.csv',index=False)
    # Select reproducible examples: ordinary, reopened, missing endpoint, tied and changed case mix.
    choices = [('ordinary',d.loc[d.reassignment_count.eq(0)&d.reopen_count.eq(0)&d.resolution_hours.notna()]),
               ('reopened',d.loc[d.reopen_count.gt(0)&d.resolution_hours.notna()]),
               ('missing_resolution',d.loc[d.resolution_hours.isna()]),
               ('tied',d.loc[d.tied_updates]),('changed_category',d.loc[d.category_changed]),
               ('counter_anomaly',d.loc[d.mod_count_decrease])]
    target=d.loc[d.initial_category.eq(categories.iloc[0].initial_category)&d.reassignment_count.ge(2)&d.resolution_hours.notna()].copy()
    if len(target):
        target['distance_to_category_median']=(target.resolution_hours-categories.iloc[0].resolution_median_hours).abs()
        choices.append(('priority_category',target.nsmallest(1,'distance_to_category_median')))
    histories=[]
    for label, subset in choices:
        if len(subset):
            row=subset.sort_values('number').iloc[0]
            h=events.loc[events.number.eq(row.number)].copy()
            h.insert(0,'example_type',label)
            histories.append(h)
    pd.concat(histories).to_csv(EVIDENCE/'incident_histories.csv',index=False)
    d.loc[d.number.isin(pd.concat(histories).number.unique())].to_csv(EVIDENCE/'history_reconstruction.csv',index=False)
    print(json.dumps(overall,indent=2))
    print(categories.head(8).to_string(index=False))
    print(json.dumps(comparisons,indent=2))


if __name__ == '__main__':
    main()
