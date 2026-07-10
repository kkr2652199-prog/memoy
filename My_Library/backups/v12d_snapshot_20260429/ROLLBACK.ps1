# ===== V12-D-FULL 롤백 스크립트 =====
# 사용법: PowerShell에서 실행
#   powershell -ExecutionPolicy Bypass -File backups\v12d_snapshot_20260429\ROLLBACK.ps1

$BACKUP_ROOT = "backups\v12d_snapshot_20260429"

Write-Host "===========================================" -ForegroundColor Yellow
Write-Host "  V12-D-FULL 상태로 롤백 시작" -ForegroundColor Yellow
Write-Host "===========================================" -ForegroundColor Yellow

# 0) 현재 상태(롤백 직전)도 안전 백업
$NOW = Get-Date -Format "yyyyMMdd_HHmmss"
$PRE_ROLLBACK = "backups\pre_rollback_$NOW"
New-Item -Path "$PRE_ROLLBACK\app\lotto2" -ItemType Directory -Force | Out-Null
New-Item -Path "$PRE_ROLLBACK\app\static\js" -ItemType Directory -Force | Out-Null
New-Item -Path "$PRE_ROLLBACK\data" -ItemType Directory -Force | Out-Null

Copy-Item "data\lotto.db"                      "$PRE_ROLLBACK\data\lotto.db" -Force
Copy-Item "app\lotto2\*.py"                     "$PRE_ROLLBACK\app\lotto2\" -Force
Copy-Item "app\static\js\lotto2.js"             "$PRE_ROLLBACK\app\static\js\lotto2.js" -Force
Copy-Item "app\static\index.html"               "$PRE_ROLLBACK\app\static\index.html" -Force
Copy-Item "app\main.py"                         "$PRE_ROLLBACK\app\main.py" -Force
Write-Host "[OK] 롤백 직전 상태 안전 백업: $PRE_ROLLBACK" -ForegroundColor Cyan

# 1) DB 복원
Copy-Item "$BACKUP_ROOT\data\lotto.db" "data\lotto.db" -Force
Write-Host "[OK] DB 복원" -ForegroundColor Green

# 2) 2군 코드 복원
Copy-Item "$BACKUP_ROOT\app\lotto2\v11_engine.py"     "app\lotto2\v11_engine.py" -Force
Copy-Item "$BACKUP_ROOT\app\lotto2\v11_models.py"     "app\lotto2\v11_models.py" -Force
Copy-Item "$BACKUP_ROOT\app\lotto2\v11_fusion.py"     "app\lotto2\v11_fusion.py" -Force
Copy-Item "$BACKUP_ROOT\app\lotto2\v11_fusion_v5.py"  "app\lotto2\v11_fusion_v5.py" -Force
Copy-Item "$BACKUP_ROOT\app\lotto2\v11_snake.py"      "app\lotto2\v11_snake.py" -Force
Copy-Item "$BACKUP_ROOT\app\lotto2\v11_routes.py"     "app\lotto2\v11_routes.py" -Force
Write-Host "[OK] 2군 코드 6개 복원" -ForegroundColor Green

# 3) UI 복원
Copy-Item "$BACKUP_ROOT\app\static\js\lotto2.js"      "app\static\js\lotto2.js" -Force
Copy-Item "$BACKUP_ROOT\app\static\index.html"        "app\static\index.html" -Force
Write-Host "[OK] UI 복원" -ForegroundColor Green

# 4) main.py 복원
Copy-Item "$BACKUP_ROOT\app\main.py"                  "app\main.py" -Force
Write-Host "[OK] main.py 복원" -ForegroundColor Green

# 5) 체크섬 검증
Write-Host ""
Write-Host "===== SHA256 검증 =====" -ForegroundColor Yellow
$checksums = Get-Content "$BACKUP_ROOT\CHECKSUMS.txt" | Where-Object { $_ -match "^[A-F0-9]{64}\s+" }
$ok = 0
$fail = 0
foreach ($line in $checksums) {
    $parts = $line -split "\s+", 2
    $expected = $parts[0]
    $file = $parts[1]
    if (Test-Path $file) {
        $actual = (Get-FileHash $file -Algorithm SHA256).Hash
        if ($actual -eq $expected) {
            Write-Host "[PASS] $file" -ForegroundColor Green
            $ok++
        } else {
            Write-Host "[FAIL] $file" -ForegroundColor Red
            Write-Host "       Expected: $expected" -ForegroundColor Red
            Write-Host "       Actual:   $actual" -ForegroundColor Red
            $fail++
        }
    }
}

Write-Host ""
Write-Host "===========================================" -ForegroundColor Yellow
Write-Host "  롤백 결과: PASS=$ok / FAIL=$fail" -ForegroundColor Yellow
Write-Host "  롤백 직전 상태: $PRE_ROLLBACK" -ForegroundColor Cyan
Write-Host "===========================================" -ForegroundColor Yellow

if ($fail -eq 0) {
    Write-Host "[ROLLBACK 완료] V12-D-FULL 상태로 100% 복원됨" -ForegroundColor Green
} else {
    Write-Host "[ROLLBACK 실패] $fail 개 파일 불일치 — 수동 점검 필요" -ForegroundColor Red
}
