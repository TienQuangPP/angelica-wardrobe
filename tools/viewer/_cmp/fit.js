// Fit the wardrobe camera to a screenshot of the game's window (debug tool, not used by the page).
// Renders the stage without the character and compares edge maps with the game picture.
//   const m = await import('/_cmp/fit.js'); await m.run({ img: '/_cmp/g.png' })
const W = 475, H = 258;  // quarter of the game's 1900x1031 client area

function gray(data) {
  const g = new Float32Array(W * H);
  for (let i = 0; i < W * H; i++) g[i] = 0.3 * data[i * 4] + 0.59 * data[i * 4 + 1] + 0.11 * data[i * 4 + 2];
  return g;
}
function grad(g) {
  const out = new Float32Array(W * H);
  for (let y = 1; y < H - 1; y++) {
    for (let x = 1; x < W - 1; x++) {
      const i = y * W + x;
      const gx = g[i + 1] - g[i - 1], gy = g[i + W] - g[i - W];
      out[i] = Math.sqrt(gx * gx + gy * gy);
    }
  }
  return out;
}

export async function run({ img = '/_cmp/g.png', iters = 400, mask: maskRects, points = [], weight = 0.5, start: p00 } = {}) {
  const { THREE, renderer, scene, camera, charGroup, controls } = window.tudo;
  const im = new Image();
  im.src = img;
  await im.decode();
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const ctx = c.getContext('2d');
  ctx.drawImage(im, 0, 0, W, H);
  const gameG = grad(gray(ctx.getImageData(0, 0, W, H).data));
  // pixels used: the 3D view between the panels, without the character, the portrait HUD and the name plate
  const skip = maskRects || [[0, 0, 360, 1031], [1600, 0, 1900, 1031], [380, 100, 720, 250], [880, 360, 1180, 1000],
    [1450, 0, 1900, 60], [0, 0, 420, 70]];
  const use = new Uint8Array(W * H);
  for (let y = 2; y < H - 2; y++) {
    for (let x = 2; x < W - 2; x++) {
      const X = x * 4, Y = y * 4;
      use[y * W + x] = skip.some(([a, b, cc, d]) => X >= a && X < cc && Y >= b && Y < d) ? 0 : 1;
    }
  }
  const rt = new THREE.WebGLRenderTarget(W, H, { samples: 4 });
  rt.texture.colorSpace = THREE.SRGBColorSpace;
  const px = new Uint8Array(W * H * 4);
  const cam = camera.clone();
  cam.clearViewOffset();
  cam.aspect = W / H;
  const wasVisible = charGroup.visible;
  charGroup.visible = false;
  const target = controls.target.clone();
  const off = camera.position.clone().sub(target);
  // parameters: target x,y,z, distance, yaw, pitch, fov, lens shift x
  const sph = new THREE.Spherical().setFromVector3(off);
  let p0 = p00 || [target.x, target.y, target.z, sph.radius, sph.theta, sph.phi, camera.fov, -71 / 1918 * 2];
  const pts = points.map(q => ({ v: new THREE.Vector3(...q.p), px: q.px }));
  const pixErr = () => {
    let e = 0;
    for (const q of pts) {
      const n = q.v.clone().project(cam);
      const x = (n.x + 1) / 2 * 1900, y = (1 - n.y) / 2 * 1031;
      e += (x - q.px[0]) ** 2 + (y - q.px[1]) ** 2;
    }
    return pts.length ? e / pts.length : 0;
  };
  const scale = [0.3, 0.3, 0.3, 1.0, 0.08, 0.06, 4, 0.05];
  function setCam(p, cm = cam) {
    const t = new THREE.Vector3(p[0], p[1], p[2]);
    const pos = new THREE.Vector3().setFromSpherical(new THREE.Spherical(p[3], p[5], p[4])).add(t);
    cm.position.copy(pos);
    cm.fov = p[6];
    cm.up.set(0, 1, 0);
    cm.lookAt(t);
    cm.updateProjectionMatrix();
    // lens shift (the game draws the character right of the centre)
    cm.projectionMatrix.elements[8] = p[7];
    cm.projectionMatrixInverse.copy(cm.projectionMatrix).invert();
    return t;
  }
  function score(p) {
    setCam(p);
    renderer.setRenderTarget(rt);
    renderer.render(scene, cam);
    renderer.readRenderTargetPixels(rt, 0, 0, W, H, px);
    renderer.setRenderTarget(null);
    // flip rows
    const flipped = new Uint8Array(W * H * 4);
    for (let y = 0; y < H; y++) flipped.set(px.subarray((H - 1 - y) * W * 4, (H - y) * W * 4), y * W * 4);
    const ourG = grad(gray(flipped));
    let sa = 0, sb = 0, n = 0;
    for (let i = 0; i < W * H; i++) if (use[i]) { sa += ourG[i]; sb += gameG[i]; n++; }
    const ma = sa / n, mb = sb / n;
    let num = 0, da = 0, db = 0;
    for (let i = 0; i < W * H; i++) {
      if (!use[i]) continue;
      const a = ourG[i] - ma, b = gameG[i] - mb;
      num += a * b; da += a * a; db += b * b;
    }
    return -num / Math.sqrt(da * db + 1e-9) + weight * pixErr() / 2500;
  }
  // Nelder-Mead
  const n = p0.length;
  let simplex = [p0.slice()];
  for (let i = 0; i < n; i++) { const q = p0.slice(); q[i] += scale[i]; simplex.push(q); }
  let vals = simplex.map(score);
  const start = vals[0];
  for (let it = 0; it < iters; it++) {
    const idx = vals.map((v, i) => i).sort((a, b) => vals[a] - vals[b]);
    simplex = idx.map(i => simplex[i]); vals = idx.map(i => vals[i]);
    const cen = new Array(n).fill(0);
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) cen[j] += simplex[i][j] / n;
    const worst = simplex[n];
    const refl = cen.map((v, j) => v + (v - worst[j]));
    const fr = score(refl);
    if (fr < vals[0]) {
      const exp = cen.map((v, j) => v + 2 * (v - worst[j]));
      const fe = score(exp);
      if (fe < fr) { simplex[n] = exp; vals[n] = fe; } else { simplex[n] = refl; vals[n] = fr; }
    } else if (fr < vals[n - 1]) {
      simplex[n] = refl; vals[n] = fr;
    } else {
      const con = cen.map((v, j) => v + 0.5 * (worst[j] - v));
      const fc = score(con);
      if (fc < vals[n]) { simplex[n] = con; vals[n] = fc; } else {
        for (let i = 1; i <= n; i++) { simplex[i] = simplex[i].map((v, j) => simplex[0][j] + 0.5 * (v - simplex[0][j])); vals[i] = score(simplex[i]); }
      }
    }
  }
  const best = vals.indexOf(Math.min(...vals));
  const p = simplex[best];
  charGroup.visible = wasVisible;
  const t = setCam(p);
  rt.dispose();
  return { start: -start, score: -vals[best], pixelError: Math.sqrt(pixErr()), params: p, position: cam.position.toArray(), target: t.toArray(), fov: p[6], shift: p[7],
    stage: charGroup.position.toArray() };
}

// apply fitted parameters to the live camera (for screenshots)
export function apply(p) {
  const { THREE, camera, controls } = window.tudo;
  const t = new THREE.Vector3(p[0], p[1], p[2]);
  camera.position.copy(new THREE.Vector3().setFromSpherical(new THREE.Spherical(p[3], p[5], p[4])).add(t));
  controls.target.copy(t);
  camera.fov = p[6];
  window.__lensShift = p[7];
  controls.update();
}
