// Lista de socios para elegir: filtra mientras se escribe (sin recargar la página), cambia el orden y trae más.
// Sin JavaScript sigue andando: el buscador y los links de orden y página recargan la pantalla.
(function () {
  function iniciar(cont) {
    var url = cont.getAttribute("data-url");
    var destino = cont.getAttribute("data-destino");
    var baseUrl = cont.getAttribute("data-base-url") || "";
    var orden = cont.getAttribute("data-orden-inicial") || "prioridad";
    var selectorEntrada = cont.getAttribute("data-input");
    var entrada = selectorEntrada ? document.querySelector(selectorEntrada) : null;
    var lista = cont.querySelector(".selector-lista");
    var temporizador = null, numero = 0;

    function pedir(extra, agregar) {
      var id = ++numero;
      var p = new URLSearchParams({ destino: destino, orden: orden, q: entrada ? entrada.value.trim() : "", base_url: baseUrl });
      Object.keys(extra || {}).forEach(function (k) { p.set(k, extra[k]); });
      fetch(url + "?" + p.toString(), { credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
        .then(function (html) {
          if (id !== numero) return;           // llegó una respuesta vieja: se descarta
          if (agregar) {
            var pie = lista.querySelector(".selector-pie");
            if (pie) pie.remove();
            lista.insertAdjacentHTML("beforeend", html);
          } else {
            lista.innerHTML = html;
          }
        })
        .catch(function () {
          if (id !== numero) return;
          lista.innerHTML = '<div class="selector-vacio text-danger py-3">No se pudo actualizar la lista. Probá de nuevo.</div>';
        });
    }

    if (entrada) {
      entrada.addEventListener("input", function () {
        clearTimeout(temporizador);
        temporizador = setTimeout(function () { pedir({}, false); }, 200);
      });
    }

    cont.addEventListener("click", function (e) {
      var mas = e.target.closest("[data-mas]");
      if (mas) { e.preventDefault(); pedir({ pagina: mas.getAttribute("data-pagina"), mas: "1" }, true); return; }
      var ord = e.target.closest("[data-orden]");
      if (ord) {
        e.preventDefault();
        orden = ord.getAttribute("data-orden");
        cont.querySelectorAll("[data-orden]").forEach(function (b) { b.classList.toggle("active", b === ord); });
        pedir({}, false);
        return;
      }
      var fila = e.target.closest("[data-elegir-dni]");
      if (fila) {                                // venta de tienda: completa el DNI con el socio elegido
        var campo = document.getElementById("socio_dni");
        var aviso = document.getElementById("socio-elegido");
        if (campo) campo.value = fila.getAttribute("data-elegir-dni");
        if (aviso) aviso.textContent = "Socio elegido: " + fila.getAttribute("data-nombre") + " (DNI " + fila.getAttribute("data-elegir-dni") + ")";
        cont.querySelectorAll(".elegido").forEach(function (f) { f.classList.remove("elegido"); });
        fila.classList.add("elegido");
      }
    });
  }
  document.querySelectorAll("[data-selector]").forEach(iniciar);
})();
