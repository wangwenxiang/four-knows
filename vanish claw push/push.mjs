#!/usr/bin/env node

import { constants as fsConstants } from 'node:fs';
import {
  mkdir,
  open,
  readFile,
  rename,
  rm,
  stat,
  writeFile,
} from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CONFIG_PATH = path.join(HERE, 'config.json');
const STATE_DIR = path.join(HERE, '.state');
const STATE_PATH = path.join(STATE_DIR, 'state.json');
const LOCK_PATH = path.join(STATE_DIR, 'push.lock');
const VANISH_SKILL_PUSH_PATH = process.env.VANISH_CLAW_PUSH_MODULE
  || '/Users/jay/.agents/skills/vanish/scripts/vanish-claw-push.mjs';

const {
  checkVanishClawConnection,
  createProactiveMessageId,
  sendVanishClawImgMix,
} = await import(pathToFileURL(VANISH_SKILL_PUSH_PATH).href);

export function beijingDate(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now);
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return `${values.year}${values.month}${values.day}`;
}

export function buildArtifactUrls(baseUrl, date) {
  if (!/^\d{8}$/.test(date)) throw new Error(`日期格式无效：${date}`);
  const pageUrl = `${baseUrl.replace(/\/$/, '')}/${date}/`;
  return { pageUrl, imageUrl: `${pageUrl}screenshots.png` };
}

export function validatePng(bytes, expected, minBytes = 100000) {
  if (!(bytes instanceof Uint8Array) || bytes.byteLength < minBytes) {
    throw new Error(`日报图片过小：${bytes?.byteLength ?? 0} bytes`);
  }
  const signature = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
  if (!signature.every((value, index) => bytes[index] === value)) {
    throw new Error('远程图片不是 PNG');
  }
  if (bytes.byteLength < 26 || String.fromCharCode(...bytes.slice(12, 16)) !== 'IHDR') {
    throw new Error('PNG 缺少有效 IHDR');
  }
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const actual = {
    width: view.getUint32(16),
    height: view.getUint32(20),
    bitDepth: view.getUint8(24),
    colorType: view.getUint8(25),
  };
  for (const key of ['width', 'height', 'bitDepth', 'colorType']) {
    if (actual[key] !== expected[key]) {
      throw new Error(`PNG ${key} 不符合要求：${actual[key]}（期望 ${expected[key]}）`);
    }
  }
  return actual;
}

function output(result) {
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

function safeError(error) {
  const text = error instanceof Error ? error.message : String(error);
  return text.replace(/[\r\n]+/g, ' ').slice(0, 500);
}

async function loadJson(filePath, fallback = null) {
  try {
    return JSON.parse(await readFile(filePath, 'utf8'));
  } catch (error) {
    if (error?.code === 'ENOENT') return fallback;
    throw error;
  }
}

async function atomicWriteJson(filePath, value) {
  await mkdir(path.dirname(filePath), { recursive: true });
  const temporaryPath = `${filePath}.${process.pid}.tmp`;
  await writeFile(temporaryPath, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
  await rename(temporaryPath, filePath);
}

async function acquireLock() {
  await mkdir(STATE_DIR, { recursive: true });
  try {
    const handle = await open(
      LOCK_PATH,
      fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_WRONLY,
      0o600,
    );
    await handle.writeFile(`${process.pid}\n${new Date().toISOString()}\n`);
    await handle.close();
    return;
  } catch (error) {
    if (error?.code !== 'EEXIST') throw error;
  }

  const lockStat = await stat(LOCK_PATH).catch(() => null);
  if (lockStat && Date.now() - lockStat.mtimeMs > 30 * 60 * 1000) {
    await rm(LOCK_PATH, { force: true });
    return acquireLock();
  }
  throw new Error('已有日报推送任务正在运行');
}

async function releaseLock() {
  await rm(LOCK_PATH, { force: true });
}

async function fetchWithTimeout(url, options, timeoutMs) {
  return fetch(url, { ...options, signal: AbortSignal.timeout(timeoutMs) });
}

function cacheBusted(url) {
  const parsed = new URL(url);
  parsed.searchParams.set('_probe', String(Date.now()));
  return parsed;
}

async function fetchArtifactsOnce(urls, config) {
  const headers = { 'cache-control': 'no-cache', 'user-agent': 'ai-v-radar-push/1.0' };
  const [pageResponse, imageResponse] = await Promise.all([
    fetchWithTimeout(cacheBusted(urls.pageUrl), { headers }, config.httpTimeoutMs),
    fetchWithTimeout(cacheBusted(urls.imageUrl), { headers }, config.httpTimeoutMs),
  ]);

  if (!pageResponse.ok) throw new Error(`日报页面尚未发布（HTTP ${pageResponse.status}）`);
  const pageType = pageResponse.headers.get('content-type') || '';
  if (!pageType.toLowerCase().includes('text/html')) {
    throw new Error(`日报页面类型异常：${pageType || 'unknown'}`);
  }
  await pageResponse.text();

  if (!imageResponse.ok) throw new Error(`日报图片尚未发布（HTTP ${imageResponse.status}）`);
  const imageType = imageResponse.headers.get('content-type') || '';
  if (!imageType.toLowerCase().includes('image/png')) {
    throw new Error(`日报图片类型异常：${imageType || 'unknown'}`);
  }
  const imageBytes = new Uint8Array(await imageResponse.arrayBuffer());
  const png = validatePng(imageBytes, config.expectedPng, config.minPngBytes);
  return { imageBytes, png };
}

async function probeArtifacts(urls, config) {
  let lastError;
  for (let attempt = 1; attempt <= config.probeAttempts; attempt += 1) {
    try {
      const artifacts = await fetchArtifactsOnce(urls, config);
      return { ...artifacts, attempt };
    } catch (error) {
      lastError = error;
      process.stderr.write(`探测 ${attempt}/${config.probeAttempts}：${safeError(error)}\n`);
      if (attempt < config.probeAttempts) {
        await new Promise((resolve) => setTimeout(resolve, config.probeIntervalMs));
      }
    }
  }
  const error = new Error(`当天日报未就绪：${safeError(lastError)}`);
  error.code = 'NOT_READY';
  throw error;
}

function parseArgs(argv) {
  const options = { dryRun: false, force: false, checkConnection: false, date: null, groupId: null };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--dry-run') options.dryRun = true;
    else if (arg === '--force') options.force = true;
    else if (arg === '--check-connection') options.checkConnection = true;
    else if (arg === '--date') options.date = argv[++index];
    else if (arg === '--group-id') options.groupId = argv[++index];
    else throw new Error(`未知参数：${arg}`);
  }
  if (options.date && !/^\d{8}$/.test(options.date)) throw new Error('--date 必须是 YYYYMMDD');
  if (options.groupId && !/^\d{6,12}$/.test(options.groupId)) {
    throw new Error('--group-id 必须是有效群 ID');
  }
  return options;
}

export async function main(argv = process.argv.slice(2)) {
  const options = parseArgs(argv);
  const config = JSON.parse(await readFile(CONFIG_PATH, 'utf8'));
  const date = options.date || beijingDate();
  const groupId = options.groupId || String(config.groupId);
  const urls = buildArtifactUrls(config.remoteBaseUrl, date);

  await acquireLock();
  try {
    if (options.checkConnection) {
      await checkVanishClawConnection();
      output({ status: 'connection_ready', groupId, provider: 'global_vanish_skill' });
      return 0;
    }

    const state = await loadJson(STATE_PATH, {});
    const deliveryKey = `${date}:${groupId}`;
    const delivery = state.deliveries?.[deliveryKey]
      || (groupId === String(config.groupId) && state.lastSuccessDate === date
        ? { status: 'sent', messageId: state.lastMessageId }
        : {});
    if (!options.force && delivery.status === 'sent') {
      output({ status: 'already_sent', date, groupId, pageUrl: urls.pageUrl });
      return 0;
    }
    if (!options.force && delivery.status === 'in_flight') {
      output({ status: 'manual_review_required', date, groupId, pageUrl: urls.pageUrl });
      return 2;
    }

    let artifacts;
    try {
      artifacts = await probeArtifacts(urls, config);
    } catch (error) {
      if (error?.code === 'NOT_READY') {
        output({ status: 'not_ready', date, groupId, pageUrl: urls.pageUrl, reason: safeError(error) });
        return 3;
      }
      throw error;
    }

    if (options.dryRun) {
      output({
        status: 'ready',
        dryRun: true,
        date,
        groupId,
        pageUrl: urls.pageUrl,
        imageUrl: urls.imageUrl,
        png: artifacts.png,
        bytes: artifacts.imageBytes.byteLength,
        probeAttempt: artifacts.attempt,
        provider: 'global_vanish_skill',
      });
      return 0;
    }

    const messageId = createProactiveMessageId();
    try {
      const acknowledgement = await sendVanishClawImgMix({
        groupId,
        imageBytes: artifacts.imageBytes,
        fileName: `ai-v-radar-${date}.png`,
        text: `点击看完整：${urls.pageUrl}`,
        messageId,
        confirmSend: true,
        beforeSend: async () => {
          await atomicWriteJson(STATE_PATH, {
            ...state,
            deliveries: {
              ...(state.deliveries || {}),
              [deliveryKey]: {
                status: 'in_flight', date, messageId, groupId,
                startedAt: new Date().toISOString(),
              },
            },
          });
        },
      });
      await atomicWriteJson(STATE_PATH, {
        ...state,
        deliveries: {
          ...(state.deliveries || {}),
          [deliveryKey]: {
            status: 'sent', date, messageId, groupId,
            pageUrl: urls.pageUrl, sentAt: new Date().toISOString(),
          },
        },
      });
      output({
        status: 'sent', date, groupId, pageUrl: urls.pageUrl,
        messageId, requestId: acknowledgement.requestId,
        provider: 'global_vanish_skill',
      });
      return 0;
    } catch (error) {
      if (error?.code !== 'DELIVERY_UNKNOWN') {
        await atomicWriteJson(STATE_PATH, {
          ...state,
          deliveries: {
            ...(state.deliveries || {}),
            [deliveryKey]: {
              status: 'failed', date, groupId, at: new Date().toISOString(), reason: safeError(error),
            },
          },
        });
      }
      throw error;
    }
  } finally {
    await releaseLock();
  }
}

const isEntrypoint = process.argv[1]
  && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;
if (isEntrypoint) {
  main().then((code) => { process.exitCode = code; }).catch((error) => {
    output({
      status: error?.code === 'DELIVERY_UNKNOWN' ? 'manual_review_required' : 'failed',
      reason: safeError(error),
    });
    process.exitCode = 1;
  });
}
