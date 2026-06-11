
var SPAN_KEY = 'tduo.timeline.buttonH';
var ZOOM_KEY = 'tduo.timeline.zoomPct';
var DEFAULT_SPAN = 24;
var DEFAULT_ZOOM = 100;
var MIN_ZOOM = 5;

function getButtonH() {
    var v = parseInt(sessionStorage.getItem(SPAN_KEY) || ('' + DEFAULT_SPAN), 10);
    return (isNaN(v) || v <= 0) ? DEFAULT_SPAN : v;
}
function getZoom() {
    var v = parseInt(sessionStorage.getItem(ZOOM_KEY) || ('' + DEFAULT_ZOOM), 10);
    if (isNaN(v) || v < MIN_ZOOM) v = MIN_ZOOM;
    if (v > 100) v = 100;
    return v;
}
function setButton(h) { sessionStorage.setItem(SPAN_KEY, '' + h); }
function setZoom(p)   { sessionStorage.setItem(ZOOM_KEY, '' + p); }

function fmtDuration(hours) {
    if (hours >= 1) {
        var h = Math.floor(hours);
        var m = Math.round((hours - h) * 60);
        if (m === 60) { h++; m = 0; }
        return m === 0 ? (h + ' h') : (h + ' h ' + (m < 10 ? '0' + m : m));
    }
    var mins = Math.round(hours * 60);
    return mins + ' min';
}

var html = '' +
'<div style="background:#fff;border-radius:8px;padding:8px 14px;box-shadow:0 2px 8px rgba(0,0,0,0.1);display:flex;flex-wrap:wrap;gap:12px;align-items:center;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;height:100%;box-sizing:border-box;align-content:center">' +
  '<div style="font-size:12px;font-weight:700;text-transform:uppercase;color:#333;letter-spacing:0.5px">Fenetre</div>' +
  '<div class="tl-btns" style="display:flex;gap:4px">' +
    ['4','8','12','24'].map(function(h){return '<button data-h="'+h+'" class="tl-btn" style="border:1px solid #ddd;background:#f5f5f5;padding:4px 12px;border-radius:4px;cursor:pointer;font-size:12px;font-weight:600">'+h+' h</button>';}).join('') +
  '</div>' +
  '<div style="flex:1;min-width:220px;display:flex;gap:8px;align-items:center">' +
    '<span style="font-size:11px;color:#888;min-width:24px">'+MIN_ZOOM+'%</span>' +
    '<input type="range" min="'+MIN_ZOOM+'" max="100" value="100" step="1" class="tl-slider" style="flex:1;accent-color:#5c6bc0" />' +
    '<span style="font-size:11px;color:#888;min-width:36px;text-align:right">100%</span>' +
  '</div>' +
  '<div class="tl-label" style="font-size:12px;color:#333;min-width:170px;font-variant-numeric:tabular-nums"></div>' +
'</div>';

if (window.__tduoTimeline && window.__tduoTimeline.refreshInterval) {
    clearInterval(window.__tduoTimeline.refreshInterval);
}
window.__tduoTimeline = {};

setTimeout(function() {
    var btns = document.querySelectorAll('.tl-btn');
    var slider = document.querySelector('.tl-slider');
    var label = document.querySelector('.tl-label');
    if (!btns || !slider || !label) return;

    function refresh() {
        var btn = getButtonH();
        var zoom = getZoom();
        var effH = btn * zoom / 100;
        btns.forEach(function(b) {
            var on = parseInt(b.dataset.h, 10) === btn;
            b.style.background  = on ? '#5c6bc0' : '#f5f5f5';
            b.style.color       = on ? '#fff'    : '#333';
            b.style.borderColor = on ? '#5c6bc0' : '#ddd';
        });
        if (parseInt(slider.value, 10) !== zoom) slider.value = zoom;
        label.innerHTML = 'Vue : <strong>' + fmtDuration(effH) + '</strong> / ' + btn + ' h';
    }

    btns.forEach(function(b) {
        b.addEventListener('click', function() {
            setButton(parseInt(b.dataset.h, 10));
            refresh();
        });
    });
    slider.addEventListener('input', function() {
        setZoom(parseInt(slider.value, 10));
        refresh();
    });

    refresh();
}, 100);

return html;
