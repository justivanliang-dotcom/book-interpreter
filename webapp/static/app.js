(function () {
  var state = {
    bookId: null,
    chapters: [],
    interpreting: false,
    chapterRatios: {},
    chapterSummaries: {},
    chapterPlain: {},
    chapterMeta: {}
  };

  var $ = function (id) { return document.getElementById(id); };
  var fileInput = $('file-input');
  var uploadBtn = $('upload-btn');
  var uploadStatus = $('upload-status');
  var bookCard = $('book-card');
  var bookTitle = $('book-title');
  var bookFilename = $('book-filename');
  var chapterList = $('chapter-list');
  var interpretBtn = $('interpret-btn');
  var emptyState = $('empty-state');
  var savedBooks = $('saved-books');
  var bookList = $('book-list');
  var report = $('report');
  var overview = $('overview');
  var keyPoints = $('key-points');
  var quotes = $('quotes');
  var qaCard = $('qa-card');
  var questionInput = $('question-input');
  var askBtn = $('ask-btn');
  var answer = $('answer');
  var sourcePanel = $('source-panel');
  var sourceBody = $('source-body');
  var sourceClose = $('source-close');

  function setStatus(msg, isError) {
    uploadStatus.textContent = msg || '';
    uploadStatus.className = 'status' + (isError ? ' error' : '');
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  async function api(url, options) {
    options = options || {};
    options.headers = Object.assign({}, options.headers, {
      'X-Access-Token': localStorage.getItem('book_interpreter_token') || ''
    });
    var resp;
    try {
      resp = await fetch(url, options);
    } catch (e) {
      throw new Error('网络连接失败，请检查服务是否运行或网络是否正常');
    }
    if (resp.status === 401 && url.indexOf('/api/auth/verify') === -1) {
      var authed = await ensureToken();
      if (authed) return api(url, options);
      throw new Error('访问口令不正确');
    }
    if (!resp.ok) {
      var detail = '';
      try {
        var err = await resp.json();
        detail = err.detail || '';
      } catch (e) { /* ignore */ }
      if (!detail) {
        try { detail = await resp.text(); } catch (e) { /* ignore */ }
      }
      throw new Error(detail || ('请求失败（HTTP ' + resp.status + '）'));
    }
    return resp.json();
  }

  var authOverlay = null;
  function ensureToken() {
    return new Promise(function (resolve) {
      if (authOverlay) {
        resolve(false);
        return;
      }
      authOverlay = document.createElement('div');
      authOverlay.className = 'auth-overlay';
      var card = document.createElement('div');
      card.className = 'auth-card';
      var title = document.createElement('div');
      title.className = 'auth-title';
      title.textContent = '请输入访问口令';
      var input = document.createElement('input');
      input.type = 'password';
      input.className = 'auth-input';
      input.placeholder = '访问口令';
      var error = document.createElement('div');
      error.className = 'auth-error';
      error.hidden = true;
      var row = document.createElement('div');
      row.className = 'auth-row';
      var cancel = document.createElement('button');
      cancel.className = 'btn ghost small';
      cancel.textContent = '取消';
      var confirm = document.createElement('button');
      confirm.className = 'btn primary small';
      confirm.textContent = '进入';
      row.appendChild(cancel);
      row.appendChild(confirm);
      card.appendChild(title);
      card.appendChild(input);
      card.appendChild(error);
      card.appendChild(row);
      authOverlay.appendChild(card);
      document.body.appendChild(authOverlay);
      input.focus();

      function finish(ok) {
        document.body.removeChild(authOverlay);
        authOverlay = null;
        resolve(ok);
      }
      function submit() {
        var token = input.value.trim();
        if (!token) return;
        fetch('/api/auth/verify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: token })
        }).then(function (r) {
          if (r.ok) {
            localStorage.setItem('book_interpreter_token', token);
            finish(true);
          } else {
            error.textContent = '口令错误，请重新输入';
            error.hidden = false;
            input.value = '';
            input.focus();
          }
        }).catch(function () {
          error.textContent = '验证失败，请检查网络';
          error.hidden = false;
        });
      }
      confirm.addEventListener('click', submit);
      cancel.addEventListener('click', function () { finish(false); });
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') submit();
      });
    });
  }

  function renderBook(book) {
    state.bookId = book.id;
    state.chapters = book.chapters;
    state.chapterRatios = {};
    state.chapterSummaries = {};
    state.chapterPlain = {};
    state.chapterMeta = {};
    book.chapters.forEach(function (ch, i) {
      state.chapterMeta[i] = {
        has_summary: !!ch.has_summary,
        summary_ratio: ch.summary_ratio != null ? Number(ch.summary_ratio) : null,
        has_plain: !!ch.has_plain,
        plain_ratio: ch.plain_ratio != null ? Number(ch.plain_ratio) : null
      };
    });
    bookTitle.textContent = book.title;
    bookFilename.textContent = book.filename;
    chapterList.innerHTML = '';
    book.chapters.forEach(function (ch, i) {
      chapterList.appendChild(buildChapterItem(i, ch.title, state.chapterMeta[i]));
    });
    bookCard.hidden = false;
    emptyState.hidden = true;
    savedBooks.hidden = true;
    report.hidden = true;
    qaCard.hidden = true;
    interpretBtn.disabled = false;
    answer.className = 'answer';
    questionInput.value = '';
  }

  // ---------- 已上传书籍恢复 ----------

  function renderBookList(items) {
    bookList.innerHTML = '';
    if (!items.length) {
      savedBooks.hidden = true;
      emptyState.hidden = false;
      return;
    }
    items.forEach(function (item) {
      var li = document.createElement('li');
      li.className = 'book-list-item';
      var name = document.createElement('span');
      name.className = 'book-list-title';
      name.textContent = item.title;
      var meta = document.createElement('span');
      meta.className = 'book-list-meta';
      meta.textContent = item.filename + ' · ' + item.chapters.length + ' 章';
      var del = document.createElement('span');
      del.className = 'book-list-del';
      del.textContent = '✕';
      del.title = '删除该书';
      del.addEventListener('click', function (e) {
        e.stopPropagation();
        deleteBook(item.id, item.title);
      });
      li.appendChild(name);
      li.appendChild(meta);
      li.appendChild(del);
      li.addEventListener('click', function () { openSavedBook(item); });
      bookList.appendChild(li);
    });
    savedBooks.hidden = false;
    emptyState.hidden = !!state.bookId;
  }

  function deleteBook(bookId, title) {
    var confirmed = true;
    if (window.confirm) {
      confirmed = window.confirm('删除《' + title + '》？该书的浓缩与讲解记录将一并清除，此操作不可恢复。');
    }
    if (!confirmed) return;
    api('/api/books/' + bookId, { method: 'DELETE' })
      .then(function () {
        if (state.bookId === bookId) {
          // 删除的是当前打开的书：重置视图并清除"上次打开"记录
          localStorage.removeItem('book_interpreter_last');
          state.bookId = null;
          state.chapters = [];
          bookCard.hidden = true;
          report.hidden = true;
          qaCard.hidden = true;
          interpretBtn.disabled = true;
        }
        loadSavedBooks();
      })
      .catch(function (err) {
        setStatus(err.message, true);
      });
  }

  function openSavedBook(item) {
    localStorage.setItem('book_interpreter_last', item.id);
    renderBook(item);
    savedBooks.hidden = false; // 保留列表，方便切换其他已上传书籍
  }

  function loadSavedBooks() {
    api('/api/books')
      .then(function (items) {
        renderBookList(items);
        var lastId = localStorage.getItem('book_interpreter_last');
        var last = null;
        if (lastId) {
          for (var i = 0; i < items.length; i++) {
            if (items[i].id === lastId) { last = items[i]; break; }
          }
        }
        if (last && last.id !== state.bookId) {
          openSavedBook(last);
        } else if (items.length === 1 && items[0].id !== state.bookId) {
          openSavedBook(items[0]);
        }
      })
      .catch(function () { /* 加载失败保持空状态 */ });
  }

  function buildChapterItem(index, title, meta) {
    meta = meta || {};
    var li = document.createElement('li');
    li.className = 'chapter-item';
    li.dataset.index = String(index);

    var head = document.createElement('div');
    head.className = 'chapter-head';
    head.textContent = title;
    head.addEventListener('click', function () { toggleChapter(index); });

    var expand = document.createElement('div');
    expand.className = 'chapter-expand';
    expand.hidden = true;

    var ratioRow = document.createElement('div');
    ratioRow.className = 'ratio-row';
    var label = document.createElement('label');
    label.textContent = '浓缩比例';
    var select = document.createElement('select');
    select.className = 'chapter-ratio';
    var defaultRatio = meta.summary_ratio != null ? meta.summary_ratio : 0.1;
    [0.05, 0.1, 0.25, 0.5, 0.75, 1].forEach(function (v) {
      var opt = document.createElement('option');
      opt.value = String(v);
      opt.textContent = Math.round(v * 100) + '%';
      if (v === defaultRatio) opt.selected = true;
      select.appendChild(opt);
    });
    var btn = document.createElement('button');
    btn.className = 'btn primary small summarize-btn';
    btn.textContent = '浓缩本章';
    ratioRow.appendChild(label);
    ratioRow.appendChild(select);
    ratioRow.appendChild(btn);

    var plainBtn = document.createElement('button');
    plainBtn.className = 'btn plain small plain-btn';
    plainBtn.textContent = '大白话讲解';
    ratioRow.appendChild(plainBtn);

    var summaryBox = document.createElement('div');
    summaryBox.className = 'chapter-summary';

    var progressWrap = document.createElement('div');
    progressWrap.className = 'progress-wrap';
    progressWrap.hidden = true;
    var progressBar = document.createElement('div');
    progressBar.className = 'progress-bar';
    progressWrap.appendChild(progressBar);

    var plainBox = document.createElement('div');
    plainBox.className = 'chapter-plain';
    plainBox.hidden = true;

    expand.appendChild(ratioRow);
    expand.appendChild(progressWrap);
    expand.appendChild(summaryBox);
    expand.appendChild(plainBox);

    select.addEventListener('change', function () {
      state.chapterRatios[index] = parseFloat(select.value);
    });
    btn.addEventListener('click', function () { condenseChapter(index); });
    plainBtn.addEventListener('click', function () { explainPlain(index); });

    li.appendChild(head);
    li.appendChild(expand);
    return li;
  }

  function toggleChapter(index) {
    var li = chapterList.querySelector('li[data-index="' + index + '"]');
    if (!li) return;
    var expand = li.querySelector('.chapter-expand');
    expand.hidden = !expand.hidden;
    if (expand.hidden) return;
    restoreChapterCaches(index);
    // 展开时显示已有缓存；restoreChapterCaches 会异步拉取落盘缓存
    var summaryBox = li.querySelector('.chapter-summary');
    var cached = state.chapterSummaries[index];
    if (cached) {
      renderSummary(summaryBox, cached, index, cached.ratio);
    } else {
      summaryBox.innerHTML = '<div class="hint">点击「浓缩本章」生成浓缩内容</div>';
    }
    var plainBox = li.querySelector('.chapter-plain');
    var ratio = parseFloat(li.querySelector('.chapter-ratio').value);
    var cacheKey = index + ':' + ratio;
    var cachedPlain = state.chapterPlain[cacheKey];
    if (cachedPlain) {
      renderPlain(plainBox, cachedPlain, index, ratio);
    } else {
      plainBox.hidden = true;
      plainBox.innerHTML = '';
    }
  }

  // 重新打开书后，展开章节时自动拉取上次落盘的浓缩/讲解缓存（命中后端缓存，秒回）
  function restoreChapterCaches(index) {
    var meta = state.chapterMeta[index];
    if (!meta) return;
    if (meta.has_summary && !state.chapterSummaries[index]) {
      condenseChapterAt(index, meta.summary_ratio);
    }
    if (meta.has_plain && !state.chapterPlain[index + ':' + meta.plain_ratio]) {
      explainPlainAt(index, meta.plain_ratio);
    }
  }

  // 朗读浮动条（全局唯一）
  var speakBar = document.createElement('div');
  speakBar.className = 'speak-bar';
  speakBar.hidden = true;
  var sbText = document.createElement('span');
  sbText.textContent = '正在朗读…';
  var sbStop = document.createElement('button');
  sbStop.className = 'btn ghost small';
  sbStop.textContent = '停止';
  sbStop.addEventListener('click', stopSpeak);
  speakBar.appendChild(sbText);
  speakBar.appendChild(sbStop);
  document.body.appendChild(speakBar);

  function showSpeakBar() { speakBar.hidden = false; }
  function hideSpeakBar() { speakBar.hidden = true; }

  function clearSpeakHighlight() {
    var all = document.querySelectorAll('.sentence-wrap.speaking');
    all.forEach(function (a) { a.classList.remove('speaking'); });
  }

  function stopSpeak() {
    if (window.TTS) window.TTS.stop();
    hideSpeakBar();
    clearSpeakHighlight();
  }

  // 从第 startIndex 句开始朗读整组句子，逐句高亮
  function speakSentences(wraps, startIndex) {
    if (!window.TTS || !window.TTS.supported) return;
    stopSpeak();
    var texts = wraps.map(function (w) {
      var s = w.querySelector('.summary-sentence');
      return s ? s.textContent : '';
    });
    showSpeakBar();
    window.TTS.speakFrom(texts, startIndex, {
      onProgress: function (i) {
        clearSpeakHighlight();
        if (wraps[i]) wraps[i].classList.add('speaking');
      },
      onEnd: stopSpeak
    });
  }

  // 长按句子弹出"朗读"菜单；长按 500ms 触发，触发后拦截随后的 click
  var LONG_PRESS_MS = 500;
  function attachLongPress(el, onLongPress) {
    var timer = null;
    var triggered = false;
    var sx = 0;
    var sy = 0;
    function cancel() {
      if (timer) { clearTimeout(timer); timer = null; }
    }
    function start(e) {
      triggered = false;
      var t = e.touches && e.touches[0];
      sx = t ? t.clientX : (e.clientX || 0);
      sy = t ? t.clientY : (e.clientY || 0);
      cancel();
      timer = setTimeout(function () {
        timer = null;
        triggered = true;
        onLongPress();
      }, LONG_PRESS_MS);
    }
    function move(e) {
      var t = e.touches && e.touches[0];
      var x = t ? t.clientX : (e.clientX || 0);
      var y = t ? t.clientY : (e.clientY || 0);
      if (Math.abs(x - sx) > 10 || Math.abs(y - sy) > 10) cancel();
    }
    el.addEventListener('mousedown', start);
    el.addEventListener('touchstart', start, { passive: true });
    el.addEventListener('mousemove', move);
    el.addEventListener('touchmove', move, { passive: true });
    el.addEventListener('mouseup', cancel);
    el.addEventListener('mouseleave', cancel);
    el.addEventListener('touchend', cancel);
    el.addEventListener('touchcancel', cancel);
    el.addEventListener('click', function (e) {
      if (triggered) {
        e.preventDefault();
        e.stopPropagation();
        triggered = false;
      }
    });
  }

  // 长按后的朗读选项菜单
  var speakMenu = null;
  function showSpeakMenu(anchor, text, onSpeak) {
    hideSpeakMenu();
    var menu = document.createElement('div');
    menu.className = 'speak-menu';
    var preview = document.createElement('div');
    preview.className = 'speak-menu-preview';
    preview.textContent = '「' + text + '」';
    var row = document.createElement('div');
    row.className = 'speak-menu-row';
    var speakBtn = document.createElement('button');
    speakBtn.className = 'btn primary small';
    speakBtn.textContent = '朗读';
    var cancelBtn = document.createElement('button');
    cancelBtn.className = 'btn ghost small';
    cancelBtn.textContent = '取消';
    speakBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      hideSpeakMenu();
      onSpeak();
    });
    cancelBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      hideSpeakMenu();
    });
    row.appendChild(speakBtn);
    row.appendChild(cancelBtn);
    menu.appendChild(preview);
    menu.appendChild(row);
    document.body.appendChild(menu);
    speakMenu = menu;
    var rect = anchor.getBoundingClientRect();
    var mw = menu.offsetWidth || 240;
    var vw = window.innerWidth || 800;
    var left = Math.max(8, Math.min(vw - mw - 8, rect.left));
    menu.style.left = left + 'px';
    menu.style.top = (rect.bottom + 6) + 'px';
  }
  function hideSpeakMenu() {
    if (speakMenu && speakMenu.parentNode) speakMenu.parentNode.removeChild(speakMenu);
    speakMenu = null;
  }
  document.addEventListener('click', hideSpeakMenu);

  // 构建句子元素：单击由 onTextClick 处理（如查看原文），长按弹出朗读菜单
  function buildSentenceWrap(text, onTextClick, index, wraps) {
    var wrap = document.createElement('span');
    wrap.className = 'sentence-wrap';
    var span = document.createElement('span');
    span.className = 'summary-sentence';
    span.textContent = text;
    if (onTextClick) {
      span.addEventListener('click', function () { onTextClick(span); });
    }
    attachLongPress(span, function () {
      showSpeakMenu(span, text, function () { speakSentences(wraps, index); });
    });
    wrap.appendChild(span);
    return wrap;
  }

  // 大白话讲解拆句：按标点拆句，保留段落信息
  function splitPlainSentences(text) {
    var paras = String(text || '').split(/\n+/).filter(function (p) { return p.trim(); });
    var out = [];
    paras.forEach(function (p, pi) {
      var segs = String(p).match(/[^。！？；…]+[。！？；…]?/g) || [];
      segs.forEach(function (seg) {
        var t = String(seg).trim();
        if (t) out.push({ text: t, para: pi });
      });
    });
    return out;
  }

  function renderSummary(container, data, index, ratio) {
    container.innerHTML = '';
    if (data.target_words && data.word_count) {
      var meta = document.createElement('div');
      meta.className = 'summary-meta';
      var pct = Math.round(data.word_count / data.target_words * 100);
      meta.textContent = '实际 ' + data.word_count + ' 字 / 目标 ' + data.target_words + ' 字（' + pct + '%）';
      container.appendChild(meta);
    }
    if (index != null && ratio != null) {
      var toolRow = document.createElement('div');
      toolRow.className = 'regen-row';
      var regenBtn = document.createElement('button');
      regenBtn.className = 'btn ghost small regen-btn';
      regenBtn.textContent = '重新生成';
      regenBtn.addEventListener('click', function () { condenseChapterAt(index, ratio, true); });
      toolRow.appendChild(regenBtn);
      container.appendChild(toolRow);
    }
    var sentences = data.sentences;
    if (sentences && sentences.length) {
      var lastPara = null;
      var wraps = [];
      sentences.forEach(function (s, i) {
        if (lastPara !== null && s.para !== lastPara) {
          container.appendChild(document.createElement('br'));
          container.appendChild(document.createElement('br'));
        }
        lastPara = s.para;
        var wrap = buildSentenceWrap(s.text, function (span) { showSource(s, span); }, i, wraps);
        wraps.push(wrap);
        container.appendChild(wrap);
        container.appendChild(document.createTextNode(' '));
      });
    } else if (data.summary) {
      // 100% 浓缩等场景后端不拆句：前端按标点拆句，确保可长按朗读
      var plainWraps = [];
      var plainSents = splitPlainSentences(data.summary);
      var lastPlainPara = null;
      plainSents.forEach(function (s, i) {
        if (lastPlainPara !== null && s.para !== lastPlainPara) {
          container.appendChild(document.createElement('br'));
          container.appendChild(document.createElement('br'));
        }
        lastPlainPara = s.para;
        var w = buildSentenceWrap(s.text, null, i, plainWraps);
        plainWraps.push(w);
        container.appendChild(w);
        container.appendChild(document.createTextNode(' '));
      });
    }
  }

  function showSource(s, el) {
    var all = document.querySelectorAll('.summary-sentence.active');
    all.forEach(function (a) { a.classList.remove('active'); });
    el.classList.add('active');
    if (s.context) {
      var html = escapeHtml(s.context);
      if (s.highlight) {
        var hl = escapeHtml(s.highlight);
        if (hl) {
          html = html.split(hl).join('<mark>' + hl + '</mark>');
        }
      }
      sourceBody.innerHTML = html;
    } else {
      sourceBody.textContent = s.source || '（该句未找到对应原文）';
    }
    sourcePanel.hidden = false;
  }

  function closeSource() {
    sourcePanel.hidden = true;
    var all = document.querySelectorAll('.summary-sentence.active');
    all.forEach(function (a) { a.classList.remove('active'); });
  }

  sourceClose.addEventListener('click', closeSource);

  // 点击面板外部（非句子、非面板）时立即关闭原文面板
  document.addEventListener('click', function (e) {
    if (sourcePanel.hidden) return;
    if (sourcePanel.contains(e.target)) return;
    if (e.target.classList && e.target.classList.contains('summary-sentence')) return;
    closeSource();
  });

  function condenseChapter(index) {
    var li = chapterList.querySelector('li[data-index="' + index + '"]');
    if (!li) return;
    var select = li.querySelector('.chapter-ratio');
    condenseChapterAt(index, parseFloat(select.value));
  }

  function condenseChapterAt(index, ratio, refresh) {
    var li = chapterList.querySelector('li[data-index="' + index + '"]');
    if (!li) return;
    var btn = li.querySelector('.summarize-btn');
    var summaryBox = li.querySelector('.chapter-summary');
    var progressWrap = li.querySelector('.progress-wrap');
    state.chapterRatios[index] = ratio;
    var cached = state.chapterSummaries[index];
    if (!refresh && cached && cached.ratio === ratio) {
      renderSummary(summaryBox, cached, index, ratio);
      return;
    }
    summaryBox.innerHTML = '<div class="loading">浓缩中...</div>';
    btn.disabled = true;
    progressWrap.hidden = false;
    api('/api/books/' + state.bookId + '/chapters/' + index + '/summarize?ratio=' + ratio + (refresh ? '&refresh=true' : ''), { method: 'POST' })
      .then(function (data) {
        state.chapterSummaries[index] = {
          ratio: ratio,
          summary: data.summary,
          sentences: data.sentences,
          word_count: data.word_count,
          target_words: data.target_words
        };
        var head = li.querySelector('.chapter-head');
        if (head && head.textContent !== data.title) head.textContent = data.title;
        renderSummary(summaryBox, data, index, ratio);
      })
      .catch(function (err) {
        summaryBox.innerHTML = '<div class="error">' + escapeHtml(err.message) + '</div>';
      })
      .finally(function () {
        btn.disabled = false;
        progressWrap.hidden = true;
      });
  }

  function explainPlain(index) {
    var li = chapterList.querySelector('li[data-index="' + index + '"]');
    if (!li) return;
    var select = li.querySelector('.chapter-ratio');
    explainPlainAt(index, parseFloat(select.value));
  }

  function explainPlainAt(index, ratio, refresh) {
    var li = chapterList.querySelector('li[data-index="' + index + '"]');
    if (!li) return;
    var btn = li.querySelector('.plain-btn');
    var plainBox = li.querySelector('.chapter-plain');
    var progressWrap = li.querySelector('.progress-wrap');
    var cacheKey = index + ':' + ratio;
    var cached = state.chapterPlain[cacheKey];
    if (!refresh && cached) {
      renderPlain(plainBox, cached, index, ratio);
      return;
    }
    plainBox.hidden = false;
    plainBox.innerHTML = '<div class="loading">讲解中...</div>';
    btn.disabled = true;
    progressWrap.hidden = false;
    api('/api/books/' + state.bookId + '/chapters/' + index + '/plain?ratio=' + ratio + (refresh ? '&refresh=true' : ''), { method: 'POST' })
      .then(function (data) {
        state.chapterPlain[cacheKey] = data.text;
        var head = li.querySelector('.chapter-head');
        if (head && head.textContent !== data.title) head.textContent = data.title;
        renderPlain(plainBox, data.text, index, ratio);
      })
      .catch(function (err) {
        plainBox.innerHTML = '<div class="error">' + escapeHtml(err.message) + '</div>';
      })
      .finally(function () {
        btn.disabled = false;
        progressWrap.hidden = true;
      });
  }

  function renderPlain(box, text, index, ratio) {
    box.hidden = false;
    box.innerHTML = '';
    var label = document.createElement('div');
    label.className = 'plain-label';
    label.textContent = '大白话解读';
    if (index != null && ratio != null) {
      var toolRow = document.createElement('div');
      toolRow.className = 'regen-row';
      var regenBtn = document.createElement('button');
      regenBtn.className = 'btn ghost small regen-btn';
      regenBtn.textContent = '重新生成';
      regenBtn.addEventListener('click', function () { explainPlainAt(index, ratio, true); });
      toolRow.appendChild(regenBtn);
      label.appendChild(toolRow);
    }
    var body = document.createElement('div');
    body.className = 'plain-body';
    var sentences = splitPlainSentences(text);
    var wraps = [];
    var lastPara = null;
    sentences.forEach(function (s, i) {
      if (lastPara !== null && s.para !== lastPara) {
        body.appendChild(document.createElement('br'));
        body.appendChild(document.createElement('br'));
      }
      lastPara = s.para;
      // 讲解与浓缩一致：长按句子弹出朗读菜单，单击不触发朗读
      var wrap = buildSentenceWrap(s.text, null, i, wraps);
      wraps.push(wrap);
      body.appendChild(wrap);
    });
    if (sentences.length > 1) {
      body.appendChild(document.createElement('br'));
      var allBtn = document.createElement('button');
      allBtn.className = 'btn ghost small speak-all-btn';
      allBtn.textContent = '朗读全部';
      allBtn.addEventListener('click', function () { speakSentences(wraps, 0); });
      body.appendChild(allBtn);
    }
    if (!sentences.length) body.textContent = text;
    box.appendChild(label);
    box.appendChild(body);
  }

  function renderReport(interp) {
    overview.textContent = interp.overview;
    keyPoints.innerHTML = '';
    interp.key_points.forEach(function (p) {
      var li = document.createElement('li');
      li.textContent = p;
      keyPoints.appendChild(li);
    });
    quotes.innerHTML = '';
    interp.quotes.forEach(function (q) {
      var li = document.createElement('li');
      li.textContent = q;
      quotes.appendChild(li);
    });
    report.hidden = false;
    qaCard.hidden = false;
  }

  function uploadFile(file) {
    setStatus('上传解析中...');
    var form = new FormData();
    form.append('file', file);
    api('/api/books', { method: 'POST', body: form })
      .then(function (book) {
        localStorage.setItem('book_interpreter_last', book.id);
        renderBook(book);
        loadSavedBooks();
        setStatus('解析完成，共 ' + book.chapters.length + ' 个章节');
      })
      .catch(function (err) {
        setStatus(err.message, true);
      });
  }

  uploadBtn.addEventListener('click', function () { fileInput.click(); });

  // 空状态拖放区本身也可点击选择文件
  emptyState.addEventListener('click', function () { fileInput.click(); });

  fileInput.addEventListener('change', function () {
    var file = fileInput.files[0];
    if (!file) return;
    uploadFile(file);
    fileInput.value = '';
  });

  // 全页拖放上传：拖入任意位置即显示提示层，松开后上传
  var dropOverlay = document.createElement('div');
  dropOverlay.className = 'drop-overlay';
  dropOverlay.hidden = true;
  dropOverlay.textContent = '松开鼠标，上传书籍';
  document.body.appendChild(dropOverlay);

  var dragDepth = 0;
  function setDragActive(active) {
    dropOverlay.hidden = !active;
  }
  // 提示层显隐只由 dragenter/dragleave 成对计数控制。
  // dragover 在拖动期间会高频触发，绝不能参与计数，
  // 否则计数失衡、drop 后提示层残留导致上传无响应。
  document.addEventListener('dragenter', function (e) {
    e.preventDefault();
    if (dragDepth === 0) setDragActive(true);
    dragDepth++;
  });
  document.addEventListener('dragover', function (e) {
    e.preventDefault();
  });
  document.addEventListener('dragleave', function (e) {
    e.preventDefault();
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) setDragActive(false);
  });
  document.addEventListener('drop', function (e) {
    e.preventDefault();
    dragDepth = 0;
    setDragActive(false);
    var file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (!file) return;
    uploadFile(file);
  });

  interpretBtn.addEventListener('click', async function () {
    if (state.interpreting || !state.bookId) return;
    state.interpreting = true;
    interpretBtn.disabled = true;
    interpretBtn.textContent = '生成中...';
    try {
      var interp = await api('/api/books/' + state.bookId + '/interpret', { method: 'POST' });
      renderReport(interp);
      interp.chapters.forEach(function (ch, i) {
        var li = chapterList.querySelector('li[data-index="' + i + '"]');
        if (li) {
          var head = li.querySelector('.chapter-head');
          if (head) head.textContent = ch.title;
        }
      });
    } catch (err) {
      setStatus(err.message, true);
    } finally {
      state.interpreting = false;
      interpretBtn.disabled = false;
      interpretBtn.textContent = '生成全书概述';
    }
  });

  askBtn.addEventListener('click', ask);
  questionInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') ask();
  });

  async function ask() {
    var q = questionInput.value.trim();
    if (!q || !state.bookId) return;
    askBtn.disabled = true;
    answer.textContent = '思考中...';
    answer.className = 'answer show';
    try {
      var data = await api('/api/books/' + state.bookId + '/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q })
      });
      answer.textContent = data.answer;
    } catch (err) {
      answer.textContent = err.message;
    } finally {
      askBtn.disabled = false;
    }
  }

  $('export-md').addEventListener('click', function () { download('md'); });
  $('export-html').addEventListener('click', function () { download('html'); });

  function download(fmt) {
    if (!state.bookId) return;
    window.location.href = '/api/books/' + state.bookId + '/report?format=' + fmt;
  }

  // 页面加载时恢复已上传书籍；有最近打开的书则自动打开
  loadSavedBooks();
})();
