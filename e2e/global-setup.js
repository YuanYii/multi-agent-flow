const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const RUNTIME_DIR = path.resolve(__dirname, '.runtime');
const PORT = 32990;
const BASE = `http://127.0.0.1:${PORT}`;

function waitForHealth(url, timeoutMs = 20000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      fetch(url).then((r) => r.json()).then(() => resolve())
        .catch(() => {
          if (Date.now() - start > timeoutMs) reject(new Error('看板服务启动超时'));
          else setTimeout(tick, 400);
        });
    };
    tick();
  });
}

async function api(method, urlPath, body, token) {
  const res = await fetch(`${BASE}${urlPath}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-Master-Token': token,
      'X-Device-Name': 'E2E-Setup',
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (res.status !== 200) throw new Error(`seed ${method} ${urlPath} -> ${res.status}: ${JSON.stringify(data)}`);
  return data;
}

module.exports = async () => {
  fs.mkdirSync(RUNTIME_DIR, { recursive: true });
  const tmpRoot = path.join(RUNTIME_DIR, 'data');
  fs.rmSync(tmpRoot, { recursive: true, force: true });
  fs.mkdirSync(path.join(tmpRoot, 'user_data', 'logs'), { recursive: true });

  const srvLog = fs.openSync(path.join(RUNTIME_DIR, 'server.log'), 'a');
  const proc = spawn('python3', ['scripts/start_kanban_server.py', '--port', String(PORT)], {
    cwd: path.resolve(__dirname, '..'),
    env: { ...process.env, YY_FLOW_PROJECT_ROOT: tmpRoot },
    stdio: ['ignore', srvLog, srvLog],
  });
  proc.on('exit', (code, sig) => console.error(`[E2E-setup] server exit code=${code} sig=${sig}`));
  await waitForHealth(`${BASE}/api/health`);

  const runtime = JSON.parse(fs.readFileSync(path.join(tmpRoot, 'user_data', 'kanban_server.json'), 'utf-8'));
  const masterToken = runtime.master_token;

  // 样本：9 状态 × 多角色 × 多阶段 + 边界样本（固定 id，便于断言）
  const S = [
    // 9 状态覆盖
    { id: 'T0101', name: 'E2E-登录接口开发', stage: 'S3 详细设计', wp: 'WP-后端', assignee: '李开发', status: '待开始' },
    { id: 'T0102', name: 'E2E-用户手册编制', stage: 'S7 文档与发布', wp: 'WP-文档', assignee: '李文通', status: '待开始' },
    { id: 'T0103', name: 'E2E-支付模块编码', stage: 'S3 详细设计', wp: 'WP-后端', assignee: '李开发', status: '进行中' },
    { id: 'T0104', name: 'E2E-看板首页样式', stage: 'S3 详细设计', wp: 'WP-前端', assignee: '马前端', status: '进行中' },
    { id: 'T0105', name: 'E2E-总体架构设计', stage: 'S2 架构设计', wp: 'WP-架构', assignee: '钱架构', status: '进行中' },
    { id: 'T0106', name: 'E2E-订单接口提审', stage: 'S3 详细设计', wp: 'WP-后端', assignee: '李开发', status: '审查中' },
    { id: 'T0107', name: 'E2E-组件交互提审', stage: 'S3 详细设计', wp: 'WP-前端', assignee: '马前端', status: '审查中' },
    { id: 'T0108', name: 'E2E-集成测试执行', stage: 'S6 工作流集成测试', wp: 'WP-测试', assignee: '章测试', status: '测试中' },
    { id: 'T0109', name: 'E2E-回归用例验证', stage: 'S6 工作流集成测试', wp: 'WP-测试', assignee: '章测试', status: '测试中' },
    { id: 'T0110', name: 'E2E-报表导出完成', stage: 'S3 详细设计', wp: 'WP-后端', assignee: '李开发', status: '已完成' },
    { id: 'T0111', name: 'E2E-移动端适配完成', stage: 'S3 详细设计', wp: 'WP-前端', assignee: '马前端', status: '已完成' },
    { id: 'T0112', name: 'E2E-需求拆解已验收', stage: 'S1 需求分析', wp: 'WP-需求', assignee: '严经理', status: '已验收' },
    { id: 'T0113', name: 'E2E-用户手册已验收', stage: 'S7 文档与发布', wp: 'WP-文档', assignee: '李文通', status: '已验收' },
    { id: 'T0114', name: 'E2E-缓存缺陷退回', stage: 'S3 详细设计', wp: 'WP-后端', assignee: '李开发', status: '已退回' },
    { id: 'T0115', name: 'E2E-发布流水线阻塞', stage: 'S6 工作流集成测试', wp: 'WP-发布', assignee: '吕改特', status: '已阻塞' },
    { id: 'T0116', name: 'E2E-废弃需求取消', stage: 'S1 需求分析', wp: 'WP-需求', assignee: '严经理', status: '已取消' },
    // 边界样本
    { id: 'T0120', name: '<script>alert(1)</script> 注入任务', stage: 'S3 详细设计', wp: 'WP-安全', assignee: '李开发', status: '待开始' },
    { id: 'T0121', name: '🚀 Emoji 国际化 ✨ 🇨🇳 任务', stage: 'S3 详细设计', wp: 'WP-前端', assignee: '马前端', status: '进行中' },
    { id: 'T0122', name: 'E2E-超长名称'.padEnd(60, '名'), stage: 'S3 详细设计', wp: 'WP-后端', assignee: '李开发', status: '待开始' },
    { id: 'T0123', name: 'E2E-超长备注任务', stage: 'S5 单元测试', wp: 'WP-测试', assignee: '李开发', status: '进行中', remarks: 'A'.repeat(1500) },
    // 拖拽/终态专用
    { id: 'T0124', name: 'E2E-拖拽验收专用', stage: 'S3 详细设计', wp: 'WP-后端', assignee: '李开发', status: '已完成' },
    { id: 'T0125', name: 'E2E-终态锁定专用', stage: 'S3 详细设计', wp: 'WP-后端', assignee: '严经理', status: '已验收' },
    // 角色视图样本
    { id: 'T0126', name: 'E2E-角色-周审查任务', stage: 'S5 代码审查', wp: 'WP-审查', assignee: '周审查', status: '进行中' },
    { id: 'T0127', name: 'E2E-角色-章测试任务', stage: 'S6 工作流集成测试', wp: 'WP-测试', assignee: '章测试', status: '进行中' },
    { id: 'T0128', name: 'E2E-角色-吕改特任务', stage: 'S6 工作流集成测试', wp: 'WP-发布', assignee: '吕改特', status: '待开始' },
    { id: 'T0129', name: 'E2E-角色-严经理任务', stage: 'S1 需求分析', wp: 'WP-需求', assignee: '严经理', status: '进行中' },
    { id: 'T0130', name: 'E2E-角色-钱架构任务', stage: 'S2 架构设计', wp: 'WP-架构', assignee: '钱架构', status: '进行中' },
  ];
  for (const c of S) {
    await api('POST', '/api/tasks', {
      id: c.id, name: c.name, stage: c.stage, wp: c.wp, assignee: c.assignee,
      status: c.status, wbs: '1.1', est_hours: 4, act_hours: 0, remarks: c.remarks || '',
    }, masterToken);
  }

  fs.writeFileSync(path.join(RUNTIME_DIR, 'config.json'), JSON.stringify({
    baseURL: BASE, masterToken, tmpRoot, pid: proc.pid,
  }));
  console.log(`[E2E-setup] server 就绪: ${BASE} · 样本 ${S.length} 张 · tmpRoot=${tmpRoot}`);
};
