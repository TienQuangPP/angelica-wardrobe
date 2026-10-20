// Drive the headless Chrome started with --remote-debugging-port=9333 (see the launch line below).
//   node cdp.mjs nav <url>
//   node cdp.mjs eval "<js expression>"         (awaits promises, prints the JSON result)
//   node cdp.mjs shot <out.png> [x y w h]
//   node cdp.mjs size <w> <h>
// Launch: chrome --headless=new --remote-debugging-port=9333 --user-data-dir=<a scratch profile folder> about:blank
const PORT = 9333;
const [cmd, ...args] = process.argv.slice(2);
const targets = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();
const page = targets.find(t => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let id = 0;
const pending = new Map();
ws.onmessage = ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
};
const send = (method, params = {}) => new Promise(res => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
const fs = await import('node:fs');
// device metrics only last as long as this session: set them on every run (the game's client area)
const [VW, VH] = (process.env.VIEW || '1900x1031').split('x').map(Number);
await send('Emulation.setDeviceMetricsOverride', { width: VW, height: VH, deviceScaleFactor: 1, mobile: false });
await new Promise(res => setTimeout(res, +(process.env.SETTLE || 600)));

if (cmd === 'size') {
  const r = await send('Emulation.setDeviceMetricsOverride', { width: +args[0], height: +args[1], deviceScaleFactor: 1, mobile: false });
  console.log(JSON.stringify(r.result || r.error));
} else if (cmd === 'nav') {
  await send('Page.enable');
  const r = await send('Page.navigate', { url: args[0] });
  console.log(JSON.stringify(r.result || r.error));
} else if (cmd === 'eval') {
  const r = await send('Runtime.evaluate', { expression: args[0], awaitPromise: true, returnByValue: true });
  if (r.result?.exceptionDetails) console.log('ERROR', JSON.stringify(r.result.exceptionDetails.exception?.description || r.result.exceptionDetails));
  else console.log(JSON.stringify(r.result?.result?.value, null, 1));
} else if (cmd === 'shot') {
  const p = { format: 'png' };
  if (args.length >= 5) p.clip = { x: +args[1], y: +args[2], width: +args[3], height: +args[4], scale: 1 };
  const r = await send('Page.captureScreenshot', p);
  fs.writeFileSync(args[0], Buffer.from(r.result.data, 'base64'));
  console.log('saved', args[0]);
} else if (cmd === 'console') {
  await send('Runtime.enable');
  await new Promise(res => setTimeout(res, 200));
}
ws.close();
process.exit(0);
