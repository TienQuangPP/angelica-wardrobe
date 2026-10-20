// Wardrobe page: a copy of the in-game "Thu thập" fashion window with a Kiếm Linh character.
// Data comes from tu_do/catalog.json written by tools/build_wardrobe.py.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DDSLoader } from 'three/addons/loaders/DDSLoader.js';
import * as SkeletonUtils from 'three/addons/utils/SkeletonUtils.js';
import { FxPlayer } from './fx.js';
import { AUI, AUI_CSS } from './aui.js';

window.wardrobeReady = true;
const $ = s => document.querySelector(s);
const DATA = 'tu_do/';
const SLOTS = ['hair', 'top', 'bottom', 'wrist', 'shoes'];
const enc = p => p.split('/').map(encodeURIComponent).join('/');

async function fetchRetry(url, tries = 4) {
  for (let i = 1; ; i++) {
    try {
      const r = await fetch(url);
      if (r.ok) return r;
      if (i >= tries) throw new Error('HTTP ' + r.status + ' ' + url);
    } catch (e) {
      if (i >= tries) throw e;
    }
    await new Promise(res => setTimeout(res, 300 * i));
  }
}
window.fetchRetry = fetchRetry;

const toast = (msg, ms = 2200) => {
  const t = $('#toast');
  t.textContent = msg;
  t.style.display = 'block';
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.style.display = 'none'), ms);
};

$('#loadMsg').textContent = 'Đọc danh mục…';
const catalog = await fetchRetry(DATA + 'catalog.json').then(r => r.json());
const ui = path => (catalog.ui[path] ? DATA + catalog.ui[path] : '');
const codex = name => ui('version02\\系统\\时装图鉴\\' + name + '.tga');
const setBg = (el, url) => { if (url) el.style.backgroundImage = `url("${url}")`; };

// ---------------------------------------------------------------- persistent state
const store = {
  get: (k, d) => { try { return JSON.parse(localStorage.getItem('tudo_' + k)) ?? d; } catch { return d; } },
  set: (k, v) => localStorage.setItem('tudo_' + k, JSON.stringify(v)),
};
const state = {
  cid: /[?&]nam\b/.test(location.search) ? 'nam' : 'nu',  // always opens on Kiếm Linh nữ (tu_do.html?nam for male)
  face: 1,
  parts: {},
  dyes: {},
  setId: null,
  tab: 'set',
  view: 'list',  // 'list' (folders), 'all' (Tinh giản icon grid) or 'search' (results page)
  allMode: 'owned',  // Tinh giản: 'owned' (Đã có) or 'all' (Tất cả Đồ Giám)
  dyeTarget: 'all',
  selected: null,
};
const setsById = cid => Object.fromEntries(catalog.sets[cid].map(s => [s.id, s]));
let SETS = setsById(state.cid);

// ---------------------------------------------------------------- three.js scene
const canvas = $('#c');
// The game draws without anti-aliasing (crisp, slightly jagged edges): same here (tu_do.html?aa to turn it on)
const renderer = new THREE.WebGLRenderer({ canvas, antialias: /[?&]aa\b/.test(location.search) });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
// The game (D3D9) dyes and lights the raw texture values (gamma space). Doing the same here keeps dyed colours
// right: a 90% dye mask over white leaves ~10% white in the game, but ~30% after a linear-space mix.
// So no colour management: textures are read as-is (gammaTex) and the result is written as-is.
THREE.ColorManagement.enabled = false;
renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
const gammaTex = tex => {
  if (tex && tex.colorSpace !== THREE.NoColorSpace) { tex.colorSpace = THREE.NoColorSpace; tex.needsUpdate = true; }
  return tex;
};
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xd9c3e6);
// Camera of the game's fashion window, fitted on its screenshot (tools/viewer/_cmp/fit.js: platform rim, eyes,
// feet and the edges of the stage): level, at eye height, 10.6 m away, 20.5° field of view (stage-relative).
const CAM = { fov: 20.52, shift: 0, target: [-0.172, 1.423, 0.025], eye: [-0.095, 1.416, 10.613] };
const camera = new THREE.PerspectiveCamera(CAM.fov, 1, 0.05, 600);
camera.position.set(0, 1.25, 4.6);
const controls = new OrbitControls(camera, canvas);
controls.target.set(0, 0.95, 0);
controls.enablePan = false;
controls.minDistance = 1.2;
controls.maxDistance = 16;
controls.minPolarAngle = Math.PI * 0.2;
controls.maxPolarAngle = Math.PI * 0.56;
controls.enableDamping = true;
// flat, mostly ambient light like the fashion window of the game (fitted on the cape red, cream and skin
// colours of its screenshot: tools/_ref/look_err.py)
const LIGHT = { day: { hemi: 3.2, sun: 0.75 }, night: { hemi: 2.1, sun: 0.45 } };
const hemi = new THREE.HemisphereLight(0xffffff, 0xc8b8b0, LIGHT.day.hemi);
const sun = new THREE.DirectionalLight(0xfff1e8, LIGHT.day.sun);
sun.position.set(2, 5, 4);
const rim = new THREE.DirectionalLight(0xe8d8ff, 0.3);
rim.position.set(-3, 3, -4);
scene.add(hemi, sun, rim);

function resize() {
  const w = innerWidth, h = innerHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  // the game draws the character a little right of the window centre
  camera.setViewOffset(w, h, -CAM.shift * w, 0, w, h);
  camera.updateProjectionMatrix();
}
addEventListener('resize', resize);
resize();

const gltfLoader = new GLTFLoader();
const buffers = new Map();
const getBuffer = url => {
  if (!buffers.has(url)) buffers.set(url, fetchRetry(enc(url)).then(r => r.arrayBuffer()));
  return buffers.get(url);
};
const parsed = new Map();
const loadGlb = url => {
  if (!parsed.has(url)) parsed.set(url, getBuffer(url).then(b => gltfLoader.parseAsync(b.slice(0), '')));
  return parsed.get(url);
};
// The game's own textures (tu_do/dds, copied by tools/ski_to_glb.py): the same DXT blocks and mipmaps the game
// samples, so the clothes are exactly as sharp as in the game. The glb's embedded picture is only a fallback.
const ddsLoader = new DDSLoader();
const ddsTextures = new Map();
const S3TC = !!renderer.extensions.get('WEBGL_compressed_texture_s3tc');
function gameTexture(name) {
  if (!ddsTextures.has(name)) {
    ddsTextures.set(name, new Promise((res, rej) => ddsLoader.load(DATA + 'dds/' + name, t => {
      t.colorSpace = THREE.NoColorSpace;
      t.wrapS = t.wrapT = THREE.RepeatWrapping;  // D3D default sampler: wrap
      t.userData.shared = true;
      res(t);
    }, undefined, rej)));
  }
  return ddsTextures.get(name);
}
function useGameTextures(root) {
  if (!S3TC) return Promise.resolve();
  const jobs = [];
  root.traverse(m => {
    if (!m.isMesh) return;
    for (const mat of [].concat(m.material)) {
      const u = mat.userData;
      if (u.dds) jobs.push(gameTexture(u.dds).then(t => { mat.map = t; mat.needsUpdate = true; }).catch(() => {}));
      if (u.ddsChannel && u.uChannel) jobs.push(gameTexture(u.ddsChannel).then(t => { u.uChannel.value = t; }).catch(() => {}));
    }
  });
  return Promise.all(jobs);
}
// The game's fashion shader (shaders\2.2\hlsl\materials\fashionrender.hlsl): the texture alpha is the dye
// mask, rgb = lerp(tex, tex * fashionColour, tex.a), and the result is always opaque.
// The game's view glows (bloom): a light screen blend in display space lifts the shading like it does.
const GLOW = 0.06;
// systemsettings.ini of the game: MipMapBias = 1 -> textures are sampled from a sharper mipmap level
const MIP_BIAS = -1.0;
// Newer fashions (rewurender.hlsl) carry a channel map (exported in the occlusion slot): blue = dye mask,
// green = strength of the armour reflection picture added on top; their texture alpha is plain transparency.
const REFLECT = new THREE.TextureLoader().load(DATA + (catalog.reflect || 'armorreflect.png'));
REFLECT.colorSpace = THREE.NoColorSpace;
REFLECT.wrapS = REFLECT.wrapT = THREE.RepeatWrapping;
// shared look settings (uniforms, so they can be tuned live against the game's screenshots)
const LOOK = { reflect: { value: 1.0 }, glow: { value: GLOW }, bias: { value: MIP_BIAS } };
function setupDye(mat) {
  mat.userData.dye = { value: new THREE.Color(1, 1, 1) };
  const masked = !!mat.userData.dyeMask;
  const channel = mat.userData.dyeChannel ? mat.userData.channel || mat.aoMap : null;
  if (masked) {
    mat.transparent = false;
    mat.alphaTest = 0;
  }
  if (channel) {
    mat.userData.channel = channel;
    mat.userData.uChannel = { value: channel };
    mat.aoMap = null;
  }
  mat.onBeforeCompile = sh => {
    sh.uniforms.uDye = mat.userData.dye;
    sh.uniforms.uReflectK = LOOK.reflect;
    sh.uniforms.uGlow = LOOK.glow;
    sh.uniforms.uBias = LOOK.bias;
    let fs = 'uniform vec3 uDye;\nuniform float uReflectK;\nuniform float uGlow;\nuniform float uBias;\n' + sh.fragmentShader;
    if (masked) {
      fs = fs.replace('#include <map_fragment>', `
#ifdef USE_MAP
  vec4 texel = texture2D( map, vMapUv, uBias );
  diffuseColor.rgb *= mix( texel.rgb, texel.rgb * uDye, texel.a );
#endif`);
    } else if (channel) {
      sh.uniforms.uChannel = mat.userData.uChannel;
      sh.uniforms.uReflect = { value: REFLECT };
      fs = 'uniform sampler2D uChannel;\nuniform sampler2D uReflect;\n' + fs;
      fs = fs.replace('#include <map_fragment>', `
#ifdef USE_MAP
  vec4 texel = texture2D( map, vMapUv, uBias );
  vec4 dyeCh = texture2D( uChannel, vMapUv, uBias );
  diffuseColor.rgb *= mix( texel.rgb, texel.rgb * uDye, dyeCh.b );
  diffuseColor.a *= texel.a;
#endif`);
      fs = fs.replace('#include <opaque_fragment>', `
#ifdef USE_MAP
  outgoingLight += uReflectK * dyeCh.g * texture2D( uReflect, normalize( normal ).xy * 0.5 + 0.5 ).rgb;
#endif
#include <opaque_fragment>`);
    } else {
      fs = fs.replace('#include <map_fragment>', `
#ifdef USE_MAP
  diffuseColor *= texture2D( map, vMapUv, uBias );
#endif`);
    }
    sh.fragmentShader = fs.replace('#include <colorspace_fragment>', `#include <colorspace_fragment>
  gl_FragColor.rgb = 1.0 - ( 1.0 - gl_FragColor.rgb ) * ( 1.0 - uGlow );`);
  };
  mat.customProgramCacheKey = () => (masked ? 'dyeMask' : channel ? 'dyeChannel' : 'char');
  return mat;
}
// colour of one material: masked materials take it in the shader, the others multiply the whole texture
function setDye(mat, color) {
  if (mat.userData.dyeMask || mat.userData.channel) {
    mat.userData.dye.value.copy(color);
    mat.color.setRGB(1, 1, 1);
  } else {
    mat.color.copy(color);
  }
}
// The game's character shaders (fashionrender / rewurender) are plain Lambert: saturate(sun * N.L + ambient) * colour,
// no specular. A PBR material would add a white sheen that turns dyed reds pink.
function toLambert(src) {
  // rewurender transparency (alphaMode BLEND): blended, but texels that are almost clear write no depth
  const blend = src.transparent;
  const mat = new THREE.MeshLambertMaterial({
    name: src.name, map: gammaTex(src.map), color: src.color.clone(), side: src.side, transparent: blend,
    opacity: src.opacity, alphaTest: blend ? Math.max(src.alphaTest, 0.03) : src.alphaTest,
    depthWrite: blend ? true : src.depthWrite,
  });
  mat.userData = { dyeMask: !!src.userData.dyeMask, dyeChannel: !!src.userData.dyeChannel,
    channel: src.userData.channel || src.aoMap || null, dds: src.userData.dds, ddsChannel: src.userData.ddsChannel };
  return mat;
}
const rgbColor = rgb => new THREE.Color().setRGB(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, THREE.SRGBColorSpace);
const HAIR_ALPHA = 0.2;  // alpha cut-off of customface hair strands
const WHITE = new THREE.Color(1, 1, 1);

function instance(gltf) {
  const obj = SkeletonUtils.clone(gltf.scene);
  obj.traverse(m => {
    if (m.isMesh) {
      m.material = setupDye(toLambert(m.material));
      m.userData.base = m.material.color.clone();
      m.frustumCulled = false;  // skinned meshes move away from their bind-pose bounds
    }
  });
  obj.userData.textures = useGameTextures(obj);
  return obj;
}
// GLTFLoader renames nodes ("Bip01 Pelvis" -> "Bip01_Pelvis"); look bones up the same way
const boneName = n => THREE.PropertyBinding.sanitizeNodeName(n || '');
const bonesOf = obj => {
  const out = {};
  obj.traverse(o => { if (o.isBone) out[o.name] = o; });
  return out;
};
// Every part carries its own copy of the skeleton; drive it with the body's bones instead.
function rebind(obj, bones) {
  obj.traverse(m => {
    if (!m.isSkinnedMesh) return;
    const list = m.skeleton.bones.map(b => bones[b.name] || b);
    m.bind(new THREE.Skeleton(list, m.skeleton.boneInverses), m.bindMatrix);
  });
}

// ---------------------------------------------------------------- body shape (dị dung [Body] sliders)
// Per bone [length, thickness, whole, segment flag] from tools/body_shape.py, applied like the game's A3DBone:
// a bone's length / thickness scale the segment from its parent (in the parent's skin matrix, along the
// parent->bone direction; a leaf bone thickens its own segment), the length also moves the joint (relative
// translation * parent whole * length) and the whole scale is inherited by the children.
function scaleAlong(d, len, thick) {  // I + (len - thick) d dᵀ + (thick - 1) I   (symmetric)
  const m = new THREE.Matrix4(), e = m.elements, v = [d.x, d.y, d.z];
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) e[j * 4 + i] = (i === j ? thick : 0) + (len - thick) * v[i] * v[j];
  return m;
}
function setupBodyShape(bones, shape) {
  const list = Object.values(bones);
  for (const b of list) {
    delete b.userData.shapeMat; delete b.userData.posScale;
    b.userData.bindPos ??= b.position.clone();
    b.userData.bindQuat ??= b.quaternion.clone();
  }
  if (!shape) return [];
  const info = Object.fromEntries(Object.entries(shape).map(([n, v]) => [boneName(n), v]));
  const accum = new Map();
  const whole = b => {
    if (!accum.has(b)) accum.set(b, (b.parent?.isBone ? whole(b.parent) : 1) * (info[b.name]?.[2] ?? 1));
    return accum.get(b);
  };
  const moved = [];
  for (const b of list) {
    const st = info[b.name];
    const k = (b.parent?.isBone ? whole(b.parent) : 1) * (st?.[0] ?? 1);
    if (Math.abs(k - 1) > 1e-6) {
      b.userData.posScale = k;
      b.userData.rawPos = b.position.clone();
      moved.push(b);
    }
    let S = null;
    const kids = b.children.filter(c => c.isBone);
    for (const c of kids) {
      const cs = info[c.name];
      if (!cs || !cs[3] || (cs[0] === 1 && cs[1] === 1) || !c.userData.bindPos.lengthSq()) continue;
      S = (S || new THREE.Matrix4()).multiply(scaleAlong(c.userData.bindPos.clone().normalize(), cs[0], cs[1]));
    }
    if (!kids.length && st && st[1] !== 1 && b.userData.bindPos.lengthSq()) {
      const d = b.userData.bindPos.clone().applyQuaternion(b.userData.bindQuat.clone().invert()).normalize();
      S = scaleAlong(d, 1, st[1]);
    }
    const a = whole(b);
    if (a !== 1) S = (S || new THREE.Matrix4()).multiply(new THREE.Matrix4().makeScale(a, a, a));
    if (S) b.userData.shapeMat = S;
  }
  for (const b of moved) b.position.multiplyScalar(b.userData.posScale);
  return moved;
}
// around an animation update: put the joints back, let the clip move them, scale them again
function unshapeJoints(moved) { for (const b of moved) b.position.copy(b.userData.rawPos); }
function shapeJoints(moved) {
  for (const b of moved) { b.userData.rawPos.copy(b.position); b.position.multiplyScalar(b.userData.posScale); }
}
{
  const update = THREE.Skeleton.prototype.update, m = new THREE.Matrix4();
  THREE.Skeleton.prototype.update = function () {
    update.call(this);
    const { bones, boneInverses, boneMatrices } = this;
    for (let i = 0; i < bones.length; i++) {
      const S = bones[i].userData.shapeMat;
      if (S) m.multiplyMatrices(bones[i].matrixWorld, S).multiply(boneInverses[i]).toArray(boneMatrices, i * 16);
    }
  };
}

// ---------------------------------------------------------------- animations
const clipCache = new Map();
function loadClips(url) {
  if (!clipCache.has(url)) {
    clipCache.set(url, fetchRetry(url).then(r => r.json()).then(j => j.clips.map(c =>
      new THREE.AnimationClip(c.name, c.duration || -1, c.tracks.flatMap(t => {
        const tr = [];
        const bone = boneName(t.n);
        if (t.t.length) tr.push(new THREE.QuaternionKeyframeTrack(`${bone}.quaternion`, t.t, t.q));
        if (t.pt.length && t.p.length) tr.push(new THREE.VectorKeyframeTrack(`${bone}.position`, t.pt, t.p));
        return tr;
      })))).catch(() => []));
  }
  return clipCache.get(url);
}
const clipsFor = cid => loadClips(DATA + catalog.characters[cid].anims);

// companion pet of a set (Linh sủng), standing at the character's front left like in the game window
let pet = null, petMixer = null, petUrl = null;
async function showPet(info) {
  const url = info ? DATA + info.glb : null;
  if (url === petUrl) return;
  petUrl = url;
  if (pet) { charGroup.remove(pet); pet = null; petMixer = null; }
  if (!url) return;
  const [g, clips] = await Promise.all([loadGlb(url), loadClips(DATA + info.anims)]);
  if (petUrl !== url) return;
  pet = instance(g);
  pet.position.set(0.72, 0, -0.38);  // character space: the group is turned to face the camera
  charGroup.add(pet);
  if (clips[0]) {
    petMixer = new THREE.AnimationMixer(pet);
    petMixer.clipAction(clips[0]).play();
  }
}
function dispose(obj) {
  obj.traverse(m => {
    if (!m.isMesh) return;
    m.geometry.dispose();
    for (const mat of [].concat(m.material)) {
      for (const k of ['map', 'normalMap', 'emissiveMap', 'aoMap']) if (!mat[k]?.userData.shared) mat[k]?.dispose();
      if (!mat.userData.channel?.userData?.shared) mat.userData.channel?.dispose();
      mat.dispose();
    }
  });
}

// scene backdrop: the fashion window's stage. Game coordinates are left-handed: z is mirrored here.
const toGl = p => new THREE.Vector3(p[0], p[1], -p[2]);
const sceneRoot = new THREE.Group();
scene.add(sceneRoot);
let sceneFx = null, currentScene = null;
async function loadScene(name) {
  const info = catalog.scenes[name];
  if (!info || currentScene === name) return;
  currentScene = name;
  const g = await loadGlb(DATA + info.glb);
  if (currentScene !== name) return;
  sceneRoot.clear();
  sceneFx?.clear();
  const s = g.scene;
  s.position.copy(toGl(info.offset));
  s.traverse(m => {
    if (!m.isMesh || m.userData.basic) return;
    const old = m.material;
    // scene textures carry their own lighting
    m.material = new THREE.MeshBasicMaterial({
      map: gammaTex(old.map), transparent: old.transparent, alphaTest: old.alphaTest || 0, side: THREE.DoubleSide,
      depthWrite: !old.transparent,
    });
    m.material.userData.dds = old.userData.dds;
    m.userData.basic = true;
  });
  useGameTextures(s);
  sceneRoot.add(s);
  sceneFx = new FxPlayer(sceneRoot);
  for (const f of info.fx) {
    sceneFx.add('', { ...f, p: f.p.map((v, i) => v + info.offset[i]) }).catch(() => {});
  }
  // stand the character on the round platform; first view framed like the game's window
  const stage = toGl(info.stage);
  charGroup.position.copy(stage);
  if (!loadScene.framed) {
    loadScene.framed = true;
    controls.target.set(stage.x + CAM.target[0], stage.y + CAM.target[1], stage.z + CAM.target[2]);
    camera.position.set(stage.x + CAM.eye[0], stage.y + CAM.eye[1], stage.z + CAM.eye[2]);
  }
  const night = name === 'blue';
  hemi.intensity = LIGHT[night ? 'night' : 'day'].hemi;
  sun.intensity = LIGHT[night ? 'night' : 'day'].sun;
  rim.color.set(night ? 0x9fb4ff : 0xe8d8ff);
  scene.background.set(night ? 0x1d2550 : 0xd9c3e6);
  store.set('scene', name);
}

// ---------------------------------------------------------------- character
const charGroup = new THREE.Group();
charGroup.rotation.y = Math.PI;  // models face -Z, the camera looks from +Z
scene.add(charGroup);
const charFx = new FxPlayer(charGroup);
const worn = {};  // key -> Object3D (body, face, basehair, hair, top...)
let outfitToken = 0;
let mixer = null, currentClip = null, bodyBones = {}, bindWorld = {}, shapedJoints = [];
const fxFollow = [];  // {inst, bone, local}: effects riding on a bone

async function playAction(name) {
  const body = worn.body;
  if (!body) return;
  const clips = await clipsFor(state.cid);
  const clip = clips.find(c => c.name === name) || clips[0];
  if (!clip) return;
  if (!mixer || mixer.getRoot() !== body) mixer = new THREE.AnimationMixer(body);
  mixer.stopAllAction();
  mixer.clipAction(clip).reset().play();
  currentClip = clip.name;
  store.set('action', clip.name);
  window.onActionChanged?.(clip.name);
}

const character = () => catalog.characters[state.cid];

// every fashion piece of the character: default colour (the game's FASHION_ESSENCE colour range), icon, name
let PART_ITEM = {};
function indexParts(cid) {
  PART_ITEM = {};
  for (const list of Object.values(catalog.items[cid])) for (const it of list) PART_ITEM[it.glb] = it;
}
indexParts(state.cid);

function applyDyes() {
  for (const slot of SLOTS) {
    const obj = worn[slot];
    if (!obj) continue;
    // a dye replaces the fashion colour, exactly like the game (the colour multiplies the masked texels)
    const rgb = state.dyes[slot] ?? state.dyes.all ?? PART_ITEM[state.parts[slot]]?.color;
    const col = rgb ? rgbColor(rgb) : WHITE;
    obj.traverse(m => { if (m.isMesh) setDye(m.material, col); });
  }
  const hairRgb = state.hairColor || character().preset?.hair;
  // customface headwear (hair_x shader): the strands (头发 texture) take the character's hair colour and are
  // alpha-blended in the game, so thin semi-transparent strands must not be cut away
  if (worn.hair && PART_ITEM[state.parts.hair]?.hairTint) {
    worn.hair.traverse(m => {
      if (!m.isMesh || !/头发/.test(m.material.name)) return;
      if (hairRgb && !state.dyes.hair && !state.dyes.all) setDye(m.material, rgbColor(hairRgb));
      if (m.material.alphaTest > HAIR_ALPHA) { m.material.alphaTest = HAIR_ALPHA; m.material.needsUpdate = true; }
    });
  }
  if (worn.basehair) {
    const col = hairRgb ? rgbColor(hairRgb) : WHITE;
    worn.basehair.traverse(m => { if (m.isMesh) setDye(m.material, col); });
  }
  const preset = character().preset;
  if (worn.face && preset?.eye && preset.eyeBase) {
    eyeTexture(preset).then(tex => worn.face?.traverse(m => {
      if (m.isMesh && /眼珠/.test(m.material.name)) {
        m.material.map = tex;
        m.material.color.setRGB(1, 1, 1);
        m.material.needsUpdate = true;
      }
    })).catch(e => console.warn('eye', e));
  }
}

// eyeballrender.hlsl of the game: base * pupil colour, then the highlight texture blended in by its alpha
const eyeTextures = new Map();
function eyeTexture(p) {
  const key = `${p.eyeBase}|${p.eyeHigh}|${p.eye}`;
  if (!eyeTextures.has(key)) {
    const load = url => new Promise((res, rej) => { const im = new Image(); im.onload = () => res(im); im.onerror = rej; im.src = DATA + url; });
    eyeTextures.set(key, Promise.all([load(p.eyeBase), p.eyeHigh ? load(p.eyeHigh) : null]).then(([base, high]) => {
      const c = document.createElement('canvas');
      c.width = base.width; c.height = base.height;
      const ctx = c.getContext('2d');
      ctx.drawImage(base, 0, 0);
      const img = ctx.getImageData(0, 0, c.width, c.height);
      for (let i = 0; i < img.data.length; i += 4) {
        for (let k = 0; k < 3; k++) img.data[i + k] = img.data[i + k] * p.eye[k] / 255;
      }
      ctx.putImageData(img, 0, 0);
      if (high) ctx.drawImage(high, 0, 0, c.width, c.height);
      const tex = new THREE.CanvasTexture(c);
      tex.colorSpace = THREE.NoColorSpace;
      tex.flipY = false;  // glTF texture orientation
      return tex;
    }));
  }
  return eyeTextures.get(key);
}

// the dị dung face: the preset's face shaped by its creator sliders (built by tools/face_morph.py)
function faceModel(ch, faceNo, face) {
  return ch.preset?.faceGlb && faceNo === (ch.preset.face || 1) ? ch.preset.faceGlb : face.face;
}

function setIsComplete(set) {
  return set && Object.entries(set.parts).every(([slot, glb]) => state.parts[slot] === glb);
}

async function applyOutfit() {
  const token = ++outfitToken;
  const ch = character();
  const face = ch.faces[state.face - 1] || ch.faces[0];
  const want = { body: ch.body && DATA + ch.body, face: face && DATA + faceModel(ch, state.face, face) };
  // own hair (dị dung): chosen hairstyle or the face's default; a fashion headwear replaces it
  const style = state.hairStyle || ch.preset?.hairStyle;
  const ownHair = style ? DATA + style : face?.hair && DATA + face.hair;
  if (!state.parts.hair && ownHair) want.basehair = ownHair;
  // an empty slot wears the game's default piece (mini skirt, top, shoes), never bare skin
  for (const slot of SLOTS) want[slot] = state.parts[slot] || ch.defaults?.[slot];
  const loaded = {};
  await Promise.all(Object.entries(want).map(async ([k, url]) => {
    if (!url) return;
    if (worn[k]?.userData.url === url) { loaded[k] = worn[k]; return; }
    try {
      const obj = instance(await loadGlb(url));
      obj.userData.url = url;
      loaded[k] = obj;
    } catch (e) {
      console.warn('load failed', url, e);
    }
  }));
  if (token !== outfitToken) return;
  const newBody = loaded.body !== worn.body;
  for (const [k, obj] of Object.entries(worn)) {
    if (loaded[k] !== obj) { charGroup.remove(obj); delete worn[k]; }
  }
  for (const [k, obj] of Object.entries(loaded)) {
    if (!worn[k]) { charGroup.add(obj); worn[k] = obj; }
  }
  if (newBody && worn.body) {
    // bind pose of the new body, before any animation touches it
    worn.body.updateMatrixWorld(true);
    bodyBones = bonesOf(worn.body);
    bindWorld = Object.fromEntries(Object.entries(bodyBones).map(([n, b]) => [n, b.matrixWorld.clone()]));
    shapedJoints = setupBodyShape(bodyBones, ch.preset?.body);
    mixer = null;
  }
  for (const [k, obj] of Object.entries(worn)) if (k !== 'body') rebind(obj, bodyBones);
  if (newBody || !mixer) await playAction(currentClip || store.get('action', 'Đứng'));
  applyDyes();
  charFx.clear();
  fxFollow.length = 0;
  const set = SETS[state.setId];
  // the character's own forehead ornament (dị dung) + the set's effects while the whole set is worn
  const complete = setIsComplete(set);
  const effects = [...(ch.preset?.fx || []), ...(state.fxOn !== false && complete ? set.fx || [] : [])];
  showPet(complete ? set.pet : null).catch(e => console.warn('pet', e));
  {
    for (const f of effects) {
      charFx.add('', f).then(inst => {
        const bn = boneName(f.b);
        const bone = f.b && bodyBones[bn];
        if (!bone || !bindWorld[bn]) return;
        // effect position in the bone's space, taken from the bind pose
        const p = charFx.root.localToWorld(new THREE.Vector3(...f.p));
        const local = p.applyMatrix4(bindWorld[bn].clone().invert());
        fxFollow.push({ inst, bone, local });
      }).catch(() => {});
    }
  }
  renderSlots();
  refreshCounts();
}

const _v3 = new THREE.Vector3();
function updateFollowers() {
  for (const f of fxFollow) {
    _v3.copy(f.local).applyMatrix4(f.bone.matrixWorld);
    f.inst.group.position.copy(charFx.root.worldToLocal(_v3));
  }
}

function wearSet(set) {
  state.parts = { ...set.parts };
  state.setId = set.id;
  applyOutfit();
}
function wearItem(item) {
  state.parts[item.slot] = item.glb;
  // set effects only play while the whole set is worn
  if (item.set && setIsComplete(SETS[item.set])) state.setId = item.set;
  else if (!setIsComplete(SETS[state.setId])) state.setId = null;
  applyOutfit();
}

// ---------------------------------------------------------------- thumbnails (rendered once, cached in IndexedDB)
const THUMB_W = 200, THUMB_H = 328;  // 2x the card's picture (100x164)
const THUMB_VERSION = 'v15';  // bump when the look of the card pictures changes (they are cached in IndexedDB)
const thumbRT = new THREE.WebGLRenderTarget(THUMB_W, THUMB_H);
thumbRT.texture.colorSpace = THREE.NoColorSpace;
const thumbScene = new THREE.Scene();
thumbScene.add(new THREE.HemisphereLight(0xffffff, 0xc8b8b0, LIGHT.day.hemi));
const tsun = new THREE.DirectionalLight(0xffffff, LIGHT.day.sun);
tsun.position.set(1.5, 4, 5);
thumbScene.add(tsun);
// framing of the game's cards: head 10 px and feet 160 px below the top of the 164 px picture
const thumbCam = new THREE.PerspectiveCamera(20.3, THUMB_W / THUMB_H, 0.1, 30);
// the piece tabs frame the piece like the game: Tóc = head and shoulders, Oản = right forearm and hand,
// Giày = from mid thigh down; Bộ / Áo / Quần show the whole character
const TAB_FRAME = { hair: 'head', wrist: 'hand', shoes: 'legs' };
function frameThumb(frame, bones) {
  const at = name => {
    const b = bones[boneName(name)];
    return b ? new THREE.Vector3().setFromMatrixPosition(b.matrixWorld) : null;
  };
  // the idle pose stands a little off the origin: centre on the pelvis / between the feet like the game
  const pelvis = at('Bip01 Pelvis');
  const feet = at('Bip01 L Foot') && at('Bip01 R Foot') ? at('Bip01 L Foot').add(at('Bip01 R Foot')).multiplyScalar(0.5) : null;
  let target = new THREE.Vector3(pelvis ? pelvis.x : 0, 0.957, 0), half = 0.889;  // whole body
  if (frame === 'head' && at('Bip01 Head')) {
    target = at('Bip01 Head').add(new THREE.Vector3(0, 0.06, 0));
    half = 0.22;
  } else if (frame === 'hand' && at('Bip01 R Hand') && at('Bip01 R Forearm')) {
    target = at('Bip01 R Hand').add(at('Bip01 R Forearm')).multiplyScalar(0.5);
    half = 0.25;
  } else if (frame === 'legs') {
    target = new THREE.Vector3(feet ? feet.x : target.x, 0.33, feet ? feet.z : 0);
    half = 0.34;
  }
  const dist = half / Math.tan(THREE.MathUtils.degToRad(thumbCam.fov / 2));
  thumbCam.position.set(target.x, target.y + 0.05 * dist / 5, target.z + dist);
  thumbCam.lookAt(target);
  thumbCam.updateMatrixWorld();
}
frameThumb('full', {});
const thumbQueue = [];
let thumbBusy = false;

const idb = await new Promise(res => {
  try {
    const r = indexedDB.open('tghm_tudo', 1);
    r.onupgradeneeded = () => r.result.createObjectStore('thumbs');
    r.onsuccess = () => res(r.result);
    r.onerror = () => res(null);
  } catch { res(null); }
});
const idbGet = key => new Promise(res => {
  if (!idb) return res(null);
  const q = idb.transaction('thumbs').objectStore('thumbs').get(key);
  q.onsuccess = () => res(q.result || null);
  q.onerror = () => res(null);
});
const idbPut = (key, val) => { if (idb) idb.transaction('thumbs', 'readwrite').objectStore('thumbs').put(val, key); };

function requestThumb(img, key, cid, parts, pet, frame) {
  idbGet(key).then(url => {
    if (url) { img.src = url; img.parentElement?.querySelector('.wait')?.remove(); return; }
    thumbQueue.push({ img, key, cid, parts, pet, frame });
    pumpThumbs();
  });
}

async function pumpThumbs() {
  if (thumbBusy) return;
  thumbBusy = true;
  while (thumbQueue.length) {
    const job = thumbQueue.shift();
    if (!job.img.isConnected) continue;
    try {
      job.img.src = await renderThumb(job.cid, job.parts, job.pet, job.frame);
      idbPut(job.key, job.img.src);
      job.img.parentElement?.querySelector('.wait')?.remove();
    } catch (e) {
      console.warn('thumb failed', e);
    }
  }
  thumbBusy = false;
}

// The game draws the card models on a near-black target with its bloom: bright parts glow softly.
const THUMB_BG = 'rgb(40,40,38)';
const THUMB_GLOW = { blur: 5, alpha: 0.55 };

async function thumbPet(info) {
  const [g, clips] = await Promise.all([
    getBuffer(DATA + info.glb).then(b => gltfLoader.parseAsync(b.slice(0), '')), loadClips(DATA + info.anims)]);
  g.scene.traverse(m => {
    if (!m.isMesh) return;
    m.frustumCulled = false;
    m.material = setupDye(toLambert(m.material));
  });
  g.scene.position.set(0.3, 0, -0.1);  // the cards show it at the character's right foot (left of the picture)
  if (clips[0]) {
    const mx = new THREE.AnimationMixer(g.scene);
    mx.clipAction(clips[0]).play();
    mx.update(0);
  }
  return g.scene;
}

async function renderThumb(cid, parts, petInfo, frame = 'full') {
  const ch = catalog.characters[cid];
  // the sample character of the creator (dị dung preset), like the cards of the game
  const face = ch.faces[(ch.preset?.face || 1) - 1] || ch.faces[0];
  const urls = [DATA + ch.body, DATA + faceModel(ch, ch.preset?.face || 1, face)];
  const ownHair = ch.preset?.hairStyle || face.hair;
  if (!parts.hair && ownHair) urls.push(DATA + ownHair);
  // empty slots wear the default pieces, like the game's cards (a top card shows the default mini skirt)
  const pieces = SLOTS.map(s => parts[s] || ch.defaults?.[s]).filter(Boolean);
  const group = new THREE.Group();
  group.rotation.y = Math.PI;
  const objs = await Promise.all([...urls, ...pieces].map(async url => {
    // parse a private copy so it can be disposed right after rendering
    const g = await gltfLoader.parseAsync((await getBuffer(url)).slice(0), '');
    const rgb = PART_ITEM[url]?.color || (url === urls[2] ? ch.preset?.hair : null);
    const hairTint = PART_ITEM[url]?.hairTint && ch.preset?.hair;
    g.scene.traverse(m => {
      if (!m.isMesh) return;
      m.frustumCulled = false;
      m.material = setupDye(toLambert(m.material));
      const strands = hairTint && /头发/.test(m.material.name);
      if (strands) m.material.alphaTest = Math.min(m.material.alphaTest, HAIR_ALPHA);
      const tint = strands ? hairTint : rgb;
      setDye(m.material, tint ? rgbColor(tint) : WHITE);
    });
    await useGameTextures(g.scene);
    return g.scene;
  }));
  objs.forEach(o => group.add(o));
  // pose everything in the standing animation, like the cards in the game
  const bones = bonesOf(objs[0]);
  objs.slice(1).forEach(o => rebind(o, bones));
  const moved = setupBodyShape(bones, ch.preset?.body);
  const clips = await clipsFor(cid);
  const stand = clips.find(c => c.name === 'Đứng') || clips.find(c => c.name === 'Đứng (đăng nhập)') || clips[0];
  if (stand) {
    const mx = new THREE.AnimationMixer(objs[0]);
    mx.clipAction(stand).play();
    unshapeJoints(moved);
    mx.update(0);
    shapeJoints(moved);
  }
  const pet = petInfo ? await thumbPet(petInfo).catch(() => null) : null;
  if (pet) { group.add(pet); objs.push(pet); }
  group.updateMatrixWorld(true);
  frameThumb(frame, bones);
  thumbScene.add(group);
  renderer.setRenderTarget(thumbRT);
  renderer.setClearColor(0x000000, 0);
  renderer.clear();
  renderer.render(thumbScene, thumbCam);
  const px = new Uint8Array(THUMB_W * THUMB_H * 4);
  renderer.readRenderTargetPixels(thumbRT, 0, 0, THUMB_W, THUMB_H, px);
  renderer.setRenderTarget(null);
  thumbScene.remove(group);
  objs.forEach(dispose);
  const model = document.createElement('canvas');
  model.width = THUMB_W; model.height = THUMB_H;
  const img = model.getContext('2d').createImageData(THUMB_W, THUMB_H);
  for (let y = 0; y < THUMB_H; y++) {
    img.data.set(px.subarray((THUMB_H - 1 - y) * THUMB_W * 4, (THUMB_H - y) * THUMB_W * 4), y * THUMB_W * 4);
  }
  model.getContext('2d').putImageData(img, 0, 0);
  const c = document.createElement('canvas');
  c.width = THUMB_W; c.height = THUMB_H;
  const ctx = c.getContext('2d');
  ctx.fillStyle = THUMB_BG;
  ctx.fillRect(0, 0, THUMB_W, THUMB_H);
  ctx.drawImage(model, 0, 0);
  ctx.filter = `blur(${THUMB_GLOW.blur}px)`;
  ctx.globalCompositeOperation = 'screen';
  ctx.globalAlpha = THUMB_GLOW.alpha;
  ctx.drawImage(model, 0, 0);
  return c.toDataURL('image/webp', 0.9);
}

// ================================================================ game UI rebuilt from interfaces\*.xml
const layout = await fetchRetry(DATA + 'ui2/layout.json').then(r => r.json());
const aui = new AUI(layout, DATA + 'ui2/');
const STR = (id, fallback = '') => layout.strings?.[id] ?? fallback;  // interfaces\ingame.stf
document.head.appendChild(Object.assign(document.createElement('style'), { textContent: AUI_CSS }));
const uiRoot = $('#ui');
const def = (dlg, name) => layout.dialogs[dlg].controls.find(c => c.name === name);
const mount = (name, opts) => { const d = aui.build(name, opts); uiRoot.appendChild(d.root); return d; };
const onlyKeep = (dlg, keep) => layout.dialogs[dlg].controls.map(c => c.name).filter(n => !keep.includes(n));
const freeDialog = (w, h) => {
  const root = document.createElement('div');
  root.className = 'aui-dlg';
  root.style.width = `${w}px`;
  root.style.height = `${h}px`;
  uiRoot.appendChild(root);
  return root;
};

const topBar = mount('collectionmain');
const left = mount('collection_clothesmain');
const detail = mount('collection_clothesdetail', {
  skip: [...Array.from({ length: 18 }, (_, i) => `tag_${i + 1}`), 'btn_zhankai', 'btn_unfold', 'Img_HighLight',
    'lable_topnumber', 'lable_toplevel'],
});
const counter = mount('collection_totalbutton');
const corner = mount('collection_bg', { skip: onlyKeep('collection_bg', ['Btn_Help', 'Btn_Close', 'Chk_Time']) });
left.root.classList.add('solid');
detail.root.classList.add('solid');

// name plate at the bottom (img_number + Label_number of collection_bg)
const plate = freeDialog(205, 33);
plate.appendChild(aui.control({ ...def('collection_bg', 'img_number'), x: 21, y: 0 }));
const plateLabel = aui.control({ ...def('collection_bg', 'Label_number'), x: 0, y: 8 });
plate.appendChild(plateLabel);

// special action buttons (collection_bg Btn_1..9 style) for the extra features of this page
const extra = freeDialog(1280, 768);
const actionBtn = (base, text, onclick) => {
  // same style and rows as the game's special action buttons, moved clear of the detail panel
  const d = def('collection_bg', base);
  const el = aui.control({ ...d, x: d.x - 46, text: { ...d.text, s: text } });
  el.onclick = onclick;
  extra.appendChild(el);
  return el;
};
const btnAct = actionBtn('Btn_1', 'Động tác thời trang', () => toggleActions());
const btnFace = actionBtn('Btn_2', 'Dị dung', () => { renderFacePanel(); $('#facePanel').classList.toggle('hidden'); });
const btnChar = actionBtn('Btn_3', 'Đổi Kiếm Linh nam', () => switchCharacter(state.cid === 'nu' ? 'nam' : 'nu'));
const btnFx = actionBtn('Btn_4', 'Hiệu ứng: Bật', () => {
  state.fxOn = state.fxOn === false;
  btnFx.setText(`Hiệu ứng: ${state.fxOn === false ? 'Tắt' : 'Bật'}`);
  charFx.visible = state.fxOn !== false;
  applyOutfit();
});

// sub menu for the actions, drawn like collection_bgbtn
let actionMenu = null;
async function toggleActions() {
  if (actionMenu) { actionMenu.remove(); actionMenu = null; return; }
  const clips = await clipsFor(state.cid);
  const rowH = 24, h = 10 + clips.length * rowH;
  actionMenu = document.createElement('div');
  actionMenu.className = 'aui-panel';
  const frame = def('collection_bgbtn', 'EditBox_38064436');
  aui.paint(actionMenu, frame.img.FrameImage, 90, h);
  Object.assign(actionMenu.style, { left: '768px', top: '306px', width: '90px', height: `${h}px` });
  clips.forEach((clip, i) => {
    const b = aui.control({ ...def('collection_bgbtn', 'Btn_1'), y: 5 + i * rowH, text: { ...def('collection_bgbtn', 'Btn_1').text, s: clip.name } });
    b.onclick = () => { playAction(clip.name); toggleActions(); };
    if (clip.name === currentClip) b.style.filter = 'brightness(1.35)';
    actionMenu.appendChild(b);
  });
  extra.appendChild(actionMenu);
}

// ---------------------------------------------------------------- top bar (collectionmain)
const TOP = topBar.ctrls;
TOP.Rdo_Clothes.setChecked(true);
for (const n of ['Rdo_Pet', 'Rdo_OrnamentPet', 'Rdo_Plane']) {
  TOP[n].onclick = () => toast('Bản xem này chỉ có phần Thời trang');
}
// search like the game: type a name, then the magnifier (or Enter) opens a page of results with "Quay lại"
const searchInput = TOP.Edi_Search.input;
searchInput.oninput = () => { TOP.Lbl_Attention.style.display = searchInput.value ? 'none' : ''; };
const runSearch = () => {
  state.view = searchInput.value.trim() ? 'search' : 'list';
  buildList();
};
searchInput.onkeydown = ev => { if (ev.key === 'Enter') runSearch(); };
TOP.Btn_Search.onclick = runSearch;
let panelsHidden = false;
TOP.Btn_Collect.onclick = () => {
  panelsHidden = !panelsHidden;
  for (const d of [left.root, detail.root, counter.root, extra]) d.classList.toggle('hidden', panelsHidden);
};

// ---------------------------------------------------------------- corner buttons (collection_bg)
const CORNER = corner.ctrls;
// the game spreads the three corner buttons 52/48 px apart from the right edge (the XML has 43/42)
[['Chk_Time', 152], ['Btn_Help', 100], ['Btn_Close', 52]].forEach(([n, r]) => { CORNER[n].style.left = `${1289 - r}px`; });
// The game's window has no buttons for the page's own tools (actions, dị dung, male/female, effects):
// they stay hidden until "?" is pressed, so the window looks exactly like the game's.
extra.classList.add('hidden');
CORNER.Btn_Help.onclick = () => {
  const show = extra.classList.contains('hidden');
  extra.classList.toggle('hidden', !show);
  if (!show) { $('#facePanel').classList.add('hidden'); if (actionMenu) toggleActions(); }
  if (show) toast('Bấm thẻ để mặc · tab Tóc/Áo/Quần/Oản/Giày để phối từng món · bấm ô ở "Thời trang đã mặc" để chọn món '
    + 'cần nhuộm, bấm đúp để cởi · kéo chuột để xoay, lăn chuột để phóng to · bấm "?" lần nữa để ẩn các nút thêm', 7000);
};
CORNER.Btn_Close.onclick = () => {
  const hide = !left.root.classList.contains('hidden');
  for (const d of [topBar.root, left.root, detail.root, counter.root, extra, plate]) d.classList.toggle('hidden', hide);
};
CORNER.Chk_Time.onclick = () => loadScene(currentScene === 'blue' ? 'pink' : 'blue').then(() => {
  CORNER.Chk_Time.setChecked(currentScene === 'blue');
});

// ---------------------------------------------------------------- left panel (clothesmain + folders + cards)
const L = left.ctrls;
const TABS = { Rdo_Suite: 'set', Rdo_Hair: 'hair', Rdo_UpperBody: 'top', Rdo_LowerBody: 'bottom', Rdo_Hand: 'wrist', Rdo_Shoes: 'shoes' };
const paintTabs = () => { for (const [n, tab] of Object.entries(TABS)) L[n].setChecked(state.tab === tab); };
for (const [n, tab] of Object.entries(TABS)) L[n].onclick = () => { state.tab = tab; paintTabs(); buildList(); };
// "Tinh giản" switches to the game's icon grid of pieces (collection_clothessuball)
L.Btn_All.onclick = () => { state.view = state.view === 'all' ? 'list' : 'all'; state.allMode = 'owned'; buildList(); };
const listBox = L.Sub_Detail;
listBox.classList.add('aui-scroll');

// The character's collection in the game (tu_do/da_thu.json: set id -> pieces owned), read off its Thu thập window.
// It drives the counters (Đã thu, folder x/y, card x/y, Nghê Thường) and the order of the cards like the game.
const OWNED = await fetch(DATA + 'da_thu.json').then(r => (r.ok ? r.json() : {})).catch(() => ({}));
const owned = id => OWNED[state.cid]?.[id] || 0;
const pieceCount = set => Object.keys(set.parts).length;
const isCollected = set => owned(set.id) >= pieceCount(set);
const setTitle = s => s.vn || s.cn;
// collection groups of the game (elements.data list 341), in the game's order
// A set can sit in several folders (the game lists e.g. a Tết set both in "Thỏ Niên Tân Phẩm" and "Đặt lễ tết").
let GROUP_OF = {}, GROUPS_OF = {};
const groupsOf = cid => catalog.groups[cid] || [];
function indexGroups(cid) {
  GROUP_OF = {};
  GROUPS_OF = {};
  for (const g of groupsOf(cid)) {
    for (const id of g.sets) {
      GROUP_OF[id] ??= g.name;
      (GROUPS_OF[id] ??= []).push(g.name);
    }
  }
}
indexGroups(state.cid);

function entriesForTab(query = '') {
  const q = query.trim().toLowerCase();
  const match = (...names) => !q || names.some(n => (n || '').toLowerCase().includes(q));
  const out = [];
  if (state.tab === 'set') {
    for (const s of catalog.sets[state.cid]) {
      if (!match(s.vn, s.cn)) continue;
      // the card shows the full name ("Bộ Thụy Thỏ Cẩm Niên nữ"), centred and running over the next card
      for (const group of GROUPS_OF[s.id] || ['Khác']) {
        out.push({ kind: 'set', id: s.id, name: setTitle(s), group, parts: s.parts, fx: s.fx?.length, ref: s });
      }
    }
  } else {
    for (const it of catalog.items[state.cid][state.tab]) {
      if (!match(it.name, SETS[it.set]?.vn, SETS[it.set]?.cn)) continue;
      for (const group of GROUPS_OF[it.set] || ['Khác']) {
        out.push({ kind: 'item', id: it.glb, name: it.name, group, parts: { [it.slot]: it.glb }, ref: it });
      }
    }
  }
  // inside a folder the cards follow the folder's own order of the game
  const order = {};
  for (const g of groupsOf(state.cid)) g.sets.forEach((id, i) => { order[`${g.name}|${id}`] = i; });
  const pos = e => order[`${e.group}|${e.kind === 'set' ? e.id : e.ref.set}`] ?? 1e9;
  // the game lists the complete sets first, then the partly collected ones, then the rest (checked in game)
  const rank = e => {
    if (e.kind !== 'set') return 0;
    const n = owned(e.id);
    return n >= pieceCount(e.ref) ? 0 : n > 0 ? 1 : 2;
  };
  return out.sort((a, b) => rank(a) - rank(b) || pos(a) - pos(b));
}

const FOLDER = def('collection_clothessub', 'Ctrl_0');
const FOLDER2 = def('collection_clothessub', 'Ctrl_1');
const CARD = {
  bg: def('collection_ctrl_clothes0', 'Edi_Bg1'), title: def('collection_ctrl_clothes0', 'Edi_Title1'),
  name: def('collection_ctrl_clothes0', 'Txt_Name1'), count: def('collection_ctrl_clothes0', 'Txt_Collection1'),
  high: def('collection_ctrl_clothes0', 'Img_HighNight'),
};
const COL_STEP = 105, ROW_STEP = 186;
// collection_ctrl_clothes0: the open folder is a 330x573 page showing 3 rows of cards with its own scroll bar
const PAGE = layout.dialogs.collection_ctrl_clothes0;
const SCROLL = def('collection_ctrl_clothes0', 'Scroll');
// like the game only one folder is open at a time; the first one opens with the window
let openGroup = groupsOf(state.cid)[0]?.name;

function buildList() {
  listBox.innerHTML = '';
  listBox.scrollTop = 0;
  if (state.view === 'all') return buildAll();
  if (state.view === 'search') return buildSearch();
  const entries = entriesForTab();
  const groups = [...groupsOf(state.cid).map(g => g.name), 'Khác']
    .map(g => [g, entries.filter(e => e.group === g)]).filter(([, list]) => list.length);
  if (openGroup !== null && !groups.some(([g]) => g === openGroup)) openGroup = groups[0]?.[0];
  groups.forEach(([g, list], gi) => {
    const head = document.createElement('div');
    head.className = 'aui-folder';
    const fdef = gi === 0 ? FOLDER : FOLDER2;
    aui.paint(head, fdef.img.TitleImage, 329, 36);
    const arrow = document.createElement('div');
    arrow.className = 'aui-layer';
    const caption = document.createElement('div');
    caption.className = 'aui-folder-text';
    aui.textStyle(caption, fdef.text);
    const done = state.tab === 'set' ? list.filter(e => isCollected(e.ref)).length : 0;
    caption.textContent = `${g}(${done}/${list.length})`;
    const open = g === openGroup;
    aui.paint(arrow, open ? fdef.img.ButtonUnfoldImg : fdef.img.ButtonFoldImg, 329, 36);
    head.append(arrow, caption);
    head.onclick = () => { openGroup = open ? null : g; buildList(); };
    listBox.append(head);
    if (open) listBox.append(makePage(list));
  });
  if (!listBox.childElementCount) {
    const none = document.createElement('div');
    none.className = 'aui-folder-text';
    none.textContent = 'Không tìm thấy';
    listBox.appendChild(none);
  }
  refreshCounts();
}

// Search results (collection_search): one page of cards over every folder, "Quay lại" goes back.
function buildSearch() {
  const seen = new Set();
  const list = entriesForTab(searchInput.value).filter(e => !seen.has(e.id) && seen.add(e.id));
  const box = document.createElement('div');
  box.className = 'aui-folder-body';
  box.style.height = `${layout.dialogs.collection_search.h}px`;
  box.appendChild(makePage(list));
  const back = aui.control(def('collection_search', 'Btn_Return'));
  back.onclick = () => { searchInput.value = ''; searchInput.oninput(); state.view = 'list'; buildList(); };
  box.appendChild(back);
  listBox.appendChild(box);
  if (!list.length) {
    const none = document.createElement('div');
    none.className = 'aui-folder-text';
    none.style.height = '60px';
    none.textContent = 'Không tìm thấy';
    box.appendChild(none);
  }
  refreshCounts();
}

// "Tinh giản" (collection_clothessuball): the pieces as an 8-column icon grid. "Đã có" lists the pieces of the
// collected sets, "Tất cả Đồ Giám" every piece of the tab; the wheel moves one row, a click puts the piece on.
const SUBALL = layout.dialogs.collection_clothessuball;
const SUBALL_GRID = { x: 8, y: 33, step: 37, cols: 8, rows: 14 };
function piecesFor(mode) {
  const slots = state.tab === 'set' ? ['hair', 'top', 'wrist', 'bottom', 'shoes'] : [state.tab];
  const seen = new Set(), out = [];
  for (const g of groupsOf(state.cid)) {
    for (const id of g.sets) {
      const s = SETS[id];
      if (!s || (mode === 'owned' && !isCollected(s))) continue;
      for (const slot of slots) {
        const it = PART_ITEM[s.parts[slot]];
        if (it && !seen.has(it.glb)) { seen.add(it.glb); out.push(it); }
      }
    }
  }
  return out;
}
function buildAll() {
  const dlg = aui.build('collection_clothessuball', {
    skip: SUBALL.controls.map(c => c.name).filter(n => /^(Img_Bg|Item_|Rdo_Storage|Btn_Gold|Txt_Gold|Chk_Bag)/.test(n)),
  });
  dlg.root.style.left = '0px';
  dlg.root.style.top = '2px';
  dlg.root.style.pointerEvents = 'auto';
  const items = piecesFor(state.allMode);
  const G = SUBALL_GRID;
  const frame = SUBALL.controls.find(c => c.name.startsWith('Img_Bg')).img.FrameImage;
  const grid = document.createElement('div');
  Object.assign(grid.style, { position: 'absolute', left: `${G.x}px`, top: `${G.y}px`, width: `${G.cols * G.step + 1}px`,
    height: `${G.rows * G.step + 1}px`, overflow: 'hidden' });
  const totalRows = Math.max(G.rows, Math.ceil(items.length / G.cols));
  let top = 0;
  const draw = () => {
    grid.innerHTML = '';
    for (let r = 0; r < G.rows; r++) {
      for (let c = 0; c < G.cols; c++) {
        const it = items[(top + r) * G.cols + c];
        const cell = aui.control({ type: 'IMAGEPICTURE', name: 'cell', x: c * G.step, y: r * G.step, w: 38, h: 38,
          img: { FrameImage: frame } });
        cell.style.position = 'absolute';
        if (it) {
          if (it.icon) {
            const ic = document.createElement('img');
            ic.src = DATA + it.icon;
            Object.assign(ic.style, { position: 'absolute', left: '3px', top: '3px', width: '32px', height: '32px' });
            cell.appendChild(ic);
          }
          cell.title = it.name;
          cell.style.cursor = 'pointer';
          cell.style.pointerEvents = 'auto';
          cell.onclick = () => { wearItem(it); showInfo({ kind: 'item', ref: it, name: it.name }); };
        }
        grid.appendChild(cell);
      }
    }
    const max = totalRows - G.rows;
    bar.style.top = `${scl.y + 15 + (max > 0 ? (scl.h - 30 - 18) * top / max : 0)}px`;
  };
  const scl = SUBALL.controls.find(c => c.name === 'Scl_Right');
  const track = aui.control({ ...scl, type: 'IMAGEPICTURE', img: { FrameImage: scl.img.ScrollImage } });
  const bar = aui.control({ ...scl, type: 'IMAGEPICTURE', h: 18, img: { FrameImage: scl.img.BarFrameImage } });
  const up = aui.control({ ...scl, type: 'IMAGEPICTURE', h: 15, img: { FrameImage: scl.img.UpImage } });
  const down = aui.control({ ...scl, type: 'IMAGEPICTURE', y: scl.y + scl.h - 15, h: 15, img: { FrameImage: scl.img.DownImage } });
  const move = d => { top = Math.max(0, Math.min(totalRows - G.rows, top + d)); draw(); };
  for (const [el, d] of [[up, -1], [down, 1]]) { el.style.pointerEvents = 'auto'; el.style.cursor = 'pointer'; el.onclick = () => move(d); }
  dlg.root.addEventListener('wheel', ev => { ev.preventDefault(); move(Math.sign(ev.deltaY)); }, { passive: false });
  dlg.root.append(grid, track, bar, up, down);
  const C = dlg.ctrls;
  C.Btn_Collected.onclick = () => { state.allMode = 'owned'; buildList(); };
  C.Btn_All.onclick = () => { state.allMode = 'all'; buildList(); };
  C.Btn_All.title = 'Hiển thị toàn bộ Thời trang trong Đồ Giám';
  C.Btn_Back.onclick = () => { state.view = 'list'; buildList(); };
  (state.allMode === 'owned' ? C.Btn_Collected : C.Btn_All).style.filter = 'brightness(1.3)';
  draw();
  listBox.appendChild(dlg.root);
}

// The open folder's page: cards in a scrolled box (the wheel moves one row) + the game's thin scroll bar.
function makePage(list) {
  const page = document.createElement('div');
  page.className = 'aui-folder-body';
  page.style.height = `${PAGE.h}px`;
  const box = document.createElement('div');
  box.className = 'aui-page';
  const inner = document.createElement('div');
  inner.className = 'aui-page-inner';
  const rowH = ROW_STEP;
  inner.style.height = `${CARD.bg.y + Math.ceil(list.length / 3) * ROW_STEP}px`;
  list.forEach((e, i) => inner.appendChild(makeCard(e, i)));
  box.appendChild(inner);
  const track = aui.control({ ...SCROLL, type: 'IMAGEPICTURE', img: { FrameImage: SCROLL.img.ScrollImage } });
  const thumb = aui.control({ ...SCROLL, type: 'IMAGEPICTURE', h: 18, img: { FrameImage: SCROLL.img.BarFrameImage } });
  track.classList.add('aui-track');
  thumb.classList.add('aui-track');
  const syncBar = () => {
    const max = box.scrollHeight - box.clientHeight;
    track.style.display = thumb.style.display = max > 0 ? '' : 'none';
    thumb.style.top = `${SCROLL.y + (max > 0 ? (SCROLL.h - 18) * box.scrollTop / max : 0)}px`;
  };
  box.addEventListener('scroll', syncBar);
  box.addEventListener('wheel', ev => {
    ev.preventDefault();
    box.scrollTop = Math.round((box.scrollTop + Math.sign(ev.deltaY) * rowH) / rowH) * rowH;
  }, { passive: false });
  // dragging the bar scrolls the page
  thumb.onmousedown = down => {
    down.preventDefault();
    const y0 = down.clientY, top0 = box.scrollTop, max = box.scrollHeight - box.clientHeight;
    const move = ev => { box.scrollTop = top0 + (ev.clientY - y0) / (SCROLL.h - 18) * max; };
    const up = () => { removeEventListener('mousemove', move); removeEventListener('mouseup', up); };
    addEventListener('mousemove', move);
    addEventListener('mouseup', up);
  };
  page.append(box, track, thumb);
  // thumbnails are drawn when their card scrolls into view
  page.observer = new IntersectionObserver(entries => {
    for (const en of entries) {
      if (!en.isIntersecting) continue;
      const img = en.target;
      page.observer.unobserve(img);
      const set = SETS[img.dataset.set];
      requestThumb(img, img.dataset.key, img.dataset.cid, JSON.parse(img.dataset.parts), set?.pet, img.dataset.frame);
    }
  }, { root: box, rootMargin: '200px' });
  inner.querySelectorAll('img.aui-thumb').forEach(img => page.observer.observe(img));
  requestAnimationFrame(syncBar);
  return page;
}

function selectEntry(card, e) {
  listBox.querySelectorAll('.aui-card.on').forEach(c => c.classList.remove('on'));
  card.classList.add('on');
  state.selected = e;
  if (e.kind === 'set') wearSet(e.ref); else wearItem(e.ref);
  showInfo(e);
}

function makeCard(e, i) {
  const card = document.createElement('div');
  card.className = 'aui-card';
  card.dataset.id = e.id;
  card.style.left = `${(i % 3) * COL_STEP}px`;
  card.style.top = `${CARD.bg.y + Math.floor(i / 3) * ROW_STEP}px`;
  card.appendChild(aui.control({ ...CARD.bg, x: 0, y: 0 }));
  const img = document.createElement('img');
  img.className = 'aui-thumb';
  card.appendChild(img);
  card.appendChild(aui.control({ ...CARD.title, x: 0, y: CARD.title.y - CARD.bg.y }));
  const name = aui.control({ ...CARD.name, x: CARD.name.x, y: CARD.name.y - CARD.bg.y });
  name.setText(e.name);
  name.classList.add('card-name');
  name.style.zIndex = 1000 - i;  // the game draws Txt_Name9..1: a card's name lies over the next card's
  card.title = e.name;
  card.appendChild(name);
  const cnt = aui.control({ ...CARD.count, x: CARD.count.x, y: 0 });
  if (e.kind === 'set') {
    cnt.classList.add('cnt');
  } else {  // a single piece: 1/1 once its set is collected
    const set = SETS[e.ref.set];
    cnt.setText(`${set && isCollected(set) ? 1 : 0}/1`);
    cnt.style.zIndex = 1001;
  }
  card.appendChild(cnt);
  const tagUrl = e.kind === 'set' && e.ref.tag ? ui(e.ref.tag) : '';
  if (tagUrl) {  // the set's label of the game (Linh phẩm, Lễ tình nhân...)
    const tag = document.createElement('img');
    tag.className = 'aui-tag';
    tag.src = tagUrl;
    card.appendChild(tag);
  }
  const high = aui.control({ ...CARD.high, x: -6, y: -7 });
  high.classList.add('sel');
  card.appendChild(high);
  const pet = e.kind === 'set' && e.ref.pet ? e.ref.pet.glb : '';
  img.dataset.frame = e.kind === 'set' ? 'full' : TAB_FRAME[state.tab] || 'full';
  img.dataset.key = `${THUMB_VERSION}|${state.cid}|${JSON.stringify(e.parts)}|${pet}|${img.dataset.frame}`;
  img.dataset.cid = state.cid;
  img.dataset.parts = JSON.stringify(e.parts);
  if (e.kind === 'set') img.dataset.set = e.id;
  if (state.selected?.id === e.id) card.classList.add('on');
  card.onclick = () => selectEntry(card, e);
  return card;
}

function refreshCounts() {
  // "collected pieces / pieces" of the game
  listBox.querySelectorAll('.aui-card').forEach(card => {
    const set = SETS[card.dataset.id];
    const cnt = card.querySelector('.cnt');
    if (set && cnt) cnt.setText(`${Math.min(owned(set.id), pieceCount(set))}/${pieceCount(set)}`);
  });
  const seen = catalog.sets[state.cid].filter(isCollected).map(s => s.id);
  counter.ctrls.Txt_Number.setText(`${seen.length}/${catalog.sets[state.cid].length}`);
  // the plate under the character shows the Nghê Thường points of the collected sets, like the game
  plateLabel.setText(STR(19331, 'Nghê Thường:%d').replace('%d', seen.reduce((n, id) => n + (SETS[id].nghe || 0), 0)));
}

// ---------------------------------------------------------------- detail panel (clothesdetail + palette)
const D = detail.ctrls;
// the rarity plate lies under its text (the game draws the label over it)
detail.root.insertBefore(D.Img_fan, D.lable_level);
const SLOT_CTRL = { all: 'Img_Suite', hair: 'Img_Hair', top: 'Img_UpperBody', bottom: 'Img_LowerBody', wrist: 'Img_Hand', shoes: 'Img_Shoes' };
const SLOT_LABEL = { all: 'Cả bộ', ...catalog.slots };
const highlight = aui.control(def('collection_clothesdetail', 'Img_HighLight'));
detail.root.appendChild(highlight);
counter.ctrls.Btn_OpenAwardDlg.onclick = () => toast(`Đã thu ${catalog.sets[state.cid].filter(isCollected).length} bộ`
  + ` trên tổng ${catalog.sets[state.cid].length} bộ (theo tu_do/da_thu.json)`);

function showInfo(e) {
  const set = e.kind === 'set' ? e.ref : SETS[e.ref.set];
  D.lable_Name.setText(set ? setTitle(set) : e.name);
  D.lable_intro.setText(set?.desc || '');
  D.lable_number.setText(set ? String(set.nghe ?? 0) : '');
  // rarity: its name (ingame.stf 19305..19308) on the plate of its colour (魅力值底板 绿/紫/黄/红)
  const rarity = Math.max(0, Math.min(3, set?.rarity ?? 0));
  D.lable_level.setText(set ? STR(19305 + rarity, catalog.rarity?.[rarity]?.name || '').trim() : '');
  D.Img_fan.setImage(set ? layout.extra?.[rarity] : null);
  // how to get it: the set's own text in green, or the game's default "Túi Càn Khôn - Lâm Lang Các - Thời Trang"
  const source = set ? (set.source ? `^00ff00${set.source}` : STR(19290)) : '';
  ['Txt_go1', 'Txt_go2', 'Txt_go3', 'Txt_go4'].forEach((n, i) => D[n].setText(i ? '' : source));
  renderSlotTitle();
  // feature tags of the set (bit i of the set's flags = tag_<i+1>: Huyễn hóa, Bạo Nguyên, Avatar, ..., Linh sủng)
  detail.root.querySelectorAll('.set-tag').forEach(t => t.remove());
  let k = 0;
  for (let i = 0; i < 18; i++) {
    if (!((set?.flags || 0) & (1 << i))) continue;
    const t = aui.control({ ...def('collection_clothesdetail', `tag_${i + 1}`), x: 30 + 54 * k++, y: 127 });
    t.classList.add('set-tag');
    detail.root.appendChild(t);
  }
}
function showCurrentSet() {
  const set = SETS[state.setId];
  if (set) showInfo({ kind: 'set', ref: set, name: setTitle(set) });
}
// title over the worn pieces: "Thời trang đã mặc", or the name of the piece picked for dyeing
function renderSlotTitle() {
  const it = state.dyeTarget !== 'all' && PART_ITEM[state.parts[state.dyeTarget]];
  D.Txt_Name.setText(it ? it.name : 'Thời trang đã mặc');
}

function renderSlots() {
  for (const [slot, name] of Object.entries(SLOT_CTRL)) {
    const el = D[name];
    if (!el) continue;
    if (slot !== 'all') {
      const it = PART_ITEM[state.parts[slot]];
      el.style.background = it?.icon ? `url("${DATA + it.icon}") 0 0 / 100% 100%` : 'none';
      el.title = it ? `${it.name} (bấm đúp để cởi)` : `${SLOT_LABEL[slot]}: trống`;
      el.ondblclick = () => { if (state.parts[slot]) { delete state.parts[slot]; applyOutfit(); } };
    } else {
      el.title = 'Nhuộm toàn bộ';
    }
    el.style.pointerEvents = 'auto';
    el.style.cursor = 'pointer';
    el.onclick = () => { state.dyeTarget = slot; renderSlots(); };
  }
  const sel = D[SLOT_CTRL[state.dyeTarget]] || D.Img_Suite;
  highlight.style.left = `${parseFloat(sel.style.left) - 1}px`;
  highlight.style.top = `${parseFloat(sel.style.top) - 1}px`;
  renderSlotTitle();
  const lines = Object.entries(state.dyes).map(([s, rgb]) =>
    `${SLOT_LABEL[s]}: ${catalog.palette.find(c => c.rgb.join() === rgb.join())?.name || 'màu riêng'}`);
  D.ListBox_Color.innerHTML = lines.map(l => `<div class="aui-line">${l}</div>`).join('');
}

// palette sub dialog: the game draws it 29 px above the Sub box of the XML (measured on its window)
const palette = aui.build('collection_clothespalette');
palette.root.style.left = '0px';
palette.root.style.top = '0px';
D.Sub.style.top = `${def('collection_clothesdetail', 'Sub').y - 29}px`;
D.Sub.appendChild(palette.root);
D.Sub.style.overflow = 'visible';
const P = palette.ctrls;
function dye(rgb, swatch) {
  for (const c of catalog.palette) P[`Rdo_${String(c.i).padStart(2, '0')}`]?.setChecked(false);
  swatch?.setChecked(true);
  if (state.dyeTarget === 'all') state.dyes = { all: rgb }; else state.dyes[state.dyeTarget] = rgb;
  P.Img_Palette.style.background = `rgb(${rgb.join(',')})`;
  applyDyes();
  renderSlots();
}
for (const c of catalog.palette) {
  const sw = P[`Rdo_${String(c.i).padStart(2, '0')}`];
  if (!sw) continue;
  sw.title = c.name;
  sw.onclick = () => dye(c.rgb, sw);
}
const SUGGESTED = [[255, 182, 193], [230, 210, 255], [173, 216, 230], [255, 236, 179], [190, 245, 210], [255, 160, 160]];
P.Btn_Best.onclick = () => { state.dyeTarget = 'all'; dye(SUGGESTED[Math.floor(Math.random() * SUGGESTED.length)]); };
P.btn_change.title = 'Ấn đổi sang xem trước màu ngẫu nhiên';
P.btn_change.onclick = () => {
  state.dyes = {};
  for (const s of SLOTS) state.dyes[s] = catalog.palette[Math.floor(Math.random() * catalog.palette.length)].rgb;
  applyDyes();
  renderSlots();
};
D.Btn_Dye.onclick = () => palette.root.classList.toggle('hidden');

// ---------------------------------------------------------------- outfits (save / list / apply / reset)
const snapshot = () => ({
  cid: state.cid, face: state.face, parts: { ...state.parts }, dyes: { ...state.dyes }, setId: state.setId,
  hairStyle: state.hairStyle || null, hairColor: state.hairColor || null,
});
function restore(o) {
  state.face = o.face || catalog.characters[o.cid || state.cid].preset?.face || 1;
  state.parts = { ...o.parts };
  state.dyes = { ...(o.dyes || {}) };
  state.setId = o.setId || null;
  state.hairStyle = o.hairStyle || null;
  state.hairColor = o.hairColor || null;
  renderFacePanel();
  applyOutfit();
}
function defaultOutfit(cid) {
  const applied = store.get('applied_' + cid, null);
  if (applied) return applied;
  const first = catalog.sets[cid].find(s => /Điềm Ngôn Miêu Ngữ/.test(s.vn)) || catalog.sets[cid][0];
  return { cid, face: catalog.characters[cid].preset?.face || 1, parts: { ...first.parts }, dyes: {}, setId: first.id };
}
D.Btn_Save.onclick = () => {
  const set = SETS[state.setId];
  const name = prompt('Tên bộ trang phục:', set ? setTitle(set) : 'Bộ của tôi');
  if (!name) return;
  const saved = store.get('saved', []);
  saved.unshift({ name, time: Date.now(), ...snapshot() });
  store.set('saved', saved.slice(0, 50));
  toast('Đã lưu "' + name + '"');
};
D.Btn_Apply.onclick = () => {
  store.set('applied_' + state.cid, snapshot());
  toast('Đã áp dụng — lần sau mở tủ đồ sẽ mặc bộ này');
};
D.Btn_ResetPlayer.onclick = () => { restore(defaultOutfit(state.cid)); showCurrentSet(); toast('Đã đặt lại'); };
function openList() {
  const saved = store.get('saved', []).filter(o => o.cid === state.cid);
  const m = document.createElement('div');
  m.className = 'modal';
  m.innerHTML = `<div class="box"><div class="t" style="font-size:17px;margin-bottom:8px">Danh sách bộ đã lưu (${catalog.characters[state.cid].label})</div>
    <ul style="list-style:none;padding:0;margin:0">${saved.map((o, i) =>
      `<li data-i="${i}"><span>${o.name}</span><span class="small">${new Date(o.time).toLocaleString('vi-VN')} <b data-del="${i}" title="Xóa">✕</b></span></li>`).join('')
      || '<li>Chưa có bộ nào. Bấm "Lưu" để lưu bộ đang mặc.</li>'}</ul>
    <div style="text-align:center;margin-top:10px"><button id="closeList">Đóng</button></div></div>`;
  m.onclick = ev => {
    const del = ev.target.dataset.del, li = ev.target.closest('li[data-i]');
    if (del != null) {
      const all = store.get('saved', []);
      all.splice(all.indexOf(all.filter(o => o.cid === state.cid)[del]), 1);
      store.set('saved', all);
      m.remove();
      openList();
    } else if (li) {
      restore(saved[li.dataset.i]);
      showCurrentSet();
      m.remove();
    } else if (ev.target === m || ev.target.id === 'closeList') m.remove();
  };
  document.body.appendChild(m);
}
D.Btn_List.onclick = openList;
D.Btn_OpenBag.onclick = openList;

// ---------------------------------------------------------------- dị dung (appearance)
function renderFacePanel() {
  const ch = catalog.characters[state.cid];
  const chip = (label, on, click) => {
    const el = document.createElement('div');
    el.className = 'chip t' + (on ? ' on' : '');
    el.textContent = label;
    setBg(el, codex(on ? '按钮高亮' : '按钮普通'));
    el.onclick = click;
    return el;
  };
  const faces = $('#faceChips');
  faces.innerHTML = '';
  ch.faces.forEach((_, i) => faces.appendChild(chip(`Mặt ${i + 1}`, state.face === i + 1, () => {
    state.face = i + 1;
    renderFacePanel();
    applyOutfit();
  })));
  const styles = $('#styleChips');
  styles.innerHTML = '';
  styles.appendChild(chip('Tóc gốc', !state.hairStyle, () => { state.hairStyle = null; renderFacePanel(); applyOutfit(); }));
  for (const s of ch.styles || []) {
    styles.appendChild(chip(s.name, state.hairStyle === s.glb, () => {
      state.hairStyle = s.glb;
      renderFacePanel();
      if (state.parts.hair) toast('Đang đội tóc thời trang — bấm đúp ô Tóc để cởi và xem kiểu tóc này');
      applyOutfit();
    }));
  }
  const pal = $('#hairPalette');
  if (!pal.childElementCount) {
    const reset = document.createElement('div');
    reset.className = 'sw';
    reset.title = 'Màu tóc gốc';
    reset.style.background = 'linear-gradient(135deg,#fff 45%,#c33 50%,#fff 55%)';
    reset.onclick = () => { state.hairColor = null; applyDyes(); };
    pal.appendChild(reset);
    for (const c of catalog.palette) {
      const sw = document.createElement('div');
      sw.className = 'sw';
      sw.style.background = `rgb(${c.rgb.join(',')})`;
      sw.title = c.name;
      sw.onclick = () => { state.hairColor = c.rgb; applyDyes(); };
      pal.appendChild(sw);
    }
  }
}
aui.paint($('#facePanel'), 'version02\\系统\\时装图鉴\\自定义底框.tga', 520, 330);

function switchCharacter(cid) {
  state.cid = cid;
  SETS = setsById(cid);
  indexParts(cid);
  indexGroups(cid);
  openFolders.clear();
  openFolders.add(groupsOf(cid)[0]?.name);
  currentClip = null;
  restore(defaultOutfit(cid));
  showCurrentSet();
  buildList();
  btnChar.setText(cid === 'nu' ? 'Đổi Kiếm Linh nam' : 'Đổi Kiếm Linh nữ');
  if (actionMenu) toggleActions();
}

// ---------------------------------------------------------------- placement (game layout at 1920x1020, scaled)
function placeUI() {
  const W = innerWidth, H = innerHeight;
  // game textures are drawn 1:1 (sharp) unless the window is much smaller or larger than the game's 1080p layout
  const raw = Math.min(W / 1920, H / 1020);
  const s = raw > 0.86 && raw < 1.2 ? 1 : Math.max(0.55, Math.min(1.3, raw));
  const put = (el, x, y) => {
    el.style.left = `${Math.round(x)}px`;
    el.style.top = `${Math.round(y)}px`;
    el.style.transform = s === 1 ? '' : `scale(${s})`;
  };
  // anchors of the game's dialogs, measured on its 1900x1031 client area
  put(topBar.root, 0, 0);
  put(left.root, 1 * s, 60 * s);
  put(detail.root, W - 280 * s, 52 * s);
  put(counter.root, W - 411 * s, 3 * s);
  put(corner.root, W - 1289 * s, 0);
  put(extra, W - 1289 * s, 0);
  put(plate, W / 2 - 43 * s, H - 105 * s);
  // the left list must end inside the window
  listBox.style.height = `${Math.min(872, (H - 60 * s) / s - 40)}px`;
}
addEventListener('resize', placeUI);
placeUI();

// ---------------------------------------------------------------- start
// troubleshooting from the console
window.tudo = { state, worn, catalog, camera, controls, wearSet, SETS: () => SETS, renderer, scene, lights: { hemi, sun, rim },
  charGroup, sceneRoot, resize, THREE, LOOK, renderThumb };
paintTabs();
btnChar.setText(state.cid === 'nu' ? 'Đổi Kiếm Linh nam' : 'Đổi Kiếm Linh nữ');
buildList();
$('#loadMsg').textContent = 'Tải cảnh và nhân vật…';
const clock = new THREE.Clock();
renderer.setAnimationLoop(() => {
  const dt = clock.getDelta();
  controls.update();
  unshapeJoints(shapedJoints);
  mixer?.update(dt);
  shapeJoints(shapedJoints);
  petMixer?.update(dt);
  charGroup.updateMatrixWorld(true);
  updateFollowers();
  sceneFx?.update(dt);
  charFx.update(dt);
  renderer.render(scene, camera);
});
await Promise.all([loadScene(store.get('scene', 'pink')).catch(e => console.warn('scene', e)), (async () => {
  restore(defaultOutfit(state.cid));
  showCurrentSet();
})()]);
CORNER.Chk_Time.setChecked(currentScene === 'blue');
$('#loading').remove();
