"""Ajoute la bascule PAC|MCHRT au widget-menu inline (state 'menu'). Additif :
élargit la requête aux 2 types + appende un script d'augmentation et du CSS.
Transform pur, deep-copie, idempotent (marqueur __MCHRT_MENU_V1__)."""
import copy

MARKER = "__MCHRT_MENU_V1__"
MENU_FQN = "system.cards.html_value_card"
QUERY_OLD = "deviceTypes:['pac hybride']"      # ajuster si l'espacement live diffère (cf. Step 0)
QUERY_NEW = "deviceTypes:['pac hybride','mchrt']"

AUG_SCRIPT = """<script>/*__MCHRT_MENU_V1__*/(function(){
  var TYPES={};
  function auth(){return localStorage.getItem('jwt_token');}
  function loadTypes(cb){
    var body={entityFilter:{type:'deviceType',deviceTypes:['pac hybride','mchrt']},
      pageLink:{pageSize:1000,page:0,sortOrder:{key:{type:'ENTITY_FIELD',key:'name'},direction:'ASC'}},
      entityFields:[{type:'ENTITY_FIELD',key:'name'},{type:'ENTITY_FIELD',key:'type'}]};
    fetch('/api/entitiesQuery/find',{method:'POST',headers:{'Content-Type':'application/json',
      'X-Authorization':'Bearer '+auth()},body:JSON.stringify(body)})
      .then(function(r){return r.json();}).then(function(res){
        (res.data||[]).forEach(function(e){var id=e.entityId&&e.entityId.id;
          var ef=e.latest&&e.latest.ENTITY_FIELD;var ty=ef&&ef.type&&ef.type.value||'';
          if(id)TYPES[id]=ty;});
        cb&&cb();}).catch(function(){cb&&cb();});
  }
  var ACTIVE='pac hybride';
  function present(t){for(var k in TYPES){if(TYPES[k]===t)return true;}return false;}
  function idFromCard(c){var oc=c.getAttribute('onclick')||'';
    var m=oc.match(/tb_menu_naviguer\\('([^']+)'/);return m?m[1]:null;}
  function applyFilter(){
    var both=present('pac hybride')&&present('mchrt');
    var bar=document.getElementById('mchrt-toggle');
    if(bar)bar.style.display=both?'flex':'none';
    if(!both)ACTIVE=(present('mchrt')&&!present('pac hybride'))?'mchrt':'pac hybride';
    var cards=document.querySelectorAll('#menu-container .ch-card');
    for(var i=0;i<cards.length;i++){var id=idFromCard(cards[i]);var ty=id?TYPES[id]:'';
      cards[i].style.display=(both&&ty&&ty!==ACTIVE)?'none':'';}
  }
  function buildToggle(){
    if(document.getElementById('mchrt-toggle'))return;
    var grid=document.getElementById('menu-container');if(!grid||!grid.parentNode)return;
    var bar=document.createElement('div');bar.id='mchrt-toggle';bar.className='mchrt-toggle';
    bar.innerHTML='<button data-t="pac hybride" class="on">PAC Hybride</button>'+
      '<button data-t="mchrt">MCHRT</button>';
    grid.parentNode.insertBefore(bar,grid);
    bar.addEventListener('click',function(e){var b=e.target.closest('button');if(!b)return;
      ACTIVE=b.getAttribute('data-t');var bs=bar.querySelectorAll('button');
      for(var i=0;i<bs.length;i++)bs[i].classList.toggle('on',bs[i]===b);applyFilter();});
  }
  function wrapNav(){var orig=window.tb_menu_naviguer;if(typeof orig!=='function')return;
    if(orig.__mchrtWrapped)return;
    var w=function(id){var ty=TYPES[id];
      if(ty==='mchrt'){var b=btoa(JSON.stringify([{id:'mchrt_apercu',
        params:{entityId:{id:id,entityType:'DEVICE'}}}]));
        window.history.pushState({},'',window.location.pathname+'?state='+encodeURIComponent(b));
        var ev=document.createEvent('Event');ev.initEvent('popstate',true,true);
        window.dispatchEvent(ev);return;}
      return orig.apply(this,arguments);};
    w.__mchrtWrapped=true;window.tb_menu_naviguer=w;}
  function init(){loadTypes(function(){wrapNav();buildToggle();applyFilter();
    var grid=document.getElementById('menu-container');
    if(grid&&window.MutationObserver)new MutationObserver(function(){buildToggle();
      wrapNav();applyFilter();}).observe(grid,{childList:true});
    setInterval(function(){loadTypes(applyFilter);},60000);});}
  if(document.readyState!=='loading')init();
  else document.addEventListener('DOMContentLoaded',init);
})();</script>"""

TOGGLE_CSS = """
/*__MCHRT_MENU_V1__*/
.mchrt-toggle{display:none;gap:8px;padding:8px 4px 4px;align-items:center;}
.mchrt-toggle button{border:1px solid #cfcfcf;background:#fff;border-radius:18px;
  padding:6px 16px;font:inherit;cursor:pointer;color:#555;}
.mchrt-toggle button.on{background:#1f6feb;border-color:#1f6feb;color:#fff;}
"""

def find_menu_widget(cfg):
    menu = cfg.get("states", {}).get("menu", {})
    wids = menu.get("layouts", {}).get("main", {}).get("widgets", {})
    for wid in wids:
        w = cfg["widgets"].get(wid, {})
        if w.get("typeFullFqn") == MENU_FQN:
            return w
    for w in cfg["widgets"].values():          # fallback: seul html_value_card
        if w.get("typeFullFqn") == MENU_FQN:
            return w
    raise SystemExit("widget menu html_value_card introuvable dans l'état 'menu'")

def _broaden_alias(cfg):
    for a in cfg.get("entityAliases", {}).values():
        f = a.get("filter", {})
        if a.get("alias") == "Toutes les chaufferies" and f.get("type") == "deviceType":
            if "mchrt" not in f.get("deviceTypes", []):
                f["deviceTypes"] = ["pac hybride", "mchrt"]

def apply(cfg):
    cfg = copy.deepcopy(cfg)
    w = find_menu_widget(cfg)
    s = w["config"]["settings"]
    html = s.get("cardHtml", "")
    if MARKER not in html:
        if QUERY_OLD in html:
            html = html.replace(QUERY_OLD, QUERY_NEW)
        else:
            raise SystemExit(f"ancre requête introuvable ({QUERY_OLD!r}); ajuster QUERY_OLD (Step 0)")
        html = html + AUG_SCRIPT
        s["cardHtml"] = html
    css = s.get("cardCss", "")
    if MARKER not in css:
        s["cardCss"] = css + TOGGLE_CSS
    _broaden_alias(cfg)
    return cfg
