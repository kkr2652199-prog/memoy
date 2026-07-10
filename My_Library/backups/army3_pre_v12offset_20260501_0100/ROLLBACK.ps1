# v12_offset 패치 직전 상태로 복원
# 사용법: powershell -ExecutionPolicy Bypass -File backups\army3_pre_v12offset_20260501_0100\ROLLBACK.ps1

$BACKUP_ROOT = $PSScriptRoot
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

Copy-Item (Join-Path $BACKUP_ROOT "app\lotto3\v12_engine.py") "app\lotto3\v12_engine.py" -Force
Copy-Item (Join-Path $BACKUP_ROOT "app\lotto3\v12_models.py") "app\lotto3\v12_models.py" -Force
Copy-Item (Join-Path $BACKUP_ROOT "app\lotto3\predict_run.py") "app\lotto3\predict_run.py" -Force
Copy-Item (Join-Path $BACKUP_ROOT "app\lotto3\predict_markov.py") "app\lotto3\predict_markov.py" -Force
Copy-Item (Join-Path $BACKUP_ROOT "data\lotto.db.before_v12offset_20260501") "data\lotto.db" -Force
if (Test-Path "app\lotto3\predict_offset.py") { Remove-Item "app\lotto3\predict_offset.py" -Force }
Write-Host "[OK] v12_offset 패치 롤백 완료: $RepoRoot" -ForegroundColor Green
