# Grab the TGHM client area at full resolution with PrintWindow (works while other windows cover it).
# Sends no input and never changes focus.
param([string]$Out = ".\g.png", [string]$Proc = "elementclient_64")
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class PW {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [StructLayout(LayoutKind.Sequential)] public struct PT { public int X, Y; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref PT p);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@
[PW]::SetProcessDPIAware() | Out-Null
$h = (Get-Process $Proc | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1).MainWindowHandle
$wr = New-Object PW+RECT; [PW]::GetWindowRect($h, [ref]$wr) | Out-Null
$cr = New-Object PW+RECT; [PW]::GetClientRect($h, [ref]$cr) | Out-Null
$p = New-Object PW+PT; [PW]::ClientToScreen($h, [ref]$p) | Out-Null
$w = $wr.R - $wr.L; $hh = $wr.B - $wr.T
$bmp = New-Object System.Drawing.Bitmap $w, $hh
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
$ok = [PW]::PrintWindow($h, $hdc, 2)
$g.ReleaseHdc($hdc); $g.Dispose()
$ox = $p.X - $wr.L; $oy = $p.Y - $wr.T
$client = $bmp.Clone((New-Object System.Drawing.Rectangle $ox, $oy, $cr.R, $cr.B), $bmp.PixelFormat)
$client.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose(); $client.Dispose()
Write-Output "ok=$ok client=$($cr.R)x$($cr.B) -> $Out"
