"""Preserve audit snapshots and reconstruct one explicitly qualified row per incident."""
import json
import numpy as np
import pandas as pd
from ingest import ROOT, RAW

PROCESSED = ROOT / 'documentation' / 'data' / 'processed'
EVIDENCE = ROOT / 'documentation' / 'evidence'
DATES = ['opened_at','sys_created_at','sys_updated_at','resolved_at','closed_at']
COUNTERS = ['reassignment_count','reopen_count','sys_mod_count']
DIMS = ['category','subcategory','priority','location','contact_type','assignment_group']


def unique_value(series):
    """Accept a sole known value; conflicting enriched endpoints remain unknown."""
    values = series.dropna().unique()
    return values[0] if len(values) == 1 else pd.NA


def counter_summary(series):
    """Use the terminal count only after checking zero start and cumulative behavior."""
    valid = (series.notna().all() and len(series) > 0 and series.iloc[0] == 0
             and series.ge(0).all() and series.mod(1).eq(0).all()
             and series.diff().dropna().ge(0).all())
    return (int(series.iloc[-1]) if valid else pd.NA), bool(valid)


def reconstruct(events):
    """Order snapshots; never infer an unobserved resolution attempt or work interval."""
    events = events.copy()
    if 'event_id' not in events:
        events.insert(0, 'event_id', np.arange(1, len(events)+1))
    events['source_update_regression'] = events.groupby('number', sort=False).sys_updated_at.diff().lt(pd.Timedelta(0))
    # Minute timestamps can tie. Modification counter then source row give deterministic
    # display order, not proof of the real ordering of tied state changes.
    events = events.sort_values(['number','sys_updated_at','sys_mod_count','event_id'], kind='stable', na_position='last')
    incidents, transitions = [], []
    for number, g in events.groupby('number', sort=False):
        first, last = g.iloc[0], g.iloc[-1]
        record = dict(number=number, event_count=len(g), final_state=last.incident_state,
                      first_observed_at=g.sys_updated_at.min(), last_observed_at=g.sys_updated_at.max(),
                      missing_update=bool(g.sys_updated_at.isna().any()),
                      tied_updates=bool(g.sys_updated_at.duplicated().any()),
                      missing_group=bool(g.assignment_group.isna().any()),
                      source_update_regression=bool(g.source_update_regression.any()))
        for c in DIMS:
            # Retain the earliest snapshot, even if unknown; no future backfill of case mix.
            record['initial_'+c] = first[c]
            record[c+'_changed'] = bool(g[c].nunique(dropna=False)>1)
        for c in ['opened_at','resolved_at','closed_at']:
            record[c] = unique_value(g[c])
            record[c+'_conflict'] = bool(g[c].nunique()>1)
        for c in COUNTERS:
            value, valid = counter_summary(g[c])
            record[c] = value
            record[c+'_valid'] = valid and not record['missing_update']
            if not record[c+'_valid']:
                record[c] = pd.NA
        known_k = g.knowledge.dropna()
        record['knowledge_ever'] = bool(known_k.eq(True).any()) if len(known_k) else pd.NA
        record['knowledge_changed'] = bool(known_k.nunique()>1)
        record['mod_count_gap'] = bool(g.sys_mod_count.diff().gt(1).any())
        record['mod_count_decrease'] = bool(g.sys_mod_count.diff().lt(0).any())
        record['all_endpoints_within_observation'] = bool(
            pd.notna(record['resolved_at']) and record['resolved_at'] <= record['last_observed_at'])
        # A missing group interrupts the chain. Do not forward-fill or bridge it.
        prev = g.shift(1)
        strict = (g.sys_updated_at.notna() & prev.sys_updated_at.notna()
                  & g.sys_updated_at.gt(prev.sys_updated_at))
        tied = g.sys_updated_at.duplicated(keep=False)
        safe = strict & ~tied & ~tied.shift(1, fill_value=False)
        changes = safe & g.assignment_group.notna() & prev.assignment_group.notna() & g.assignment_group.ne(prev.assignment_group)
        for idx in g.index[changes]:
            transitions.append(dict(number=number, from_event_id=int(prev.loc[idx,'event_id']),
                                    to_event_id=int(g.loc[idx,'event_id']),
                                    from_group=prev.loc[idx,'assignment_group'],
                                    to_group=g.loc[idx,'assignment_group']))
        record['observed_group_changes'] = int(changes.sum())
        record['state_changes_observed'] = int((safe & g.incident_state.ne(prev.incident_state)).sum())
        incidents.append(record)
    inc = pd.DataFrame(incidents)
    for c in ['opened_at','resolved_at','closed_at','first_observed_at','last_observed_at']:
        inc[c] = pd.to_datetime(inc[c], errors='coerce')
    for endpoint, prefix in [('resolved_at','resolution'), ('closed_at','closure')]:
        elapsed = (inc[endpoint]-inc.opened_at).dt.total_seconds()/3600
        reason = np.select([inc.opened_at.isna(), inc[endpoint].isna(), elapsed.lt(0),
                            inc[endpoint].gt(inc.last_observed_at)],
                           ['missing_or_conflicting_open','missing_or_conflicting_endpoint','negative_duration','endpoint_after_observation'], default='eligible')
        inc[prefix+'_eligibility'] = reason
        inc[prefix+'_hours'] = elapsed.where(reason=='eligible')
    inc['closure_before_resolution'] = inc.closed_at.lt(inc.resolved_at)
    # Inconsistent endpoint order invalidates both outcome durations.
    for prefix in ['resolution','closure']:
        inc.loc[inc.closure_before_resolution, prefix+'_hours'] = np.nan
        inc.loc[inc.closure_before_resolution, prefix+'_eligibility'] = 'closure_before_resolution'
    return events, inc, pd.DataFrame(transitions, columns=['number','from_event_id','to_event_id','from_group','to_group'])


def main():
    """Write analytical tables, per-record eligibility, and reconciliation evidence."""
    PROCESSED.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(RAW / 'incident_event_log.csv', na_values=['?'], low_memory=False)
    raw_count, duplicates = len(raw), int(raw.duplicated().sum())
    invalid = {}
    for c in DATES:
        parsed = pd.to_datetime(raw[c], format='%d/%m/%Y %H:%M', errors='coerce')
        invalid[c] = int((parsed.isna() & raw[c].notna()).sum())
        raw[c] = parsed
    if raw.number.isna().any():
        raise ValueError('Unknown incident IDs require explicit quarantine')
    for c in COUNTERS:
        raw[c] = pd.to_numeric(raw[c], errors='coerce')
    events, inc, transitions = reconstruct(raw)
    assert len(events) == raw_count
    assert inc.number.is_unique and inc.event_count.sum() == len(events)
    assert len(events.merge(inc[['number']], on='number', validate='many_to_one')) == len(events)
    events.to_parquet(PROCESSED/'events.parquet', index=False)
    inc.to_parquet(PROCESSED/'incidents.parquet', index=False)
    transitions.to_parquet(PROCESSED/'transitions.parquet', index=False)
    quality = dict(events=len(events), incidents=len(inc), duplicate_rows_retained=duplicates,
                   invalid_timestamp_values=invalid,
                   missing_fields=raw.isna().sum().to_dict(),
                   timestamp_tie_rows_after_first=int(events.duplicated(['number','sys_updated_at']).sum()),
                   state_values=events.incident_state.value_counts().to_dict(),
                   resolution_eligibility=inc.resolution_eligibility.value_counts().to_dict(),
                   closure_eligibility=inc.closure_eligibility.value_counts().to_dict(),
                   flags={c:int(inc[c].sum()) for c in inc if c.endswith(('_changed','_conflict','_valid')) or c in ['missing_update','tied_updates','missing_group','mod_count_gap','mod_count_decrease','source_update_regression','closure_before_resolution']},
                   final_states=inc.final_state.value_counts().to_dict(),
                   transitions=len(transitions), transitions_distinct_incidents=transitions.number.nunique())
    (EVIDENCE/'quality.json').write_text(json.dumps(quality, indent=2, default=int), encoding='utf-8')
    inc.loc[inc.resolution_eligibility.ne('eligible') | inc.closure_eligibility.ne('eligible'),
            ['number','resolution_eligibility','closure_eligibility']].to_csv(EVIDENCE/'exclusions.csv', index=False)
    print(json.dumps(quality, indent=2, default=int))


if __name__ == '__main__':
    main()
