# 전원이 내려갔다 올라와도 스스로 서는가 — 그 자국을 잰다 (11-2).
#
# **재기만 하고 아무것도 안 바꿉니다.** 내리기 전에 한 번, 올라온 뒤에 한 번
# 돌려서 두 출력을 나란히 놓고 봅니다 — 같은 것을 같은 방식으로 재야 견줄 수
# 있어서 명령을 그때그때 다시 짜지 않고 이 파일 하나로 둡니다.
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File scripts\되살아나나.ps1
#
# **일부러 안 찍는 것이 있습니다** — 바깥 주소 · 터널 id · 커넥터 id ·
# 나가는 쪽 IP. 이 출력은 **보고와 채팅 덩어리에 그대로 실리고**, 11-2 의
# 「저장소와 실명」 이 그 둘에 바깥 주소를 적지 말라고 합니다(안내서인
# `docs/배포-안내.md` 에는 있어야 하는 값입니다 — 금지의 자리가 다릅니다).
# 붙어 있는지(몇 개인지 · 언제 붙었는지)만으로 「섰나」 는 판정됩니다.
#
# **관리자 권한이 없어도 돕니다.** 서비스를 다시 시작하거나 작업을 멈추는
# 것은 이 파일이 하지 않습니다 — 그것은 배포-안내 12장입니다.

$ErrorActionPreference = 'Continue'
$뿌리 = Split-Path -Parent $PSScriptRoot

"때: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') (KST)"
try {
  "마지막 부팅: $((Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToString('yyyy-MM-dd HH:mm:ss'))"
} catch { "마지막 부팅: 못 읽었습니다 — $($_.Exception.Message)" }
""

# ── 1. 작업 스케줄러에 걸린 이 저장소의 일 ────────────────────────────
# **이름으로 고릅니다.** 이 노트북에는 다른 프로그램의 작업도 걸려 있고,
# 그것까지 세면 「우리 것이 다 있나」 를 못 봅니다.
"[작업 스케줄러 — 이름이 「대청부」 로 시작하는 것]"
$일 = Get-ScheduledTask | Where-Object { $_.TaskName -like '대청부*' } | Sort-Object TaskName
if (-not $일) { "  없습니다 — 이것 자체가 고장입니다" }
foreach ($t in $일) {
  $i = Get-ScheduledTaskInfo -TaskName $t.TaskName -TaskPath $t.TaskPath
  $트리거 = ($t.Triggers | ForEach-Object { $_.CimClass.CimClassName -replace '^MSFT_Task', '' -replace 'Trigger$', '' }) -join ','
  if (-not $트리거) { $트리거 = '없음' }
  $동작 = ($t.Actions | ForEach-Object { Split-Path -Leaf $_.Execute }) -join ','
  "  {0,-12} 상태={1,-9} 켬={2,-5} 트리거={3,-12} 동작={4}" -f $t.TaskName, $t.State, $t.Settings.Enabled, $트리거, $동작
  "  {0,-12}   마지막실행={1} 결과={2} 다음={3}" -f '', $i.LastRunTime, $i.LastTaskResult, $i.NextRunTime
  # **꺼져 있으면 그때 안 돕니다.** 「등록돼 있다」 와 「돈다」 는 다릅니다.
  if ($t.Settings.DisallowStartIfOnBatteries) { "  {0,-12}   !! 배터리면 시작 안 함" -f '' }
  if (-not $t.Settings.StartWhenAvailable -and $트리거 -match 'Daily|Weekly|Time') {
    "  {0,-12}   !! 그 시각에 꺼져 있었으면 건너뛰고 나중에 안 채웁니다 (StartWhenAvailable=False)" -f ''
  }
}
""

# ── 2. 터널 ───────────────────────────────────────────────────────────
# **터널은 작업 스케줄러에 없습니다 — 윈도우 서비스입니다** (배포-안내 8-3).
# 작업 목록만 보면 통째로 안 보이는 자리라 여기서 따로 봅니다.
"[터널 — 윈도우 서비스 Cloudflared]"
$s = Get-CimInstance Win32_Service -Filter "Name='Cloudflared'" -ErrorAction SilentlyContinue
if (-not $s) {
  "  서비스가 없습니다 — 밖에서 못 들어옵니다 (배포-안내 8-3)"
} else {
  "  상태={0} 시작={1} 계정={2}" -f $s.State, $s.StartMode, $s.StartName
  # 등록 경로에 --config 가 빠지면 켜지자마자 1067 로 죽습니다 (배포-안내 8-3).
  "  실행 경로에 --config 있음: {0}" -f [bool]($s.PathName -match '--config')
}
$cf = 'C:\cloudflared\cloudflared.exe'
if (-not (Test-Path $cf)) {
  "  $cf 가 없습니다 — 못 쟀습니다"
} else {
  $글 = (& $cf tunnel info daecheongbu 2>&1 | Out-String)
  # **못 잰 것과 안 붙은 것을 가릅니다.** 이 명령은 사용자 폴더의 cert 가
  # 있어야 도는데(배포-안내 3·8-3), 다른 계정이나 관리자 창에서 돌리면
  # 실패합니다. 종료 코드를 안 보면 그때도 「0개」 가 나와서, 사람이 멀쩡한
  # 터널을 다시 시작하러 갑니다 — **구별되지 않는 실패가 가장 비쌉니다**(12장).
  if ($LASTEXITCODE -ne 0) {
    "  붙은 커넥터: **못 쟀습니다** — tunnel info 가 $LASTEXITCODE 로 끝났습니다"
    "    (안 붙은 것이 아닙니다. 배포-안내 11장 ② 로 사람이 봅니다)"
  } else {
    # **id 와 IP 는 안 찍습니다.** 몇 개가 언제 붙었는지만 냅니다.
    $붙음 = [regex]::Matches($글, '(?m)^[0-9a-f-]{36}\s+(\S+)')
    "  붙은 커넥터: $($붙음.Count)개"
    foreach ($m in $붙음) { "    붙은 때: $($m.Groups[1].Value) (UTC)" }
    if ($붙음.Count -eq 0) { "    !! 비어 있으면 서비스가 떠 있어도 밖에서는 못 들어옵니다" }
  }
}
""

# ── 3. 앱 ─────────────────────────────────────────────────────────────
"[앱 — 127.0.0.1:8000]"
$쥔 = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
      Select-Object -ExpandProperty OwningProcess -Unique
if (-not $쥔) { "  아무도 8000 을 안 쥐고 있습니다" } else {
  "  포트를 쥔 PID: $($쥔 -join ', ')"
  # **PID 가 바뀌는 것만으로는 「부팅이 띄웠다」 가 안 됩니다** — 이 작업에는
  # 「실패하면 다시 시작」 이 켜져 있어 재부팅 없이도 새 PID 가 섭니다
  # (봐둘것 AM-f · AX-c). 시작 시각이 마지막 부팅 뒤인지로 갈립니다.
  foreach ($id in $쥔) {
    $pr = Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
    if ($pr -and $pr.CreationDate) {
      "    {0} 시작: {1}" -f $id, $pr.CreationDate.ToString('yyyy-MM-dd HH:mm:ss')
    } else {
      "    {0} 시작: 못 읽었습니다" -f $id
    }
  }
}
try {
  $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/login' -UseBasicParsing -TimeoutSec 10
  "  안에서 GET /login -> $($r.StatusCode)"
} catch { "  안에서 GET /login -> 실패: $($_.Exception.Message)" }
""

# ── 4. 백업 ───────────────────────────────────────────────────────────
# 파일이 몇 개인지가 아니라 **새벽 3시 것이 언제까지 있나**를 봅니다 —
# 스크립트가 손으로 뜬 사본도 같은 폴더에 쌓여서, 개수로는 안 갈립니다.
"[백업 — data\backups]"
$방 = Join-Path $뿌리 'data\backups'
if (-not (Test-Path $방)) { "  폴더가 없습니다" } else {
  $새벽 = Get-ChildItem $방 -Filter 'app-*.db' |
          Where-Object { $_.Name -match 'app-(\d{8})-03\d{4}\.db' } |
          Sort-Object Name
  "  새벽 3시 백업: $($새벽.Count)개"
  if ($새벽) {
    "    가장 이른 것: $($새벽[0].Name)"
    "    가장 최근 것: $($새벽[-1].Name)"
  } else { "    !! 하나도 없습니다 — 하루에 한 번 도는 것이 안 돌고 있습니다" }
  $전부 = Get-ChildItem $방 -Filter 'app-*.db'
  "  손으로 뜬 것까지 합쳐: $($전부.Count)개"
}
