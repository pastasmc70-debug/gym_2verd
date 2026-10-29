/* Modo kiosco. Sin librerías: el campo de DNI siempre tiene el foco y solo acepta números. */
(function () {
  "use strict";
  var campo = document.getElementById("dni");
  var raiz = document.querySelector("[data-kiosco]");
  var resultado = document.getElementById("resultado");

  function sonido(ok) {
    if (!raiz || raiz.dataset.sonido !== "1") return;
    try {
      var Ctx = window.AudioContext || window.webkitAudioContext;
      var audio = new Ctx();
      var tonos = ok ? [[880, 0, 0.18]] : [[220, 0, 0.22], [180, 0.28, 0.3]];   // aceptado: un pip agudo; rechazado: dos graves
      tonos.forEach(function (t) {
        var osc = audio.createOscillator(), vol = audio.createGain();
        osc.type = ok ? "sine" : "square"; osc.frequency.value = t[0]; vol.gain.value = 0.15;
        osc.connect(vol); vol.connect(audio.destination);
        osc.start(audio.currentTime + t[1]); osc.stop(audio.currentTime + t[1] + t[2]);
      });
    } catch (e) { /* sin audio: no pasa nada */ }
  }

  if (!campo) {   // pantalla de resultado sin JavaScript (HTML) o login: solo vuelve sola a los 5 segundos
    var fijo = document.querySelector("[data-volver]");
    if (fijo) { sonido(fijo.dataset.ok === "1"); setTimeout(function () { location.href = fijo.dataset.volver; }, 5000); }
    return;
  }

  var ocupado = false;
  function enfocar() { if (!ocupado && document.activeElement !== campo) campo.focus(); }
  enfocar();
  campo.addEventListener("blur", function () { setTimeout(enfocar, 0); });
  window.addEventListener("focus", enfocar);
  document.addEventListener("click", enfocar);
  document.addEventListener("visibilitychange", enfocar);
  setInterval(enfocar, 400);

  // Solo números (el teclado numérico manda dígitos y Enter; Borrar/Backspace corrige).
  campo.addEventListener("keydown", function (e) {
    if (ocupado) { e.preventDefault(); return; }
    if (e.key.length === 1 && !/\d/.test(e.key) && !e.ctrlKey && !e.metaKey) e.preventDefault();
  });
  campo.addEventListener("input", function () { campo.value = campo.value.replace(/\D/g, "").slice(0, 8); });

  // Pantalla completa con la primera tecla (el navegador lo exige tras una acción de la persona).
  document.addEventListener("keydown", function () {
    if (!document.fullscreenElement && document.documentElement.requestFullscreen) {
      document.documentElement.requestFullscreen().catch(function () {});
    }
  }, { once: true });

  function limpiar() {
    resultado.hidden = true; ocupado = false; campo.value = ""; enfocar();
  }

  function mostrar(r) {
    resultado.className = "resultado " + (r.ok ? "ok" : "no");
    document.getElementById("r-nombre").textContent = r.nombre || "";
    document.getElementById("r-estado").textContent = r.estado || "";
    document.getElementById("r-dias").textContent = r.dias || "";
    document.getElementById("r-mensaje").textContent = r.mensaje || "";
    var foto = document.getElementById("r-foto");
    if (r.foto_url) { foto.src = r.foto_url; foto.hidden = false; } else { foto.hidden = true; foto.removeAttribute("src"); }
    resultado.hidden = false;
    sonido(r.ok);
    setTimeout(limpiar, 5000);
  }

  var form = document.getElementById("form-dni");
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (ocupado || !campo.value) return;
    ocupado = true;
    fetch(form.action, { method: "POST", body: new FormData(form), headers: { "X-Requested-With": "kiosco", "Accept": "application/json" }, credentials: "same-origin" })
      .then(function (resp) { return resp.json(); })
      .then(mostrar)
      .catch(function () { mostrar({ ok: false, mensaje: "No hay conexión con el sistema. Avisá en recepción." }); });
  });

  // Teclado en pantalla (opcional, para tablets táctiles).
  Array.prototype.forEach.call(document.querySelectorAll("[data-tecla]"), function (b) {
    b.addEventListener("mousedown", function (e) { e.preventDefault(); });   // no le saca el foco al campo
    b.addEventListener("click", function () {
      if (ocupado) return;
      var t = b.dataset.tecla;
      if (t === "borrar") campo.value = campo.value.slice(0, -1);
      else if (t === "enter") form.requestSubmit();
      else if (campo.value.length < 8) campo.value += t;
      enfocar();
    });
  });
})();
