// Debug: put the live camera on fitted parameters (see fit.js) and optionally hide the character.
export function set(p, { hideChar = false } = {}) {
  const { THREE, camera, controls, charGroup } = window.tudo;
  const t = new THREE.Vector3(p[0], p[1], p[2]);
  camera.position.copy(new THREE.Vector3().setFromSpherical(new THREE.Spherical(p[3], p[5], p[4])).add(t));
  controls.target.copy(t);
  camera.fov = p[6];
  camera.setViewOffset(innerWidth, innerHeight, p[7] * innerWidth / 2, 0, innerWidth, innerHeight);
  camera.updateProjectionMatrix();
  controls.update();
  charGroup.visible = !hideChar;
  return camera.position.toArray();
}
