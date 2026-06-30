self.onInit=function(){
  function PD(){ if(window.__pacData) return window.__pacData;
    var d={hours:12,frac:1,offset:0,hist:[],eid:null,et:'DEVICE',ls:[],fetching:false,
      register:function(fn){ if(this.ls.indexOf(fn)<0) this.ls.push(fn); },
      unregister:function(fn){ var i=this.ls.indexOf(fn); if(i>=0) this.ls.splice(i,1); },
      notify:function(){ this.ls.forEach(function(fn){ try{fn();}catch(e){} }); },
      ensure:function(et,eid){ if(!eid) return; if(eid!==this.eid){ this.eid=eid; this.et=et||'DEVICE'; this.load(); } else if(this.hist.length){ this.notify(); } else if(!this.fetching){ this.load(); } },
      setHours:function(h){ this.hours=h; this.frac=1; this.offset=0; this.load(); },
      setFrac:function(f){ this.frac=f; this.notify(); },
      setOffset:function(o){ this.offset=o; this.notify(); },
      load:function(){ var s=this; if(!s.eid) return; s.fetching=true; var end=Date.now(), start=end-s.hours*3600000;
        fetch('/api/plugins/telemetry/'+s.et+'/'+s.eid+'/values/timeseries?keys=pac_v2&startTs='+start+'&endTs='+end+'&limit=8000&orderBy=ASC',{headers:{'X-Authorization':'Bearer '+localStorage.getItem('jwt_token')}})
          .then(function(r){return r.json();})
          .then(function(dd){ var arr=(dd&&dd.pac_v2)||[]; s.hist=arr.map(function(x){ var v=null; try{v=JSON.parse(x.value);}catch(e){} return [Number(x.ts),v]; }).filter(function(x){return x[1];}); s.fetching=false; s.notify(); })
          .catch(function(){ s.fetching=false; s.notify(); });
      }};
    window.__pacData=d; return d; }

  var $c=self.ctx.$container; var pd=PD();
  function vue(){ var el=$c.find('#pw-vue'); if(el.length) el.text('Vue : '+Math.round(pd.hours*pd.frac)+' h / '+pd.hours+' h'); }
  var btns=$c.find('.pw-btn');
  btns.off('click').on('click',function(){ var h=parseInt(this.getAttribute('data-h'))||12; pd.setHours(h); btns.removeClass('active'); this.className=this.className.replace(/\s*active/g,'')+' active'; var r=$c.find('#pw-rng')[0]; if(r) r.value=100; $c.find('#pw-retro').removeClass('active'); vue(); });
  $c.find('#pw-rng').off('input').on('input',function(){ pd.setFrac((parseInt(this.value)||100)/100); vue(); });
  $c.find('#pw-retro').off('click').on('click',function(){ var no=pd.offset+pd.frac; if(no+pd.frac>1.0001) no=0; pd.setOffset(no); if(no>0) this.className=this.className.replace(/\s*active/g,'')+' active'; else this.className=this.className.replace(/\s*active/g,''); vue(); });
  vue();
};
self.onResize=function(){};self.onDestroy=function(){};