// Formulario de pago: al elegir cuántos períodos paga, completa el monto con el valor que calculó el servidor
// (precio x períodos, con el descuento anual si corresponde). El monto sigue siendo editable.
// Sin JavaScript el formulario funciona igual: el servidor usa el monto escrito.
(function () {
  var periodos = document.getElementById("periodos");
  var monto = document.getElementById("monto");
  var ayuda = document.getElementById("ayuda-periodos");
  if (!periodos || !monto) return;
  var textoBase = ayuda ? ayuda.textContent : "";

  function actualizar(completarMonto) {
    var opcion = periodos.options[periodos.selectedIndex];
    if (!opcion) return;
    if (completarMonto) monto.value = opcion.getAttribute("data-monto") || "";
    if (ayuda) {
      var descuento = opcion.getAttribute("data-descuento");
      ayuda.textContent = descuento
        ? "Pago anual: incluye un descuento de " + descuento + ". Si cambiás el monto a uno menor al sugerido, el descuento no se aplica."
        : textoBase;
    }
  }

  periodos.addEventListener("change", function () { actualizar(true); });
  actualizar(false);
})();
