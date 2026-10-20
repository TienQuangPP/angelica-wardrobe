# Passive capture of the TGHM window (elementclient_64): only when it is ALREADY the foreground window.
# Never changes focus and never sends input, so other apps (e.g. a running LoL match) are untouched.
param([string]$Out = ".\game.png", [string]$Proc = "elementclient_64")
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class W {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
}
"@
[W]::SetProcessDPIAware() | Out-Null
$fg = [W]::GetForegroundWindow()
$fgPid = 0
[W]::GetWindowThreadProcessId($fg, [ref]$fgPid) | Out-Null
$fgProc = (Get-Process -Id $fgPid -ErrorAction SilentlyContinue).ProcessName
if ($fgProc -ne $Proc) { Write-Output "NOT_FOREGROUND ($fgProc is in front)"; exit 3 }
$r = New-Object W+RECT
[W]::GetWindowRect($fg, [ref]$r) | Out-Null
$w = $r.R - $r.L; $hh = $r.B - $r.T
$bmp = New-Object System.Drawing.Bitmap $w, $hh
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r.L, $r.T, 0, 0, $bmp.Size)
$g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output "size=${w}x${hh} at $($r.L),$($r.T) -> $Out"
