// Rebuilds the game's Angelica AUI dialogs (exported by tools/build_ui.py) as positioned HTML.
// Every control keeps the position, size, images and text style from the game's XML.

const FONT_SCALE = 1.25;  // AUI point size -> CSS px at 1080p
const div = cls => { const d = document.createElement('div'); if (cls) d.className = cls; return d; };
const rgba = c => (c ? `rgba(${c[0]},${c[1]},${c[2]},${(c[3] ?? 255) / 255})` : null);

// Game strings carry colour codes ("^00ff00Túi Càn Khôn ..."): each code colours the text after it.
export function setRichText(el, s) {
  el.textContent = '';
  const parts = String(s ?? '').split(/\^([0-9a-fA-F]{6})/);
  if (parts.length === 1) { el.textContent = parts[0]; return; }
  if (parts[0]) el.append(parts[0]);
  for (let i = 1; i < parts.length; i += 2) {
    if (!parts[i + 1]) continue;
    const span = document.createElement('span');
    span.style.color = `#${parts[i]}`;
    span.textContent = parts[i + 1];
    el.appendChild(span);
  }
}

export class AUI {
  constructor(layout, base) {
    this.L = layout;
    this.base = base;
  }

  image(path) {
    const im = path && this.L.images[path];
    return im ? { url: this.base + im.u, w: im.w, h: im.h } : null;
  }

  // Paint an image onto an element: stretched when it roughly fits, otherwise as a nine-slice frame.
  paint(el, path, w, h) {
    const im = this.image(path);
    if (!im) { el.style.background = 'none'; el.style.borderImage = 'none'; el.style.borderWidth = '0'; return; }
    const fits = !w || !h || (Math.abs(im.w - w) <= Math.max(6, w * 0.2) && Math.abs(im.h - h) <= Math.max(6, h * 0.2));
    if (fits) {
      el.style.borderImage = 'none';
      el.style.borderWidth = '0';
      el.style.background = `url("${im.url}") 0 0 / 100% 100% no-repeat`;
    } else {
      const s = Math.max(1, Math.min(Math.floor(im.w / 3), Math.floor(im.h / 3), 28));
      const b = Math.max(1, Math.min(s, Math.floor(w / 2), Math.floor(h / 2)));
      el.style.background = 'none';
      el.style.borderStyle = 'solid';
      el.style.borderWidth = `${b}px`;
      el.style.borderImage = `url("${im.url}") ${s} fill / ${b}px stretch`;
    }
  }

  textStyle(el, t) {
    if (!t) return;
    el.style.fontSize = `${(t.size || 10) * FONT_SCALE}px`;
    el.style.fontWeight = t.bold ? 'bold' : 'normal';
    el.style.color = rgba(t.color) || '#fff';
    // crisp 1px outline like the game's text renderer (no blurred halo)
    if (t.outline) {
      const o = rgba(t.oc) || '#000';
      el.style.textShadow = `-1px 0 ${o},1px 0 ${o},0 -1px ${o},0 1px ${o},-1px -1px ${o},1px 1px ${o},-1px 1px ${o},1px -1px ${o}`;
    } else {
      el.style.textShadow = '1px 1px 0 rgba(0,0,0,.55)';
    }
  }

  // Build a dialog: returns {root, ctrls: {name: element}, def}
  build(name, { skip = [] } = {}) {
    const d = this.L.dialogs[name];
    const root = div('aui-dlg');
    root.style.width = `${d.w}px`;
    root.style.height = `${d.h}px`;
    if (d.frame) {
      const bg = div('aui-layer');
      this.paint(bg, d.frame, d.w, d.h);
      root.appendChild(bg);
    }
    const ctrls = {};
    for (const c of d.controls) {
      if (skip.includes(c.name) || c.x >= 2000 || c.y >= 2000) continue;
      const el = this.control(c);
      if (!el) continue;
      root.appendChild(el);
      ctrls[c.name] = el;
    }
    return { root, ctrls, def: d };
  }

  control(c) {
    const img = c.img || {};
    let el;
    switch (c.type) {
      case 'LABEL':
      case 'TEXT': {
        el = div('aui-text');
        setRichText(el, c.text?.s || '');
        this.textStyle(el, c.text);
        if (c.Align === '1' && !c.w) {  // centred on x
          el.classList.add('center');
        } else if (c.Align === '1') {  // centred inside its box
          el.style.width = `${c.w}px`;
          el.style.textAlign = 'center';
        } else if (c.w) {
          el.style.width = `${c.w}px`;
        }
        // a label with a size is cut at its box, like the game ("Cách thu được:" shows as "Cách thu đượ")
        if (c.w) el.style.overflow = 'hidden';
        el.setText = s => setRichText(el, s);
        break;
      }
      case 'EDIT': {
        el = div('aui-edit');
        const bg = div('aui-layer');
        this.paint(bg, img.FrameImage, c.w, c.h);
        el.appendChild(bg);
        if (c.ReadOnly !== 'true' && c.w > 30 && c.h > 10) {
          const input = document.createElement('input');
          input.className = 'aui-input';
          if (c.MaxLen) input.maxLength = +c.MaxLen * 2;
          this.textStyle(input, c.text);
          el.appendChild(input);
          el.input = input;
        }
        break;
      }
      case 'IMAGEPICTURE': {
        if (!img.FrameImage && c.name.startsWith('Gfx')) return null;
        el = div('aui-pic');
        this.paint(el, img.FrameImage, c.w, c.h);
        el.setImage = path => this.paint(el, path, c.w, c.h);
        break;
      }
      case 'STILLIMAGEBUTTON': {
        el = div('aui-btn');
        const bg = div('aui-layer');
        el.appendChild(bg);
        const state = s => this.paint(bg, img[s] || img.FrameUpImage, c.w, c.h);
        state('FrameUpImage');
        el.onmouseenter = () => !el.disabled && state('FrameOnHoverImage');
        el.onmouseleave = () => !el.disabled && state('FrameUpImage');
        el.onmousedown = () => !el.disabled && state('FrameDownImage');
        el.onmouseup = () => !el.disabled && state('FrameOnHoverImage');
        el.setDisabled = v => { el.disabled = v; state(v ? 'FrameDisabledImage' : 'FrameUpImage'); };
        this.label(el, c);
        break;
      }
      case 'RADIO':
      case 'CHECK': {
        el = div('aui-btn');
        const bg = div('aui-layer');
        el.appendChild(bg);
        let checked = false, hover = false;
        const paint = () => {
          const key = checked ? (hover && img.CheckedOnHoverImage ? 'CheckedOnHoverImage' : 'CheckedImage')
            : (hover && img.OnHoverImage ? 'OnHoverImage' : 'NormalImage');
          this.paint(bg, img[key] || img.NormalImage, c.w, c.h);
        };
        el.onmouseenter = () => { hover = true; paint(); };
        el.onmouseleave = () => { hover = false; paint(); };
        el.setChecked = v => { checked = !!v; paint(); };
        el.isChecked = () => checked;
        paint();
        this.label(el, c);
        break;
      }
      case 'SUBDIALOG':
      case 'LIST':
        el = div('aui-sub');
        break;
      default:
        return null;  // CTRLFOLDER and SCROLL are built by the page
    }
    el.dataset.name = c.name;
    el.style.left = `${c.x}px`;
    el.style.top = `${c.y}px`;
    if (c.w && c.type !== 'LABEL' && c.type !== 'TEXT') el.style.width = `${c.w}px`;
    if (c.h && c.type !== 'LABEL') el.style.height = `${c.h}px`;
    return el;
  }

  label(el, c) {
    if (!c.text?.s) return;
    const t = div('aui-caption');
    t.textContent = c.text.s;
    this.textStyle(t, c.text);
    const ox = +c.TextOffsetX || 0, oy = +c.TextOffsetY || 0;
    if (ox || oy) t.style.transform = `translate(${ox}px, ${oy}px)`;
    el.appendChild(t);
    el.setText = s => { t.textContent = s; };
  }
}

export const AUI_CSS = `
.aui-dlg { position: absolute; transform-origin: 0 0; }
.aui-dlg > * { position: absolute; }
.aui-layer { position: absolute; inset: 0; box-sizing: border-box; pointer-events: none; }
.aui-text { white-space: nowrap; line-height: 1.15; pointer-events: none; }
.aui-text.center { transform: translateX(-50%); text-align: center; }
.aui-btn { cursor: pointer; display: flex; align-items: center; justify-content: center; }
.aui-caption { position: relative; white-space: nowrap; pointer-events: none; line-height: 1; }
.aui-edit .aui-input { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; outline: none;
  background: transparent; padding: 0 6px; box-sizing: border-box; font-family: inherit; }
.aui-sub { overflow: hidden; }
`;
