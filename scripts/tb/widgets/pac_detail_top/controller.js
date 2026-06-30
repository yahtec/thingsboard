self.onInit=function(){};
self.onDataUpdated=function(){
  var $c=self.ctx.$container; var host=$c.find('.pd-top'); if(!host.length) return;
  function stateParams(){ try{ var raw=new URL(window.location.href).searchParams.get('state'); if(!raw) return {}; var arr=JSON.parse(atob(decodeURIComponent(raw))); for(var i=arr.length-1;i>=0;i--){ if(arr[i]&&arr[i].params) return arr[i].params; } }catch(e){} return {}; }
  function fv(v,dec){ if(v==null||v==='') return '—'; var f=parseFloat(v); if(isNaN(f)) return '—'; return f.toFixed(dec==null?1:dec); }
  function htime(v){ var f=parseFloat(v); return isNaN(f)?null:f/3600; }
  function kv(k,v,u,dec){ return '<div class="pd-kv"><span class="k">'+k+'</span><span class="v">'+fv(v,dec)+(u?'<span class="u">'+u+'</span>':'')+'</span></div>'; }
  function getHP(){ var raw=null; (self.ctx.data||[]).forEach(function(d){ if(d.dataKey&&/pac_v2/i.test(d.dataKey.name)&&d.data&&d.data.length) raw=d.data[d.data.length-1][1]; }); var p=null; if(raw){ try{ p=(typeof raw==='string')?JSON.parse(raw):raw; }catch(e){} } var n=parseInt(stateParams().hpIndex||stateParams().hp||1)||1; return {n:n, H:(p&&p.HPs&&p.HPs[n-1])||{}}; }

  var X=getHP(), n=X.n, H=X.H; var hp=H.HP||{}, inv=H.invert||{};
  function gauge(val,min,max,col){
    var cx=100,cy=100,R=80,nn=10;
    function pt(t,r){ var a=(135+t*270)*Math.PI/180; return [cx+r*Math.cos(a), cy+r*Math.sin(a)]; }
    var f=parseFloat(val); var t=isNaN(f)?0:(f-min)/(max-min); if(t<0)t=0; if(t>1)t=1;
    var g=''; for(var i=0;i<=nn;i++){ var tt=i/nn; var p1=pt(tt,R),p2=pt(tt,R-9),pl=pt(tt,R-23);
      g+='<line x1="'+p1[0].toFixed(1)+'" y1="'+p1[1].toFixed(1)+'" x2="'+p2[0].toFixed(1)+'" y2="'+p2[1].toFixed(1)+'" stroke="#c4c4c4" stroke-width="2"/>';g+='<text x="'+pl[0].toFixed(1)+'" y="'+(pl[1]+3).toFixed(1)+'" font-size="9" fill="#999" text-anchor="middle">'+Math.round(min+(max-min)*tt)+'</text>';
       }
    var tip=pt(t,R-6),tail=pt(t,-16); var c=col==='hp'?'#c62828':'#1976d2'; var bg=col==='hp'?'#ffebee':'#e3f2fd';
    return '<svg viewBox="0 0 200 200" class="gz"><circle cx="100" cy="100" r="90" fill="'+bg+'" stroke="#ececec"/>'+g+
      '<line x1="'+tail[0].toFixed(1)+'" y1="'+tail[1].toFixed(1)+'" x2="'+tip[0].toFixed(1)+'" y2="'+tip[1].toFixed(1)+'" stroke="'+c+'" stroke-width="2.5" stroke-linecap="round"/>'+
      '<circle cx="100" cy="100" r="7" fill="#333"/><text x="100" y="140" font-size="12" fill="#9e9e9e" text-anchor="middle">bar</text></svg>';
  }
  function gz(title,val,min,max,col,fl,fvl){ return '<div class="pd-card gz-card '+(col==='bp'?'bp':'')+'"><div class="gz-t">'+title+'</div>'+gauge(val,min,max,col)+'<div class="gz-lcd"><span class="v">'+fv(val,1)+'</span></div><div class="gz-foot">'+fl+'<b>'+fv(fvl,1)+' °C</b></div></div>'; }
  var dataPac='<div class="pd-card pd-data"><div class="pd-card-t">Données PAC '+n+'</div><div class="pd-rows">'+
    kv('Fréquence compresseur',inv.freq,' Hz',1)+kv('Puissance compresseur',inv.pwr,' W',0)+
    kv('Vitesse ventilateur',hp.rpm,' rpm',0)+kv('Position détendeur',hp.dpf,'',0)+
    kv('T° surchauffe',hp.tOH,' °C',1)+kv('Temps de fonctionnement',htime(hp.time),' h',0)+'</div></div>';
  host.html('<div class="pd-h">PAC Hybride N'+n+'</div><div class="pd-row">'+
    gz('Pression HP',hp.pHi,-5,35,'hp','T cond',hp.tCond)+gz('Pression BP',hp.pLo,-5,25,'bp','T evap',hp.tEvap)+dataPac+'</div>');
};
self.typeParameters=function(){return{maxDatasources:1,maxDataKeys:2,singleEntity:true};};
self.onResize=function(){};self.onDestroy=function(){};