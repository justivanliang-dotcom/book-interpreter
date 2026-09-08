/* 语音朗读引擎：优先使用豆包（火山引擎）在线自然女声，失败自动回退浏览器语音。
 * 服务器模式：按批预取 mp3 音频，Audio 逐句播放并高亮；回退模式：
 * 逐句调用 speechSynthesis，天然规避 Chrome 长文本截断问题。
 */
(function () {
  var supported = typeof window !== 'undefined' && 'speechSynthesis' in window;
  var runId = 0;
  var voices = [];
  // null=未知，true=豆包可用，false=不可用
  var serverAvailable = null;

  if (supported) {
    refreshVoices();
    if (window.speechSynthesis.onvoiceschanged !== undefined) {
      window.speechSynthesis.onvoiceschanged = refreshVoices;
    }
  }

  // 加载时即探测后端豆包语音，点击朗读时通常已就绪
  probeServer(function () {});

  function refreshVoices() {
    try { voices = window.speechSynthesis.getVoices() || []; } catch (e) { voices = []; }
  }

  // 自然女声偏好列表（按名字关键词匹配，微软 Edge 的晓晓/晓伊等是自然音）。
  // 只在普通话（zh-CN）里挑选，绝不选粤语/台湾（zh-HK/zh-TW），保证朗读统一普通话
  var FEMALE_HINTS = ['xiaoxiao', 'xiaoyi', 'yaoyao', 'huihui', 'meijia', 'tingting', 'female'];
  function pickVoice() {
    var zhCN = voices.filter(function (v) { return /^zh-cn/i.test(v.lang || ''); });
    if (!zhCN.length) return null;
    for (var i = 0; i < FEMALE_HINTS.length; i++) {
      var hit = zhCN.filter(function (v) {
        return (v.name || '').toLowerCase().indexOf(FEMALE_HINTS[i]) >= 0;
      })[0];
      if (hit) return hit;
    }
    return zhCN[0];
  }

  function probeServer(cb) {
    if (serverAvailable !== null) return cb(serverAvailable);
    if (typeof window === 'undefined' || !window.fetch) {
      serverAvailable = false;
      return cb(false);
    }
    window.fetch('/api/tts/status')
      .then(function (r) { return r.json(); })
      .then(function (d) { serverAvailable = !!(d && d.available); cb(serverAvailable); })
      .catch(function () { serverAvailable = false; cb(false); });
  }

  // 朗读前清除 markdown 语法符号（** 加粗、* 斜体、` 代码、# 标题、[]() 链接、列表符号等），
  // 避免语音引擎把符号读成"星号"等
  function cleanText(text) {
    if (!text) return text;
    return String(text)
      .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
      .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
      .replace(/`([^`]*)`/g, '$1')
      .replace(/\*\*([^*]+)\*\*/g, '$1')
      .replace(/\*([^*]+)\*/g, '$1')
      .replace(/__([^_]+)__/g, '$1')
      .replace(/_([^_]+)_/g, '$1')
      .replace(/~~([^~]+)~~/g, '$1')
      .replace(/^\s{0,3}#{1,6}\s+/gm, '')
      .replace(/^\s*>\s?/gm, '')
      .replace(/^\s*[-+*]\s+/gm, '')
      .replace(/^\s*\d+[.)]\s+/gm, '')
      .replace(/[`*_~]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function normItems(sentences) {
    return (sentences || [])
      .map(function (s) { return typeof s === 'string' ? s : (s && s.text ? s.text : ''); })
      .map(cleanText)
      .filter(function (t) { return t && t.trim(); });
  }

  // ---------- 浏览器语音回退（逐句推进） ----------
  function browserSpeakFrom(items, start, opts) {
    if (!supported) {
      if (opts.onUnsupported) opts.onUnsupported();
      return;
    }
    var id = ++runId;
    var i = start;
    var voice = pickVoice();
    if (opts.onStart) opts.onStart(i);
    step();

    function step() {
      if (id !== runId) return;
      if (i >= items.length) {
        if (opts.onEnd) opts.onEnd();
        return;
      }
      if (opts.onProgress) opts.onProgress(i);
      var u = new SpeechSynthesisUtterance(items[i]);
      if (voice) {
        u.voice = voice;
        u.lang = voice.lang;
      } else {
        u.lang = 'zh-CN';
      }
      u.rate = 1.0;
      u.pitch = 1.0;
      u.onend = function () {
        if (id !== runId) return;
        i++;
        step();
      };
      u.onerror = function () {
        if (id !== runId) return;
        if (opts.onEnd) opts.onEnd();
      };
      window.speechSynthesis.speak(u);
    }
  }

  // ---------- 豆包在线语音（Audio 播放） ----------
  var BATCH_SIZE = 8;
  var audio = null;
  var pending = {}; // 批次起始索引 -> Promise<blobUrl[]>
  var serverRun = null;

  function ensureAudio() {
    if (!audio) {
      audio = new Audio();
      audio.preload = 'auto';
    }
    return audio;
  }

  function base64ToBlobUrl(b64) {
    var bin = atob(b64);
    var u8 = new Uint8Array(bin.length);
    for (var k = 0; k < bin.length; k++) u8[k] = bin.charCodeAt(k);
    var blob = new Blob([u8], { type: 'audio/mpeg' });
    return URL.createObjectURL(blob);
  }

  function prefetch(items, start) {
    for (var i = start; i < items.length; i += BATCH_SIZE) {
      if (pending[i] !== undefined) continue;
      (function (from) {
        var slice = items.slice(from, from + BATCH_SIZE);
        pending[from] = window.fetch('/api/tts/batch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ texts: slice })
        }).then(function (r) {
          if (!r.ok) throw new Error('tts batch http ' + r.status);
          return r.json();
        }).then(function (data) {
          return (data.audios || []).map(base64ToBlobUrl);
        });
      })(i);
    }
  }

  function getAudio(i, start) {
    var from = start + Math.floor((i - start) / BATCH_SIZE) * BATCH_SIZE;
    var p = pending[from];
    if (!p) return Promise.reject(new Error('no prefetch'));
    return p.then(function (urls) {
      var idx = i - from;
      if (idx < 0 || idx >= urls.length) throw new Error('prefetch idx out of range');
      return urls[idx];
    });
  }

  function speakServer(items, start, opts) {
    var id = ++runId;
    var el = ensureAudio();
    el.pause();
    el.removeAttribute('src');
    var run = { id: id, items: items, start: start, idx: start, failed: false };
    serverRun = run;
    if (opts.onStart) opts.onStart(start);
    prefetch(items, start);
    playServer(run, opts);
  }

  function playServer(run, opts) {
    if (serverRun !== run || run.failed) return;
    if (run.idx >= run.items.length) {
      serverRun = null;
      if (opts.onEnd) opts.onEnd();
      return;
    }
    var i = run.idx;
    if (opts.onProgress) opts.onProgress(i);
    getAudio(i, run.start).then(function (url) {
      if (serverRun !== run || run.failed) return;
      var el = ensureAudio();
      el.onended = function () {
        URL.revokeObjectURL(url);
        if (serverRun === run) {
          run.idx++;
          playServer(run, opts);
        }
      };
      el.onerror = function () {
        URL.revokeObjectURL(url);
        if (serverRun === run) {
          run.idx++;
          playServer(run, opts);
        }
      };
      el.src = url;
      el.play().catch(function () {
        URL.revokeObjectURL(url);
        if (serverRun === run) {
          run.idx++;
          playServer(run, opts);
        }
      });
    }, function () {
      // 预取失败 → 整体回退浏览器语音（从当前句开始）
      if (serverRun !== run || run.failed) return;
      run.failed = true;
      serverRun = null;
      browserSpeakFrom(run.items, run.idx, opts);
    });
  }

  function speakFrom(sentences, start, opts) {
    opts = opts || {};
    stop();
    var items = normItems(sentences);
    if (!items.length) return;
    if (start < 0 || start >= items.length) start = 0;
    if (serverAvailable === true) {
      speakServer(items, start, opts);
    } else {
      // 未探测完成或后端不可用：浏览器语音
      browserSpeakFrom(items, start, opts);
    }
  }

  function stop() {
    runId++;
    if (audio) {
      audio.pause();
      audio.removeAttribute('src');
      audio.onended = null;
      audio.onerror = null;
    }
    serverRun = null;
    pending = {};
    if (supported) window.speechSynthesis.cancel();
  }

  window.TTS = {
    speakFrom: speakFrom,
    stop: stop,
    supported: supported,
    pickVoice: pickVoice,
    probeServer: probeServer
  };
})();
