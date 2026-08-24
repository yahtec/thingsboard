self.onInit=function(){};
self.onDataUpdated=function(){
  var $c=self.ctx.$container; var host=$c.find('.pd-boiler'); if(!host.length) return;
  function stateParams(){ try{ var raw=new URL(window.location.href).searchParams.get('state'); if(!raw) return {}; var arr=JSON.parse(atob(decodeURIComponent(raw))); for(var i=arr.length-1;i>=0;i--){ if(arr[i]&&arr[i].params) return arr[i].params; } }catch(e){} return {}; }
  function fv(v,dec){ if(v==null||v==='') return '—'; var f=parseFloat(v); if(isNaN(f)) return '—'; return f.toFixed(dec==null?1:dec); }
  function htime(v){ var f=parseFloat(v); return isNaN(f)?null:f/3600; }
  function kv(k,v,u,dec){ return '<div class="pd-kv"><span class="k">'+k+'</span><span class="v">'+fv(v,dec)+(u?'<span class="u">'+u+'</span>':'')+'</span></div>'; }
  function getHP(){ var raw=null; (self.ctx.data||[]).forEach(function(d){ if(d.dataKey&&/pac_v2/i.test(d.dataKey.name)&&d.data&&d.data.length) raw=d.data[d.data.length-1][1]; }); var p=null; if(raw){ try{ p=(typeof raw==='string')?JSON.parse(raw):raw; }catch(e){} } var n=parseInt(stateParams().hpIndex||stateParams().hp||1)||1; return {n:n, H:(p&&p.HPs&&p.HPs[n-1])||{}}; }

  var X=getHP(), n=X.n, H=X.H; var hp=H.HP||{}, boil=H.boil||{}, pump=H.pump||{};
  host.html('<div class="pd-card pd-data"><div class="pd-card-t">Données chaudière '+n+'</div><div class="pd-cols">'+
    '<div class="pd-col"><div class="ch">Chaudière</div>'+
      kv('T° entrée',hp.tOut,' °C',1)+kv('T° sortie',boil.tOut,' °C',1)+kv('T° fumée',boil.tSmoke,' °C',1)+
      kv('Débit eau',boil.qe,' L/h',0)+kv('Vitesse brûleur',boil.rpm,' rpm',0)+kv('Temps de fonctionnement',htime(boil.time),' h',0)+(boil.conG20!=null?kv('Concentration G20',boil.conG20*0.1,' %LFL',1)+'<div class="pd-kv"><span class="k">Capteur G20</span><span class="v">'+(boil.errG20==null?'—':(Number(boil.errG20)===0?'OK':String(boil.errG20)))+'</span></div>':'')+'</div>'+
    '<div class="pd-col"><div class="ch">Pompe</div>'+
      kv('Vitesse',pump.rpm,' rpm',0)+kv('DeltaP',pump.dP,' mCE',2)+kv('Puissance',pump.pwr,' W',0)+
      kv('Débit',pump.qe,' L/h',0)+kv('Durée ON',pump.time,' h',0)+'</div>'+
    '</div></div>');
};
self.typeParameters=function(){return{maxDatasources:1,maxDataKeys:2,singleEntity:true};};
self.onResize=function(){};self.onDestroy=function(){};
