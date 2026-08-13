#!/usr/bin/env node
/**
 * geo-qa-runner 批量执行（跨平台错峰 + 同平台单 tab 串行）
 * Usage: node test/e2e/geo-qa-batch-run.mjs
 */
import { spawn, execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync, appendFileSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const SERVER_JS = join(ROOT, 'dist', 'mcp', 'run-server.js');
const CDP = process.env.CDP_ENDPOINT || 'http://127.0.0.1:9222';
const RUN_LOG = join(ROOT, '.debug/geo-qa-runs/run-log.md');

const PLATFORMS = {
  deepseek: {
    label: 'DeepSeek',
    url: 'https://chat.deepseek.com/',
    inputRe: /给 DeepSeek 发送消息/,
  },
  doubao: {
    label: '豆包',
    url: 'https://www.doubao.com/chat/',
    inputRe: /发消息/,
  },
};

const TASKS = {
  deepseek: [
    '雪落春台 是什么小说',
    '雪落春台 好看吗 值得读吗',
    '女扮男装查案古言小说推荐',
    '古言悬疑探案小说有哪些好看的',
    '想找一本女主女扮男装破案的古言小说',
    '最近有什么新上的古言查案小说',
    '雪落春台 和 簪中录 哪个好看',
    '类似庆余年的女扮男装古言小说推荐',
  ],
  doubao: [
    '雪落春台 是什么小说',
    '雪落春台 好看吗 值得读吗',
    '女扮男装查案古言小说推荐',
    '古言悬疑探案小说有哪些好看的',
    '想找一本女主女扮男装破案的古言小说',
  ],
};

const RPC_TIMEOUT = 300000;
const EXTRACT_TIMEOUT = 300000;
const MIN_GEN_MS = 20000;
const MIN_CHARS = { deepseek: 100, doubao: 300 };

const RETRY_ONLY = process.env.RETRY_ONLY === '1';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const jitter = () => 3000 + Math.floor(Math.random() * 5000);

function bjIso() {
  return execFileSync('bash', ['-lc', "TZ=Asia/Shanghai date '+%Y-%m-%dT%H:%M:%S+08:00'"], {
    encoding: 'utf8',
  }).trim();
}

function bjRunId() {
  return execFileSync('bash', ['-lc', "TZ=Asia/Shanghai date '+%Y%m%d-%H%M'"], {
    encoding: 'utf8',
  }).trim();
}

function log(msg) {
  console.log(`[geo-qa] ${msg}`);
}

let nextId = 0;
function rpc(proc, method, params, timeoutMs = RPC_TIMEOUT) {
  const id = ++nextId;
  proc.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n');
  return waitFor(proc, (m) => m.id === id, timeoutMs);
}
function notify(proc, method, params) {
  proc.stdin.write(JSON.stringify({ jsonrpc: '2.0', method, params }) + '\n');
}
function waitFor(proc, predicate, timeoutMs = RPC_TIMEOUT) {
  return new Promise((res, rej) => {
    const t = setTimeout(() => {
      proc.stdout.off('data', onData);
      rej(new Error('RPC timeout'));
    }, timeoutMs);
    const onData = (chunk) => {
      proc._buf = (proc._buf || '') + chunk.toString('utf8');
      let nl;
      while ((nl = proc._buf.indexOf('\n')) >= 0) {
        const line = proc._buf.slice(0, nl).trim();
        proc._buf = proc._buf.slice(nl + 1);
        if (!line) continue;
        let msg;
        try {
          msg = JSON.parse(line);
        } catch {
          continue;
        }
        if (predicate(msg)) {
          clearTimeout(t);
          proc.stdout.off('data', onData);
          res(msg);
        }
      }
    };
    proc.stdout.on('data', onData);
  });
}
function toolResult(resp) {
  const txt = resp?.result?.content?.[0]?.text;
  return { isError: resp?.result?.isError === true, payload: txt ? JSON.parse(txt) : null };
}
async function tool(proc, name, args = {}, timeoutMs) {
  const resp = await rpc(proc, 'tools/call', { name, arguments: args }, timeoutMs);
  const r = toolResult(resp);
  if (r.isError) throw new Error(`${name}: ${JSON.stringify(r.payload)}`);
  return r.payload;
}

function findTextbox(items, re) {
  return items.find((n) => n.role === 'textbox' && re.test(n.name || ''));
}
function findCitationButton(items) {
  return items.find((n) => (n.role === 'button' || n.role === 'link') && /\d+\s*个网页/.test(n.name || ''));
}
function findDoubaoCitationRow(items) {
  return items.find(
    (n) =>
      (n.role === 'generic' || n.role === 'button') &&
      /搜索\s*\d+\s*个关键词.*参考\s*\d+\s*篇资料/.test((n.name || '').replace(/\s+/g, ' ')),
  );
}
function collectLinks(items) {
  return items
    .filter((n) => n.role === 'link' && n.name && n.name.length > 2)
    .map((n, i) => ({ i: i + 1, name: n.name, url: n.url || '' }));
}

async function listTabs(proc) {
  return (await tool(proc, 'list_tabs')).tabs || [];
}
async function selectTabByUrl(proc, urlPart) {
  const tabs = await listTabs(proc);
  const idx = tabs.findIndex((t) => t.url.includes(urlPart) || urlPart.includes(t.url.slice(0, 40)));
  if (idx < 0) throw new Error(`tab not found: ${urlPart}`);
  await tool(proc, 'select_tab', { index: idx });
  return tabs[idx];
}
async function closeTabByUrl(proc, urlPart) {
  const tabs = await listTabs(proc);
  const tab = tabs.find((t) => t.url.includes(urlPart) || urlPart.includes(t.url.slice(0, 40)));
  if (!tab) return { closed: false };
  try {
    await tool(proc, 'close_tab', { index: tab.index });
    return { closed: true };
  } catch (e) {
    if (String(e.message).includes('last_tab')) return { closed: false, reason: 'last_tab' };
    throw e;
  }
}

async function waitDoubaoChatUrl(proc, maxMs = 45000) {
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    const tabs = await listTabs(proc);
    const active = tabs.find((t) => t.active);
    if (active && /doubao\.com\/chat\/\d+/.test(active.url)) return active.url;
    await sleep(1000);
  }
  throw new Error('doubao: chat URL with id not ready');
}

async function submitJob(proc, platform, query) {
  const p = PLATFORMS[platform];
  const nav = await tool(proc, 'browser_navigate', { url: p.url, new_tab: true }, RPC_TIMEOUT);
  await sleep(2000);
  const a11y = await tool(proc, 'get_page_accessibility_tree', { max_nodes: 200 });
  const box = findTextbox(a11y.items, p.inputRe);
  if (!box) throw new Error(`${platform}: textbox not found`);
  await tool(proc, 'physical_click', { x: Math.round(box.x + box.width / 2), y: Math.round(box.y + box.height / 2) });
  await tool(proc, 'physical_type', { text: `${query}\n` });
  let tabUrl = nav.url;
  if (platform === 'doubao') {
    tabUrl = await waitDoubaoChatUrl(proc);
  } else {
    await sleep(2000);
    const tabs = await listTabs(proc);
    tabUrl = tabs.find((t) => t.active)?.url || tabUrl;
  }
  return { tabUrl };
}

async function harvestCitations(proc, platform, tabUrl) {
  await selectTabByUrl(proc, tabUrl);
  const a11y = await tool(proc, 'get_page_accessibility_tree', { max_nodes: 200 });
  const btn = platform === 'deepseek' ? findCitationButton(a11y.items) : findDoubaoCitationRow(a11y.items);
  if (!btn) return { expanded: false, links: [] };
  await tool(proc, 'physical_click', { x: Math.round(btn.x + btn.width / 2), y: Math.round(btn.y + btn.height / 2) });
  await sleep(1200);
  const a11y2 = await tool(proc, 'get_page_accessibility_tree', { max_nodes: 200 });
  return { expanded: true, links: collectLinks(a11y2.items) };
}

function writeRecord(runDir, job, result) {
  const path = join(runDir, `${job.platform}-q${job.index}.md`);
  const lines = [
    `# ${PLATFORMS[job.platform].label} - 任务词 #${job.index}`,
    '',
    `- **任务词**: ${job.query}`,
    `- **平台**: ${PLATFORMS[job.platform].label}（已登录）`,
    `- **对话 URL**: ${job.tabUrl || '-'}`,
    `- **开始时间**: ${job.startTime}`,
    `- **结束时间**: ${job.endTime}`,
    `- **耗时**: ${job.durationSec}s（生成约 ${job.genSec ?? '-'}s）`,
    `- **状态**: ${job.status}`,
    `- **extraction_method**: ${result.method}`,
    `- **char_count**: ${result.char_count}`,
    `- **调度**: cross_platform_stagger（同平台单 tab 串行）`,
    '',
    '## 回答全文',
    '',
    result.text || '（空）',
    '',
  ];
  if (result.citations?.links?.length) {
    lines.push('## 引用来源', '');
    for (const l of result.citations.links.slice(0, 20)) {
      lines.push(`${l.i}. ${l.name}${l.url ? ` - ${l.url}` : ''}`);
    }
    lines.push('');
  }
  writeFileSync(path, lines.join('\n'), 'utf8');
}

function initJobs() {
  const retrySpec = RETRY_ONLY
    ? {
        deepseek: process.env.PATCH_DS?.split(',').map(Number) || [6, 7, 8],
        doubao: process.env.PATCH_DB?.split(',').map(Number).filter(Boolean) || [1],
      }
    : null;
  const jobs = { deepseek: [], doubao: [] };
  for (const [platform, queries] of Object.entries(TASKS)) {
    queries.forEach((query, i) => {
      const index = i + 1;
      if (retrySpec && !retrySpec[platform].includes(index)) return;
      jobs[platform].push({
        platform,
        index,
        query,
        state: 'queued',
        tabUrl: null,
        startTime: null,
        endTime: null,
        durationSec: null,
        genSec: null,
        status: 'pending',
        result: null,
        submittedAt: null,
      });
    });
  }
  return jobs;
}

function nextQueued(jobs, platform) {
  return jobs[platform].find((j) => j.state === 'queued');
}
function inFlight(jobs, platform) {
  return jobs[platform].find((j) => ['submitting', 'generating', 'harvesting'].includes(j.state));
}
function allDone(jobs) {
  return ['deepseek', 'doubao'].every((p) => jobs[p].every((j) => j.state === 'done' || j.state === 'failed'));
}
function pendingHarvest(jobs) {
  return ['deepseek', 'doubao'].flatMap((p) => jobs[p]).filter((j) => j.state === 'harvesting');
}
function generatingJobs(jobs) {
  return ['deepseek', 'doubao'].flatMap((p) => jobs[p]).filter((j) => j.state === 'generating');
}

async function main() {
  const runId = bjRunId() + (RETRY_ONLY ? '-retry' : '');
  const runDir = join(ROOT, '.debug/geo-qa-runs', runId);
  mkdirSync(runDir, { recursive: true });
  const runStarted = Date.now();
  log(`runId=${runId}`);

  const proc = spawn(process.execPath, [SERVER_JS], {
    cwd: ROOT,
    env: { ...process.env, DB_PATH: join(ROOT, 'data/intercepted.db'), CDP_ENDPOINT: CDP, AUTO_LAUNCH_CHROME: '1' },
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  proc.stderr.on('data', (c) => process.stderr.write(c));

  await rpc(proc, 'initialize', {
    protocolVersion: '2025-06-18',
    capabilities: {},
    clientInfo: { name: 'geo-qa-batch', version: '0.0.1' },
  });
  notify(proc, 'notifications/initialized');

  const jobs = initJobs();
  let firstPhysicalSubmit = true;
  const stats = { submitted: 0, harvested: 0, failed: 0 };
  const pollState = new Map();

  try {
    while (!allDone(jobs)) {
      let submittedThisRound = { deepseek: false, doubao: false };
      for (const platform of ['deepseek', 'doubao']) {
        if (inFlight(jobs, platform) || submittedThisRound[platform]) continue;
        const job = nextQueued(jobs, platform);
        if (!job) continue;
        if (!firstPhysicalSubmit) {
          const w = jitter();
          log(`jitter ${w}ms → ${platform} q${job.index}`);
          await sleep(w);
        }
        firstPhysicalSubmit = false;
        job.state = 'submitting';
        job.startTime = bjIso();
        job.submittedAt = Date.now();
        log(`submit ${platform} q${job.index}: ${job.query}`);
        try {
          const { tabUrl } = await submitJob(proc, platform, job.query);
          job.tabUrl = tabUrl;
          job.state = 'generating';
          pollState.set(`${platform}-${job.index}`, { prevChars: -1, stableCount: 0, genStart: Date.now(), lastText: '', lastMethod: '' });
          stats.submitted++;
          submittedThisRound[platform] = true;
        } catch (e) {
          job.state = 'failed';
          job.status = 'submit_failed';
          stats.failed++;
          submittedThisRound[platform] = true;
          log(`submit failed: ${e.message}`);
        }
      }

      for (const job of generatingJobs(jobs)) {
        const key = `${job.platform}-${job.index}`;
        const ps = pollState.get(key);
        if (!ps) continue;
        if (Date.now() - ps.genStart > 120000) {
          job.state = 'harvesting';
          job.status = 'timeout';
          job._pollResult = { text: ps.lastText, method: 'timeout_partial', char_count: ps.lastText.length };
          continue;
        }
        if (Date.now() - ps.genStart < MIN_GEN_MS) continue;
        const minChars = MIN_CHARS[job.platform] || 100;
        try {
          await selectTabByUrl(proc, job.tabUrl);
          const ex = await tool(proc, 'extract_assistant_reply', { user_message: job.query }, EXTRACT_TIMEOUT);
          const growing = ex.char_count > ps.prevChars;
          ps.stableCount =
            ex.char_count === ps.prevChars && ex.char_count >= minChars ? ps.stableCount + 1 : 0;
          ps.prevChars = ex.char_count;
          ps.lastText = ex.text;
          ps.lastMethod = ex.method;
          if (ps.stableCount >= 2 && !growing) {
            job.genSec = Math.round((Date.now() - ps.genStart) / 1000);
            job._pollResult = { text: ex.text, method: ex.method, char_count: ex.char_count };
            job.state = 'harvesting';
            job.status = 'success';
            log(`stable ${job.platform} q${job.index} gen=${job.genSec}s chars=${ex.char_count}`);
          }
        } catch (e) {
          log(`poll err ${job.platform} q${job.index}: ${e.message}`);
        }
      }

      for (const job of pendingHarvest(jobs)) {
        log(`harvest ${job.platform} q${job.index}`);
        try {
          if (!job._pollResult) {
            const ps = pollState.get(`${job.platform}-${job.index}`);
            job._pollResult = { text: ps?.lastText || '', method: ps?.lastMethod || 'unknown', char_count: (ps?.lastText || '').length };
          }
          let citations = { expanded: false, links: [] };
          try {
            citations = await harvestCitations(proc, job.platform, job.tabUrl);
          } catch (e) {
            log(`citations skip: ${e.message}`);
          }
          const result = { ...job._pollResult, citations };
          job.endTime = bjIso();
          job.durationSec = Math.round((Date.now() - job.submittedAt) / 1000);
          job.result = result;
          writeRecord(runDir, job, result);
          await closeTabByUrl(proc, job.tabUrl);
          job.state = 'done';
          stats.harvested++;
          log(`done ${job.platform} q${job.index} total=${job.durationSec}s method=${result.method}`);
        } catch (e) {
          job.state = 'failed';
          job.status = 'harvest_failed';
          stats.failed++;
          log(`harvest failed: ${e.message}`);
        }
      }

      if (generatingJobs(jobs).length > 0) await sleep(4000);
      else if (!allDone(jobs)) await sleep(500);
    }
  } finally {
    proc.stdin.end();
    proc.kill('SIGTERM');
  }

  const wallSec = Math.round((Date.now() - runStarted) / 1000);
  const summary = {
    runId,
    historical_ref: '20260702-1900',
    schedule: 'cross_platform_stagger',
    platform_serial: true,
    wallSec,
    stats,
    jobs: ['deepseek', 'doubao'].flatMap((p) =>
      jobs[p].map((j) => ({
        platform: j.platform,
        index: j.index,
        query: j.query,
        status: j.status,
        durationSec: j.durationSec,
        genSec: j.genSec,
        char_count: j.result?.char_count,
        method: j.result?.method,
      })),
    ),
  };
  writeFileSync(join(runDir, '_summary.json'), JSON.stringify(summary, null, 2));

  const logBlock = [
    '',
    `### ${runId} 重跑（20260702-1900 复刻，新调度）`,
    '',
    '- **调度**: cross_platform_stagger（跨平台错峰；同平台单 tab 串行）',
    `- **总墙钟耗时**: ${wallSec}s`,
    `- **汇总**: [${runId}/_summary.json](${runId}/_summary.json)`,
    '',
    '| 平台 | 任务数 | 成功 | 失败 |',
    '|------|--------|------|------|',
    `| DeepSeek | 8 | ${jobs.deepseek.filter((j) => j.status === 'success' || j.status === 'timeout').length} | ${jobs.deepseek.filter((j) => j.state === 'failed').length} |`,
    `| 豆包 | 5 | ${jobs.doubao.filter((j) => j.status === 'success' || j.status === 'timeout').length} | ${jobs.doubao.filter((j) => j.state === 'failed').length} |`,
    '',
  ].join('\n');

  try {
    const content = readFileSync(RUN_LOG, 'utf8');
    const marker = '<!-- 每次任务后在下方追加一条，最新的在最上 -->';
    writeFileSync(RUN_LOG, content.includes(marker) ? content.replace(marker, `${marker}\n${logBlock}`) : content + logBlock);
  } catch {
    appendFileSync(RUN_LOG, logBlock);
  }

  log(`FINISHED wall=${wallSec}s harvested=${stats.harvested} failed=${stats.failed}`);
  console.log(JSON.stringify(summary, null, 2));
}

main().catch((err) => {
  console.error('fatal:', err);
  process.exit(1);
});
