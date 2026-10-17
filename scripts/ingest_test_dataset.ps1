# Replace MySQL contents with the host test dataset (not alongside sample).
# Usage:
#   .\scripts\ingest_test_dataset.ps1
#   .\scripts\ingest_test_dataset.ps1 -Path "C:\path\to\test-data\dataset"
param(
  [string]$Path = "C:\Users\DELL\Desktop\flytbase-ahc-swe-asset-intelligence-dataset\test-data\dataset"
)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Output "Wiping schema and loading test dataset from: $Path"
.\.venv\Scripts\python.exe -c @"
from assetiq.config import load_settings
from assetiq.store.schema import Base, make_engine
from sqlalchemy import text
s = load_settings()
eng = make_engine(s.mysql_url)
with eng.begin() as conn:
    conn.execute(text('SET FOREIGN_KEY_CHECKS=0'))
    Base.metadata.drop_all(bind=conn)
    conn.execute(text('SET FOREIGN_KEY_CHECKS=1'))
Base.metadata.create_all(eng)
print('schema_recreated')
eng.dispose()
"@

.\.venv\Scripts\python.exe -m assetiq.cli ingest --path $Path --tag test
Write-Output "Test dataset loaded as tag 'test' (sample replaced)."
