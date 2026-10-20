# Tiny static file server for the 3D viewer (no admin rights, no Python needed).
# Serves the folder this script lives in on http://localhost:<port>/ and opens the browser.
param([int]$Port = 8753, [switch]$NoBrowser, [string]$Page = 'xem_3d.html')

$root = [IO.Path]::GetFullPath((Split-Path -Parent $MyInvocation.MyCommand.Path)).TrimEnd('\') + '\'
$types = @{
    '.html' = 'text/html; charset=utf-8'; '.js' = 'text/javascript; charset=utf-8'
    '.json' = 'application/json; charset=utf-8'; '.css' = 'text/css; charset=utf-8'
    '.glb' = 'model/gltf-binary'; '.png' = 'image/png'; '.jpg' = 'image/jpeg'; '.dds' = 'application/octet-stream'
}

$listener = $null
for ($p = $Port; $p -lt $Port + 20; $p++) {
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $p)
        $listener.Start()
        $Port = $p
        break
    } catch { $listener = $null }
}
if (-not $listener) { Write-Host "Khong mo duoc cong may chu."; Read-Host; exit 1 }

$url = "http://localhost:$Port/$Page"
Write-Host "Trinh xem 3D dang chay tai $url"
Write-Host "Dong cua so nay de tat."
if (-not $NoBrowser) { Start-Process $url }

$ascii = [Text.Encoding]::ASCII
# Browsers open spare connections before they have a request to send. Keep every accepted
# connection in a list and only serve the ones that have data, so idle ones never block others.
$waiting = New-Object System.Collections.ArrayList
while ($true) {
    while ($listener.Pending()) {
        [void]$waiting.Add(@{ Client = $listener.AcceptTcpClient(); Since = [DateTime]::UtcNow })
    }
    $client = $null
    foreach ($entry in @($waiting)) {
        if ($entry.Client.Available -gt 0) {
            $client = $entry.Client
            $waiting.Remove($entry)
            break
        }
        if (([DateTime]::UtcNow - $entry.Since).TotalSeconds -gt 60) {
            $entry.Client.Close()
            $waiting.Remove($entry)
        }
    }
    if (-not $client) {
        Start-Sleep -Milliseconds 5
        continue
    }
    $client.ReceiveTimeout = 5000
    $client.SendTimeout = 30000
    try {
        $stream = $client.GetStream()
        $reader = New-Object System.IO.StreamReader($stream, $ascii, $false, 8192, $true)
        $requestLine = $reader.ReadLine()
        while ($true) { $h = $reader.ReadLine(); if ($null -eq $h -or $h -eq '') { break } }
        if (-not $requestLine) { continue }
        $target = ($requestLine -split ' ')[1].Split('?')[0]
        $rel = [Uri]::UnescapeDataString($target).TrimStart('/').Replace('/', '\')
        if ($rel -eq '') { $rel = 'xem_3d.html' }
        $full = [IO.Path]::GetFullPath((Join-Path $root $rel))
        if ($full.StartsWith($root, [StringComparison]::OrdinalIgnoreCase) -and [IO.File]::Exists($full)) {
            $body = [IO.File]::ReadAllBytes($full)
            $type = $types[[IO.Path]::GetExtension($full).ToLower()]
            if (-not $type) { $type = 'application/octet-stream' }
            $status = '200 OK'
        } else {
            $body = [Text.Encoding]::UTF8.GetBytes('Not found')
            $type = 'text/plain'
            $status = '404 Not Found'
        }
        # tu_do\dds\ files are named after their content: they never change, let the browser keep them
        $cache = if ($rel -like 'tu_do\dds\*') { 'max-age=31536000, immutable' } else { 'no-cache' }
        $head = $ascii.GetBytes("HTTP/1.1 $status`r`nContent-Type: $type`r`nContent-Length: $($body.Length)`r`nCache-Control: $cache`r`nConnection: close`r`n`r`n")
        $stream.Write($head, 0, $head.Length)
        $stream.Write($body, 0, $body.Length)
        $stream.Flush()
    } catch {
    } finally {
        $client.Close()
    }
}
