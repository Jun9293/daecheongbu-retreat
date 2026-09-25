# 창을 앞으로 내고, **확인된 때만** 창 조작 키를 보낸다.
#
# 왜 저장소 안에 있나 — 2026-09-24 판까지 이 일은 저장소 **밖**(임시 폴더)의
# 스크립트가 했다. 그래서 무엇을 보내는지, 무엇을 확인하고 보내는지가
# 어디에도 안 적혀 있었고, 커밋 전 검토가 「이것이 선 안인지 밖인지 규칙이
# 없다」 고 짚어 사람에게 올렸다. 2026-09-25 에 사람이 정했다 —
#
#   · 창을 앞으로 내는 것은 된다
#   · 키는 **그 창이 앞에 왔는지 확인한 뒤에만** 보낸다 (창 제목 · 주소 8001)
#   · **창 조작 키만** 보낸다. 글자 입력과 Enter 는 보내지 않는다
#
# 규칙은 CLAUDE.md 11-2 에 있고 여기는 그것을 지키는 자리다.
#
#   .\창앞으로.ps1 -목록
#   .\창앞으로.ps1 -앞으로 <hwnd>
#   .\창앞으로.ps1 -앞으로 <hwnd> -제목조각 "목록" -주소 "http://127.0.0.1:8001/tasks" -키 "^9"
#
# **BOM 을 붙여 저장한다** — Windows PowerShell 5.1 은 BOM 이 없으면 .ps1 을
# 시스템 코드페이지로 읽어 한글 이름이 깨지고 파싱부터 실패한다
# (`되살아나나.ps1` · `.bat` 을 cp949 로 두는 것과 같은 자리).
#   **`-최대화` 는 두지 않는다** — 사람의 창 상태를 바꾸면서 되돌리지 않는
#   스위치였고, 부르는 자리도 없었다. 10장이 드로어 폭에서 세운 규칙
#   (되돌릴 수 있으면 되돌리고 `finally` 에 둔다)과 부딪힌다.
param(
  [switch]$목록,
  [long]$앞으로 = 0,
  [string]$제목조각 = '',
  [string]$주소 = '',
  [string]$키 = ''
)

# **보낼 수 있는 키는 이 목록뿐이다.** 탭을 고르는 것만 있다 — 글자도,
# Enter 도, 조합키로 무언가를 저장하거나 닫는 것도 없다. 목록 밖은
# **보내지 않는다**(거절하고 까닭을 찍는다). 목록을 넓히려면 사람이 정한다.
$허용키 = @('^1', '^2', '^3', '^4', '^5', '^6', '^7', '^8', '^9')

# 주소가 이것으로 시작할 때만 키를 보낸다 — 운영(8000)이나 바깥 주소에서는
# 아무 키도 안 보낸다. **이 값은 부르는 쪽이 탭에서 읽어 넘긴다**:
# 창 제목만으로는 포트를 알 수 없어서다(그 한계는 보고에 적는다).
$허용주소 = 'http://127.0.0.1:8001'

if (-not ('Win3' -as [type])) {
  Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public class Win3 {
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsZoomed(IntPtr h);
  [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool attach);
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
  public delegate bool EnumProc(IntPtr h, IntPtr p);
  public static string TitleOf(IntPtr h) {
    var t = new StringBuilder(512); GetWindowTextW(h, t, 512); return t.ToString();
  }
  public static List<string> List() {
    var outp = new List<string>();
    EnumWindows(delegate(IntPtr h, IntPtr p) {
      if (!IsWindowVisible(h)) return true;
      var cls = new StringBuilder(256); GetClassNameW(h, cls, 256);
      if (cls.ToString() != "Chrome_WidgetWin_1") return true;
      var t = TitleOf(h);
      if (t.Length == 0) return true;
      uint pid; GetWindowThreadProcessId(h, out pid);
      outp.Add(h.ToInt64() + "|" + pid + "|" + t);
      return true;
    }, IntPtr.Zero);
    return outp;
  }
  // 윈도우가 배경 프로세스의 SetForegroundWindow 를 막으므로, 지금 앞에
  // 있는 창의 입력 스레드에 잠깐 붙었다 뗀다.
  public static bool Front(IntPtr h) {
    IntPtr fore = GetForegroundWindow();
    uint foreTid = GetWindowThreadProcessId(fore, out _dummy);
    uint myTid = GetCurrentThreadId();
    if (foreTid != myTid) AttachThreadInput(myTid, foreTid, true);
    // **최소화됐을 때만 되돌린다** — 최대화된 창에 SW_RESTORE 를 주면
    // 최대화가 풀려 폭이 줄고, 그러면 drawer.js 의 전제(1280px 위)가 깨진다
    if (IsIconic(h)) ShowWindow(h, 9);   // SW_RESTORE
    bool ok = SetForegroundWindow(h);
    if (foreTid != myTid) AttachThreadInput(myTid, foreTid, false);
    return ok;
  }
  static uint _dummy;
}
'@
}

if ($목록 -or $앞으로 -eq 0) {
  [Win3]::List() | ForEach-Object { $_ }
  return
}

$h = [IntPtr]$앞으로
$냈나 = [Win3]::Front($h)
Start-Sleep -Milliseconds 500
$앞에온것 = [Win3]::GetForegroundWindow().ToInt64()
$맞나 = ($앞에온것 -eq $앞으로)
# **앞에 온 창에서 읽는다** — 요청한 창에서 읽으면 「앞에 온 창의 제목이
# 다르다」 는 말이 거짓일 수 있다(그 창이 앞에 안 왔을 때). 지금은 맞나
# 검사가 먼저 막지만, 두 문의 순서에 기대는 말은 순서가 바뀌면 거짓이 된다
$제목 = [Win3]::TitleOf([IntPtr]$앞에온것)
"앞으로 $앞으로 · SetForegroundWindow $냈나 · 지금 앞 $앞에온것 · 맞나 $맞나 · 최대화 $([Win3]::IsZoomed($h))"
"확인한 제목: $제목"

if (-not $키) { return }

# ── 키를 보내기 전에 넷을 본다. 하나라도 아니면 **안 보낸다.** ──────────
# 「확인된 때만 보낸다」 이지 「아닌 것이 확인될 때만 안 보낸다」 가 아니다 —
# 못 읽는 자리가 생겨도 조용히 보내는 쪽으로 기울지 않는다.
$막힘 = @()
if ($허용키 -notcontains $키)            { $막힘 += "허용 목록에 없는 키다: $키" }
if (-not $맞나)                          { $막힘 += "그 창이 앞에 안 왔다 (지금 앞 $앞에온것)" }
if (-not $제목조각)                      { $막힘 += "-제목조각 이 없다 (무엇을 확인할지 모른다)" }
elseif (-not $제목.Contains($제목조각)) { $막힘 += "앞에 온 창의 제목이 다르다" }
if (-not $주소)                          { $막힘 += "-주소 가 없다" }
elseif (-not ($주소 -eq $허용주소 -or $주소.StartsWith($허용주소 + '/'))) {
  $막힘 += "주소가 $허용주소 의 것이 아니다"
}

if ($막힘.Count -gt 0) {
  "키를 안 보냈다 — " + ($막힘 -join ' · ')
  return
}

# **보내기 직전에 한 번 더 본다.** 위에서 잰 뒤 SendKeys 까지 사이에 앞 창이
# 바뀔 수 있다 — 그 틈으로 나가면 **남의 창에 키가 들어간다.**
$지금앞 = [Win3]::GetForegroundWindow().ToInt64()
if ($지금앞 -ne $앞으로) {
  "키를 안 보냈다 — 재는 사이에 앞 창이 바뀌었다 (지금 앞 $지금앞)"
  return
}

$ws = New-Object -ComObject WScript.Shell
$ws.SendKeys($키)
"보낸 키: $키 (제목 확인 「$제목조각」 · 주소 확인 $허용주소)"
