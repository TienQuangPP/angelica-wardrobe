# Capture the TGHM client area from the screen (the game must be the window in front; D3D content is black with
# PrintWindow). Uses the process main window and its client rectangle, so it works even when the foreground
# handle is a helper window of the game.
param([string]$Out = ".\game.png", [string]$Proc = "elementclient_64")
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class C2 {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [StructLayout(LayoutKind.Sequential)] public struct PT { public int X, Y; }
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref PT p);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@
[C2]::SetProcessDPIAware() | Out-Null
$h = (Get-Process $Proc | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1).MainWindowHandle
$cr = New-Object C2+RECT; [C2]::GetClientRect($h, [ref]$cr) | Out-Null
$p = New-Object C2+PT; [C2]::ClientToScreen($h, [ref]$p) | Out-Null
$bmp = New-Object System.Drawing.Bitmap $cr.R, $cr.B
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($p.X, $p.Y, 0, 0, $bmp.Size)
$g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output "client=$($cr.R)x$($cr.B) at $($p.X),$($p.Y) -> $Out"
