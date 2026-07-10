# ===== 3군 진입 직전 상태로 롤백 =====
# 사용법: powershell -ExecutionPolicy Bypass -File backups\army3_pre_snapshot_20260430\ROLLBACK.ps1

$BACKUP_ROOT = $PSScriptRoot
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

Write-Host "===========================================" -ForegroundColor Yellow
Write-Host "  3군 진입 직전 상태로 롤백 시작" -ForegroundColor Yellow
Write-Host "  REPO: $RepoRoot" -ForegroundColor Gray
Write-Host "  BACKUP: $BACKUP_ROOT" -ForegroundColor Gray
Write-Host "===========================================" -ForegroundColor Yellow

# 0) 롤백 직전 상태 안전 백업
$NOW = Get-Date -Format "yyyyMMdd_HHmmss"
$PRE_ROLLBACK = Join-Path $RepoRoot "backups\pre_rollback_army3_$NOW"
New-Item -Path "$PRE_ROLLBACK\app\lotto" -ItemType Directory -Force | Out-Null
New-Item -Path "$PRE_ROLLBACK\app\lotto2" -ItemType Directory -Force | Out-Null
New-Item -Path "$PRE_ROLLBACK\app\lotto3" -ItemType Directory -Force -ErrorAction SilentlyContinue | Out-Null
New-Item -Path "$PRE_ROLLBACK\app\static\js" -ItemType Directory -Force | Out-Null
New-Item -Path "$PRE_ROLLBACK\app\static\css" -ItemType Directory -Force | Out-Null
New-Item -Path "$PRE_ROLLBACK\data" -ItemType Directory -Force | Out-Null

if (Test-Path "data\lotto.db") { Copy-Item "data\lotto.db" "$PRE_ROLLBACK\data\" -Force }
if (Test-Path "app\lotto\*.py") { Copy-Item "app\lotto\*.py" "$PRE_ROLLBACK\app\lotto\" -Force }
if (Test-Path "app\lotto2\*.py") { Copy-Item "app\lotto2\*.py" "$PRE_ROLLBACK\app\lotto2\" -Force }
if (Test-Path "app\lotto3") { Copy-Item "app\lotto3\*" "$PRE_ROLLBACK\app\lotto3\" -Recurse -Force }
if (Test-Path "app\static\js\*.js") { Copy-Item "app\static\js\*.js" "$PRE_ROLLBACK\app\static\js\" -Force }
if (Test-Path "app\static\css\*.css") { Copy-Item "app\static\css\*.css" "$PRE_ROLLBACK\app\static\css\" -Force }
if (Test-Path "app\static\index.html") { Copy-Item "app\static\index.html" "$PRE_ROLLBACK\app\static\" -Force }
if (Test-Path "app\main.py") { Copy-Item "app\main.py" "$PRE_ROLLBACK\app\" -Force }
Write-Host "[OK] 롤백 직전 상태 백업: $PRE_ROLLBACK" -ForegroundColor Cyan

# 1) 3군 폴더 통째 삭제 (있으면)
if (Test-Path "app\lotto3") {
    Remove-Item "app\lotto3" -Recurse -Force
    Write-Host "[OK] app\lotto3 폴더 제거" -ForegroundColor Green
}

# 2) DB 복원
Copy-Item (Join-Path $BACKUP_ROOT "data\lotto.db") "data\lotto.db" -Force
Write-Host "[OK] DB 복원" -ForegroundColor Green

# 3) 1군 복원
Copy-Item (Join-Path $BACKUP_ROOT "app\lotto\*.py") "app\lotto\" -Force
Write-Host "[OK] 1군 복원" -ForegroundColor Green

# 4) 2군 복원
Copy-Item (Join-Path $BACKUP_ROOT "app\lotto2\*.py") "app\lotto2\" -Force
Write-Host "[OK] 2군 복원" -ForegroundColor Green

# 5) UI 복원
Copy-Item (Join-Path $BACKUP_ROOT "app\static\js\lotto.js") "app\static\js\" -Force
Copy-Item (Join-Path $BACKUP_ROOT "app\static\js\lotto2.js") "app\static\js\" -Force
Copy-Item (Join-Path $BACKUP_ROOT "app\static\css\lotto.css") "app\static\css\" -Force
Copy-Item (Join-Path $BACKUP_ROOT "app\static\css\lotto2.css") "app\static\css\" -Force
Copy-Item (Join-Path $BACKUP_ROOT "app\static\index.html") "app\static\" -Force
Write-Host "[OK] UI 복원" -ForegroundColor Green

# 6) main.py 복원
Copy-Item (Join-Path $BACKUP_ROOT "app\main.py") "app\main.py" -Force
Write-Host "[OK] main.py 복원" -ForegroundColor Green

# 7) SHA256 검증
Write-Host ""
Write-Host "===== SHA256 검증 =====" -ForegroundColor Yellow
$checksumPath = Join-Path $BACKUP_ROOT "CHECKSUMS.txt"
$checksums = Get-Content $checksumPath | Where-Object { $_ -match "^[A-F0-9]{64}\s+" }
$ok = 0
$fail = 0
foreach ($line in $checksums) {
    $parts = $line -split "\s+", 2
    $expected = $parts[0]
    $rel = $parts[1]
    $current_path = Join-Path $RepoRoot $rel
    if (Test-Path -LiteralPath $current_path) {
        $actual = (Get-FileHash -LiteralPath $current_path -Algorithm SHA256).Hash
        if ($actual -eq $expected) { $ok++ } else { $fail++; Write-Host "[FAIL] $rel" -ForegroundColor Red }
    } else {
        $fail++
        Write-Host "[MISSING] $rel" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "===========================================" -ForegroundColor Yellow
Write-Host "  롤백 결과: PASS=$ok / FAIL=$fail" -ForegroundColor Yellow
Write-Host "  롤백 직전 상태: $PRE_ROLLBACK" -ForegroundColor Cyan
Write-Host "===========================================" -ForegroundColor Yellow

if ($fail -eq 0) {
    Write-Host "[ROLLBACK 완료] 3군 진입 직전 상태로 100% 복원됨" -ForegroundColor Green
} else {
    Write-Host "[ROLLBACK 실패] $fail 개 파일 불일치 — 수동 점검 필요" -ForegroundColor Red
}
