"""Atomically load dedicated project tables and execute every analytical SQL file."""
import json
import os
import numpy as np
import pandas as pd
import psycopg
from psycopg import sql
from clean import ROOT, PROCESSED, EVIDENCE


def pg_type(series):
    """Map typed analytical parquet columns to modest PostgreSQL types."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return 'timestamp'
    if pd.api.types.is_bool_dtype(series):
        return 'boolean'
    if pd.api.types.is_integer_dtype(series):
        return 'bigint'
    if pd.api.types.is_numeric_dtype(series):
        return 'double precision'
    known=series.dropna()
    if len(known) and known.map(lambda x: isinstance(x,(bool,np.bool_))).all():
        return 'boolean'
    return 'text'


def scalar(value):
    """COPY accepts Python scalars and SQL NULL, not pandas missing sentinels."""
    if pd.isna(value):
        return None
    if isinstance(value,np.generic):
        return value.item()
    if isinstance(value,pd.Timestamp):
        return value.to_pydatetime()
    return value


def main():
    """Replace only registered project tables; roll back an incomplete reload."""
    url=os.environ.get('DATABASE_URL')
    if not url:
        raise SystemExit('Set DATABASE_URL to your PostgreSQL connection string')
    with psycopg.connect(url) as conn:
        conn.execute('CREATE SCHEMA IF NOT EXISTS resolution_gap')
        # A marker protects an unrelated pre-existing schema from replacement.
        tables=conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='resolution_gap'").fetchall()
        if tables and ('project_identity',) not in tables:
            raise ValueError('Existing unregistered schema: refusing replacement')
        conn.execute('CREATE TABLE IF NOT EXISTS resolution_gap.project_identity (name text PRIMARY KEY)')
        conn.execute("INSERT INTO resolution_gap.project_identity VALUES ('closing-resolution-gap-v1') ON CONFLICT DO NOTHING")
        identity=conn.execute('SELECT name FROM resolution_gap.project_identity').fetchall()
        if identity != [('closing-resolution-gap-v1',)]:
            raise ValueError('Project identity mismatch')
        # Drop dependent project tables first so an ordinary second run is safe.
        for name in ['transitions','events','incidents']:
            conn.execute(sql.SQL('DROP TABLE IF EXISTS {}').format(sql.Identifier('resolution_gap',name)))
        for name in ['events','incidents','transitions']:
            frame=pd.read_parquet(PROCESSED/f'{name}.parquet')
            table=sql.Identifier('resolution_gap',name)
            definitions=[sql.SQL('{} {}').format(sql.Identifier(c),sql.SQL(pg_type(frame[c]))) for c in frame]
            conn.execute(sql.SQL('CREATE TABLE {} ({})').format(table,sql.SQL(',').join(definitions)))
            with conn.cursor().copy(sql.SQL('COPY {} FROM STDIN').format(table)) as copy:
                for row in frame.itertuples(index=False,name=None):
                    copy.write_row(tuple(scalar(v) for v in row))
            key='event_id' if name=='events' else 'number'
            if name!='transitions':
                conn.execute(sql.SQL('ALTER TABLE {} ADD PRIMARY KEY ({})').format(table,sql.Identifier(key)))
            conn.execute(sql.SQL('CREATE INDEX ON {} (number)').format(table))
            conn.execute(sql.SQL('ANALYZE {}').format(table))
        for name in ['events','transitions']:
            conn.execute(sql.SQL('ALTER TABLE {} ADD FOREIGN KEY (number) REFERENCES resolution_gap.incidents(number)').format(sql.Identifier('resolution_gap',name)))
        for key in ['from_event_id','to_event_id']:
            conn.execute(sql.SQL('ALTER TABLE resolution_gap.transitions ADD FOREIGN KEY ({}) REFERENCES resolution_gap.events(event_id)').format(sql.Identifier(key)))
    with psycopg.connect(url) as conn:
        for path in sorted((ROOT/'code'/'sql').glob('*.sql')):
            cursor=conn.execute(path.read_text(encoding='utf-8'))
            result=pd.DataFrame(cursor.fetchall(),columns=[c.name for c in cursor.description])
            result.to_csv(EVIDENCE/f'sql_{path.stem}.csv',index=False)
        base=json.loads((EVIDENCE/'baseline.json').read_text())
        actual=pd.read_csv(EVIDENCE/'sql_01_baseline.csv').iloc[0]
        for key in ['incidents','resolution_n','resolution_median_hours','resolution_p90_hours','closure_n','closure_median_hours','reopen_eligible_n','reopened_n','reopened_pct']:
            assert np.isclose(actual[key],base[key]), (key,actual[key],base[key])
        peers=pd.read_csv(EVIDENCE/'sql_05_peer_comparisons.csv')
        expected=json.loads((EVIDENCE/'peer_comparisons.json').read_text())
        for row in expected:
            if row['variant']=='primary':
                actual=peers.loc[peers.exposure.eq(row['exposure'])].iloc[0]
                for key in ['supported_strata','supported_n','eligible_known_case_mix_n','weighted_within_stratum_median_difference_hours']:
                    assert np.isclose(actual[key],row[key]), (key, actual[key],row[key])
        checks=pd.read_csv(EVIDENCE/'sql_07_validation.csv').iloc[0]
        assert checks.events==checks.unique_events==checks.summed_event_counts==checks.joined_rows
        assert checks.incidents==checks.unique_incidents and checks.negative_eligible==checks.orphan_transitions==0
        version=conn.info.server_version
    (EVIDENCE/'postgres_validation.json').write_text(json.dumps(dict(baseline_matches_python=True,peer_comparisons_match_python=True,cardinality_checks_pass=True,postgres_version=version),indent=2),encoding='utf-8')
    print('Loaded three tables; seven SQL exports reconcile with Python.')


if __name__=='__main__':
    main()
