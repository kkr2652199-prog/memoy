# v12_run 패치 직전 상태로 복원 (한 번에 실행)
# 사용법: powershell -ExecutionPolicy Bypass -File backups\army3_pre_v12run_20260430_2315\ROLLBACK.ps1

$BACKUP_ROOT = $PSScriptRoot
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

Copy-Item (Join-Path $BACKUP_ROOT "app\lotto3\v12_engine.py") "app\lotto3\v12_engine.py" -Force
Copy-Item (Join-Path $BACKUP_ROOT "app\lotto3\v12_models.py") "app\lotto3\v12_models.py" -Force
Copy-Item (Join-Path $BACKUP_ROOT "app\lotto3\predict_stat.py") "app\lotto3\predict_stat.py" -Force
Copy-Item (Join-Path $BACKUP_ROOT "data\lotto.db.before_v12run_20260430") "data\lotto.db" -Force
if (Test-Path "app\lotto3\predict_run.py") { Remove-Item "app\lotto3\predict_run.py" -Force }
Write-Host "[OK] v12_run 패치 롤백 완료: $RepoRoot" -ForegroundColor Green
