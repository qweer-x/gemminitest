// ==UserScript==
// @name         Chat-to-Codebase AUTO_SYNC
// @namespace    https://github.com/qweer-x/chat-to-codebase
// @version      1.3.1
// @description  Capture AUTO_SYNC blocks from ChatGPT and send them to a local Chat-to-Codebase bridge server.
// @author       qweer-x
// @match        https://chatgpt.com/*
// @match        https://chat.openai.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_addStyle
// @grant        GM_getValue
// @grant        GM_setValue
// @connect      127.0.0.1
// @connect      localhost
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    const LOCAL_SYNC_URL = 'http://127.0.0.1:9999/sync';

    const START_MARK = '###=== AUTO' + '_SYNC ===###';
    const END_MARK = '###=== END' + '_SYNC ===###';

    const SCAN_INTERVAL_MS = 1500;
    const MAX_SAVED_HASHES = 500;
    const PANEL_ID = 'chat-to-codebase-panel';
    const STATUS_ID = 'chat-to-codebase-status';

    let enabled = GM_getValue('autoSyncEnabled', true);
    let sentHashes = new Set(GM_getValue('sentHashes', []));

    function hashText(text) {
        let h1 = 0xdeadbeef ^ text.length;
        let h2 = 0x41c6ce57 ^ text.length;

        for (let i = 0; i < text.length; i++) {
            const ch = text.charCodeAt(i);
            h1 = Math.imul(h1 ^ ch, 2654435761);
            h2 = Math.imul(h2 ^ ch, 1597334677);
        }

        h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
        h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);

        return String(4294967296 * (2097151 & h2) + (h1 >>> 0));
    }

    function saveSentHash(hash) {
        sentHashes.add(hash);

        let arr = Array.from(sentHashes);

        if (arr.length > MAX_SAVED_HASHES) {
            arr = arr.slice(arr.length - MAX_SAVED_HASHES);
            sentHashes = new Set(arr);
        }

        GM_setValue('sentHashes', arr);
    }

    function extractSyncBlocks(text) {
        const blocks = [];

        if (!text || !text.includes(START_MARK)) {
            return blocks;
        }

        let searchFrom = 0;

        while (true) {
            const startIndex = text.indexOf(START_MARK, searchFrom);

            if (startIndex === -1) {
                break;
            }

            const endIndex = text.indexOf(END_MARK, startIndex);

            if (endIndex === -1) {
                break;
            }

            const blockEnd = endIndex + END_MARK.length;
            const block = text.slice(startIndex, blockEnd).trim();

            if (block.includes('FILE:')) {
                blocks.push(block);
            }

            searchFrom = blockEnd;
        }

        return blocks;
    }

    function getLatestAssistantMessageRoot() {
        const assistantNodes = Array.from(
            document.querySelectorAll('[data-message-author-role="assistant"]')
        );

        if (assistantNodes.length > 0) {
            return assistantNodes[assistantNodes.length - 1];
        }

        const articles = Array.from(document.querySelectorAll('article'));

        if (articles.length > 0) {
            return articles[articles.length - 1];
        }

        return document.querySelector('main') || document.body;
    }

    function collectCandidateTexts() {
        const root = getLatestAssistantMessageRoot();
        const texts = new Set();

        if (!root) {
            return [];
        }

        const codeLikeNodes = Array.from(root.querySelectorAll('pre, code'));

        for (const node of codeLikeNodes) {
            const text = node.innerText || node.textContent || '';

            if (text.includes(START_MARK)) {
                texts.add(text);
            }
        }

        const fullText = root.innerText || root.textContent || '';

        if (fullText.includes(START_MARK)) {
            texts.add(fullText);
        }

        return Array.from(texts);
    }

    function sendBlockToLocal(block) {
        const hash = hashText(block);

        if (sentHashes.has(hash)) {
            updatePanel('已跳过重复块');
            return;
        }

        updatePanel('发现同步块，正在发送...');

        GM_xmlhttpRequest({
            method: 'POST',
            url: LOCAL_SYNC_URL,
            headers: {
                'Content-Type': 'text/plain; charset=utf-8'
            },
            data: block,
            timeout: 10000,

            onload: function (response) {
                if (response.status >= 200 && response.status < 300) {
                    saveSentHash(hash);
                    updatePanel('同步成功：HTTP ' + response.status);
                    console.log('[Chat-to-Codebase] 同步成功:', response.responseText);
                } else {
                    updatePanel('同步失败：HTTP ' + response.status);
                    console.error('[Chat-to-Codebase] 同步失败:', response.status, response.responseText);
                }
            },

            onerror: function (error) {
                updatePanel('连接失败：请检查本地 9999 服务');
                console.error('[Chat-to-Codebase] 请求错误:', error);
            },

            ontimeout: function () {
                updatePanel('请求超时：请检查本地服务');
                console.error('[Chat-to-Codebase] 请求超时');
            }
        });
    }

    function scanLatestMessage() {
        if (!enabled) {
            return;
        }

        const candidateTexts = collectCandidateTexts();

        for (const text of candidateTexts) {
            const blocks = extractSyncBlocks(text);

            for (const block of blocks) {
                sendBlockToLocal(block);
            }
        }
    }

    function createPanel() {
        if (document.getElementById(PANEL_ID)) {
            return;
        }

        GM_addStyle(`
            #${PANEL_ID} {
                position: fixed;
                right: 16px;
                bottom: 16px;
                z-index: 999999;
                width: 280px;
                padding: 10px;
                border-radius: 10px;
                background: rgba(32, 33, 35, 0.94);
                color: #fff;
                font-size: 13px;
                font-family: Arial, sans-serif;
                box-shadow: 0 4px 18px rgba(0, 0, 0, 0.28);
                user-select: none;
            }

            #${PANEL_ID} .title {
                font-weight: bold;
                margin-bottom: 6px;
            }

            #${PANEL_ID} .status {
                margin-bottom: 8px;
                line-height: 1.4;
                color: #d7d7d7;
                word-break: break-word;
            }

            #${PANEL_ID} .buttons {
                display: flex;
                gap: 6px;
                flex-wrap: wrap;
            }

            #${PANEL_ID} button {
                cursor: pointer;
                border: none;
                border-radius: 6px;
                padding: 5px 8px;
                font-size: 12px;
                background: #3b82f6;
                color: #fff;
            }

            #${PANEL_ID} button.secondary {
                background: #4b5563;
            }

            #${PANEL_ID} button.danger {
                background: #dc2626;
            }
        `);

        const panel = document.createElement('div');
        panel.id = PANEL_ID;

        panel.innerHTML = `
            <div class="title">Chat-to-Codebase</div>
            <div class="status" id="${STATUS_ID}">状态：${enabled ? '已启用' : '已暂停'}</div>
            <div class="buttons">
                <button id="chatgpt-auto-sync-toggle">${enabled ? '暂停' : '启用'}</button>
                <button class="secondary" id="chatgpt-auto-sync-scan">重扫最新</button>
                <button class="danger" id="chatgpt-auto-sync-clear">清缓存</button>
            </div>
        `;

        document.body.appendChild(panel);

        document.getElementById('chatgpt-auto-sync-toggle').addEventListener('click', function () {
            enabled = !enabled;
            GM_setValue('autoSyncEnabled', enabled);

            this.textContent = enabled ? '暂停' : '启用';
            updatePanel(enabled ? '已启用，等待同步块' : '已暂停');
        });

        document.getElementById('chatgpt-auto-sync-scan').addEventListener('click', function () {
            updatePanel('手动扫描最新回复...');
            scanLatestMessage();
        });

        document.getElementById('chatgpt-auto-sync-clear').addEventListener('click', function () {
            sentHashes = new Set();
            GM_setValue('sentHashes', []);
            updatePanel('已清空同步缓存');
        });
    }

    function updatePanel(message) {
        const status = document.getElementById(STATUS_ID);

        if (status) {
            status.textContent = '状态：' + message;
        }
    }

    function start() {
        createPanel();

        setInterval(function () {
            scanLatestMessage();
        }, SCAN_INTERVAL_MS);

        updatePanel(enabled ? '已启用，等待同步块' : '已暂停');
        console.log('[Chat-to-Codebase] Tampermonkey bridge 已启动');
    }

    start();
})();