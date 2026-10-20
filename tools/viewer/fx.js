// Approximate player for Angelica .gfx effects exported by tools/build_fx.py.
// Coordinates inside an effect are the game's (left-handed); FxPlayer.root mirrors Z once.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const BLEND = {
  1: THREE.ZeroFactor, 2: THREE.OneFactor, 3: THREE.SrcColorFactor, 4: THREE.OneMinusSrcColorFactor,
  5: THREE.SrcAlphaFactor, 6: THREE.OneMinusSrcAlphaFactor, 7: THREE.DstAlphaFactor,
  8: THREE.OneMinusDstAlphaFactor, 9: THREE.DstColorFactor, 10: THREE.OneMinusDstColorFactor,
};
const MAX_PARTICLES = 400;
const rand = (a, b) => a + Math.random() * (b - a);
const vec = a => new THREE.Vector3(a?.[0] || 0, a?.[1] || 0, a?.[2] || 0);
const UP = new THREE.Vector3(0, 1, 0);

// ---------- shared resources ----------
const textures = new Map();
const getRetry = url => (window.fetchRetry ? window.fetchRetry(url) : fetch(url));
function texture(url) {
  if (!url) return null;
  if (!textures.has(url)) {
    const t = new THREE.Texture();
    t.colorSpace = THREE.NoColorSpace;
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.flipY = true;
    getRetry(url).then(r => r.blob()).then(b => createImageBitmap(b, { imageOrientation: 'flipY' })).then(img => {
      t.image = img;
      t.flipY = false;  // already flipped by createImageBitmap
      t.needsUpdate = true;
    }).catch(() => {});
    textures.set(url, t);
  }
  return textures.get(url);
}

const VERT_BILLBOARD = `
  attribute vec3 iPos; attribute vec2 iSize; attribute float iRot; attribute vec4 iColor; attribute vec4 iUV;
  varying vec2 vUv; varying vec4 vColor;
  void main() {
    vec4 mv = modelViewMatrix * vec4(iPos, 1.0);
    float s = sin(iRot), c = cos(iRot);
    vec2 p = position.xy * iSize;
    mv.xy += vec2(p.x * c - p.y * s, p.x * s + p.y * c);
    gl_Position = projectionMatrix * mv;
    vUv = iUV.xy + uv * iUV.zw;
    vColor = iColor;
  }`;
const VERT_MESH = `
  attribute vec4 color4; varying vec2 vUv; varying vec4 vColor; uniform vec4 tint; uniform vec4 uvRect;
  void main() {
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    vUv = uvRect.xy + uv * uvRect.zw;
    vColor = tint * color4;
  }`;
const FRAG = `
  uniform sampler2D map; uniform float hasMap; varying vec2 vUv; varying vec4 vColor;
  void main() {
    vec4 c = (hasMap > 0.5 ? texture2D(map, vUv) : vec4(1.0)) * vColor;
    if (c.a < 0.003) discard;
    gl_FragColor = c;
  }`;

function material(el, vertexShader, uniforms = {}) {
  const map = texture(el.texUrl);
  return new THREE.ShaderMaterial({
    uniforms: { map: { value: map }, hasMap: { value: map ? 1 : 0 }, ...uniforms },
    vertexShader, fragmentShader: FRAG,
    transparent: true, depthWrite: false, depthTest: el.z !== 0, side: THREE.DoubleSide,
    blending: THREE.CustomBlending,
    blendSrc: BLEND[el.src ?? 5] ?? THREE.SrcAlphaFactor, blendDst: BLEND[el.dst ?? 6] ?? THREE.OneMinusSrcAlphaFactor,
  });
}

class Billboards {
  constructor(max, mat) {
    const plane = new THREE.PlaneGeometry(1, 1);
    const geo = new THREE.InstancedBufferGeometry();
    geo.index = plane.index;
    geo.setAttribute('position', plane.getAttribute('position'));
    geo.setAttribute('uv', plane.getAttribute('uv'));
    const attr = (name, size) => {
      const a = new THREE.InstancedBufferAttribute(new Float32Array(max * size), size);
      a.setUsage(THREE.DynamicDrawUsage);
      geo.setAttribute(name, a);
      return a;
    };
    this.pos = attr('iPos', 3); this.size = attr('iSize', 2); this.rot = attr('iRot', 1);
    this.color = attr('iColor', 4); this.uv = attr('iUV', 4);
    geo.instanceCount = 0;
    this.geo = geo;
    this.mesh = new THREE.Mesh(geo, mat);
    this.mesh.frustumCulled = false;
    this.max = max;
  }
  set(i, p, w, h, rot, c, uv) {
    this.pos.setXYZ(i, p.x, p.y, p.z); this.size.setXY(i, w, h); this.rot.setX(i, rot);
    this.color.setXYZW(i, c[0], c[1], c[2], c[3]); this.uv.setXYZW(i, uv[0], uv[1], uv[2], uv[3]);
  }
  commit(n) {
    this.geo.instanceCount = n;
    for (const a of [this.pos, this.size, this.rot, this.color, this.uv]) a.needsUpdate = true;
  }
}

// Texture atlas frame -> [u0, v0, du, dv]
function frameUV(el, frame) {
  const rows = Math.max(1, el.rows || 1), cols = Math.max(1, el.cols || 1);
  const n = rows * cols;
  const f = ((Math.floor(frame) % n) + n) % n;
  const r = Math.floor(f / cols), c = f % cols;
  return [c / cols, 1 - (r + 1) / rows, 1 / cols, 1 / rows];
}

// ---------- controllers ----------
function colorTrans(c, ms) {
  const cols = c.c || [], spans = c.d || [];
  if (!cols.length) return null;
  let t = ms;
  for (let i = 0; i < cols.length - 1; i++) {
    const d = spans[i] ?? spans[spans.length - 1] ?? 1;
    if (t <= d) {
      const f = d > 0 ? t / d : 1;
      return cols[i].map((v, k) => v + (cols[i + 1][k] - v) * f);
    }
    t -= d;
  }
  return cols[cols.length - 1].slice();
}

function scaleTrans(c, ms) {
  const ks = c.k || [], spans = c.d || [];
  if (!ks.length) return null;
  let t = ms;
  for (let i = 0; i < ks.length - 1; i++) {
    const d = spans[i] ?? spans[spans.length - 1] ?? 1;
    if (t <= d) return ks[i] + (ks[i + 1] - ks[i]) * (d > 0 ? t / d : 1);
    t -= d;
  }
  return ks[ks.length - 1];
}

function curve(c) {
  if (!c._curve) {
    const pts = (c.p || []).map(vec);
    c._curve = pts.length >= 2 ? new THREE.CatmullRomCurve3(pts) : null;
    c._single = pts[0] || new THREE.Vector3();
  }
  return c._curve;
}

const _v = new THREE.Vector3(), _q = new THREE.Quaternion();
// st: {pos: Vector3, quat: Quaternion, color: [4], scale, rot}; tau and span in seconds
function applyCtrl(c, st, tau, span) {
  const start = c.s || 0, end = c.e < 0 ? Infinity : c.e;
  if (tau < start) return;
  const t = Math.min(tau, end) - start;
  const dist = (c.v || 0) * t + 0.5 * (c.a || 0) * t * t;
  switch (c.t) {
    case 100: st.pos.addScaledVector(vec(c.dir).normalize(), dist); break;
    case 101: st.rot += dist; break;
    case 102:
    case 103: {
      const axis = vec(c.ax).normalize();
      if (axis.lengthSq() === 0) break;
      _q.setFromAxisAngle(axis, dist);
      const center = vec(c.p);
      st.pos.sub(center).applyQuaternion(_q).add(center);
      if (c.t === 102) st.quat.premultiply(_q);
      break;
    }
    case 104: {
      _v.copy(st.pos).sub(vec(c.p));
      if (_v.lengthSq() > 1e-8) st.pos.addScaledVector(_v.normalize(), dist);
      break;
    }
    case 105: for (let k = 0; k < 4; k++) st.color[k] = Math.min(1, Math.max(0, st.color[k] + (c.cd?.[k] || 0) / 255 * t)); break;
    case 106: {
      const [d, lo, hi] = c.sc || [0, 0, 9999];
      st.scale = Math.min(hi, Math.max(lo, st.scale + d * t));
      break;
    }
    case 108: {
      const col = colorTrans(c, t * 1000);
      if (col) {
        if (c.ao) st.color[3] = col[3];
        else st.color = col;
      }
      break;
    }
    case 110: {
      const cv = curve(c);
      const u = span > 0 ? Math.min(1, t / span) : 0;
      st.pos.add(cv ? cv.getPoint(u) : c._single);
      break;
    }
    case 111: {
      const s = scaleTrans(c, t * 1000);
      if (s != null) st.scale = s;
      break;
    }
    default: break;  // noise controllers are not reproduced
  }
}

// ---------- element timeline ----------
// Returns null when inactive, {done:true} when finished, otherwise the evaluated state.
function evaluate(el, ms) {
  const kps = el.kps || [];
  let t = ms - (el.start || 0);
  if (t < 0) return null;
  let total = 0, infinite = !kps.length;
  for (const kp of kps) { if (kp.d < 0) { infinite = true; break; } total += kp.d; }
  if (!infinite) {
    const rep = el.rep ?? 1, cycle = total + (el.repd || 0);
    if (rep >= 0 && t >= cycle * Math.max(rep, 1)) return { done: true };
    t = cycle > 0 ? t % cycle : 0;
    if (t > total) return null;
  }
  const st = { pos: new THREE.Vector3(), quat: new THREE.Quaternion(), color: [1, 1, 1, 1], scale: 1, rot: 0, t };
  if (!kps.length) return st;
  let acc = 0, i = 0;
  for (; i < kps.length - 1; i++) {
    if (kps[i].d < 0 || t < acc + kps[i].d) break;
    acc += kps[i].d;
  }
  const kp = kps[i], next = kps[i + 1];
  const tau = t - acc;
  const f = next && kp.d > 0 ? Math.min(1, tau / kp.d) : 0;
  st.pos.copy(vec(kp.p)).lerp(vec(next?.p || kp.p), f);
  st.quat.set(...(kp.q || [0, 0, 0, 1])).normalize();
  if (next) st.quat.slerp(new THREE.Quaternion(...(next.q || [0, 0, 0, 1])).normalize(), f);
  st.color = kp.c.map((v, k) => v + ((next?.c || kp.c)[k] - v) * f);
  st.scale = kp.s + ((next?.s ?? kp.s) - kp.s) * f;
  st.rot = kp.r + ((next?.r ?? kp.r) - kp.r) * f;
  for (const c of kp.ctrl || []) applyCtrl(c, st, tau / 1000, kp.d > 0 ? kp.d / 1000 : 1);
  return st;
}

// ---------- elements ----------
class ParticleElement {
  constructor(el) {
    this.el = el;
    const p = el.props;
    this.quota = Math.min(MAX_PARTICLES, p.Quota > 0 ? p.Quota : MAX_PARTICLES);
    this.bb = new Billboards(this.quota, material(el, VERT_BILLBOARD));
    this.object = this.bb.mesh;
    this.parts = [];
    this.acc = 0;
    this.colorMin = argb(p.ColorMin ?? -1);
    this.colorMax = argb(p.ColorMax ?? -1);
    this.accVec = vec(p.AccDir).multiplyScalar(p.Acc || 0);
    this.curve = p.curve?.length >= 2 ? new THREE.CatmullRomCurve3(p.curve.map(vec)) : null;
  }
  spawnOffset() {
    const p = this.el.props, a = vec(Array.isArray(p.AreaSize) ? p.AreaSize : [0, 0, 0]);
    switch (this.el.t) {
      case 121: case 122:
        return new THREE.Vector3(rand(-.5, .5) * a.x, rand(-.5, .5) * a.y, rand(-.5, .5) * a.z);
      case 123: {
        const d = new THREE.Vector3(rand(-1, 1), rand(-1, 1), rand(-1, 1)).normalize();
        const r = p.IsSurface ? 1 : Math.cbrt(Math.random());
        return d.multiply(a).multiplyScalar(r);
      }
      case 124: {
        const ang = rand(0, Math.PI * 2), r = p.IsSurface ? 1 : Math.sqrt(Math.random());
        return new THREE.Vector3(Math.cos(ang) * a.x * r, rand(-.5, .5) * a.z, Math.sin(ang) * a.y * r);
      }
      case 125: {
        const base = this.curve ? this.curve.getPoint(Math.random()) : new THREE.Vector3();
        const rad = p.Radius || 0;
        return base.add(new THREE.Vector3(rand(-1, 1), rand(-1, 1), rand(-1, 1)).normalize().multiplyScalar(rad * Math.random()));
      }
      default: return new THREE.Vector3();
    }
  }
  spawn(st) {
    const p = this.el.props;
    const dir = UP.clone();
    const ang = p.Angle || 0;
    if (ang > 0) dir.applyEuler(new THREE.Euler(rand(-ang, ang), 0, rand(-ang, ang)));
    dir.applyQuaternion(st.quat);
    const k = Math.random();
    const scale = rand(p.ScaleMin ?? 1, p.ScaleMax ?? 1);
    const offset = this.spawnOffset().multiplyScalar(st.scale).applyQuaternion(st.quat);
    this.parts.push({
      age: 0, ttl: Math.max(0.05, p.TTL || 1),
      local: offset, origin: st.pos.clone(), pos: new THREE.Vector3(),
      vel: dir.clone().multiplyScalar(p.Speed || 0), acc: dir.clone().multiplyScalar(p.ParAcc || 0).add(this.accVec),
      color: this.colorMin.map((v, i) => (v + (this.colorMax[i] - v) * k) * st.color[i]),
      scale: scale * st.scale, rot: rand(p.RotMin || 0, p.RotMax || 0),
      frame: this.el.props.InitRandomTexture ? Math.floor(Math.random() * 64) : 0,
    });
  }
  update(dt, st) {
    const p = this.el.props;
    if (st && !st.done) {
      this.emitter = st;
      this.acc += (p.EmissionRate || 0) * dt;
      while (this.acc >= 1 && this.parts.length < this.quota) { this.spawn(st); this.acc -= 1; }
      if (this.parts.length >= this.quota) this.acc = 0;
    }
    const w = p.ParticleWidth || 0.1, h = p.ParticleHeight || 0.1;
    let n = 0;
    this.parts = this.parts.filter(q => (q.age += dt) < q.ttl);
    for (const q of this.parts) {
      q.vel.addScaledVector(q.acc, dt);
      q.local.addScaledVector(q.vel, dt);
      const base = p.IsBind && this.emitter ? this.emitter.pos : q.origin;
      const s = { pos: q.pos.copy(base).add(q.local), quat: new THREE.Quaternion(), color: q.color.slice(), scale: q.scale, rot: q.rot };
      for (const c of this.el.aff || []) applyCtrl(c, s, q.age, q.ttl);
      const frame = q.frame + (this.el.ti > 0 ? q.age * 1000 / this.el.ti : 0);
      this.bb.set(n++, s.pos, w * s.scale, h * s.scale, s.rot, s.color, frameUV(this.el, frame));
    }
    this.bb.commit(n);
  }
}

class DecalElement {
  constructor(el) {
    this.el = el;
    const p = el.props;
    const grid = el.t === 210 || el.t === 211;
    this.w = grid ? Math.max(1, (p.wNumber || 2) - 1) * (p.fGridSize || 1) : (p.Width ?? 1);
    this.h = grid ? Math.max(1, (p.hNumber || 2) - 1) * (p.fGridSize || 1) : (p.Height ?? 1);
    // Screen / billboard decals face the camera; 3D decals keep their own orientation.
    this.facing = el.t === 101 || el.t === 102 || el.t === 211 || p.RotFromView === 1;
    if (this.facing) {
      this.bb = new Billboards(1, material(el, VERT_BILLBOARD));
      this.object = this.bb.mesh;
    } else {
      const geo = new THREE.PlaneGeometry(1, 1);
      geo.setAttribute('color4', new THREE.Float32BufferAttribute(new Array(16).fill(1), 4));
      this.mat = material(el, VERT_MESH, { tint: { value: new THREE.Vector4(1, 1, 1, 1) }, uvRect: { value: new THREE.Vector4(0, 0, 1, 1) } });
      this.object = new THREE.Mesh(geo, this.mat);
    }
  }
  update(dt, st) {
    const on = st && !st.done;
    this.object.visible = !!on;
    if (!on) return;
    const uv = frameUV(this.el, this.el.ti > 0 ? st.t / this.el.ti : 0);
    if (this.facing) {
      this.bb.set(0, st.pos, this.w * st.scale, this.h * st.scale, st.rot, st.color, uv);
      this.bb.commit(1);
    } else {
      this.object.position.copy(st.pos);
      this.object.quaternion.copy(st.quat);
      this.object.rotateZ(st.rot);
      this.object.scale.set(this.w * st.scale, this.h * st.scale, 1);
      this.mat.uniforms.tint.value.set(...st.color);
      this.mat.uniforms.uvRect.value.set(...uv);
    }
  }
}

class RingElement {
  constructor(el) {
    this.el = el;
    const p = el.props, r = p.Radius || 0.5, hgt = p.Height || 0.2, pitch = p.Pitch || Math.PI / 2;
    const top = r + (Math.abs(Math.tan(pitch)) > 1e-3 ? hgt / Math.tan(pitch) : 0);
    const geo = new THREE.CylinderGeometry(top, r, hgt, 32, 1, true);
    if (!p.OrgAtCenter) geo.translate(0, hgt / 2, 0);
    geo.setAttribute('color4', new THREE.Float32BufferAttribute(new Array(geo.attributes.position.count * 4).fill(1), 4));
    this.mat = material(el, VERT_MESH, { tint: { value: new THREE.Vector4(1, 1, 1, 1) }, uvRect: { value: new THREE.Vector4(0, 0, 1, 1) } });
    this.object = new THREE.Mesh(geo, this.mat);
  }
  update(dt, st) {
    const on = st && !st.done;
    this.object.visible = !!on;
    if (!on) return;
    this.object.position.copy(st.pos);
    this.object.quaternion.copy(st.quat);
    this.object.scale.setScalar(st.scale);
    this.mat.uniforms.tint.value.set(...st.color);
    this.mat.uniforms.uvRect.value.set(...frameUV(this.el, this.el.ti > 0 ? st.t / this.el.ti : 0));
  }
}

class TrailElement {
  constructor(el) {
    this.el = el;
    const p = el.props;
    this.a = vec(p.OrgPos1 || [0.05, 0.05, 0.05]);
    this.b = vec(p.OrgPos2 || [-0.05, -0.05, -0.05]);
    this.life = (p.SegLife || 500) / 1000;
    this.max = 96;
    this.samples = [];
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(this.max * 2 * 3), 3).setUsage(THREE.DynamicDrawUsage));
    geo.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(this.max * 2 * 2), 2).setUsage(THREE.DynamicDrawUsage));
    geo.setAttribute('color4', new THREE.BufferAttribute(new Float32Array(this.max * 2 * 4), 4).setUsage(THREE.DynamicDrawUsage));
    const idx = [];
    for (let i = 0; i < this.max - 1; i++) idx.push(2 * i, 2 * i + 1, 2 * i + 2, 2 * i + 1, 2 * i + 3, 2 * i + 2);
    geo.setIndex(idx);
    this.geo = geo;
    this.mat = material(el, VERT_MESH, { tint: { value: new THREE.Vector4(1, 1, 1, 1) }, uvRect: { value: new THREE.Vector4(0, 0, 1, 1) } });
    this.object = new THREE.Mesh(geo, this.mat);
    this.object.frustumCulled = false;
  }
  update(dt, st) {
    for (const s of this.samples) s.age += dt;
    this.samples = this.samples.filter(s => s.age < this.life);
    if (st && !st.done) {
      const a = this.a.clone().multiplyScalar(st.scale).applyQuaternion(st.quat).add(st.pos);
      const b = this.b.clone().multiplyScalar(st.scale).applyQuaternion(st.quat).add(st.pos);
      this.samples.unshift({ a, b, age: 0, color: st.color.slice() });
      if (this.samples.length > this.max) this.samples.length = this.max;
    }
    const pos = this.geo.attributes.position, uv = this.geo.attributes.uv, col = this.geo.attributes.color4;
    const n = this.samples.length;
    this.samples.forEach((s, i) => {
      const u = s.age / this.life, fade = 1 - u;
      pos.setXYZ(2 * i, s.a.x, s.a.y, s.a.z); pos.setXYZ(2 * i + 1, s.b.x, s.b.y, s.b.z);
      uv.setXY(2 * i, u, 0); uv.setXY(2 * i + 1, u, 1);
      col.setXYZW(2 * i, s.color[0], s.color[1], s.color[2], s.color[3] * fade);
      col.setXYZW(2 * i + 1, s.color[0], s.color[1], s.color[2], s.color[3] * fade);
    });
    this.geo.setDrawRange(0, n > 1 ? (n - 1) * 6 : 0);
    pos.needsUpdate = uv.needsUpdate = col.needsUpdate = true;
  }
}

const gltf = new GLTFLoader();
class ModelElement {
  constructor(el, base) {
    this.el = el;
    this.object = new THREE.Group();
    if (!el.model) return;
    getRetry(base + el.model).then(r => r.arrayBuffer()).then(buf => gltf.parseAsync(buf, '')).then(g => {
      g.scene.traverse(m => {
        if (!m.isMesh) return;
        m.material = m.material.clone();
        m.material.transparent = true;
        m.material.depthWrite = false;
        if (el.dst === 2) m.material.blending = THREE.AdditiveBlending;
        m.material.side = THREE.DoubleSide;
      });
      // Effect models are converted to glTF (right-handed); undo that inside the mirrored effect space.
      g.scene.scale.z = -1;
      this.object.add(g.scene);
      this.meshes = [];
      g.scene.traverse(m => { if (m.isMesh) this.meshes.push(m); });
    }).catch(() => {});
  }
  update(dt, st) {
    const on = st && !st.done;
    this.object.visible = !!on;
    if (!on) return;
    this.object.position.copy(st.pos);
    this.object.quaternion.copy(st.quat);
    this.object.scale.setScalar(st.scale);
    for (const m of this.meshes || []) m.material.opacity = st.color[3];
  }
}

class ContainerElement {
  constructor(el, defs, base) {
    this.el = el;
    this.object = new THREE.Group();
    this.child = el.gfx && defs[el.gfx] ? new GfxInstance(defs, el.gfx, base) : null;
    if (this.child) this.object.add(this.child.group);
    this.speed = el.props.PlaySpeed || 1;
  }
  update(dt, st) {
    const on = st && !st.done;
    this.object.visible = !!on;
    if (!on || !this.child) return;
    this.object.position.copy(st.pos);
    this.object.quaternion.copy(st.quat);
    this.object.scale.setScalar(st.scale);
    this.child.update(dt * this.speed);
  }
  get finished() { return !this.child || this.child.finished; }
}

function argb(c) {
  const v = (Number(c) >>> 0);
  return [((v >>> 16) & 255) / 255, ((v >>> 8) & 255) / 255, (v & 255) / 255, ((v >>> 24) & 255) / 255];
}

function makeElement(el, defs, base) {
  el.texUrl = el.tex ? base + el.tex : null;
  switch (el.t) {
    case 120: case 121: case 122: case 123: case 124: case 125: return new ParticleElement(el);
    case 100: case 101: case 102: case 210: case 211: return new DecalElement(el);
    case 110: return new TrailElement(el);
    case 140: return new RingElement(el);
    case 160: return new ModelElement(el, base);
    case 200: return new ContainerElement(el, defs, base);
    default: return null;  // lightning, paraboloid, sound...
  }
}

class GfxInstance {
  constructor(defs, key, base) {
    this.def = defs[key];
    this.group = new THREE.Group();
    this.group.scale.setScalar(this.def.scale || 1);
    this.items = [];
    for (const el of this.def.elements || []) {
      const obj = makeElement(el, defs, base);
      if (obj) { this.items.push(obj); this.group.add(obj.object); }
    }
    this.time = 0;
    this.finished = false;
  }
  update(dt) {
    this.time += dt * 1000 * (this.def.speed || 1);
    let allDone = true;
    for (const it of this.items) {
      const st = evaluate(it.el, this.time);
      if (st && !st.done) st.color[3] *= this.def.alpha ?? 1;
      it.update(dt, st);
      if (!(st && st.done) || (it instanceof ParticleElement && it.parts.length)) allDone = false;
    }
    // Fashion effects play continuously in game: restart once everything has finished.
    if (allDone || this.time > 60000) this.time = 0;
  }
}

export class FxPlayer {
  constructor(scene) {
    this.root = new THREE.Group();
    this.root.scale.set(1, 1, -1);  // game space is left-handed
    scene.add(this.root);
    this.instances = [];
    this.cache = new Map();
  }
  async add(base, fx) {
    const url = base + fx.u;
    if (!this.cache.has(url)) this.cache.set(url, getRetry(url).then(r => r.json()));
    const data = await this.cache.get(url);
    const fxBase = url.slice(0, url.lastIndexOf('/') + 1);
    const inst = new GfxInstance(structuredClone(data.defs), data.root, fxBase);
    inst.group.position.set(...fx.p);
    if (fx.s) inst.group.scale.multiplyScalar(fx.s);
    this.root.add(inst.group);
    this.instances.push(inst);
    return inst;
  }
  clear() {
    for (const inst of this.instances) {
      this.root.remove(inst.group);
      inst.group.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose?.(); });
    }
    this.instances = [];
  }
  set visible(v) { this.root.visible = v; }
  update(dt) { for (const inst of this.instances) inst.update(Math.min(dt, 0.1)); }
}
