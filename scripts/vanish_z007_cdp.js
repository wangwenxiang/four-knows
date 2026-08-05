#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

function parseArgs(argv) {
  const out = { send: false, dryRun: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--send") out.send = true;
    else if (arg === "--dry-run") out.dryRun = true;
    else if (arg === "--from") out.from = argv[++i];
    else if (arg === "--to") out.to = argv[++i];
    else if (arg === "--port") out.port = argv[++i];
    else if (arg === "--help" || arg === "-h") out.help = true;
  }
  return out;
}

function usage() {
  console.log([
    "Usage:",
    "  node scripts/vanish_z007_cdp.js --dry-run --from <name> --to <group>",
    "  node scripts/vanish_z007_cdp.js --send --from <name> --to <group>",
    "",
    "This forwards the latest inbound Vanish message from <name> to <group>",
    "through Vanish's native forward dialog. It never caches message ids."
  ].join("\n"));
}

async function readDevtoolsPort() {
  const fixed = "9222";
  try {
    const devtoolsFile = path.join(
      process.env.HOME || "",
      "Library/Application Support/Vanish/DevToolsActivePort"
    );
    const text = fs.readFileSync(devtoolsFile, "utf8").trim();
    const first = text.split(/\s+/)[0];
    return first || fixed;
  } catch {
    return fixed;
  }
}

async function connect(port) {
  const listUrl = `http://127.0.0.1:${port}/json/list`;
  const pages = await fetch(listUrl).then((r) => r.json());
  const page = pages.find((p) => p.url.includes("/website/web/index.html#/chat"));
  if (!page) throw new Error(`Vanish chat page not found on ${listUrl}`);

  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let nextId = 1;
  const pending = new Map();

  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (!message.id || !pending.has(message.id)) return;
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(JSON.stringify(message.error)));
    else resolve(message.result);
  };

  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = reject;
  });

  function call(method, params = {}) {
    const id = nextId++;
    ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
  }

  return { call, close: () => ws.close() };
}

function buildPageScript({ from, to, send }) {
  return String.raw`
    (async () => {
      const SOURCE_NAME = ${JSON.stringify(from)};
      const TARGET_NAME = ${JSON.stringify(to)};
      const SHOULD_SEND = ${JSON.stringify(send)};
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

      function textOf(el) {
        return (el && (el.innerText || el.textContent) || "").trim();
      }

      function visible(el) {
        if (!el) return false;
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
      }

      function click(el) {
        if (!el) return false;
        el.scrollIntoView({ block: "center", inline: "center" });
        const rect = el.getBoundingClientRect();
        const opts = {
          bubbles: true,
          cancelable: true,
          view: window,
          clientX: rect.left + Math.max(4, Math.min(20, rect.width / 2)),
          clientY: rect.top + Math.max(4, Math.min(20, rect.height / 2))
        };
        for (const type of ["mouseover", "mousemove", "mousedown", "mouseup", "click"]) {
          el.dispatchEvent(new MouseEvent(type, opts));
        }
        return true;
      }

      function setNativeValue(el, value) {
        const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const desc = Object.getOwnPropertyDescriptor(proto, "value");
        desc.set.call(el, value);
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
      }

      function displayName(obj) {
        const direct = obj?.username || obj?.name || obj?.showName || obj?.groupName || obj?.group_name || obj?.gname || obj?.alias || obj?.title || obj?.sessionName;
        if (direct) return String(direct);
        return deepPick(obj, (key, value) => /^(username|name|showname|groupname|group_name|gname|alias|title|sessionname)$/i.test(key) && typeof value === "string") || "";
      }

      function objectCode(obj) {
        const direct = obj?.code || obj?.ucode || obj?.userCode || obj?.user_code || obj?.gcode || obj?.groupCode || obj?.group_code;
        if (direct) return String(direct);
        const byKey = deepPick(obj, (key, value) => /^(code|ucode|usercode|user_code|gcode|groupcode|group_code)$/i.test(key) && /^\d+$/.test(String(value)));
        if (byKey) return String(byKey);
        const sessionId = obj?.sessionId || obj?.key;
        if (typeof sessionId === "string" && sessionId.startsWith("group")) return sessionId.replace(/^group/, "");
        return "";
      }

      function deepPick(obj, predicate, seen = new Set()) {
        if (!obj || typeof obj !== "object" || seen.has(obj)) return "";
        seen.add(obj);
        for (const [key, value] of Object.entries(obj)) {
          if (predicate(key, value)) return value;
        }
        for (const value of Object.values(obj)) {
          const found = deepPick(value, predicate, seen);
          if (found) return found;
        }
        return "";
      }

      function storeNameFromMap(value) {
        if (typeof value === "string" || typeof value === "number") return String(value);
        if (!value || typeof value !== "object") return "";
        for (const key of ["storeName", "tableName", "name", "value", "id", "storeId", "tableId"]) {
          if (value[key] !== undefined && value[key] !== null) return String(value[key]);
        }
        const raw = JSON.stringify(value);
        const match = raw.match(/"(\d{1,4})"/) || raw.match(/:(\d{1,4})(?:,|})/);
        return match ? match[1] : "";
      }

      async function openDb() {
        const dbs = await indexedDB.databases();
        const main = dbs.map((db) => db.name).filter(Boolean).find((name) => /^vanish-\d+$/.test(name));
        if (!main) throw new Error("No vanish-<userCode> IndexedDB database found");
        return new Promise((resolve, reject) => {
          const req = indexedDB.open(main);
          req.onerror = () => reject(req.error);
          req.onsuccess = () => resolve(req.result);
        });
      }

      function idbAll(db, storeName) {
        return new Promise((resolve, reject) => {
          const tx = db.transaction(storeName, "readonly");
          const store = tx.objectStore(storeName);
          const out = [];
          const req = store.openCursor();
          req.onerror = () => reject(req.error);
          req.onsuccess = (event) => {
            const cursor = event.target.result;
            if (!cursor) return resolve(out);
            out.push(cursor.value);
            cursor.continue();
          };
        });
      }

      function idbGet(db, storeName, key) {
        return new Promise((resolve, reject) => {
          const tx = db.transaction(storeName, "readonly");
          const req = tx.objectStore(storeName).get(key);
          req.onerror = () => reject(req.error);
          req.onsuccess = () => resolve(req.result);
        });
      }

      function idbEntries(db, storeName) {
        return new Promise((resolve, reject) => {
          const tx = db.transaction(storeName, "readonly");
          const store = tx.objectStore(storeName);
          const out = [];
          const req = store.openCursor();
          req.onerror = () => reject(req.error);
          req.onsuccess = (event) => {
            const cursor = event.target.result;
            if (!cursor) return resolve(out);
            out.push({ key: cursor.key, value: cursor.value });
            cursor.continue();
          };
        });
      }

      async function mappedStore(db, key) {
        const candidates = [key];
        if (/^\d+$/.test(String(key))) candidates.push(Number(key), "user" + key);
        if (!String(key).startsWith("group")) candidates.push("group" + key);
        for (const candidate of candidates) {
          const direct = await idbGet(db, "mapTable", candidate).catch(() => undefined);
          const name = storeNameFromMap(direct);
          if (name) return name;
        }
        const entries = await idbEntries(db, "mapTable");
        const matched = entries.find((entry) => candidates.some((candidate) => String(entry.key) === String(candidate)));
        return matched ? storeNameFromMap(matched.value) : "";
      }

      async function findStoreByMessages(db, predicate) {
        const numericStores = Array.from(db.objectStoreNames).filter((name) => /^\d+$/.test(name));
        let best = null;
        for (const storeName of numericStores) {
          let messages = [];
          try {
            messages = await idbAll(db, storeName);
          } catch {
            continue;
          }
          const matches = messages.filter(predicate);
          if (!matches.length) continue;
          const latest = matches.slice().sort((a, b) => (b.timeval || b.date || 0) - (a.timeval || a.date || 0))[0];
          if (!best || (latest.timeval || latest.date || 0) > (best.latest.timeval || best.latest.date || 0)) {
            best = { storeName, latest };
          }
        }
        return best ? best.storeName : "";
      }

      async function resolveContext() {
        const db = await openDb();
        const currentUserCode = db.name.replace(/^vanish-/, "");
        const users = await idbAll(db, "users");
        const groups = await idbAll(db, "groups");
        const sessions = await idbAll(db, "sessionList");
        const source = users.find((u) => displayName(u) === SOURCE_NAME || objectCode(u) === SOURCE_NAME);
        const target = sessions.find((s) => displayName(s) === TARGET_NAME || objectCode(s) === TARGET_NAME || JSON.stringify(s).includes("\"" + TARGET_NAME + "\""))
          || groups.find((g) => displayName(g) === TARGET_NAME || objectCode(g) === TARGET_NAME || JSON.stringify(g).includes("\"" + TARGET_NAME + "\""));
        if (!source) throw new Error("Source user not found: " + SOURCE_NAME);
        if (!target) throw new Error("Target group not found: " + TARGET_NAME);

        const sourceCode = objectCode(source);
        let targetCode = objectCode(target);
        if (!targetCode) {
          const targetSession = sessions.find((s) => displayName(s) === TARGET_NAME || JSON.stringify(s).includes(TARGET_NAME));
          targetCode = objectCode(targetSession);
        }
        if (!targetCode) throw new Error("Target group code not found for " + TARGET_NAME);
        let sourceStore = await mappedStore(db, sourceCode);
        let targetStore = await mappedStore(db, "group" + targetCode);
        if (!sourceStore) {
          sourceStore = await findStoreByMessages(db, (m) => String(m.scode) === sourceCode && String(m.rcode || "") === currentUserCode && !m.gcode);
        }
        if (!targetStore) {
          targetStore = await findStoreByMessages(db, (m) => String(m.gcode || "") === targetCode);
        }
        if (!sourceStore) throw new Error("Source message store not found for " + SOURCE_NAME + "/" + sourceCode);
        if (!targetStore) throw new Error("Target message store not found for " + TARGET_NAME + "/" + targetCode);

        const sourceMessages = await idbAll(db, sourceStore);
        const latest = sourceMessages
          .filter((m) => String(m.scode) === sourceCode)
          .sort((a, b) => (b.timeval || b.date || 0) - (a.timeval || a.date || 0))[0];
        if (!latest) throw new Error("No inbound messages found from " + SOURCE_NAME + "/" + sourceCode);

        const targetMessages = await idbAll(db, targetStore);
        const beforeTargetLatest = targetMessages
          .slice()
          .sort((a, b) => (b.timeval || b.date || 0) - (a.timeval || a.date || 0))[0];

        return {
          db,
          dbName: db.name,
          currentUserCode,
          source: { code: sourceCode, name: displayName(source) },
          target: { code: targetCode, name: displayName(target) || TARGET_NAME },
          sourceStore,
          targetStore,
          latest: {
            id: String(latest.id || latest.msgid || latest.key || ""),
            scode: latest.scode,
            sname: latest.sname,
            type: latest.body?.type,
            content: latest.body?.content,
            fname: latest.body?.fname,
            timeval: latest.timeval || latest.date
          },
          targetLatest: beforeTargetLatest ? {
            id: String(beforeTargetLatest.id || beforeTargetLatest.msgid || beforeTargetLatest.key || ""),
            scode: beforeTargetLatest.scode,
            sname: beforeTargetLatest.sname,
            type: beforeTargetLatest.body?.type,
            content: beforeTargetLatest.body?.content,
            fname: beforeTargetLatest.body?.fname,
            timeval: beforeTargetLatest.timeval || beforeTargetLatest.date,
            sendStatus: beforeTargetLatest.extUI?.sendStatus
          } : null,
          beforeTargetLatestId: beforeTargetLatest ? String(beforeTargetLatest.id || beforeTargetLatest.msgid || beforeTargetLatest.key || "") : ""
        };
      }

      async function selectSourceChat(sourceName) {
        const header = textOf(document.querySelector(".window-header.header, .window-header, .chat-window-title"));
        if (header === sourceName) return { ok: true, method: "already-active" };

        const search = Array.from(document.querySelectorAll(".chat-search-wrapper input, .global-search input, input"))
          .filter(visible)
          .find((el) => (el.placeholder || "").includes("搜索") && el.getBoundingClientRect().top < 80);
        if (!search) return { ok: false, reason: "global search input not found" };
        search.focus();
        setNativeValue(search, sourceName);
        await sleep(1200);

        const candidate = Array.from(document.querySelectorAll(".item-contact, *"))
          .filter((el) => visible(el) && textOf(el).startsWith(sourceName))
          .sort((a, b) => textOf(a).length - textOf(b).length)[0];
        if (!candidate) return { ok: false, reason: "search result not found for " + sourceName };
        click(candidate);
        await sleep(1500);
        const afterHeader = textOf(document.querySelector(".window-header.header, .window-header, .chat-window-title"));
        return { ok: afterHeader === sourceName, method: "search-click", afterHeader, candidateText: textOf(candidate).slice(0, 120) };
      }

      async function scrollChatToBottom() {
        const panes = Array.from(document.querySelectorAll("#chat-window, .dialog-pane, .dialog-inner, .content"))
          .filter((el) => el && el.scrollHeight > el.clientHeight);
        for (const pane of panes) pane.scrollTop = pane.scrollHeight;
        await sleep(900);
        for (const pane of panes) pane.scrollTop = pane.scrollHeight;
        await sleep(500);
      }

      function findMessageElement(messageId, latest) {
        const byId = messageId && (document.getElementById(messageId) || document.getElementById("w" + messageId));
        if (byId) return byId;
        const textPart = typeof latest.content === "string"
          ? latest.content.slice(0, 40)
          : Array.isArray(latest.content)
            ? latest.content.map((x) => x?.body?.content || "").find((x) => typeof x === "string" && x.length > 6)
            : "";
        if (!textPart) return null;
        return Array.from(document.querySelectorAll(".message-outer, .message-outer-wrapper, .message-content-wrapper, *"))
          .filter((el) => visible(el) && textOf(el).includes(textPart))
          .sort((a, b) => textOf(a).length - textOf(b).length)[0] || null;
      }

      async function openForwardDialog(messageEl) {
        const target = messageEl.closest(".message-outer") || messageEl.closest(".message-outer-wrapper") || messageEl;
        const rect = target.getBoundingClientRect();
        target.dispatchEvent(new MouseEvent("contextmenu", {
          bubbles: true,
          cancelable: true,
          view: window,
          button: 2,
          buttons: 2,
          clientX: rect.left + Math.max(8, Math.min(40, rect.width / 2)),
          clientY: rect.top + Math.max(8, Math.min(40, rect.height / 2))
        }));
        await sleep(500);
        const forward = Array.from(document.querySelectorAll("#message-handle-menu li, .contextmenu li, *"))
          .filter((el) => visible(el) && textOf(el) === "转发")
          .sort((a, b) => textOf(a).length - textOf(b).length)[0];
        if (!forward) throw new Error("Forward menu item not found");
        click(forward);
        await sleep(1000);
        const dialog = document.querySelector(".forward-message-dialog");
        if (!dialog || !visible(dialog)) throw new Error("Forward dialog not opened");
        return dialog;
      }

      async function chooseTargetAndSend(dialog, target) {
        let checkbox = dialog.querySelector('input[value="' + target.code + '"]');
        if (!checkbox) {
          const search = Array.from(dialog.querySelectorAll("input")).filter(visible).find((el) => (el.placeholder || "").includes("搜索"));
          if (search) {
            search.focus();
            setNativeValue(search, target.name);
            await sleep(900);
          }
          checkbox = dialog.querySelector('input[value="' + target.code + '"]');
        }
        if (!checkbox) {
          const labelByName = Array.from(dialog.querySelectorAll("label, .user-list, *"))
            .filter((el) => visible(el) && textOf(el) === target.name)
            .map((el) => el.closest("label") || el)
            [0];
          checkbox = labelByName?.querySelector?.("input") || null;
        }
        if (!checkbox) throw new Error("Target checkbox not found for " + target.name + "/" + target.code);

        const label = checkbox.closest("label") || checkbox;
        label.click();
        checkbox.dispatchEvent(new Event("change", { bubbles: true }));
        await sleep(800);

        const button = Array.from(dialog.querySelectorAll(".button, button, [role=button], div"))
          .filter((el) => visible(el) && textOf(el) === "转发")
          .sort((a, b) => Number(String(a.className || "").includes("button-primary")) - Number(String(b.className || "").includes("button-primary")))
          .pop();
        if (!button) throw new Error("Forward submit button not found");
        if (String(button.className || "").includes("button-disabled")) throw new Error("Forward submit button is still disabled");
        click(button);
        await sleep(2500);
      }

      async function validate(ctx) {
        const messages = await idbAll(ctx.db, ctx.targetStore);
        const latest = messages
          .slice()
          .sort((a, b) => (b.timeval || b.date || 0) - (a.timeval || a.date || 0))[0];
        if (!latest) return { ok: false, reason: "target store is empty" };
        const latestId = String(latest.id || latest.msgid || latest.key || "");
        return {
          ok: latestId !== ctx.beforeTargetLatestId && String(latest.scode) === ctx.currentUserCode,
          latest: {
            id: latestId,
            scode: latest.scode,
            sname: latest.sname,
            type: latest.body?.type,
            content: latest.body?.content,
            fname: latest.body?.fname,
            timeval: latest.timeval || latest.date,
            sendStatus: latest.extUI?.sendStatus
          },
          beforeTargetLatestId: ctx.beforeTargetLatestId
        };
      }

      const startedAt = new Date().toISOString();
      const ctx = await resolveContext();
      const summary = {
        startedAt,
        source: ctx.source,
        target: ctx.target,
        sourceStore: ctx.sourceStore,
        targetStore: ctx.targetStore,
        latest: ctx.latest,
        targetLatest: ctx.targetLatest,
        send: SHOULD_SEND
      };

      if (!SHOULD_SEND) return { ok: true, mode: "dry-run", ...summary };

      const selected = await selectSourceChat(ctx.source.name);
      if (!selected.ok) return { ok: false, step: "select-source", selected, ...summary };
      await scrollChatToBottom();
      const messageEl = findMessageElement(ctx.latest.id, ctx.latest);
      if (!messageEl) return { ok: false, step: "find-message-dom", selected, ...summary };
      const dialog = await openForwardDialog(messageEl);
      await chooseTargetAndSend(dialog, ctx.target);
      const validation = await validate(ctx);
      return { ok: validation.ok, mode: "send", selected, validation, ...summary };
    })()
  `;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help || !args.from || !args.to || (!args.send && !args.dryRun)) {
    usage();
    process.exit(args.help ? 0 : 2);
  }

  const port = args.port || await readDevtoolsPort();
  const client = await connect(port);
  try {
    const result = await client.call("Runtime.evaluate", {
      expression: buildPageScript({ from: args.from, to: args.to, send: args.send }),
      awaitPromise: true,
      returnByValue: true
    });
    if (result.exceptionDetails) {
      console.error(JSON.stringify(result.exceptionDetails, null, 2));
      process.exit(1);
    }
    const value = result.result?.value || result;
    console.log(JSON.stringify(value, null, 2));
    if (!value.ok) process.exitCode = 1;
  } finally {
    client.close();
  }
}

main().catch((error) => {
  console.error(error.stack || error.message || String(error));
  process.exit(1);
});
