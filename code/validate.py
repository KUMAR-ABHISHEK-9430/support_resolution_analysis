"""Independently check selected raw histories and export chronology limitations."""
import csv
import json
from datetime import datetime
import pandas as pd
from ingest import RAW
from clean import EVIDENCE, PROCESSED


def parse(value):
    """Use the original explicit day/month format without a pandas parser."""
    return None if value in ['?',''] else datetime.strptime(value,'%d/%m/%Y %H:%M')


def main():
    """Reconcile raw rows with reconstructed examples and quantify observation gaps."""
    examples=pd.read_csv(EVIDENCE/'history_reconstruction.csv').set_index('number')
    selected={n:[] for n in examples.index}
    with (RAW/'incident_event_log.csv').open(newline='',encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row['number'] in selected:
                selected[row['number']].append(row)
    checks=[]
    for number,rows in selected.items():
        reconstructed=examples.loc[number]
        opened={parse(r['opened_at']) for r in rows}
        resolved={parse(r['resolved_at']) for r in rows if parse(r['resolved_at']) is not None}
        closed={parse(r['closed_at']) for r in rows}
        assert len(opened)==len(closed)==1
        resolution=(next(iter(resolved))-next(iter(opened))).total_seconds()/3600 if len(resolved)==1 else None
        closure=(next(iter(closed))-next(iter(opened))).total_seconds()/3600
        assert len(rows)==reconstructed.event_count
        assert abs(closure-reconstructed.closure_hours)<1e-8
        assert (resolution is None and pd.isna(reconstructed.resolution_hours)) or abs(resolution-reconstructed.resolution_hours)<1e-8
        ordered=sorted(enumerate(rows),key=lambda item:(parse(item[1]['sys_updated_at']),int(item[1]['sys_mod_count']),item[0]))
        for c in ['reassignment_count','reopen_count']:
            counts=[int(r[c]) for _,r in ordered]
            assert counts[0]==0 and all(b>=a for a,b in zip(counts,counts[1:]))
            assert counts[-1]==reconstructed[c]
        checks.append(dict(number=number,raw_rows=len(rows),resolution_hours=resolution,closure_hours=closure,
                           reassignment_count=int(reconstructed.reassignment_count),reopen_count=int(reconstructed.reopen_count),checks_passed=True))
    events=pd.read_parquet(PROCESSED/'events.parquet')
    inc=pd.read_parquet(PROCESSED/'incidents.parquet')
    groups=events.groupby(['number','sys_updated_at'])
    chronology=dict(
        update_before_open_rows=int(events.sys_updated_at.lt(events.opened_at).sum()),
        update_before_open_incidents=int(events.loc[events.sys_updated_at.lt(events.opened_at),'number'].nunique()),
        resolution_later_than_snapshot_rows=int(events.resolved_at.gt(events.sys_updated_at).sum()),
        closure_later_than_snapshot_rows=int(events.closed_at.gt(events.sys_updated_at).sum()),
        tied_buckets_with_conflicting_state=int(groups.incident_state.nunique().gt(1).sum()),
        tied_buckets_with_conflicting_group=int(groups.assignment_group.nunique().gt(1).sum()),
        tied_buckets_with_conflicting_reassignment=int(groups.reassignment_count.nunique().gt(1).sum()),
        tied_buckets_with_conflicting_reopen=int(groups.reopen_count.nunique().gt(1).sum()),
        all_final_states_closed=bool(inc.final_state.eq('Closed').all()),
        raw_history_checks=checks)
    negative_ids=events.loc[events.sys_updated_at.lt(events.opened_at),'number'].unique()
    strict=inc.loc[~inc.number.isin(negative_ids),'resolution_hours']
    chronology['exclude_update_before_open']={'resolution_n':int(strict.notna().sum()),'median_hours':strict.median(),'p90_hours':strict.quantile(.9)}
    (EVIDENCE/'history_validation.json').write_text(json.dumps(chronology,indent=2),encoding='utf-8')
    print(json.dumps(chronology,indent=2))


if __name__=='__main__':
    main()
