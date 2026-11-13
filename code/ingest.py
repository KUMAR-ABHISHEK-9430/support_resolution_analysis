"""Download the original UCI archive without altering its records."""
from pathlib import Path
import hashlib
import json
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'documentation' / 'data' / 'raw'
URL = 'https://archive.ics.uci.edu/static/public/498/incident%2Bmanagement%2Bprocess%2Benriched%2Bevent%2Blog.zip'
SOURCE = 'https://archive.ics.uci.edu/dataset/498/incident+management+process+enriched+event+log'


def main():
    """Cache original bytes; save provenance and a CSV checksum."""
    RAW.mkdir(parents=True, exist_ok=True)
    archive = RAW / 'uci_498.zip'
    if not archive.exists():
        with urllib.request.urlopen(URL, timeout=90) as response:
            content = response.read()
        temporary = archive.with_suffix('.part')
        temporary.write_bytes(content)
        temporary.replace(archive)
    with zipfile.ZipFile(archive) as source:
        names = [n for n in source.namelist() if Path(n).name == 'incident_event_log.csv']
        if len(names) != 1:
            raise ValueError('Expected exactly one original incident CSV')
        content = source.read(names[0])
    (RAW / 'incident_event_log.csv').write_bytes(content)
    manifest = dict(source=SOURCE, download=URL, verified_date='2026-11-14',
                    license='CC BY 4.0', doi='10.24432/C57S4H',
                    creators=['Claudio Amaral', 'Marcelo Fantinato', 'Sarajane Peres'],
                    csv_sha256=hashlib.sha256(content).hexdigest(),
                    archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                    bytes=len(content), changes='None; original CSV bytes retained')
    (RAW / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
