# STEP2-FINAL 롤백: 백업 폴더의 부모의 부모 = My_Library 루트
$ErrorActionPreference = "Stop"
$b = $PSScriptRoot
$root = Split-Path (Split-Path $b)
Copy-Item "$b\v12_engine.py" "$root\app\lotto3\v12_engine.py" -Force
Copy-Item "$b\v12_models.py" "$root\app\lotto3\v12_models.py" -Force
Copy-Item "$b\v12_routes.py" "$root\app\lotto3\v12_routes.py" -Force
Copy-Item "$b\predict_run.py" "$root\app\lotto3\predict_run.py" -Force
Copy-Item "$b\predict_offset.py" "$root\app\lotto3\predict_offset.py" -Force
Copy-Item "$b\lotto3.js" "$root\app\static\js\lotto3.js" -Force
Copy-Item "$b\lotto.db.before_step2final_20260501" "$root\data\lotto.db" -Force
Write-Host "ROLLBACK 완료: $root"
