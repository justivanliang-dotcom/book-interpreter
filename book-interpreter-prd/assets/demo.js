/* 终端演示交互：点击"运行演示"逐步展示输出 */
(function () {
  document.querySelectorAll('.terminal').forEach(function (term) {
    var btn = term.querySelector('.run-btn');
    var lines = Array.prototype.slice.call(term.querySelectorAll('.term-line.out'));
    var running = false;

    btn.addEventListener('click', function () {
      if (running) return;
      running = true;
      btn.disabled = true;
      btn.textContent = '运行中…';
      lines.forEach(function (line) { line.style.display = 'none'; });

      var i = 0;
      function showNext() {
        if (i >= lines.length) {
          btn.textContent = '重新运行';
          btn.disabled = false;
          running = false;
          return;
        }
        lines[i].style.display = 'block';
        i += 1;
        setTimeout(showNext, 240);
      }
      setTimeout(showNext, 350);
    });
  });
})();
