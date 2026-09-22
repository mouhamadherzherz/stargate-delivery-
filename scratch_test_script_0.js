

// ─── Smart Fast Store Picker Engine (محرك اختيار وبحث المتاجر السريع) ───────
let smartMerchantsData = [];

function initSmartMerchantPicker() {
  const select = document.getElementById('modalMerchantSelect');
  if (!select) return;
  smartMerchantsData = [];
  for (let i = 0; i < select.options.length; i++) {
    const opt = select.options[i];
    if (!opt.value) continue;
    smartMerchantsData.push({
      id: opt.value,
      name: opt.getAttribute('data-name') || '',
      store: opt.getAttribute('data-store') || opt.text,
      phone: opt.getAttribute('data-phone') || '',
      fee: opt.getAttribute('data-def-fee') || '',
      comm: opt.getAttribute('data-def-comm') || ''
    });
  }
}

function openSmartStoreDropdown() {
  initSmartMerchantPicker();
  const input = document.getElementById('smartStoreSearchInput');
  const val = input ? input.value : '';
  renderSmartStoreDropdown(val);
  const list = document.getElementById('smartStoreDropdownList');
  if (list) list.classList.remove('hidden');
}

function closeSmartStoreDropdown() {
  setTimeout(() => {
    const list = document.getElementById('smartStoreDropdownList');
    if (list) list.classList.add('hidden');
  }, 250);
}

function clearSmartSearchInput() {
  const input = document.getElementById('smartStoreSearchInput');
  if (input) {
    input.value = '';
    onSmartStoreSearchInput('');
    input.focus();
  }
}

function onSmartStoreSearchInput(query) {
  const clearBtn = document.getElementById('smartStoreClearInputBtn');
  if (clearBtn) {
    if (query && query.trim()) clearBtn.classList.remove('hidden');
    else clearBtn.classList.add('hidden');
  }
  renderSmartStoreDropdown(query);
  const list = document.getElementById('smartStoreDropdownList');
  if (list) list.classList.remove('hidden');
}

function renderSmartStoreDropdown(query) {
  const list = document.getElementById('smartStoreDropdownList');
  if (!list) return;
  if (smartMerchantsData.length === 0) initSmartMerchantPicker();

  const q = (query || '').trim().toLowerCase();
  let matches = smartMerchantsData;
  if (q) {
    matches = smartMerchantsData.filter(m => 
      m.store.toLowerCase().includes(q) || 
      m.name.toLowerCase().includes(q) || 
      m.phone.toLowerCase().includes(q)
    );
  }

  if (matches.length === 0) {
    const safeQ = (query || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
    list.innerHTML = `
      <div class="p-3 text-center space-y-2">
        <p class="text-xs font-bold text-slate-500">لا يوجد متجر مطابق لـ "${safeQ}"</p>
        <button type="button" onclick="quickCreateMerchantFromSmartInput('${safeQ}')" class="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-black transition inline-flex items-center gap-1 shadow-xs cursor-pointer">
          <i class="fa-solid fa-plus text-[10px]"></i>
          <span>➕ إضافة "${safeQ}" كمتجر جديد فوراً</span>
        </button>
      </div>
    `;
    return;
  }

  let html = '';
  matches.slice(0, 15).forEach((m, idx) => {
    const safeStore = m.store.replace(/'/g, "\\'");
    const feeStr = m.fee && parseFloat(m.fee) > 0 ? `<span class="text-[10px] bg-purple-100 text-purple-800 px-2 py-0.5 rounded-md font-bold">توصيل: ${Number(m.fee).toLocaleString()}</span>` : '';
    html += `
      <div onclick="selectSmartStore('${m.id}', '${safeStore}', '${m.phone}', '${m.fee}', '${m.comm}')"
           class="p-2.5 hover:bg-purple-50 cursor-pointer flex items-center justify-between transition ${idx === 0 ? 'bg-purple-50/40' : ''}">
        <div class="flex items-center gap-2">
          <div class="w-8 h-8 rounded-lg bg-purple-100 text-purple-700 flex items-center justify-center font-bold text-xs shrink-0 shadow-2xs">
            <i class="fa-solid fa-store"></i>
          </div>
          <div>
            <div class="font-black text-slate-900 text-xs">${m.store}</div>
            <div class="text-[10px] text-slate-400 font-mono">${m.phone ? '📞 ' + m.phone : ''} ${m.name && m.name !== m.store ? '• ' + m.name : ''}</div>
          </div>
        </div>
        <div class="text-left font-mono">
          ${feeStr}
        </div>
      </div>
    `;
  });
  list.innerHTML = html;
}

function selectSmartStore(id, storeName, phone, fee, comm) {
  const select = document.getElementById('modalMerchantSelect');
  if (select) {
    select.value = id;
    onMainMerchantSelectChange(select);
  }

  const card = document.getElementById('smartSelectedStoreCard');
  const inputBox = document.getElementById('smartStoreInputBox');
  const nameEl = document.getElementById('smartSelectedStoreName');
  const phoneEl = document.getElementById('smartSelectedStorePhone');
  const feeEl = document.getElementById('smartSelectedStoreFee');

  if (nameEl) nameEl.textContent = storeName;
  if (phoneEl) phoneEl.textContent = phone ? '📞 ' + phone : '';
  if (feeEl) feeEl.textContent = fee && parseFloat(fee) > 0 ? `(أجرة التوصيل: ${Number(fee).toLocaleString()} ل.ل)` : '';

  if (card) card.classList.remove('hidden');
  if (inputBox) inputBox.classList.add('hidden');

  const list = document.getElementById('smartStoreDropdownList');
  if (list) list.classList.add('hidden');

  // Focus the first item name for rapid order entry!
  setTimeout(() => {
    const firstItemInput = document.querySelector('#storeItemsContainer_1 .item-name');
    if (firstItemInput) firstItemInput.focus();
  }, 100);
}

function clearSmartSelectedStore() {
  const select = document.getElementById('modalMerchantSelect');
  if (select) {
    select.value = '';
    onMainMerchantSelectChange(select);
  }

  const card = document.getElementById('smartSelectedStoreCard');
  const inputBox = document.getElementById('smartStoreInputBox');
  const input = document.getElementById('smartStoreSearchInput');

  if (card) card.classList.add('hidden');
  if (inputBox) inputBox.classList.remove('hidden');
  if (input) {
    input.value = '';
    input.focus();
    openSmartStoreDropdown();
  }
}

function onSmartStoreKeydown(e) {
  if (e.key === 'Enter') {
    e.preventDefault();
    const list = document.getElementById('smartStoreDropdownList');
    if (list) {
      const firstItem = list.querySelector('[onclick^="selectSmartStore"]');
      if (firstItem) {
        firstItem.click();
      }
    }
  } else if (e.key === 'Escape') {
    const list = document.getElementById('smartStoreDropdownList');
    if (list) list.classList.add('hidden');
  }
}

function quickCreateMerchantFromSmartInput(name) {
  const storeName = (name || '').trim();
  if (!storeName) return;

  fetch('/api/merchants/quick-add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    body: JSON.stringify({ store_name: storeName, name: storeName, phone: '', category: 'عام' })
  })
  .then(res => res.json())
  .then(data => {
    if (data.success && data.merchant) {
      const select = document.getElementById('modalMerchantSelect');
      if (select) {
        const opt = document.createElement('option');
        opt.value = data.merchant.id;
        opt.textContent = `${data.merchant.store_name} — ${data.merchant.phone || ''}`;
        opt.setAttribute('data-name', data.merchant.name || '');
        opt.setAttribute('data-store', data.merchant.store_name || '');
        opt.setAttribute('data-phone', data.merchant.phone || '');
        opt.setAttribute('data-def-fee', data.merchant.default_delivery_fee || '');
        opt.setAttribute('data-def-comm', data.merchant.default_courier_commission || '');
        select.appendChild(opt);
      }
      initSmartMerchantPicker();
      selectSmartStore(data.merchant.id, data.merchant.store_name, data.merchant.phone || '', data.merchant.default_delivery_fee || '', '');
    }
  });
}

// Close dropdown on outside click
document.addEventListener('click', function(e) {
  const wrapper = document.getElementById('smartStoreSearchWrapper');
  if (wrapper && !wrapper.contains(e.target)) {
    const list = document.getElementById('smartStoreDropdownList');
    if (list) list.classList.add('hidden');
  }
});

// ─── Dynamic Multi-Store & Per-Store Products Engine ───────────────────────
window.STORE_COUNTER = 1;

// 1. Filter merchants for any store
function filterStoreOptions(input) {
  const q = (input.value || '').trim().toLowerCase();
  const card = input.closest('.store-order-card');
  if (!card) return;
  const select = card.querySelector('.store-select');
  if (!select) return;

  for (let i = 0; i < select.options.length; i++) {
    const opt = select.options[i];
    if (!opt.value) {
      opt.hidden = false;
      continue;
    }
    const name = (opt.getAttribute('data-name') || '').toLowerCase();
    const store = (opt.getAttribute('data-store') || '').toLowerCase();
    const phone = (opt.getAttribute('data-phone') || '').toLowerCase();
    const text = (opt.text || '').toLowerCase();

    if (!q || name.includes(q) || store.includes(q) || phone.includes(q) || text.includes(q)) {
      opt.hidden = false;
    } else {
      opt.hidden = true;
    }
  }
}

// 2. When main merchant select changes
function onMainMerchantSelectChange(select) {
  if (typeof onMerchantChange === 'function') {
    onMerchantChange(select);
  }
  recalculateAllStoresAndFinancials();
  if (typeof updateLiveInvoice === 'function') {
    updateLiveInvoice();
  }
}

// 3. Add a product row inside a store
function addStoreProductRow(storeIdx, name = '', qty = 1, priceUsd = '', priceLbp = '') {
  const container = document.getElementById(`storeItemsContainer_${storeIdx}`);
  if (!container) return;

  const row = document.createElement('div');
  row.className = 'store-item-row p-2 bg-slate-50 hover:bg-purple-50/40 rounded-xl border border-slate-200 transition grid grid-cols-1 sm:grid-cols-12 gap-1.5 items-center';
  row.innerHTML = `
    <div class="sm:col-span-5">
      <input type="text" placeholder="اسم المنتج (مثال: برغر، عطر، حذاء...)" value="${name}"
             class="item-name w-full border border-slate-300 focus:border-purple-500 rounded-lg px-2.5 py-1.5 text-xs font-bold text-slate-800 bg-white focus:outline-none"
             oninput="recalculateAllStoresAndFinancials()">
    </div>
    <div class="sm:col-span-2 flex items-center">
      <span class="sm:hidden text-xs font-bold text-slate-500 ml-1">الكمية:</span>
      <input type="number" min="1" value="${qty}" placeholder="1"
             class="item-qty w-full border border-slate-300 focus:border-purple-500 rounded-lg px-1.5 py-1.5 text-xs font-black font-mono text-center text-slate-800 bg-white focus:outline-none"
             oninput="recalculateAllStoresAndFinancials()">
    </div>
    <div class="sm:col-span-2 relative">
      <span class="sm:hidden text-xs font-bold text-slate-500 ml-1">السعر $:</span>
      <input type="text" inputmode="decimal" placeholder="0.00" value="${priceUsd}"
             class="item-price-usd w-full border border-slate-300 focus:border-purple-500 rounded-lg pr-4 pl-1 py-1.5 text-xs font-black font-mono text-center text-emerald-700 bg-white focus:outline-none" dir="ltr"
             oninput="onStoreItemUsdChange(this)">
      <span class="absolute right-1 top-1/2 -translate-y-1/2 text-[10px] font-bold text-emerald-600">$</span>
    </div>
    <div class="sm:col-span-2 relative">
      <span class="sm:hidden text-xs font-bold text-slate-500 ml-1">السعر ل.ل:</span>
      <input type="text" inputmode="decimal" placeholder="0" value="${priceLbp}"
             class="item-price-lbp w-full border border-slate-300 focus:border-purple-500 rounded-lg pl-5 pr-1 py-1.5 text-xs font-black font-mono text-center text-emerald-700 bg-white focus:outline-none" dir="ltr"
             oninput="onStoreItemLbpChange(this)">
      <span class="absolute left-1 top-1/2 -translate-y-1/2 text-[9px] font-bold text-emerald-600">ل.ل</span>
    </div>
    <div class="sm:col-span-1 text-center flex justify-end sm:justify-center">
      <button type="button" onclick="removeStoreProductRow(this)" class="w-7 h-7 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 flex items-center justify-center transition active:scale-90 cursor-pointer" title="حذف هذا الصنف">
        <i class="fa-solid fa-trash-can text-xs"></i>
      </button>
    </div>
  `;
  container.appendChild(row);
  recalculateAllStoresAndFinancials();
  row.querySelector('.item-name')?.focus();
}

// 4. Remove a product row
function removeStoreProductRow(btn) {
  const row = btn.closest('.store-item-row');
  const container = btn.closest('.store-items-container');
  if (!row || !container) return;

  if (container.querySelectorAll('.store-item-row').length > 1) {
    row.remove();
  } else {
    // If only 1 row left, just clear it
    const inputs = row.querySelectorAll('input');
    inputs.forEach(i => i.value = (i.classList.contains('item-qty') ? 1 : ''));
  }
  recalculateAllStoresAndFinancials();
}

// 5. Add an additional store block
function addNewStoreBlock() {
  window.STORE_COUNTER++;
  const nextIdx = window.STORE_COUNTER;
  const container = document.getElementById('allStoresCardsContainer');
  if (!container) return;

  // Copy options from store 1 select
  const mainSelect = document.getElementById('modalMerchantSelect');
  const optionsHtml = mainSelect ? mainSelect.innerHTML : '<option value="">-- اختر المتجر --</option>';

  const card = document.createElement('div');
  card.className = 'store-order-card bg-indigo-50/60 p-4 rounded-2xl border-2 border-indigo-300 shadow-sm space-y-3 animate-in';
  card.setAttribute('data-store-index', nextIdx);
  card.id = `storeCard_${nextIdx}`;

  card.innerHTML = `
    <div class="flex items-center justify-between border-b border-indigo-200/80 pb-2">
      <div class="flex items-center gap-2">
        <span class="w-6 h-6 rounded-lg bg-indigo-700 text-white flex items-center justify-center text-xs font-black">${nextIdx}</span>
        <span class="font-black text-indigo-950 text-xs flex items-center gap-1.5">
          <i class="fa-solid fa-store text-indigo-700"></i>
          <span>المتجر رقم (${nextIdx}) - مشترك بنفس الطلب</span>
        </span>
      </div>
      <button type="button" onclick="removeStoreBlock(this)" class="text-xs text-rose-600 hover:text-rose-800 font-black px-2.5 py-1 rounded-lg bg-rose-50 hover:bg-rose-100 transition cursor-pointer border border-rose-200">
        ✕ إلغاء هذا المتجر
      </button>
    </div>

    <!-- اختيار المتجر مع البحث -->
    <div class="space-y-1.5">
      <input type="text" oninput="filterStoreOptions(this)"
             placeholder="🔍 ابحث في المتاجر بالاسم أو الهاتف..."
             class="store-filter-input w-full border border-indigo-200 focus:border-indigo-500 rounded-xl px-3 py-1.5 text-xs font-bold focus:outline-none focus:ring-1 focus:ring-indigo-200 bg-white">

      <select class="store-select w-full border-2 border-indigo-300 focus:border-indigo-600 rounded-xl px-3.5 py-2 text-sm font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-100 bg-white"
              onchange="recalculateAllStoresAndFinancials()">
        ${optionsHtml}
      </select>
    </div>

    <!-- جدول أصناف المتجر -->
    <div class="space-y-1.5 bg-white/90 p-3 rounded-xl border border-indigo-200/80">
      <div class="flex items-center justify-between mb-1">
        <span class="text-[11px] font-black text-indigo-900 flex items-center gap-1">
          <i class="fa-solid fa-basket-shopping text-indigo-600"></i>
          <span>المنتجات المأخوذة من هذا المتجر وأسعارها:</span>
        </span>
        <span class="text-[10px] text-indigo-700 font-bold">تظهر مفصلة للزبون والسائق</span>
      </div>

      <div class="hidden sm:grid grid-cols-12 gap-2 text-[10px] font-black text-slate-500 px-1">
        <span class="col-span-5">اسم المنتج / الصنف</span>
        <span class="col-span-2 text-center">الكمية</span>
        <span class="col-span-2 text-center">السعر ($)</span>
        <span class="col-span-2 text-center">السعر (ل.ل)</span>
        <span class="col-span-1 text-center">حذف</span>
      </div>

      <div class="store-items-container space-y-1.5" id="storeItemsContainer_${nextIdx}">
        <!-- صف منتج افتراضي -->
        <div class="store-item-row p-2 bg-slate-50 hover:bg-indigo-50/40 rounded-xl border border-slate-200 transition grid grid-cols-1 sm:grid-cols-12 gap-1.5 items-center">
          <div class="sm:col-span-5">
            <input type="text" placeholder="اسم المنتج من هذا المتجر..."
                   class="item-name w-full border border-slate-300 focus:border-indigo-500 rounded-lg px-2.5 py-1.5 text-xs font-bold text-slate-800 bg-white focus:outline-none"
                   oninput="recalculateAllStoresAndFinancials()">
          </div>
          <div class="sm:col-span-2 flex items-center">
            <span class="sm:hidden text-xs font-bold text-slate-500 ml-1">الكمية:</span>
            <input type="number" min="1" value="1" placeholder="1"
                   class="item-qty w-full border border-slate-300 focus:border-indigo-500 rounded-lg px-1.5 py-1.5 text-xs font-black font-mono text-center text-slate-800 bg-white focus:outline-none"
                   oninput="recalculateAllStoresAndFinancials()">
          </div>
          <div class="sm:col-span-2 relative">
            <span class="sm:hidden text-xs font-bold text-slate-500 ml-1">السعر $:</span>
            <input type="text" inputmode="decimal" placeholder="0.00"
                   class="item-price-usd w-full border border-slate-300 focus:border-indigo-500 rounded-lg pr-4 pl-1 py-1.5 text-xs font-black font-mono text-center text-emerald-700 bg-white focus:outline-none" dir="ltr"
                   oninput="onStoreItemUsdChange(this)">
            <span class="absolute right-1 top-1/2 -translate-y-1/2 text-[10px] font-bold text-emerald-600">$</span>
          </div>
          <div class="sm:col-span-2 relative">
            <span class="sm:hidden text-xs font-bold text-slate-500 ml-1">السعر ل.ل:</span>
            <input type="text" inputmode="decimal" placeholder="0"
                   class="item-price-lbp w-full border border-slate-300 focus:border-indigo-500 rounded-lg pl-5 pr-1 py-1.5 text-xs font-black font-mono text-center text-emerald-700 bg-white focus:outline-none" dir="ltr"
                   oninput="onStoreItemLbpChange(this)">
            <span class="absolute left-1 top-1/2 -translate-y-1/2 text-[9px] font-bold text-emerald-600">ل.ل</span>
          </div>
          <div class="sm:col-span-1 text-center flex justify-end sm:justify-center">
            <button type="button" onclick="removeStoreProductRow(this)" class="w-7 h-7 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 flex items-center justify-center transition active:scale-90 cursor-pointer" title="حذف هذا الصنف">
              <i class="fa-solid fa-trash-can text-xs"></i>
            </button>
          </div>
        </div>
      </div>

      <div class="pt-1.5 flex items-center justify-between">
        <button type="button" onclick="addStoreProductRow(${nextIdx})"
                class="inline-flex items-center gap-1.5 px-3 py-1 bg-indigo-100 hover:bg-indigo-200 text-indigo-900 rounded-lg text-xs font-black transition cursor-pointer active:scale-95">
          <i class="fa-solid fa-plus text-[10px]"></i>
          <span>+ إضافة صنف من هذا المتجر</span>
        </button>

        <div class="flex items-center gap-2">
          <span class="text-xs font-bold text-slate-700">مجموع بضاعة هذا المتجر:</span>
          <span class="store-subtotal-display font-black font-mono text-sm text-indigo-900 bg-indigo-100/80 px-2.5 py-0.5 rounded-lg border border-indigo-300" id="storeSubtotalDisplay_${nextIdx}">0 ل.ل</span>
          <input type="hidden" class="store-subtotal-val" id="storeSubtotalVal_${nextIdx}" value="0">
        </div>
      </div>
    </div>
  `;

  container.appendChild(card);
  // Reset selected option
  const newSelect = card.querySelector('.store-select');
  if (newSelect) newSelect.value = '';

  recalculateAllStoresAndFinancials();
  card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// 6. Remove an additional store block
function removeStoreBlock(btn) {
  const card = btn.closest('.store-order-card');
  if (card) {
    card.remove();
    recalculateAllStoresAndFinancials();
  }
}

// 7. Item currency converters
function onStoreItemUsdChange(input) {
  const rate = (typeof EXCHANGE_RATE !== 'undefined' && EXCHANGE_RATE > 0) ? EXCHANGE_RATE : 89500.0;
  const row = input.closest('.store-item-row');
  if (!row) return;
  const lbpInput = row.querySelector('.item-price-lbp');
  const usdVal = parseSmartNumber(input.value);
  if (lbpInput) {
    lbpInput.value = usdVal > 0 ? Math.round(usdVal * rate) : '';
  }
  recalculateAllStoresAndFinancials();
}

function onStoreItemLbpChange(input) {
  const rate = (typeof EXCHANGE_RATE !== 'undefined' && EXCHANGE_RATE > 0) ? EXCHANGE_RATE : 89500.0;
  const row = input.closest('.store-item-row');
  if (!row) return;
  const usdInput = row.querySelector('.item-price-usd');
  const lbpVal = parseSmartNumber(input.value);
  if (usdInput) {
    usdInput.value = lbpVal > 0 ? (lbpVal / rate).toFixed(2) : '';
  }
  recalculateAllStoresAndFinancials();
}

// 8. MASTER RECALCULATE: All stores, products, totals & structured data
function recalculateAllStoresAndFinancials() {
  const rate = (typeof EXCHANGE_RATE !== 'undefined' && EXCHANGE_RATE > 0) ? EXCHANGE_RATE : 89500.0;
  const cards = document.querySelectorAll('.store-order-card');

  let grandGoodsLbp = 0;
  const storesData = [];
  const allFormattedItems = [];
  const invoiceHtmlRows = [];
  let validItemsCount = 0;

  cards.forEach((card, cIdx) => {
    const storeIdx = card.getAttribute('data-store-index') || (cIdx + 1);
    const select = card.querySelector('.store-select');
    const storeId = select ? parseSmartNumber(select.value) : null;
    const storeName = (select && select.selectedIndex > 0) ? select.options[select.selectedIndex].text.split('—')[0].trim() : `متجر ${cIdx + 1}`;

    const rows = card.querySelectorAll('.store-item-row');
    let storeTotalLbp = 0;
    const storeItemsList = [];
    const storeItemStrings = [];

    rows.forEach((row, rIdx) => {
      const nameInput = row.querySelector('.item-name');
      const qtyInput = row.querySelector('.item-qty');
      const lbpInput = row.querySelector('.item-price-lbp');
      const usdInput = row.querySelector('.item-price-usd');

      const name = nameInput ? nameInput.value.trim() : '';
      const qty = Math.max(1, parseInt(qtyInput ? qtyInput.value : 1) || 1);
      const unitLbp = parseSmartNumber(lbpInput ? lbpInput.value : 0);
      const unitUsd = parseSmartNumber(usdInput ? usdInput.value : 0);

      const lineTotalLbp = qty * unitLbp;
      storeTotalLbp += lineTotalLbp;

      if (name || unitLbp > 0 || unitUsd > 0) {
        validItemsCount++;
        const itemTitle = name || (`صنف ${rIdx + 1}`);
        const priceLabel = unitLbp > 0 ? `${unitLbp.toLocaleString()} ل.ل` : (unitUsd > 0 ? `$${unitUsd}` : 'بدون سعر');

        storeItemsList.push({
          name: itemTitle,
          qty: qty,
          unit_price_lbp: unitLbp,
          unit_price_usd: unitUsd,
          line_total_lbp: lineTotalLbp
        });

        storeItemStrings.push(`${itemTitle} [${qty} × ${priceLabel}]`);

        // Add to digital receipt items list
        invoiceHtmlRows.push(`
          <div class="flex items-center justify-between text-[11px] py-1 border-b border-slate-800 last:border-0">
            <div class="flex items-center gap-1.5 min-w-0">
              <span class="w-4 h-4 rounded bg-purple-500/20 text-purple-300 flex items-center justify-center text-[10px] font-mono shrink-0">${qty}</span>
              <span class="font-bold text-white truncate max-w-[120px]">${itemTitle}</span>
              <span class="text-[9px] text-slate-400 font-normal">(${storeName})</span>
            </div>
            <div class="text-left font-mono font-bold text-emerald-300 shrink-0">
              ${lineTotalLbp > 0 ? lineTotalLbp.toLocaleString() + ' ل.ل' : (unitUsd > 0 ? '$' + (qty * unitUsd).toFixed(2) : '0')}
            </div>
          </div>
        `);
      }
    });

    // Update store display subtotal
    const subDisp = document.getElementById(`storeSubtotalDisplay_${storeIdx}`);
    const subVal = document.getElementById(`storeSubtotalVal_${storeIdx}`);
    if (subDisp) subDisp.textContent = `${storeTotalLbp.toLocaleString()} ل.ل`;
    if (subVal) subVal.value = storeTotalLbp;

    grandGoodsLbp += storeTotalLbp;

    if (storeId || storeTotalLbp > 0 || storeItemsList.length > 0) {
      storesData.push({
        merchant_id: storeId,
        store_name: storeName,
        goods_price: storeTotalLbp,
        items: storeItemsList,
        items_text: storeItemStrings.join(' + ')
      });

      if (storeItemStrings.length > 0) {
        allFormattedItems.push(`[${storeName}]: ${storeItemStrings.join(' + ')} (${storeTotalLbp.toLocaleString()} ل.ل)`);
      } else if (storeTotalLbp > 0) {
        allFormattedItems.push(`[${storeName}]: بضاعة بقيمة ${storeTotalLbp.toLocaleString()} ل.ل`);
      }
    }
  });

  // 9. Update hidden inputs and form totals
  const totalLbpInput = document.getElementById('totalOrderPriceLbp');
  const totalUsdInput = document.getElementById('totalOrderPriceUsd');
  if (totalLbpInput) totalLbpInput.value = grandGoodsLbp;
  if (totalUsdInput) totalUsdInput.value = grandGoodsLbp > 0 ? (grandGoodsLbp / rate).toFixed(2) : '';

  const hiddenDetail = document.getElementById('hiddenItemsDetail');
  if (hiddenDetail) {
    hiddenDetail.value = allFormattedItems.join(' | ');
  }

  const multiDataInput = document.getElementById('multiMerchantsDataInput');
  if (multiDataInput) {
    multiDataInput.value = JSON.stringify(storesData);
  }

  const firstPriceInput = document.getElementById('firstMerchantPriceInput');
  if (firstPriceInput && storesData.length > 0) {
    firstPriceInput.value = storesData[0].goods_price;
  }

  const secondSelect = document.getElementById('modalSecondMerchantSelect');
  const secondPriceInput = document.getElementById('secondMerchantPriceInput');
  if (storesData.length > 1) {
    if (secondSelect) secondSelect.value = storesData[1].merchant_id || '';
    if (secondPriceInput) secondPriceInput.value = storesData[1].goods_price || 0;
  } else {
    if (secondSelect) secondSelect.value = '';
    if (secondPriceInput) secondPriceInput.value = '0';
  }

  // Update Live Invoice List Container
  const invContainer = document.getElementById('invItemsDetailedList');
  if (invContainer) {
    if (invoiceHtmlRows.length > 0) {
      invContainer.innerHTML = invoiceHtmlRows.join('');
    } else {
      invContainer.innerHTML = '<div class="text-[11px] text-slate-500 text-center py-1 font-medium">لم يتم إدخال أصناف بعد</div>';
    }
  }

  const legacyInvSummary = document.getElementById('invItemsSummary');
  if (legacyInvSummary) {
    legacyInvSummary.textContent = allFormattedItems.length > 0 ? allFormattedItems.join(' | ') : 'عام (بدون تحديد)';
  }

  const countBadge = document.getElementById('invItemCountBadge');
  if (countBadge) countBadge.textContent = `${validItemsCount} أصناف (${storesData.length} متاجر)`;

  // Recalculate Master Financials (Adds single delivery fee)
  if (typeof recalculatePosFinancials === 'function') {
    recalculatePosFinancials();
  }
}

// Backward compatibility aliases
function addProductRow(name = '', qty = 1, priceUsd = '', priceLbp = '') {
  addStoreProductRow(1, name, qty, priceUsd, priceLbp);
}
function removeProductRow(btn) {
  removeStoreProductRow(btn);
}
function recalculateItemizedProducts() {
  recalculateAllStoresAndFinancials();
}

window.addProductRow = addProductRow;
window.removeProductRow = removeProductRow;
window.recalculateItemizedProducts = recalculateItemizedProducts;
window.addStoreProductRow = addStoreProductRow;
window.removeStoreProductRow = removeStoreProductRow;
window.addNewStoreBlock = addNewStoreBlock;
window.removeStoreBlock = removeStoreBlock;
window.filterStoreOptions = filterStoreOptions;
window.onMainMerchantSelectChange = onMainMerchantSelectChange;
window.onStoreItemUsdChange = onStoreItemUsdChange;
window.onStoreItemLbpChange = onStoreItemLbpChange;
window.recalculateAllStoresAndFinancials = recalculateAllStoresAndFinancials;



// ─── Direct Modal Controller ───────────────────────────────────────────────

function openOrderModal() {
  const el = document.getElementById('newOrderModal');
  if (!el) return;

  el.style.display = 'block';
  el.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
  el.scrollTop = 0;

  try { initNewOrderDefaults(); } catch(e) { console.error(e); }
  try { updateLiveInvoice(); } catch(e) {}

  try {
    initSmartMerchantPicker();
    const mSelect = document.getElementById('modalMerchantSelect');
    if (mSelect && mSelect.value) {
      const opt = mSelect.options[mSelect.selectedIndex];
      if (opt && opt.value) {
        selectSmartStore(opt.value, opt.getAttribute('data-store') || opt.text, opt.getAttribute('data-phone') || '', opt.getAttribute('data-def-fee') || '', opt.getAttribute('data-def-comm') || '');
      }
    } else {
      clearSmartSelectedStore();
    }
  } catch(e) {}

  setTimeout(() => {
    const phoneInput = document.getElementById('recipientPhoneInput');
    if (phoneInput) phoneInput.focus();
  }, 100);
}



function closeOrderModal() {

  const el = document.getElementById('newOrderModal');

  if (el) {

    el.style.display = 'none';

    document.body.style.overflow = '';

  }

}



function openWizardModal(id) {

  if (id === 'newOrderModal') {

    openOrderModal();

  } else {

    const el = document.getElementById(id);

    if (el) el.classList.remove('hidden');

  }

}



function closeWizardModal(id) {

  if (id === 'newOrderModal') {

    closeOrderModal();

  } else {

    const el = document.getElementById(id);

    if (el) el.classList.add('hidden');

  }

}



// Global Keyboard Shortcut: F2 to Save, Esc to Close

document.addEventListener('keydown', function(e) {

  const modal = document.getElementById('newOrderModal');

  if (!modal || modal.style.display === 'none' || modal.classList.contains('hidden')) return;

  if (e.key === 'Escape') {

    closeOrderModal();

  } else if (e.key === 'F2') {

    e.preventDefault();

    submitOrderWithAction('save');

  }

});



// Update Live Digital Invoice View

function updateLiveInvoice() {

  const custName = document.getElementById('recipientNameInput')?.value.trim() || '';

  const custPhone = document.getElementById('recipientPhoneInput')?.value.trim() || '';

  const custCity = document.getElementById('recipientCityInput')?.value.trim() || 'بيروت';

  const custAddress = document.getElementById('recipientAddressInput')?.value.trim() || '';



  const merchSelect = document.getElementById('modalMerchantSelect');

  const merchName = (merchSelect && merchSelect.selectedIndex > 0) ? merchSelect.options[merchSelect.selectedIndex].text : 'لم يتم الاختيار';



  const courSelect = document.getElementById('modalCourierSelect');

  const courName = (courSelect && courSelect.selectedIndex > 0) ? courSelect.options[courSelect.selectedIndex].text : '⏳ بالمكتب (بدون سائق)';

  const itemsVal = document.getElementById('hiddenItemsDetail')?.value.trim() || '';

  const invItems = document.getElementById('invItemsSummary');

  if (invItems) invItems.textContent = itemsVal ? itemsVal : 'عام (بدون تحديد)';



  // Update Parties Card

  const invCust = document.getElementById('invCustSummary');

  if (invCust) invCust.textContent = custName ? custName + ' (' + custCity + ')' : 'لم يُحدد بعد';



  const invPhone = document.getElementById('invPhoneSummary');

  if (invPhone) invPhone.textContent = custPhone ? custPhone : '--------';



  const invAddr = document.getElementById('invAddressSummary');

  if (invAddr) invAddr.textContent = custAddress ? custCity + '، ' + custAddress : custCity;



  const invMerch = document.getElementById('invMerchSummary');

  if (invMerch) invMerch.textContent = merchName;



  const invCour = document.getElementById('invCourSummary');

  if (invCour) invCour.textContent = courName;



  // Master Financials Calculation

  recalculatePosFinancials();

}



window.openOrderModal = openOrderModal;

window.closeOrderModal = closeOrderModal;

window.openWizardModal = openWizardModal;

window.closeWizardModal = closeWizardModal;

window.updateLiveInvoice = updateLiveInvoice;


    function openDirectWhatsAppChat() {
        const rawPhone = document.getElementById('recipientPhoneInput')?.value || '';
        const clean = rawPhone.replace(/[^0-9]/g, '');
        if (!clean) {
            alert('يرجى كتابة رقم هاتف الزبون أولاً');
            return;
        }
        let finalPhone = clean;
        if (!finalPhone.startsWith('961') && !finalPhone.startsWith('+961')) {
            finalPhone = '961' + finalPhone.replace(/^0+/, '');
        }
        finalPhone = finalPhone.replace('+', '');
        const msg = encodeURIComponent('مرحباً، بخصوص طلبك من Stargate Express، يمكنك تتبع شحنتك وموعد التوصيل عبر الرابط:\n' + window.location.origin + '/track/');
        window.open('https://wa.me/' + finalPhone + '?text=' + msg, '_blank');
    }

    function fetchCustomerDetails(phone) {
        if (typeof onPhoneInputLookup === 'function') {
            onPhoneInputLookup(phone);
        }
    }


// ─── STARGATE NATIVE AI JAVASCRIPT HELPERS ───

// 1. فحص درجة أمان وموثوقية الزبون (Customer Trust Score)
function checkCustomerRisk(phone) {
    if (!phone || phone.length < 6) {
        const badge = document.getElementById('customerRiskBadge');
        if (badge) badge.classList.add('hidden');
        return;
    }
    fetch('/api/ai/customer-risk?phone=' + encodeURIComponent(phone))
        .then(r => r.json())
        .then(res => {
            const badge = document.getElementById('customerRiskBadge');
            const text = document.getElementById('riskText');
            const advice = document.getElementById('riskAdvice');
            const icon = document.getElementById('riskIcon');
            if (!badge || !text) return;

            badge.className = 'mt-2 p-3 rounded-2xl border-2 flex items-center justify-between text-xs font-bold transition shadow-sm animate-in';

            if (res.color === 'green') {
                badge.classList.add('bg-emerald-50', 'border-emerald-400', 'text-emerald-900');
                if (icon) icon.className = 'fa-solid fa-shield-check text-emerald-600 text-lg';
            } else if (res.color === 'red') {
                badge.classList.add('bg-rose-50', 'border-rose-400', 'text-rose-900', 'animate-pulse');
                if (icon) icon.className = 'fa-solid fa-triangle-exclamation text-rose-600 text-lg';
            } else if (res.color === 'yellow') {
                badge.classList.add('bg-amber-50', 'border-amber-400', 'text-amber-900');
                if (icon) icon.className = 'fa-solid fa-shield-halved text-amber-600 text-lg';
            } else {
                badge.classList.add('bg-blue-50', 'border-blue-300', 'text-blue-900');
                if (icon) icon.className = 'fa-solid fa-user-check text-blue-600 text-lg';
            }

            text.innerText = res.badge + ' (' + res.score + '%)';
            if (advice) advice.innerText = res.advice || '';
            badge.classList.remove('hidden');
        })
        .catch(e => console.log('Risk check err:', e));
}

// 2. اقتراح وترشيح السائق الأنسب للمنطقة (Smart Dispatch Matrix)
function recommendCourier(area) {
    if (!area || area.trim().length < 2) {
        const note = document.getElementById('courierRecommendationNote');
        if (note) note.classList.add('hidden');
        return;
    }
    fetch('/api/ai/recommend-courier?area=' + encodeURIComponent(area))
        .then(r => r.json())
        .then(res => {
            const note = document.getElementById('courierRecommendationNote');
            if (res && res.id) {
                const select = document.querySelector('select[name="courier_id"]') || document.getElementById('modalCourierSelect');
                if (select && (!select.value || select.value === '')) {
                    select.value = res.id;
                }
                if (note) {
                    note.innerText = '💡 يُقترح: ' + res.name + ' (معه ' + res.active_orders + ' طرود)';
                    note.classList.remove('hidden');
                }
            } else if (note) {
                note.classList.add('hidden');
            }
        })
        .catch(e => console.log('Courier recommend err:', e));
}

