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

  function stateParams(){ try{ var raw=new URL(window.location.href).searchParams.get('state'); if(!raw) return {}; var arr=JSON.parse(atob(decodeURIComponent(raw))); for(var i=arr.length-1;i>=0;i--){ if(arr[i]&&arr[i].params) return arr[i].params; } }catch(e){} return {}; }
  function getField(obj,f,n){ if(!obj) return null; if(f.indexOf('.')<0) return obj[f]; var hp=(obj.HPs&&obj.HPs[n-1])||{}; var ps=f.split('.'); var v=hp; for(var i=0;i<ps.length;i++){ v=v&&v[ps[i]]; } return v; }
  var GEO={mL:44,mR:12,mT:8,mB:22};
  self._draw=function(){
    var $c=self.ctx.$container; if(!$c.find('.pc-card').length) return;
    var s=self.ctx.settings||{}; $c.find('.pc-title').text(s.title||'');
    var series=s.series||[]; var n=parseInt(stateParams().hpIndex||stateParams().hp||1)||1;
    var hist=(window.__pacData&&window.__pacData.hist)||[];
    var datasets=series.map(function(se){ var pts=[]; for(var i=0;i<hist.length;i++){ var ts=hist[i][0], p=hist[i][1]; var v=getField(p,se.field,n); var f=parseFloat(v); if(v!=null&&!isNaN(f)&&isFinite(f)) pts.push([ts,se.scale!=null?f*se.scale:f]); } return {label:se.label,color:se.color,unit:se.unit,pts:pts}; });
    var tA=-Infinity,tB=Infinity; datasets.forEach(function(d){ d.pts.forEach(function(p){ if(p[0]>tA)tA=p[0]; if(p[0]<tB)tB=p[0]; }); });
    if(isFinite(tA)){ var span=tA-tB; var fr=(window.__pacData&&window.__pacData.frac)||1; var off=(window.__pacData&&window.__pacData.offset)||0; var vEnd=tA-off*span; var vStart=vEnd-fr*span; datasets.forEach(function(d){ d.pts=d.pts.filter(function(p){ return p[0]>=vStart&&p[0]<=vEnd; }); }); }
    var svgEl=$c.find('.pc-svg')[0], plot=$c.find('.pc-plot')[0]; if(!svgEl) return;
    var W=plot.clientWidth||600, Hh=plot.clientHeight||200; var mL=GEO.mL,mR=GEO.mR,mT=GEO.mT,mB=GEO.mB;
    var tmin=Infinity,tmax=-Infinity,vmin=Infinity,vmax=-Infinity;
    datasets.forEach(function(d){ d.pts.forEach(function(p){ if(p[0]<tmin)tmin=p[0]; if(p[0]>tmax)tmax=p[0]; if(p[1]<vmin)vmin=p[1]; if(p[1]>vmax)vmax=p[1]; }); });
    if(!isFinite(tmin)){ svgEl.innerHTML='<div class="pc-empty">Pas de données sur la période</div>'; $c.find('.pc-legend').html(''); plot._cd=null; return; }
    if(vmin===vmax){ vmin-=1; vmax+=1; } var pad=(vmax-vmin)*0.12; vmin-=pad; vmax+=pad;
    function X(t){ return mL+(t-tmin)/((tmax-tmin)||1)*(W-mL-mR); }
    function Y(v){ return mT+(1-(v-vmin)/((vmax-vmin)||1))*(Hh-mT-mB); }
    var U=(datasets.length&&datasets.every(function(x){return (x.unit||'')===(datasets[0].unit||'');}))?(datasets[0].unit||''):''; var svg='<svg width="'+W+'" height="'+Hh+'" viewBox="0 0 '+W+' '+Hh+'">';
    for(var i=0;i<=4;i++){ var vv=vmin+(vmax-vmin)*i/4; var y=Y(vv);
      svg+='<line x1="'+mL+'" y1="'+y.toFixed(1)+'" x2="'+(W-mR)+'" y2="'+y.toFixed(1)+'" stroke="#eee"/>'; if(U) svg+='<text x="'+(mL-3)+'" y="'+(y-2).toFixed(1)+'" font-size="9" fill="#999" text-anchor="end">'+(Math.round(vv*10)/10)+' '+U+'</text>';
       }
    for(var j=0;j<=4;j++){ var t=tmin+(tmax-tmin)*j/4; var x=X(t); var dt=new Date(t); var hh=('0'+dt.getHours()).slice(-2)+':'+('0'+dt.getMinutes()).slice(-2);
      svg+='<text x="'+x.toFixed(1)+'" y="'+(Hh-6)+'" font-size="10" fill="#999" text-anchor="middle">'+hh+'</text>'; }
    function __sm(pts,k){if(!pts||pts.length<2*k+1||k<1)return pts||[];var o=[];for(var i=0;i<pts.length;i++){var a=i-k<0?0:i-k,b=i+k>pts.length-1?pts.length-1:i+k,s=0,n=0;for(var j=a;j<=b;j++){s+=pts[j][1];n++;}o.push([pts[i][0],s/n]);}return o;} datasets.forEach(function(d){ if(!d.pts.length) return; var pa=__sm(d.pts,3).map(function(p){ return X(p[0]).toFixed(1)+','+Y(p[1]).toFixed(1); }).join(' '); svg+='<polyline points="'+pa+'" fill="none" stroke="'+d.color+'" stroke-width="2" stroke-linejoin="round"/>'; });
    svg+='</svg>'; svgEl.innerHTML=svg;
    plot._cd={datasets:datasets,tmin:tmin,tmax:tmax,mL:mL,mR:mR,W:W};
    $c.find('.pc-legend').html(datasets.map(function(d){ return '<span class="lg"><i style="background:'+d.color+'"></i>'+d.label+(d.unit?' ('+d.unit+')':'')+'</span>'; }).join(''));
    if(!plot._bound){ plot._bound=true;
      var tip=$c.find('.pc-tip')[0], cur=$c.find('.pc-cursor')[0];
      plot.addEventListener('mousemove',function(ev){ var cd=plot._cd; if(!cd){return;} var rect=plot.getBoundingClientRect(); var x=ev.clientX-rect.left;
        if(x<cd.mL||x>cd.W-cd.mR){ tip.style.display='none'; cur.style.display='none'; return; }
        var tt=cd.tmin+(x-cd.mL)/((cd.W-cd.mL-cd.mR)||1)*(cd.tmax-cd.tmin);
        var rows=[]; var ats=null; cd.datasets.forEach(function(d){ if(!d.pts.length) return; var best=d.pts[0],bd=Math.abs(d.pts[0][0]-tt); for(var i=1;i<d.pts.length;i++){var q=Math.abs(d.pts[i][0]-tt); if(q<bd){bd=q;best=d.pts[i];}} ats=best[0]; rows.push('<div class="pc-tip-r"><i style="background:'+d.color+'"></i>'+d.label+' : <b>'+(Math.round(best[1]*10)/10)+(d.unit?' '+d.unit:'')+'</b></div>'); });
        if(!rows.length){ tip.style.display='none'; cur.style.display='none'; return; }
        var dt=new Date(ats); var ds=('0'+dt.getDate()).slice(-2)+'/'+('0'+(dt.getMonth()+1)).slice(-2)+' '+('0'+dt.getHours()).slice(-2)+':'+('0'+dt.getMinutes()).slice(-2);
        tip.innerHTML='<div class="pc-tip-t">'+ds+'</div>'+rows.join(''); tip.style.display='block';
        var tw=tip.offsetWidth||140; var tx=x+14; if(tx+tw>cd.W) tx=x-tw-14; if(tx<0) tx=4; tip.style.left=tx+'px'; tip.style.top='6px';
        cur.style.display='block'; cur.style.left=x+'px'; });
      plot.addEventListener('mouseleave',function(){ tip.style.display='none'; cur.style.display='none'; });
    }
  };
  PD().register(self._draw);
};
self.onDataUpdated=function(){ var ds=self.ctx.datasources&&self.ctx.datasources[0]; if(ds&&ds.entityId&&window.__pacData) window.__pacData.ensure(ds.entityType||'DEVICE',ds.entityId); if(self._draw) self._draw(); };
self.onResize=function(){ if(self._draw) self._draw(); };
self.onDestroy=function(){ if(window.__pacData&&self._draw) window.__pacData.unregister(self._draw); };
self.typeParameters=function(){return{maxDatasources:1,maxDataKeys:2,singleEntity:true};};