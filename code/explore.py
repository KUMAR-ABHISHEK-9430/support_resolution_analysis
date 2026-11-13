"""Separate initial reconnaissance; never used as a production transformation."""
import json
import pandas as pd
from ingest import RAW, ROOT


def main():
    """Save observed field, chronology, counter and snapshot properties."""
    d = pd.read_csv(RAW / 'incident_event_log.csv', na_values=['?'], low_memory=False)
    out = {'shape': list(d.shape), 'incidents': d.number.nunique(),
           'duplicates_after_first': int(d.duplicated().sum()),
           'fields': {c: {'missing': int(d[c].isna().sum()), 'distinct': d[c].nunique(),
                          'examples': d[c].dropna().unique()[:12].tolist()} for c in d}}
    for c in ['opened_at', 'sys_created_at', 'sys_updated_at', 'resolved_at', 'closed_at']:
        p = pd.to_datetime(d[c], format='%d/%m/%Y %H:%M', errors='coerce')
        out[c] = {'invalid_nonmissing': int((p.isna() & d[c].notna()).sum()),
                  'min': str(p.min()), 'max': str(p.max()),
                  'varying_incidents': int(d.groupby('number')[c].nunique().gt(1).sum())}
        d[c] = p
    out['source_update_regressions'] = int(d.groupby('number').sys_updated_at.diff().lt(pd.Timedelta(0)).sum())
    out['timestamp_ties_after_first'] = int(d.duplicated(['number','sys_updated_at']).sum())
    s = d.sort_values(['number','sys_updated_at','sys_mod_count'], kind='stable')
    for c in ['reassignment_count', 'reopen_count', 'sys_mod_count']:
        out[c] = {'decreases': int(s.groupby('number')[c].diff().lt(0).sum()),
                  'nonzero_first': int(s.groupby('number')[c].first().gt(0).sum()),
                  'last_not_max': int(s.groupby('number')[c].last().ne(s.groupby('number')[c].max()).sum())}
    out['states'] = d.incident_state.value_counts().to_dict()
    out['resolved_missing_by_state'] = d.assign(missing=d.resolved_at.isna()).groupby('incident_state').missing.agg(['sum','count']).to_dict()
    out['varying_fields'] = {c: int(d.groupby('number')[c].nunique().gt(1).sum()) for c in ['knowledge','made_sla','category','priority','location']}
    dest = ROOT / 'documentation' / 'evidence' / 'initial_profile.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, default=int), encoding='utf-8')
    print(json.dumps({k:v for k,v in out.items() if k!='fields'}, indent=2, default=int))
    print(d.head(5).to_string(index=False))


if __name__ == '__main__':
    main()
