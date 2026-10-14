(function () {
  var grid = document.getElementById("product-grid");
  var cartList = document.getElementById("cart-list");
  var emptyMsg = document.getElementById("cart-empty");
  var totalEl = document.getElementById("cart-total");
  var changeEl = document.getElementById("cart-change");
  var paidEl = document.getElementById("paid");
  var errEl = document.getElementById("cart-error");
  var payBtn = document.getElementById("checkout");
  var cart = {}; // id -> {id, name, price, stock, qty}

  function rp(n) {
    return "Rp " + Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  }
  function total() {
    return Object.keys(cart).reduce(function (s, k) { return s + cart[k].price * cart[k].qty; }, 0);
  }
  function showError(msg) {
    errEl.textContent = msg || "";
    errEl.hidden = !msg;
  }

  function render() {
    cartList.innerHTML = "";
    var ids = Object.keys(cart);
    emptyMsg.hidden = ids.length > 0;
    ids.forEach(function (id) {
      var it = cart[id];
      var li = document.createElement("li");
      var name = document.createElement("div");
      name.className = "name";
      var b = document.createElement("strong");
      b.textContent = it.name;
      var small = document.createElement("small");
      small.textContent = rp(it.price) + " × " + it.qty + " = " + rp(it.price * it.qty);
      name.appendChild(b); name.appendChild(small);

      var qty = document.createElement("div");
      qty.className = "qty";
      var minus = document.createElement("button");
      minus.type = "button"; minus.textContent = "−";
      minus.onclick = function () { change(id, -1); };
      var n = document.createElement("span");
      n.textContent = it.qty;
      var plus = document.createElement("button");
      plus.type = "button"; plus.textContent = "+";
      plus.onclick = function () { change(id, 1); };
      qty.appendChild(minus); qty.appendChild(n); qty.appendChild(plus);

      li.appendChild(name); li.appendChild(qty);
      cartList.appendChild(li);
    });
    var t = total();
    var paid = parseInt(paidEl.value || "0", 10) || 0;
    totalEl.textContent = rp(t);
    changeEl.textContent = rp(Math.max(0, paid - t));
    payBtn.disabled = t <= 0 || paid < t;
  }

  function change(id, d) {
    var it = cart[id];
    if (!it) return;
    var q = it.qty + d;
    if (q <= 0) delete cart[id];
    else if (q > it.stock) showError("Stok " + it.name + " hanya " + it.stock + ".");
    else { it.qty = q; showError(""); }
    render();
  }

  grid && grid.addEventListener("click", function (e) {
    var card = e.target.closest(".product");
    if (!card) return;
    var id = card.dataset.id;
    if (cart[id]) return change(id, 1);
    cart[id] = {
      id: parseInt(id, 10), name: card.dataset.name,
      price: parseInt(card.dataset.price, 10), stock: parseInt(card.dataset.stock, 10), qty: 1
    };
    showError(""); render();
  });

  var search = document.getElementById("search");
  if (search && grid) {
    search.addEventListener("input", function () {
      var q = search.value.trim().toLowerCase();
      grid.querySelectorAll(".product").forEach(function (c) {
        var match = !q || c.dataset.name.toLowerCase().indexOf(q) !== -1;
        c.hidden = !match;
      });
    });
  }

  paidEl.addEventListener("input", render);
  document.getElementById("pay-exact").onclick = function () { paidEl.value = total(); render(); };
  document.querySelectorAll("[data-add]").forEach(function (b) {
    b.onclick = function () {
      paidEl.value = (parseInt(paidEl.value || "0", 10) || 0) + parseInt(b.dataset.add, 10);
      render();
    };
  });
  document.getElementById("clear-cart").onclick = function () {
    cart = {}; paidEl.value = ""; showError(""); render();
  };

  payBtn.onclick = function () {
    payBtn.disabled = true;
    fetch(window.CHECKOUT_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        paid: parseInt(paidEl.value || "0", 10) || 0,
        items: Object.keys(cart).map(function (k) { return { id: cart[k].id, qty: cart[k].qty }; })
      })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.ok) window.location.href = d.redirect;
        else { showError(d.error || "Gagal memproses."); render(); }
      })
      .catch(function () { showError("Koneksi bermasalah, coba lagi."); render(); });
  };

  render();
})();
