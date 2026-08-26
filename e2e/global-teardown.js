const fs = require('fs');
const path = require('path');

module.exports = async () => {
  try {
    const cfg = JSON.parse(fs.readFileSync(path.resolve(__dirname, '.runtime/config.json'), 'utf-8'));
    try { process.kill(cfg.pid, 'SIGTERM'); } catch (e) { /* already dead */ }
    console.log('[E2E-teardown] server 已停止');
  } catch (e) { console.error('[E2E-teardown]', e.message); }
};
