// The G: filesystem on this Windows host reports EISDIR for readlink on a
// non-symlink. Node normally reports EINVAL, which Next's webpack path expects.
// Normalize only this host drive; leave all other filesystem errors intact.
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const pathModule = require('node:path');
function normalize(error, path) {
  if (error?.code === 'EISDIR' && pathModule.resolve(String(path)).toUpperCase().startsWith('G:')) {
    error.code = 'EINVAL';
  }
  return error;
}
const originalSync = fs.readlinkSync.bind(fs);
fs.readlinkSync = function(path, ...rest) {
  try { return originalSync(path, ...rest); } catch (error) { throw normalize(error, path); }
};
const originalCallback = fs.readlink.bind(fs);
fs.readlink = function(path, ...rest) {
  const callback = rest.pop();
  return originalCallback(path, ...rest, (error, result) => callback(error ? normalize(error, path) : null, result));
};
const originalPromise = fsp.readlink.bind(fsp);
fsp.readlink = async function(path, ...rest) {
  try { return await originalPromise(path, ...rest); } catch (error) { throw normalize(error, path); }
};
fs.promises.readlink = fsp.readlink;
