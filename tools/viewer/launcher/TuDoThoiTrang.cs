// Standalone launcher of the wardrobe (tủ đồ thời trang): no console, no browser bar.
// Starts the local file server (server.ps1, hidden) on a free port, opens tu_do.html in an app window
// (Edge or Chrome --app, profile kept next to the exe so saved outfits and card pictures persist),
// and stops the server when that window is closed. Everything is relative to the exe's folder (USB friendly).
using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Windows.Forms;

static class TuDoThoiTrang
{
    static int FreePort(int start)
    {
        for (int p = start; p < start + 50; p++)
        {
            try { var l = new TcpListener(IPAddress.Loopback, p); l.Start(); l.Stop(); return p; } catch { }
        }
        return start;
    }

    static string Browser()
    {
        string pf = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        string pf86 = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86);
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string[] candidates = {
            Path.Combine(pf86, @"Microsoft\Edge\Application\msedge.exe"),
            Path.Combine(pf, @"Microsoft\Edge\Application\msedge.exe"),
            Path.Combine(pf, @"Google\Chrome\Application\chrome.exe"),
            Path.Combine(pf86, @"Google\Chrome\Application\chrome.exe"),
            Path.Combine(local, @"Google\Chrome\Application\chrome.exe"),
        };
        foreach (var c in candidates) if (File.Exists(c)) return c;
        return null;
    }

    static bool ProfileInUse(string exe, string profile)
    {
        try
        {
            using (var q = new System.Management.ManagementObjectSearcher(
                "SELECT CommandLine FROM Win32_Process WHERE Name='" + exe + "'"))
            {
                foreach (System.Management.ManagementObject p in q.Get())
                {
                    var cmd = p["CommandLine"] as string;
                    if (cmd != null && cmd.IndexOf(profile, StringComparison.OrdinalIgnoreCase) >= 0) return true;
                }
            }
        }
        catch { }
        return false;
    }

    static bool Up(int port)
    {
        try
        {
            var req = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:" + port + "/tu_do.html");
            req.Timeout = 1000;
            using (var res = (HttpWebResponse)req.GetResponse()) return res.StatusCode == HttpStatusCode.OK;
        }
        catch { return false; }
    }

    [STAThread]
    static void Main()
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string server = Path.Combine(root, "server.ps1");
        if (!File.Exists(server))
        {
            MessageBox.Show("Không tìm thấy server.ps1 cạnh chương trình.", "Tủ đồ thời trang");
            return;
        }
        int port = FreePort(8763);
        var srv = Process.Start(new ProcessStartInfo("powershell.exe",
            "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"" + server + "\" -Port " + port +
            " -NoBrowser -Page tu_do.html")
        { CreateNoWindow = true, UseShellExecute = false, WindowStyle = ProcessWindowStyle.Hidden });
        for (int i = 0; i < 100 && !Up(port); i++) Thread.Sleep(100);
        string url = "http://localhost:" + port + "/tu_do.html";
        string browser = Browser();
        try
        {
            if (browser == null)
            {
                Process.Start(url);
                MessageBox.Show("Đang mở tủ đồ trong trình duyệt.\nBấm OK để tắt tủ đồ.", "Tủ đồ thời trang");
            }
            else
            {
                string profile = Path.Combine(root, "_app");
                var app = Process.Start(new ProcessStartInfo(browser,
                    "--app=" + url + " --user-data-dir=\"" + profile + "\" --window-size=1920,1080 --start-maximized" +
                    " --no-first-run --no-default-browser-check --disable-features=Translate") { UseShellExecute = false });
                app.WaitForExit();
                // the browser may hand the window to another process: wait while one still uses our profile
                while (ProfileInUse(Path.GetFileName(browser), profile)) Thread.Sleep(1000);
            }
        }
        finally
        {
            try { if (!srv.HasExited) srv.Kill(); } catch { }
        }
    }
}
