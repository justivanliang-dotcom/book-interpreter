(function () {
  var state = {
    bookId: null,
    chapters: [],
    interpreting: false,
    chapterRatios: {},
    chapterSummaries: {},
    chapterPlain: {}
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
    var resp;
    try {
      resp = await fetch(url, options);
    } catch (e) {
      throw new Error('网络连接失败，请检查服务是否运行或网络是否正常');
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

  function renderBook(book) {
    state.bookId = book.id;
    state.chapters = book.chapters;
    state.chapterRatios = {};
    state.chapterSummaries = {};
    state.chapterPlain = {};
    bookTitle.textContent = book.title;
    bookFilename.textContent = book.filename;
    chapterList.innerHTML = '';
    book.chapters.forEach(function (ch, i) {
      chapterList.appendChild(buildChapterItem(i, ch.title));
    });
    bookCard.hidden = false;
    emptyState.hidden = true;
    report.hidden = true;
    qaCard.hidden = true;
    interpretBtn.disabled = false;
    answer.className = 'answer';
    questionInput.value = '';
  }

  function buildChapterItem(index, title) {
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
    [0.05, 0.1, 0.25, 0.5, 0.75, 1].forEach(function (v) {
      var opt = document.createElement('option');
      opt.value = String(v);
      opt.textContent = Math.round(v * 100) + '%';
      if (v === 0.1) opt.selected = true;
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

    var plainBox = document.createElement('div');
    plainBox.className = 'chapter-plain';
    plainBox.hidden = true;

    expand.appendChild(ratioRow);
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
    // 展开时只显示标题与比例选择，不自动浓缩；有缓存则展示缓存
    var summaryBox = li.querySelector('.chapter-summary');
    var cached = state.chapterSummaries[index];
    if (cached) {
      renderSummary(summaryBox, cached);
    } else {
      summaryBox.innerHTML = '<div class="hint">点击「浓缩本章」生成浓缩内容</div>';
    }
    var plainBox = li.querySelector('.chapter-plain');
    var cachedPlain = state.chapterPlain[index];
    if (cachedPlain) {
      renderPlain(plainBox, cachedPlain);
    } else {
      plainBox.hidden = true;
      plainBox.innerHTML = '';
    }
  }

  function renderSummary(container, data) {
    var sentences = data.sentences;
    if (sentences && sentences.length) {
      container.innerHTML = '';
      sentences.forEach(function (s) {
        var span = document.createElement('span');
        span.className = 'summary-sentence';
        span.textContent = s.text;
        span.addEventListener('click', function () { showSource(s, span); });
        container.appendChild(span);
        container.appendChild(document.createTextNode(' '));
      });
    } else {
      container.innerHTML = escapeHtml(data.summary);
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
    var btn = li.querySelector('.summarize-btn');
    var summaryBox = li.querySelector('.chapter-summary');
    var ratio = parseFloat(select.value);
    state.chapterRatios[index] = ratio;
    var cached = state.chapterSummaries[index];
    if (cached && cached.ratio === ratio) {
      renderSummary(summaryBox, cached);
      return;
    }
    summaryBox.innerHTML = '<div class="loading">浓缩中...</div>';
    btn.disabled = true;
    api('/api/books/' + state.bookId + '/chapters/' + index + '/summarize?ratio=' + ratio, { method: 'POST' })
      .then(function (data) {
        state.chapterSummaries[index] = { ratio: ratio, summary: data.summary, sentences: data.sentences };
        var head = li.querySelector('.chapter-head');
        if (head && head.textContent !== data.title) head.textContent = data.title;
        renderSummary(summaryBox, data);
      })
      .catch(function (err) {
        summaryBox.innerHTML = '<div class="error">' + escapeHtml(err.message) + '</div>';
      })
      .finally(function () {
        btn.disabled = false;
      });
  }

  function explainPlain(index) {
    var li = chapterList.querySelector('li[data-index="' + index + '"]');
    if (!li) return;
    var btn = li.querySelector('.plain-btn');
    var plainBox = li.querySelector('.chapter-plain');
    var cached = state.chapterPlain[index];
    if (cached) {
      renderPlain(plainBox, cached);
      return;
    }
    plainBox.hidden = false;
    plainBox.innerHTML = '<div class="loading">讲解中...</div>';
    btn.disabled = true;
    api('/api/books/' + state.bookId + '/chapters/' + index + '/plain', { method: 'POST' })
      .then(function (data) {
        state.chapterPlain[index] = data.text;
        var head = li.querySelector('.chapter-head');
        if (head && head.textContent !== data.title) head.textContent = data.title;
        renderPlain(plainBox, data.text);
      })
      .catch(function (err) {
        plainBox.innerHTML = '<div class="error">' + escapeHtml(err.message) + '</div>';
      })
      .finally(function () {
        btn.disabled = false;
      });
  }

  function renderPlain(box, text) {
    box.hidden = false;
    box.innerHTML = '';
    var label = document.createElement('div');
    label.className = 'plain-label';
    label.textContent = '大白话解读';
    var body = document.createElement('div');
    body.className = 'plain-body';
    body.textContent = text;
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

  uploadBtn.addEventListener('click', function () { fileInput.click(); });

  fileInput.addEventListener('change', async function () {
    var file = fileInput.files[0];
    if (!file) return;
    setStatus('上传解析中...');
    var form = new FormData();
    form.append('file', file);
    try {
      var book = await api('/api/books', { method: 'POST', body: form });
      renderBook(book);
      setStatus('解析完成，共 ' + book.chapters.length + ' 个章节');
    } catch (err) {
      setStatus(err.message, true);
    }
    fileInput.value = '';
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
})();
